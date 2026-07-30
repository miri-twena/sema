"""
SEMA agent: semantic-layer loader.

Loads every metric definition from sql/semantic/*.yaml -- the agent's
"grounding". Think of these YAML files as the governed measure definitions
in a BI tool: one trusted place that says what "Revenue", "Churn Risk",
etc. mean and how to compute them, so the agent never invents its own
(possibly wrong) definition.

This module is pure file-loading + validation. It has NO dependency on the
Claude API key -- it works whether or not the key is configured.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from sema_core.client_registry import PROJECT_ROOT, active_client_id, get_client_by_id

# Every metric file must define these keys, or we consider it malformed.
REQUIRED_KEYS = {"name", "label", "description", "grain", "sql", "dimensions", "examples"}

# Data-access scopes (sema_core.data_scope) gate metrics by these domains --
# every metric must declare exactly one. Keep in sync with
# sema_core.data_scope.DOMAINS (that module is the enforcement side; this is
# the loader-side validation that the YAML never drifts from it).
VALID_DOMAINS = {"sales", "customers", "marketing", "finance"}
# The only sensitivity tag defined so far -- profitability data (gross
# margin, COGS, and similar) that's blocked even inside an otherwise-allowed
# domain under the no_financials/sales_only scopes.
VALID_SENSITIVE_TAGS = {"financials"}

# Sibling YAML files that hold the OTHER semantic-layer sections (business
# rules, calendar/knowledge, glossary) -- not metric files, so they're skipped
# by load_semantic_layer's glob and read by their own loaders below. Each is a
# bare top-level YAML list; a client with none of these files (every client
# before this feature shipped) just gets an empty list back, unchanged
# behavior for load_semantic_layer itself.
RESERVED_FILENAMES = {"rules.yaml", "knowledge.yaml", "glossary.yaml"}


def semantic_dir(client_id: str | None = None) -> Path:
    """Folder of *.yaml metric files for the active (or given) client.

    Resolved at call time (not import time) so switching clients in the UI
    immediately changes which semantic layer the agent is grounded in.
    """
    client = get_client_by_id(client_id or active_client_id())
    return PROJECT_ROOT / client["semantic_dir"]


class SemanticLayerError(Exception):
    """Raised when a metric file is missing or malformed."""


def _load_one(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise SemanticLayerError(f"{path.name}: top level must be a mapping")

    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise SemanticLayerError(f"{path.name}: missing required keys {sorted(missing)}")

    domain = data.get("domain")
    if domain not in VALID_DOMAINS:
        raise SemanticLayerError(
            f"{path.name}: missing or unknown domain {domain!r} (must be one of {sorted(VALID_DOMAINS)})"
        )
    sensitive = data.get("sensitive")
    if sensitive is not None and sensitive not in VALID_SENSITIVE_TAGS:
        raise SemanticLayerError(
            f"{path.name}: unknown sensitive tag {sensitive!r} (must be one of {sorted(VALID_SENSITIVE_TAGS)})"
        )

    return data


def load_semantic_layer(client_id: str | None = None) -> list[dict]:
    """Return every metric definition for the active (or given) client.

    Raises SemanticLayerError if the folder is empty or any file is invalid.
    """
    folder = semantic_dir(client_id)
    if not folder.exists():
        raise SemanticLayerError(f"semantic layer folder not found: {folder}")

    files = sorted(p for p in folder.glob("*.yaml") if p.name not in RESERVED_FILENAMES)
    if not files:
        raise SemanticLayerError(f"no .yaml metric files found in {folder}")

    metrics = [_load_one(path) for path in files]

    # Guard against duplicate metric names (would confuse the agent).
    names = [m["name"] for m in metrics]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise SemanticLayerError(f"duplicate metric names: {sorted(duplicates)}")

    return metrics


def get_metric(name: str, client_id: str | None = None) -> dict | None:
    """Look up a single metric by its name, or None if not found."""
    for metric in load_semantic_layer(client_id):
        if metric["name"] == name:
            return metric
    return None


def _load_reserved_list(filename: str, client_id: str | None) -> list[dict]:
    """Load one of the RESERVED_FILENAMES as a bare top-level YAML list.

    Missing file -> [] (every client before this feature shipped has none of
    these files; they must keep working unchanged). A non-list top level is
    treated as malformed, same strictness as metric files.
    """
    path = semantic_dir(client_id) / filename
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return []
    if not isinstance(data, list):
        raise SemanticLayerError(f"{filename}: top level must be a list")
    return data


def load_rules(client_id: str | None = None) -> list[dict]:
    """Business rules (rules.yaml): name, definition, optional logic (SQL),
    applies_to (metric names), status. [] if the client has no rules.yaml."""
    return _load_reserved_list("rules.yaml", client_id)


def load_knowledge(client_id: str | None = None) -> list[dict]:
    """Calendar & knowledge items (knowledge.yaml): type
    (recurring_event/incident/note), name, date_range or recurrence,
    description, affects. [] if the client has no knowledge.yaml."""
    return _load_reserved_list("knowledge.yaml", client_id)


def load_glossary(client_id: str | None = None) -> list[dict]:
    """Glossary terms (glossary.yaml): term -> canonical metric/entity mapping
    (Hebrew or English terms). [] if the client has no glossary.yaml."""
    return _load_reserved_list("glossary.yaml", client_id)
