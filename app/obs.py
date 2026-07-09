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
    """Emit one structured JSON log line: {"event": <event>, ...fields}."""
    logger.info(json.dumps({"event": event, **fields}, default=str))


def new_request_id() -> str:
    """A short unique id to correlate one request across log lines."""
    return uuid.uuid4().hex[:12]
