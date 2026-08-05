"""
Shared pytest setup for the SEMA backend tests.

`sema_core` and `api` resolve via the editable install (pip install -e .,
see pyproject.toml) -- no path manipulation needed. Tests require neither a
live database, an API key, nor Streamlit.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Redirect the conversation store BEFORE anything imports sema_core.settings
# (a module-level singleton, read once at import time) -- otherwise importing
# api.main during test collection would eagerly create the real
# var/sema_state.db as a side effect, before any fixture gets a chance to
# monkeypatch it away. pytest loads conftest.py before collecting test
# modules, so this always wins the race.
os.environ.setdefault(
    "SEMA_CONVERSATION_DB", str(Path(tempfile.mkdtemp(prefix="sema_test_")) / "conversations.db")
)

import pytest


@pytest.fixture(autouse=True)
def _isolated_conversation_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway SQLite conversation store, so tests
    never read or write the app's real var/sema_state.db."""
    import api.main as main
    from sema_core.conversation_store import SqliteConversationStore

    monkeypatch.setattr(
        main, "conversation_store", SqliteConversationStore(tmp_path / "test_conversations.db")
    )


@pytest.fixture(autouse=True)
def _isolated_org_user_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway org-users store (admin panel), same
    isolation as the conversation store above -- tests never touch the real
    var/sema_state.db."""
    import api.main as main
    from sema_core.org_user_store import OrgUserStore

    monkeypatch.setattr(main, "org_user_store", OrgUserStore(tmp_path / "test_org_users.db"))


@pytest.fixture(autouse=True)
def _isolated_org_settings_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway org-settings store (admin panel),
    same isolation as the org-users store above."""
    import api.main as main
    from sema_core.org_settings_store import OrgSettingsStore

    monkeypatch.setattr(main, "org_settings_store", OrgSettingsStore(tmp_path / "test_org_settings.db"))


