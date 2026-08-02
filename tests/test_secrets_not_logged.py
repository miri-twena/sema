"""
deployment_prep_prompt.md item 5: no secret value the app is configured with
may ever appear in a captured log line from a request cycle. Structured
logging (sema_core.obs.log_event) only ever logs explicit named fields, never
an arbitrary request/settings dump, so this is a regression guard against
that discipline slipping -- not a check expected to find anything today.

Uses caplog.set_level(..., logger="sema") rather than the default root
logger: obs.configure_logging() sets `propagate = False` on the "sema"
logger (deliberately, so it doesn't double-log through the root logger),
which would otherwise make caplog's default root-logger capture see nothing.
"""

from __future__ import annotations

import dataclasses
import logging

from fastapi.testclient import TestClient

import api.main as main

_VALID_FERNET_KEY = "4YuN_Pa2xK8a5jsT1v_fixLfh__sV_YGBUBg0ZL7j70="


def test_no_secrets_logged_during_a_request_cycle(monkeypatch, caplog):
    fake_anthropic_key = "sk-ant-super-secret-test-value"
    fake_sema_api_key = "my-super-secret-sema-api-key"
    fake_db_password = "hunter2-postgres-password"
    fake_secrets_key = _VALID_FERNET_KEY

    monkeypatch.setenv("ANTHROPIC_API_KEY", fake_anthropic_key)
    monkeypatch.setenv("SEMA_SECRETS_KEY", fake_secrets_key)
    monkeypatch.setattr(
        main,
        "settings",
        dataclasses.replace(main.settings, api_key=fake_sema_api_key, db_password=fake_db_password),
    )

    client = TestClient(main.app)
    with caplog.at_level(logging.DEBUG, logger="sema"):
        # A representative spread of request shapes, incl. the ones most
        # likely to accidentally echo a credential: the no-auth probe, the
        # gated health check, a wrong-key rejection (exactly where a naive
        # implementation might log the attempted key or compare values),
        # and a wrong-admin-auth rejection.
        client.get("/healthz")
        client.get("/api/health", headers={"X-API-Key": fake_sema_api_key})
        client.get("/api/clients", headers={"X-API-Key": "definitely-wrong-key"})
        client.get("/api/clients", headers={"X-API-Key": fake_sema_api_key})
        client.get("/api/admin/me", headers={"X-API-Key": fake_sema_api_key})

    log_text = caplog.text
    for secret, label in [
        (fake_anthropic_key, "ANTHROPIC_API_KEY"),
        (fake_sema_api_key, "SEMA_API_KEY"),
        (fake_db_password, "POSTGRES_PASSWORD"),
        (fake_secrets_key, "SEMA_SECRETS_KEY"),
    ]:
        assert secret not in log_text, f"{label}'s configured value leaked into a log line"
