"""
Fallback visibility at the wiring layer.

When the agent is configured but crashes at runtime, get_response falls back to
the rule-based router. That path used to be SILENT (with a key present); now it
must disclose itself with a router_fallback notice so the user knows a built-in
report stood in for a live analysis. insight_builder/detect_intent are stubbed
so the test needs no live DB.
"""

from __future__ import annotations

from sema_core import wiring


def test_router_fallback_attaches_notice(monkeypatch):
    monkeypatch.setattr(wiring.agent, "api_key_configured", lambda: True)

    def boom(*args, **kwargs):
        raise RuntimeError("agent exploded")

    monkeypatch.setattr(wiring.agent, "run", boom)
    monkeypatch.setattr(wiring, "detect_intent", lambda q: "revenue_trend")
    monkeypatch.setattr(
        wiring.insight_builder, "build", lambda intent: {"insight_text": "built-in report", "mode": "answer"}
    )

    resp = wiring.get_response("show revenue")

    assert resp["insight_text"] == "built-in report"  # the FALLBACK_NOTE prefix is NOT added when a key is present
    assert {"kind": "router_fallback"} in resp["notices"]


def test_no_key_offline_note_has_no_router_notice(monkeypatch):
    # No API key is the normal offline path, not a degradation -- it keeps the
    # text note and must NOT carry a router_fallback badge.
    monkeypatch.setattr(wiring.agent, "api_key_configured", lambda: False)
    monkeypatch.setattr(wiring, "detect_intent", lambda q: "revenue_trend")
    monkeypatch.setattr(
        wiring.insight_builder, "build", lambda intent: {"insight_text": "built-in report", "mode": "answer"}
    )

    resp = wiring.get_response("show revenue")

    assert resp["insight_text"].startswith(wiring.FALLBACK_NOTE)
    assert "notices" not in resp or resp["notices"] == []
