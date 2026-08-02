"""
Suggested-questions fallback follows the org's chrome language
(home_hebrew_polish_prompt.md item 4): config/clients.yaml's
`suggested_questions` is the language-agnostic (English) default;
`suggested_questions_he` is an optional Hebrew variant, picked when
org_settings.default_language is "he" -- the same org-language source every
other piece of chrome copy already reads. An admin's own home_config
override (whatever language they typed) always wins over BOTH, unchanged.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main
from sema_core import client_registry

CID = "ecommerce"


def test_static_fallback_picks_hebrew_variant_when_configured():
    client_cfg = {
        "suggested_questions": ["Show revenue trend."],
        "suggested_questions_he": ["הראי מגמת הכנסות."],
    }
    assert main._client_static_suggested_questions(client_cfg, "he") == ["הראי מגמת הכנסות."]
    assert main._client_static_suggested_questions(client_cfg, "en") == ["Show revenue trend."]


def test_static_fallback_degrades_to_english_when_no_hebrew_variant_exists():
    client_cfg = {"suggested_questions": ["Show revenue trend."]}
    assert main._client_static_suggested_questions(client_cfg, "he") == ["Show revenue trend."]


def test_static_fallback_treats_an_empty_hebrew_list_as_not_configured():
    client_cfg = {"suggested_questions": ["Show revenue trend."], "suggested_questions_he": []}
    assert main._client_static_suggested_questions(client_cfg, "he") == ["Show revenue trend."]


def test_api_clients_reflects_the_real_configured_hebrew_variant():
    """The real config/clients.yaml -- not a synthetic fixture -- so this
    also catches a future edit that drops the Hebrew variant by accident."""
    real_cfg = client_registry.get_client_by_id(CID)
    assert real_cfg.get("suggested_questions_he"), "ecommerce's real config lost its Hebrew variant"

    client = TestClient(main.app)
    main.org_settings_store.get_or_create(CID, default_name="E-Commerce")
    main.org_settings_store.update(CID, {"default_language": "he"})

    body = client.get("/api/clients").json()
    ecommerce = next(c for c in body if c["id"] == CID)
    assert ecommerce["suggested_questions"] == real_cfg["suggested_questions_he"]


def test_api_clients_stays_english_when_org_language_is_english():
    client = TestClient(main.app)
    main.org_settings_store.get_or_create(CID, default_name="E-Commerce")
    main.org_settings_store.update(CID, {"default_language": "en"})

    real_cfg = client_registry.get_client_by_id(CID)
    body = client.get("/api/clients").json()
    ecommerce = next(c for c in body if c["id"] == CID)
    assert ecommerce["suggested_questions"] == real_cfg["suggested_questions"]


def test_admin_override_wins_over_the_hebrew_variant_too(monkeypatch):
    """A published home_config override (whatever language the admin typed)
    always wins over the static per-language fallback -- unchanged by this
    task, confirmed explicitly since it's the ONE thing that must NOT start
    silently picking a different list."""
    main.org_settings_store.get_or_create(CID, default_name="E-Commerce")
    main.org_settings_store.update(CID, {"default_language": "he"})
    main.org_user_store.seed_demo_users(CID)
    monkeypatch.setattr(main, "current_identity", lambda: {"client_id": CID, "email": "miri1988@gmail.com"})
    client = TestClient(main.app)

    body = {
        "kpis": {"order": ["revenue"], "deltas": {"revenue": True}},
        "default_period_months": 3,
        "daily_brief": {"pulse_enabled": True, "insights_enabled": True, "sensitivity": "balanced"},
        "suggested_questions": {"questions": ["Custom admin question?"], "trending_enabled": True},
        "alerts": {},
    }
    client.put("/api/admin/home-config", json=body)
    pub = client.post("/api/admin/home-config/publish")
    assert pub.status_code == 200

    resp = client.get("/api/clients").json()
    ecommerce = next(c for c in resp if c["id"] == CID)
    assert ecommerce["suggested_questions"] == ["Custom admin question?"]
