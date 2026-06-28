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

import os
from functools import lru_cache
from pathlib import Path

import streamlit as st
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
    """Look up a client by id; fall back to the first client if not found."""
    clients = load_clients()
    for client in clients:
        if client["id"] == client_id:
            return client
    return clients[0]


def active_client_id() -> str:
    """The id of the currently-active client.

    Reads st.session_state.active_client_id, defaulting to DEFAULT_CLIENT_ID.
    Wrapped in try/except so it also works outside a Streamlit run (e.g. a
    plain Python script or test), where session_state isn't available.
    """
    try:
        return st.session_state.get("active_client_id", DEFAULT_CLIENT_ID)
    except Exception:
        return DEFAULT_CLIENT_ID


def get_active_client() -> dict:
    """The full config dict of the currently-active client."""
    return get_client_by_id(active_client_id())
