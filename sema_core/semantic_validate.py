"""
SEMA: semantic-model draft validation ("dry run").

Backs `POST /api/admin/semantic/validate`. For a metric or business rule with
SQL, this is the SAME safety chain AgentTools.run_sql (sema_core/agent/tools.py)
uses -- validate_and_prepare (safety.py) then run_sql_readonly (db.py) -- so
admin-authored SQL gets exactly the guarantees agent-authored SQL gets: a real
parser rejects anything but a single SELECT, system catalogs are blocked, and
results are row-capped. Never raises on a bad query; a validation failure is a
normal outcome ({"ok": False, "error": ...}), same philosophy as run_sql.

Non-SQL sections (knowledge, glossary, a rule with no `logic`) get a schema
check only -- there's nothing to execute.
"""

from __future__ import annotations

import calendar
import re
import time
from datetime import date, datetime

import sqlglot
from sqlglot import expressions as exp

from sema_core import client_registry
from sema_core.agent.safety import SQLSafetyError, validate_and_prepare
from sema_core.agent.semantic import get_metric
from sema_core.db import run_sql_readonly
from sema_core.overview import _max_order_date

# Matches DATE_TRUNC('month', <col>) in a metric's "month" dimension SQL, the
# convention every existing metric file uses (see sql/semantic/*.yaml).
_MONTH_DIM_RE = re.compile(r"date_trunc\(\s*'[^']*'\s*,\s*([\w.]+)\s*\)", re.IGNORECASE)

_KNOWLEDGE_TYPES = {"recurring_event", "incident", "note"}


def _last_complete_month(max_date: date) -> tuple[date, date]:
    """The latest calendar month fully covered by the data's own max order
    date (not the wall clock) -- same "dataset's own now" convention as
    overview.py. If max_date isn't the last day of its month, that month is
    still in progress, so the prior month is the last COMPLETE one."""
    year, month = max_date.year, max_date.month
    last_day = calendar.monthrange(year, month)[1]
    if max_date.day < last_day:
        # This month is still in progress -- the prior month is the last
        # complete one.
        if month == 1:
            year, month = year - 1, 12
        else:
            month -= 1
        last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _date_column(metric: dict | None) -> str | None:
    """Best-effort: the column a metric's "month" dimension truncates, e.g.
    "order_date" from DATE_TRUNC('month', order_date). None if the metric has
    no such dimension -- the caller then validates unscoped."""
    if not metric:
        return None
    for dim in metric.get("dimensions", []):
        if dim.get("name") == "month":
            m = _MONTH_DIM_RE.search(dim.get("sql", ""))
            if m:
                return m.group(1)
    return None


def _scope_to_last_complete_month(safe_sql: str, date_column: str | None) -> tuple[str, str | None]:
    """Best-effort date-scoping: inject `AND <date_column> BETWEEN start AND
    end` for the dataset's last complete month.

    SAFETY ORDERING: `safe_sql` must already be the OUTPUT of
    validate_and_prepare (a confirmed single, read-only SELECT/UNION) -- never
    raw admin input. sqlglot.parse_one() silently keeps only the first
    statement of its input, which would otherwise let a multi-statement
    injection attempt (e.g. "SELECT 1; DROP TABLE orders") slip past the
    safety layer's "exactly one statement" check by truncating it to just the
    harmless first half BEFORE that check ever ran. Validating first, then
    scoping the already-proven-safe SQL, closes that gap.

    Returns (sql, period_label); period_label is None when scoping wasn't
    possible (no date dimension, or a shape sqlglot can't add a WHERE to) --
    the caller still runs the query, just unscoped.
    """
    if not date_column:
        return safe_sql, None
    max_date = _max_order_date()
    if max_date is None:
        return safe_sql, None
    start, end = _last_complete_month(max_date)

    try:
        statement = sqlglot.parse_one(safe_sql, read="postgres")
    except Exception:
        return safe_sql, None
    if not isinstance(statement, exp.Select):
        return safe_sql, None  # CTE/UNION shapes: skip scoping rather than guess

    scoped = statement.where(f"{date_column} BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'")
    return scoped.sql(dialect="postgres"), f"{start:%b %Y}"


