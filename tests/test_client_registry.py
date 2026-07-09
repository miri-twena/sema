"""
P0 item 2: unknown client ids must NOT silently fall back to another tenant.
Also covers the ContextVar per-request override the FastAPI layer relies on.
"""

from __future__ import annotations

import pytest

import client_registry
from client_registry import (
    ClientConfigError,
    active_client_id,
    get_client_by_id,
    set_active_client_override,
)


def test_known_id_returns_that_client():
    client = get_client_by_id("ecommerce")
    assert client["id"] == "ecommerce"


def test_unknown_id_raises_instead_of_falling_back():
    # The bug: get_client_by_id used to return clients[0] for any unknown id,
    # so a bad client_id would quietly query the WRONG tenant's database.
    with pytest.raises(ClientConfigError):
        get_client_by_id("does-not-exist")


def test_override_sets_and_clears_active_client():
    set_active_client_override("insurance")
    try:
        assert active_client_id() == "insurance"
    finally:
        set_active_client_override(None)
    # Cleared -> falls back to the configured default (outside Streamlit).
    assert active_client_id() == client_registry.DEFAULT_CLIENT_ID