@pytest.fixture(autouse=True)
def _isolated_semantic_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway semantic-model store (drafts +
    version history), same isolation as the org-users store above. Note this
    does NOT isolate the semantic YAML files themselves (sql/semantic/*.yaml)
    -- tests that Publish/Restore must additionally redirect semantic_dir
    (see test_semantic_model.py's own autouse fixture), or they'd write to
    the real files."""
    import api.main as main
    from sema_core.semantic_store import SemanticStore

    monkeypatch.setattr(main, "semantic_store", SemanticStore(tmp_path / "test_semantic.db"))


@pytest.fixture(autouse=True)
def _isolated_audit_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway audit-log store (admin panel), same
    isolation as the other admin-panel stores above."""
    import api.main as main
    from sema_core.audit_store import AuditStore

    monkeypatch.setattr(main, "audit_store", AuditStore(tmp_path / "test_audit.db"))


@pytest.fixture(autouse=True)
def _isolated_home_config_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway home-config store (admin panel),
    same isolation as the other admin-panel stores above."""
    import api.main as main
    from sema_core.home_config_store import HomeConfigStore

    monkeypatch.setattr(main, "home_config_store", HomeConfigStore(tmp_path / "test_home_config.db"))


@pytest.fixture(autouse=True)
def _isolated_retention_run_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway retention-run-tracking store (admin
    panel), same isolation as the other admin-panel stores above."""
    import api.main as main
    from sema_core.retention_store import RetentionRunStore

    monkeypatch.setattr(main, "retention_run_store", RetentionRunStore(tmp_path / "test_retention_runs.db"))


@pytest.fixture(autouse=True)
def _isolated_data_source_add_stores(tmp_path, monkeypatch):
    """Every test gets its own throwaway client-connections/source-requests/
    uploads stores (data_sources_add_prompt.md), same isolation as the other
    admin-panel stores above."""
    import api.main as main
    from sema_core.client_connections_store import ClientConnectionsStore
    from sema_core.source_requests_store import SourceRequestsStore
    from sema_core.uploads_store import UploadsStore

    monkeypatch.setattr(main, "client_connections_store", ClientConnectionsStore(tmp_path / "test_connections.db"))
    monkeypatch.setattr(main, "source_requests_store", SourceRequestsStore(tmp_path / "test_source_requests.db"))
    monkeypatch.setattr(main, "uploads_store", UploadsStore(tmp_path / "test_uploads.db"))


@pytest.fixture(autouse=True)
def _isolated_org_alerts_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway org-alerts store (alert_templates_
    prompt.md), same isolation as the other admin-panel stores above."""
    import api.main as main
    from sema_core.org_alerts_store import OrgAlertsStore

    monkeypatch.setattr(main, "org_alerts_store", OrgAlertsStore(tmp_path / "test_org_alerts.db"))


@pytest.fixture(autouse=True)
def _isolated_feedback_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway turn-feedback store (answer_feedback_
    prompt.md), same isolation as the other admin-panel stores above."""
    import api.main as main
    from sema_core.feedback_store import TurnFeedbackStore

    monkeypatch.setattr(main, "feedback_store", TurnFeedbackStore(tmp_path / "test_feedback.db"))


@pytest.fixture(autouse=True)
def _isolated_impersonation_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway impersonation-session store
    (impersonation_prompt.md), same isolation as the other admin-panel
    stores above. Unlike those stores, this one is a module-level singleton
    inside sema_core.current_user rather than api.main -- current_identity()
    (the single identity swap point) needs to consult it directly, with no
    store object threaded through every one of its call sites."""
    import sema_core.current_user as current_user
    from sema_core.impersonation_store import ImpersonationStore

    monkeypatch.setattr(
        current_user, "_impersonation_store", ImpersonationStore(tmp_path / "test_impersonation.db")
    )


@pytest.fixture(autouse=True)
def _isolated_query_limit_store(tmp_path, monkeypatch):
    """Every test gets its own throwaway daily-query-limit store
    (backend_qa_prompt.md item 5), same isolation as the other admin-panel
    stores above."""
    import api.main as main
    from sema_core.query_limit_store import QueryLimitStore

    monkeypatch.setattr(main, "query_limit_store", QueryLimitStore(tmp_path / "test_query_limit.db"))


@pytest.fixture(autouse=True)
def _isolated_secrets_key(monkeypatch):
    """A fixed, valid Fernet key for every test -- SEMA_SECRETS_KEY must
    never depend on whatever happens to be in the developer's real .env."""
    monkeypatch.setenv("SEMA_SECRETS_KEY", "4YuN_Pa2xK8a5jsT1v_fixLfh__sV_YGBUBg0ZL7j70=")


@pytest.fixture(autouse=True)
def _isolated_data_source_health(monkeypatch):
    """Every test gets a deterministic, always-reachable data-source health
    check instead of a real Postgres round-trip -- same isolation rationale
    as the stores above (see the module docstring: no test may depend on a
    live database). sema_core.agent.response._clean_evidence calls into
    sema_core.data_sources on every evidence-panel build whenever a query
    ran, so without this a plain `pytest` run would silently open a real DB
    connection. Tests that specifically exercise a source failure
    (tests/test_data_sources.py) re-patch these within the test body, which
    simply layers on top of this default."""
    import pandas as pd

    from sema_core import data_sources

    monkeypatch.setattr(data_sources.db, "check_connection", lambda **kw: True)
    monkeypatch.setattr(
        data_sources.db, "run_query", lambda sql, client_id=None: pd.DataFrame({"max_date": [None]})
    )


@pytest.fixture(autouse=True)
def _no_real_anthropic_key(monkeypatch):
    """Force every test onto the no-API-key code path (friendly fallback
    responses, instant trim-based titles) even though the developer's local
    .env carries a real ANTHROPIC_API_KEY for the Docker stack. Without this,
    any test that hits /api/chat or /api/chat/stream without mocking
    generate_title would make a REAL Anthropic call to title a new
    conversation -- slow, costs money, and non-deterministic in CI."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
