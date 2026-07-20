"""
Deterministic clarification flow: the tenant-config layer that decides -- from
governed configuration, not model self-confidence -- whether each ambiguity axis
is "resolved, use this default, do not ask" or "genuinely ambiguous, ask before
running SQL", plus the resolved_interpretation transparency line.

No API key, no network, no DB: get_analytics_config reads config/clients.yaml,
build_tenant_context is pure string assembly, and the agent-loop checks drive a
scripted fake client (same pattern as test_response_modes.py).
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import api.main as main
from api.models import ChatRequest
from api.serialize import to_chat_response
from sema_core import client_registry
from sema_core.agent import agent
from sema_core.agent.prompts import build_tenant_context
from sema_core.agent.response import build_response


# --- get_analytics_config: normalization + the calendar-default decision ------
def test_ecommerce_defaults_to_calendar_and_configures_only_timezone():
    cfg = client_registry.get_analytics_config("ecommerce")
    # Only a timezone is configured -> that axis is resolved, the rest default.
    assert cfg["timezone"] == "Asia/Jerusalem"
    assert cfg["fiscal_configured"] is False
    assert cfg["fiscal_start_month"] is None
    assert cfg["business_days_configured"] is False


def test_fiscal_only_counts_when_it_differs_from_calendar(monkeypatch):
    """A fiscal calendar starting in January is the calendar year spelled out --
    no ambiguity. Only a non-January start makes 'quarter' ambiguous."""

    def fake_client(cfg):
        return lambda _cid: {"id": "x", "analytics_config": cfg}

    monkeypatch.setattr(client_registry, "get_client_by_id", fake_client({"fiscal_calendar": {"start_month": 2}}))
    assert client_registry.get_analytics_config("x")["fiscal_configured"] is True

    monkeypatch.setattr(client_registry, "get_client_by_id", fake_client({"fiscal_calendar": {"start_month": 1}}))
    assert client_registry.get_analytics_config("x")["fiscal_configured"] is False

    monkeypatch.setattr(client_registry, "get_client_by_id", fake_client({}))
    assert client_registry.get_analytics_config("x")["fiscal_configured"] is False


# --- build_tenant_context: config drives the ASK vs USE-DEFAULT instruction ---
def test_unconfigured_axes_tell_the_agent_to_use_calendar_defaults():
    ctx = build_tenant_context(client_registry.get_analytics_config("ecommerce"))
    # Calendar/fiscal + business-days resolve to the safe default: do NOT ask.
    assert "do NOT ask calendar-vs-fiscal" in ctx
    assert "do NOT ask calendar-vs-business-days" in ctx
    # Configured timezone is used, not asked about.
    assert "Asia/Jerusalem" in ctx and "do NOT ask about timezone" in ctx


def test_configured_fiscal_and_business_days_tell_the_agent_to_ask():
    ctx = build_tenant_context(
        {
            "timezone": None,
            "fiscal_configured": True,
            "fiscal_start_month": 2,
            "business_days_configured": True,
            "revenue_default": None,
        }
    )
    # Fiscal that differs from calendar -> ask, naming the axis + the start month.
    assert "calendar_vs_fiscal" in ctx and "February" in ctx
    # Business-day calendar present -> ask, naming that axis.
    assert "business_vs_calendar_days" in ctx
    # No timezone configured -> ask rather than assume UTC.
    assert "missing_timezone" in ctx


def test_configured_revenue_default_is_used_not_asked():
    ctx = build_tenant_context(
        {
            "timezone": None,
            "fiscal_configured": False,
            "fiscal_start_month": None,
            "business_days_configured": False,
            "revenue_default": "net",
        }
    )
    assert "'net'" in ctx and "Revenue definition" in ctx


# --- _internal_context always carries the governed defaults (main + drill) -----
def test_internal_context_always_includes_tenant_block():
    # Plain question (no drill): the tenant policy block is still present, so the
    # clarification flow is config-driven on the main chat too.
    plain = main._internal_context(ChatRequest(question="Show revenue last quarter"), "ecommerce")
    assert plain is not None and "Governed analytics configuration" in plain

    # Drill-down: tenant policy AND the widget focus, both server-built.
    drilled = main._internal_context(
        ChatRequest(
            question="Compare this to last quarter",
            drill_context={"kind": "chart", "title": "Revenue by quarter", "detail": "..."},
        ),
        "ecommerce",
    )
    assert "Governed analytics configuration" in drilled
    assert "clicked a chart" in drilled  # drill focus appended after the policy


# --- resolved_interpretation: transparency line, cleaned + plumbed ------------
def _tools(dfs):
    return SimpleNamespace(
        results=[{"sql": f"SELECT {i}", "df": df} for i, df in enumerate(dfs)],
        failures=[],
    )


def _df():
    return pd.DataFrame({"month": ["2026-01"], "revenue": [100]})


def test_resolved_interpretation_is_cleaned_and_reaches_the_api_contract():
    resp = build_response(
        {
            "mode": "answer",
            "insight_text": "Fiscal Q2 revenue was $1.2M.",
            "evidence": {
                "semantic_definitions": ["revenue"],
                "resolved_interpretation": [
                    {"label": "Quarter type", "value": "Fiscal"},
                    {"label": "Timezone", "value": "Asia/Jerusalem"},
                    {"label": "bad"},  # malformed -> dropped
                    "nonsense",  # wrong type -> dropped
                ],
            },
        },
        _tools([_df()]),
    )
    interp = resp["evidence"]["resolved_interpretation"]
    assert interp == [
        {"label": "Quarter type", "value": "Fiscal"},
        {"label": "Timezone", "value": "Asia/Jerusalem"},
    ]
    # And it survives serialization to the API contract the frontend renders.
    out = to_chat_response(resp)
    assert out.evidence.resolved_interpretation == interp


def test_clarification_carries_no_interpretation():
    """A clarification is the ASK, not the resolved answer -- it strips all
    evidence (incl. the interpretation line), same as the other non-answer modes."""
    resp = build_response(
        {
            "mode": "clarification",
            "reason_code": "calendar_vs_fiscal",
            "insight_text": "Calendar or fiscal quarter?",
            "clarification_options": ["Calendar quarter", "Fiscal quarter"],
            "evidence": {"resolved_interpretation": [{"label": "Quarter type", "value": "Fiscal"}]},
        },
        _tools([]),
    )
    assert resp["mode"] == "clarification"
    assert resp["reason_code"] == "calendar_vs_fiscal"
    assert resp["evidence"] is None


# --- the ambiguity taxonomy is exposed on the present_answer tool -------------
def test_new_ambiguity_reason_codes_are_offered_to_the_model():
    enum = agent.PRESENT_ANSWER_TOOL["input_schema"]["properties"]["reason_code"]["enum"]
    for code in (
        "calendar_vs_fiscal",
        "business_vs_calendar_days",
        "ambiguous_date_range",
        "ambiguous_comparison",
        "ambiguous_scope",
        "ambiguous_inclusion_rule",
        "missing_timezone",
    ):
        assert code in enum


# --- deterministic agent-loop checks: a clarification runs NO SQL ------------
def _tool_block(name, tool_input, block_id="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=block_id)


def _api_response(content):
    return SimpleNamespace(
        stop_reason="tool_use",
        content=content,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.messages = SimpleNamespace(create=lambda **kw: self._responses.pop(0))


def _clarification_call(reason, question, tenant_ctx, monkeypatch):
    """Drive agent.run with a scripted clarification and a governed tenant
    context; assert no data tool ran before the clarification was surfaced."""
    dispatched: list[str] = []
    monkeypatch.setattr(
        agent.AgentTools, "dispatch", lambda self, name, ti: dispatched.append(name) or {}
    )
    fake = FakeClient(
        [
            _api_response(
                [
                    _tool_block(
                        "present_answer",
                        {
                            "mode": "clarification",
                            "reason_code": reason,
                            "insight_text": "Which one did you mean?",
                            "clarification_options": ["Calendar", "Fiscal"],
                        },
                    )
                ]
            )
        ]
    )
    return agent.run(question, client=fake, internal_context=tenant_ctx), dispatched


def test_calendar_vs_fiscal_clarification_in_main_chat_runs_no_sql(monkeypatch):
    ctx = build_tenant_context(
        {"timezone": None, "fiscal_configured": True, "fiscal_start_month": 2,
         "business_days_configured": False, "revenue_default": None}
    )
    resp, dispatched = _clarification_call("calendar_vs_fiscal", "Show revenue last quarter", ctx, monkeypatch)
    assert resp["mode"] == "clarification"
    assert resp["reason_code"] == "calendar_vs_fiscal"
    assert resp["clarification_options"] == ["Calendar", "Fiscal"]
    assert dispatched == []  # no get_semantic_layer, no run_sql before clarifying
    assert resp["sql_used"] is None


def test_business_days_clarification_in_drilldown_runs_no_sql(monkeypatch):
    # Tenant policy + a drill-down focus block, exactly as the API composes them.
    ctx = (
        build_tenant_context(
            {"timezone": "Asia/Jerusalem", "fiscal_configured": False, "fiscal_start_month": None,
             "business_days_configured": True, "revenue_default": None}
        )
        + "\n\nThe user clicked a table element from the previous answer."
    )
    resp, dispatched = _clarification_call(
        "business_vs_calendar_days", "Show customers inactive for 30 days", ctx, monkeypatch
    )
    assert resp["mode"] == "clarification"
    assert resp["reason_code"] == "business_vs_calendar_days"
    assert dispatched == []
