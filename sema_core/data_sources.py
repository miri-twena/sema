"""
SEMA: data source registry (client panel spec §4, view-only slice).

Architectural principle (spec §4.1): the semantic layer and agent always
query ONE read-only analytical Postgres per client. Nothing else is queried
live -- an external system (Priority, Salesforce) would sync INTO that
Postgres via a scheduled ETL job, and the entities it lands get tagged with
that source. Creating/editing connections is platform-level only; this
module only ever reads config + runs a health check, never writes one.

"Entities" reuses the SAME real-table concept the trust panel already computes
(sema_core.agent.response.tables_in_sql) and the admin Entities tab already
shows (schema introspection) -- not a second, hand-maintained list that could
drift out of sync with what the agent actually queries.

`source_for_entity` currently returns each client's single configured source
for every entity (both demo tenants have exactly one connector). The plural
list-of-sources shape exists so a client with >1 connector is a config
change, not a rewrite -- see the `data_sources` block in config/clients.yaml.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from sema_core import db
from sema_core.agent.semantic import load_semantic_layer
from sema_core.client_registry import get_client_by_id

# Connector catalog -- schema-ready for connectors not implemented yet (spec
# §4.2: Priority ERP, Salesforce). Only "postgres" has a live health check;
# an unimplemented type always reports status "paused" (never fabricates a
# reading it can't take).
SOURCE_TYPES: dict[str, dict] = {
    "postgres": {"display_name": "PostgreSQL", "implemented": True},
    "priority": {"display_name": "Priority ERP", "implemented": False},
    "salesforce": {"display_name": "Salesforce", "implemented": False},
}

_DEFAULT_SOURCE = {"id": "postgres_main", "type": "postgres", "display_name": "PostgreSQL"}


def client_sources(client_id: str) -> list[dict]:
    """This client's configured data sources (config/clients.yaml). A client
    with no `data_sources` block gets one implicit postgres source -- every
    client before this feature shipped keeps working unchanged."""
    configured = get_client_by_id(client_id).get("data_sources")
    return configured if configured else [dict(_DEFAULT_SOURCE)]


def source_for_entity(entity: str, client_id: str) -> str:
    """Which source id an entity's data comes from. Every client today has
    exactly one connector, so every entity resolves to it -- kept as a
    function (not a plain dict lookup) so a client with more than one source
    can later override specific entities without callers changing."""
    return client_sources(client_id)[0]["id"]


def source_type_for_entity(entity: str, client_id: str) -> str:
    """The connector TYPE (postgres/priority/salesforce) an entity's data
    comes from -- spec §4.4's literal `source` field on a semantic entity.
    Distinct from source_for_entity's instance id (e.g. "postgres_main"),
    which the Data sources screen and stale_source_caveat key off of."""
    source_id = source_for_entity(entity, client_id)
    source = next((s for s in client_sources(client_id) if s["id"] == source_id), None)
    return source["type"] if source else "postgres"


def _metric_tables(metric: dict) -> set[str]:
    """Every real table a metric can touch: its main query PLUS any table a
    dimension's `requires_join` declares (e.g. policies_in_force's `region`
    dimension joins policyholders even though the metric's own base query
    never does) PLUS each alert's own query. Lazy-imports tables_in_sql to
    avoid a module import cycle (response.py will import this module for the
    evidence-panel caveat, see stale_source_caveat below)."""
    from sema_core.agent.response import tables_in_sql

    tables = set(tables_in_sql(metric.get("sql", "")))
    for dim in metric.get("dimensions") or []:
        tables.update(dim.get("requires_join") or [])
    for alert in metric.get("alerts") or []:
        tables.update(tables_in_sql(alert.get("sql", "")))
    return tables


def dependent_metrics_by_entity(client_id: str) -> dict[str, list[str]]:
    """{table_name: [metric names that depend on it]} -- powers the "revenue,
    aov ← PostgreSQL" trust-chain expander (spec §4.3)."""
    out: dict[str, list[str]] = {}
    for metric in load_semantic_layer(client_id):
        for table in _metric_tables(metric):
            out.setdefault(table, []).append(metric["name"])
    for table, names in out.items():
        names.sort()
    return out


