"""
SEMA: client registry -- the multi-client config layer.

SEMA serves several business clients, each with its own database and its own
semantic layer. This module is the single source of truth for "which clients
exist" (read from config/clients.yaml) and "which client is active right now"
(from Streamlit session state). Adding a client is a YAML change, not a code
change.

Think of a client like a separate data model + connection in a BI tool: same
app and visuals, different governed dataset behind it.
"""

from __future__ import annotations

import contextvars
import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load .env before reading SEMA_CLIENT, so the startup client honours .env even
# though this module is imported before db.py (which also calls load_dotenv).
load_dotenv()

# Project root = the folder above app/. clients.yaml and the semantic_dir
# paths in it are resolved relative to here.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLIENTS_FILE = PROJECT_ROOT / "config" / "clients.yaml"

# Fallback client when session state isn't set yet (first load) or when code
# runs outside a Streamlit context (tests/scripts). SEMA_CLIENT in .env still
# controls the *startup* client; switching at runtime happens via the UI.
DEFAULT_CLIENT_ID = (os.environ.get("SEMA_CLIENT") or "ecommerce").strip().lower()


class ClientConfigError(Exception):
    """Raised when the client registry is missing or malformed."""


@lru_cache(maxsize=1)
def load_clients() -> list[dict]:
    """Return the list of configured clients from config/clients.yaml."""
    if not CLIENTS_FILE.exists():
        raise ClientConfigError(f"clients config not found: {CLIENTS_FILE}")
    with CLIENTS_FILE.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    clients = data.get("clients", [])
    if not clients:
        raise ClientConfigError("no clients defined in config/clients.yaml")
    return clients


def get_client_by_id(client_id: str) -> dict:
    """Look up a client by id, or raise if it doesn't exist.

    Previously this silently returned the FIRST client for an unknown id, which
    meant an API call with a bad client_id would quietly query the WRONG
    tenant's database. We never cross tenant boundaries on a bad id: raise and
    let the caller (e.g. the API) turn it into a 404.
    """
    clients = load_clients()
    for client in clients:
        if client["id"] == client_id:
            return client
    raise ClientConfigError(f"unknown client id: {client_id!r}")


# Per-request client override for non-Streamlit callers (the FastAPI layer).
# A ContextVar is concurrency-safe: each request sets its own client without
# touching global state or affecting Streamlit. Streamlit leaves it unset.
_active_override: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "sema_active_client_override", default=None
)


def set_active_client_override(client_id: str | None) -> None:
    """Set the active client for the current execution context (FastAPI use)."""
    _active_override.set(client_id)


def active_client_id() -> str:
    """The id of the currently-active client.

    Resolution order: a per-request override (set by the API) -> Streamlit
    session_state -> DEFAULT_CLIENT_ID. Streamlit is imported lazily INSIDE
    this function so the module has no hard Streamlit dependency -- FastAPI,
    tests, and scripts work without Streamlit installed; the try/except also
    covers running outside a Streamlit session (no session_state).
    """
    override = _active_override.get()
    if override:
        return override
    try:
        import streamlit as st

        return st.session_state.get("active_client_id", DEFAULT_CLIENT_ID)
    except Exception:
        return DEFAULT_CLIENT_ID


def get_active_client() -> dict:
    """The full config dict of the currently-active client."""
    return get_client_by_id(active_client_id())


def get_analytics_config(client_id: str) -> dict:
    """Normalized governed defaults that drive the clarification flow.

    Reads the optional `analytics_config` block for a client and resolves it to
    a flat, always-present shape the agent/prompt layer can reason about without
    None-checking raw YAML. The KEY product decision lives here: an unconfigured
    axis resolves to its unambiguous default (calendar periods, calendar days,
    semantic-layer canonical revenue), so SEMA does NOT ask about it. An axis is
    only "ambiguous -> ask" when the client explicitly configured it to differ
    (a real fiscal calendar, a business-day calendar). This makes the decision
    to clarify a deterministic function of config, not of model self-confidence.

    An unknown client_id raises (via get_client_by_id) rather than silently
    returning another tenant's defaults -- same multi-tenant safety rule as the
    rest of the registry.
    """
    raw = get_client_by_id(client_id).get("analytics_config") or {}

    fiscal = raw.get("fiscal_calendar") or {}
    business = raw.get("business_days") or {}
    tz = raw.get("timezone")
    revenue = raw.get("revenue_definition")

    start_month = fiscal.get("start_month")
    # A fiscal calendar only creates ambiguity when it actually differs from the
    # calendar year (i.e. does not start in January). A "start_month: 1" config
    # is the calendar year spelled out -- no ambiguity, no clarification.
    fiscal_configured = bool(fiscal) and start_month not in (None, 1)

    return {
        "timezone": tz.strip() if isinstance(tz, str) and tz.strip() else None,
        "fiscal_configured": fiscal_configured,
        "fiscal_start_month": start_month if fiscal_configured else None,
        "business_days_configured": bool(business.get("working_week")),
        "revenue_default": revenue.strip() if isinstance(revenue, str) and revenue.strip() else None,
    }
