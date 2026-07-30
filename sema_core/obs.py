"""
SEMA: observability -- structured logging.

Emits one JSON object per event to stderr, so log lines are greppable and can
later be shipped to a log store for per-tenant cost/usage tracking. Think of
each log line like a row in an events table: an `event` name plus typed fields
(request_id, client_id, tokens, duration_ms, ...).

Standard-library logging only; no new dependency. `logger.exception(...)` is
still used directly for error stack traces -- those stay human-readable.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from datetime import datetime, timezone

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Attach a single stderr handler to the 'sema' logger tree (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger("sema")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False  # don't double-log through the root logger
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger (e.g. get_logger('agent') -> 'sema.agent')."""
    configure_logging()
    return logging.getLogger(f"sema.{name}")


def log_event(logger: logging.Logger, event: str, **fields) -> None:
    """Emit one structured JSON log line: {"event", "ts", ...fields}.

    `ts` is a UTC ISO timestamp on every event so offline reporting (e.g. the
    daily cache report) can bucket events by day -- the stderr handler's format
    is bare `%(message)s`, so the time has to travel inside the JSON."""
    ts = datetime.now(timezone.utc).isoformat()
    logger.info(json.dumps({"event": event, "ts": ts, **fields}, default=str))


def new_request_id() -> str:
    """A short unique id to correlate one request across log lines."""
    return uuid.uuid4().hex[:12]


def log_admin_event(
    logger: logging.Logger,
    event: str,
    *,
    audit_store,
    client_id: str,
    actor: dict,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    target_label: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    **fields,
) -> dict:
    """The ONE call site an admin-panel mutation uses instead of log_event:
    emits the usual structured stderr line AND appends a row to the durable,
    append-only audit_events table (sema_core.audit_store), so callers never
    have to remember to do both separately ("no double logging").

    `audit_store` is passed in rather than imported here, so this
    dependency-free module (see the module docstring) never needs a DB
    import -- the caller already has its own store instance. `actor` is the
    admin-panel identity dict (require_client_admin's return value: id,
    name/email, role). `action` is a canonical dotted id (e.g.
    "user.role_changed", "semantic.published") the frontend keys its
    human-readable sentence off; `target_*`/`before`/`after` describe what
    changed for the audit drawer's diff view.
    """
    log_event(logger, event, client_id=client_id, action=action, actor_id=actor.get("id"), **fields)
    return audit_store.record(
        client_id,
        actor_id=actor.get("id"),
        actor_name=actor.get("name") or actor.get("email"),
        actor_role=actor.get("role"),
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        before=before,
        after=after,
    )