def _run_sql_dry_run(client_id: str, sql: str, date_column: str | None) -> dict:
    # Validate the RAW input first -- rejects multi-statement / non-SELECT /
    # catalog-probing SQL before any scoping touches it (see the safety-
    # ordering note on _scope_to_last_complete_month).
    try:
        safe_sql = validate_and_prepare(sql)
    except SQLSafetyError as e:
        return {"ok": False, "error": str(e)}

    # Scope the now-proven-safe SQL, then re-validate the scoped result too
    # (cheap, and it re-applies the row cap to the rewritten statement).
    scoped_sql, period_label = _scope_to_last_complete_month(safe_sql, date_column)
    try:
        safe_sql = validate_and_prepare(scoped_sql)
    except SQLSafetyError as e:
        return {"ok": False, "error": str(e)}

    client_registry.set_active_client_override(client_id)
    start_time = time.perf_counter()
    try:
        df = run_sql_readonly(safe_sql, client_id=client_id)
    except Exception as e:
        return {"ok": False, "error": str(e).splitlines()[0]}
    finally:
        client_registry.set_active_client_override(None)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 1)

    value = None
    if len(df) and len(df.columns):
        value = df.iloc[0, 0]
        if hasattr(value, "item"):
            value = value.item()

    return {
        "ok": True,
        "value": value,
        "row_count": int(len(df)),
        "duration_ms": duration_ms,
        "period_label": period_label,
    }


def _valid_iso_date(s: str) -> bool:
    try:
        datetime.fromisoformat(s)
        return True
    except (ValueError, TypeError):
        return False


def validate_item(client_id: str, section: str, item_key: str, data: dict) -> dict:
    """Validate one draft's content. Returns:
      - {"ok": True, "value", "row_count", "duration_ms", "period_label"} for a
        SQL dry run that ran successfully,
      - {"ok": True, "message": "..."} for a schema-only check that passed,
      - {"ok": False, "error": "..."} for anything that failed.
    Never raises -- a bad draft is a normal, displayable outcome.
    """
    if section == "metric":
        sql = data.get("sql")
        if not sql or not sql.strip():
            return {"ok": False, "error": "SQL is required."}
        date_column = _date_column(get_metric(item_key, client_id))
        return _run_sql_dry_run(client_id, sql, date_column)

    if section == "rule":
        if not (data.get("definition") or "").strip():
            return {"ok": False, "error": "Definition is required."}
        logic = data.get("logic")
        if logic and logic.strip():
            return _run_sql_dry_run(client_id, logic, date_column=None)
        return {"ok": True, "message": "Schema check passed (no logic SQL to run)."}

    if section == "knowledge":
        if data.get("type") not in _KNOWLEDGE_TYPES:
            return {"ok": False, "error": f"type must be one of {sorted(_KNOWLEDGE_TYPES)}."}
        if not (data.get("description") or "").strip():
            return {"ok": False, "error": "Description is required."}
        date_range = data.get("date_range")
        if date_range:
            start, end = date_range.get("start"), date_range.get("end")
            if (start and not _valid_iso_date(start)) or (end and not _valid_iso_date(end)):
                return {"ok": False, "error": "date_range must use ISO dates (YYYY-MM-DD)."}
        elif not (data.get("recurrence") or "").strip():
            return {"ok": False, "error": "Provide either a date_range or a recurrence."}
        return {"ok": True, "message": "Schema check passed."}

    if section == "glossary":
        # `term` isn't in `data` -- it's the item_key (the URL segment), a
        # required path parameter, so it's guaranteed non-empty already.
        if not (data.get("maps_to") or "").strip():
            return {"ok": False, "error": "Maps-to is required."}
        return {"ok": True, "message": "Schema check passed."}

    return {"ok": False, "error": f"Unknown section: {section}"}