def entities_for_client(client_id: str) -> list[str]:
    """Every real table the semantic layer depends on, sorted -- the entity
    list the Data sources screen and evidence caveats reason about."""
    return sorted(dependent_metrics_by_entity(client_id))


def _data_age_days(table: str | None, field: str | None, client_id: str) -> float | None:
    """Days since the primary entity's newest row -- None when unconfigured
    or the query fails (offline DB, missing table), never a fabricated
    number."""
    if not table or not field:
        return None
    try:
        result = db.run_query(f"SELECT MAX({field}) AS max_date FROM {table}", client_id=client_id)
    except Exception:
        return None
    if result.empty or result["max_date"].iloc[0] is None:
        return None
    max_date = result["max_date"].iloc[0]
    if hasattr(max_date, "to_pydatetime"):
        max_date = max_date.to_pydatetime()
    if getattr(max_date, "tzinfo", None) is None:
        max_date = datetime(max_date.year, max_date.month, max_date.day, tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - max_date).total_seconds() / 86400


def source_health(source: dict, client_id: str) -> dict:
    """One source's live status card (spec §4.3): reachability, "last sync" +
    duration, and data age. `source` is one entry from client_sources().

    Only "postgres" has a live check today -- direct, real-time connection,
    so "last sync" is simply "as of this check" and "duration" is the actual
    round-trip time of the check itself (never a fabricated number). A
    connector type with no implementation reports "paused": it exists in the
    catalog (schema-ready) but nothing is actually wired up to check.
    """
    if source["type"] != "postgres":
        return {
            **source,
            "status": "paused",
            "last_sync_at": None,
            "sync_duration_ms": None,
            "data_age_days": None,
        }

    started = time.monotonic()
    reachable = db.check_connection(client_id=client_id)
    age = _data_age_days(source.get("primary_table"), source.get("primary_date_field"), client_id) if reachable else None
    duration_ms = int((time.monotonic() - started) * 1000)

    return {
        **source,
        "status": "healthy" if reachable else "error",
        "last_sync_at": datetime.now(timezone.utc).isoformat() if reachable else None,
        "sync_duration_ms": duration_ms if reachable else None,
        "data_age_days": age,
    }


def get_data_sources(client_id: str) -> list[dict]:
    """Full status-card payload for every configured source -- GET
    /api/admin/data-sources. Each source's `entities` lists only the
    entities THAT source owns (source_for_entity), with their dependent
    metrics attached for the trust-chain expander."""
    dep = dependent_metrics_by_entity(client_id)
    cards = []
    for source in client_sources(client_id):
        health = source_health(source, client_id)
        owned = [e for e in dep if source_for_entity(e, client_id) == source["id"]]
        cards.append(
            {
                **health,
                "entities": [{"name": e, "dependent_metrics": dep[e]} for e in sorted(owned)],
            }
        )
    return cards


def stale_source_caveat(entities: set[str] | list[str], client_id: str) -> list[str]:
    """Deterministic caveat(s) for the agent evidence panel (spec §4.4): when
    a question's queried entities depend on a source whose sync has FAILED,
    append a caveat the model can't reason away by omission -- same trust
    rationale as response._knowledge_caveats for incident overlap. Silently
    empty when every touched source is healthy (the common case): data AGE
    alone is informational, not itself a failure worth flagging.
    """
    if not entities:
        return []
    touched_source_ids = {source_for_entity(e, client_id) for e in entities}
    caveats: list[str] = []
    for source in client_sources(client_id):
        if source["id"] not in touched_source_ids:
            continue
        health = source_health(source, client_id)
        if health["status"] != "error":
            continue
        display = SOURCE_TYPES.get(source["type"], {}).get("display_name", source["type"])
        age = health["data_age_days"]
        if age is None:
            caveats.append(f"{display} is currently unreachable — this answer may be based on stale data.")
        else:
            days = int(age)
            caveats.append(f"{display} data was last updated {days} day{'s' if days != 1 else ''} ago.")
    return caveats
