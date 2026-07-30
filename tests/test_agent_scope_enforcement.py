"""
Agent-pipeline data-access-scope enforcement (sema_core.agent.tools +
sema_core.agent.response) -- the core of the data-access-scopes feature.

No API key, no live DB (run_sql itself needs Postgres, so those cases use the
real docker-compose 'ecommerce' database via run_sql_readonly, matching the
existing test_prompt_injection.py/test_safety.py convention of exercising
run_sql for real rather than mocking the DB layer). The agent-LOOP tests
(FakeClient) need no DB at all -- they monkeypatch AgentTools.dispatch, same
pattern as test_response_modes.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sema_core.agent import agent
from sema_core.agent.response import build_response
from sema_core.agent.tools import AgentTools, _policy_index
from sema_core.client_registry import set_active_client_override

CID = "ecommerce"


@pytest.fixture(autouse=True)
def _active_client():
    set_active_client_override(CID)
    yield
    set_active_client_override(None)


# --- get_semantic_layer filtering --------------------------------------------

def test_full_scope_sees_every_metric_including_gross_margin():
    names = {m["name"] for m in AgentTools(scope_id="full").get_semantic_layer()["metrics"]}
    assert "gross_margin" in names
    assert len(names) == 10


def test_no_financials_hides_gross_margin_only():
    names = {m["name"] for m in AgentTools(scope_id="no_financials").get_semantic_layer()["metrics"]}
    assert "gross_margin" not in names
    assert "vip_customers" in names and "campaign_roi" in names


def test_sales_only_shows_only_sales_domain_metrics():
    names = {m["name"] for m in AgentTools(scope_id="sales_only").get_semantic_layer()["metrics"]}
    assert names == {"revenue", "aov", "revenue_by_category"}


# --- _policy_index: derived from the semantic YAML, not hardcoded -----------

def test_policy_index_flags_unit_cost_as_the_only_sensitive_column():
    index = _policy_index(CID)
    assert index["sensitive_columns"] == {"unit_cost"}


def test_policy_index_marks_marketing_tables_exclusive():
    index = _policy_index(CID)
    assert index["domain_exclusive_tables"]["marketing_campaigns"] == "marketing"
    assert index["domain_exclusive_tables"]["website_sessions"] == "marketing"


def test_policy_index_does_not_flag_shared_tables():
    """orders/order_items/products back metrics in more than one domain (e.g.
    orders backs both revenue [sales] and churn_risk [customers]) -- a table
    used by multiple domains can't gate on its own."""
    index = _policy_index(CID)
    assert "orders" not in index["domain_exclusive_tables"]
    assert "order_items" not in index["domain_exclusive_tables"]
    assert "products" not in index["domain_exclusive_tables"]


# --- run_sql enforcement matrix ----------------------------------------------

GROSS_MARGIN_SQL = (
    "SELECT SUM(oi.quantity * (oi.unit_price - p.unit_cost)) AS gp "
    "FROM order_items oi JOIN products p ON p.product_id = oi.product_id"
)
REVENUE_SQL = "SELECT SUM(total_amount) FROM orders WHERE status = 'completed'"
CAMPAIGN_SQL = "SELECT * FROM marketing_campaigns"
VIP_SQL = "SELECT * FROM customers WHERE segment = 'VIP'"


@pytest.mark.parametrize(
    "scope_id,sql,metrics_used,expect_blocked",
    [
        # full: nothing is ever blocked.
        ("full", GROSS_MARGIN_SQL, ["gross_margin"], False),
        ("full", VIP_SQL, ["vip_customers"], False),
        # no_financials: blocks the sensitive metric only.
        ("no_financials", GROSS_MARGIN_SQL, ["gross_margin"], True),
        ("no_financials", REVENUE_SQL, ["revenue"], False),
        ("no_financials", VIP_SQL, ["vip_customers"], False),
        ("no_financials", CAMPAIGN_SQL, None, False),
        # sales_only: blocks finance, customers, and marketing.
        ("sales_only", GROSS_MARGIN_SQL, ["gross_margin"], True),
        ("sales_only", VIP_SQL, ["vip_customers"], True),
        ("sales_only", CAMPAIGN_SQL, ["campaign_roi"], True),
        ("sales_only", REVENUE_SQL, ["revenue"], False),
    ],
)
def test_run_sql_enforcement_matrix(scope_id, sql, metrics_used, expect_blocked):
    tools = AgentTools(scope_id=scope_id)
    result = tools.run_sql(sql, metrics_used)
    assert result.get("policy_blocked", False) is expect_blocked
    if expect_blocked:
        assert tools.results == []  # never executed
        assert tools.access_denied is not None
        assert "reason" in result and "can_ask_about" in result
    else:
        assert len(tools.results) == 1  # actually ran


def test_untrusted_llm_backstop_blocks_even_without_declared_metrics():
    """The model can mislabel or simply omit metrics_used -- the independent
    structural check (sensitive column) must still catch it."""
    tools = AgentTools(scope_id="sales_only")
    result = tools.run_sql(GROSS_MARGIN_SQL)  # no metrics_used at all
    assert result["policy_blocked"] is True
    assert tools.results == []


def test_untrusted_llm_backstop_ignores_a_dishonest_metrics_used_label():
    """The model claims 'revenue' but the SQL actually computes gross margin
    -- the structural column check overrides the (wrong) self-report."""
    tools = AgentTools(scope_id="sales_only")
    result = tools.run_sql(GROSS_MARGIN_SQL, metrics_used=["revenue"])
    assert result["policy_blocked"] is True


def test_blocked_query_never_touches_failures_either():
    """A policy block is not a SQL error -- it must not count toward the
    sql_retried notice, which is specifically about self-correction."""
    tools = AgentTools(scope_id="sales_only")
    tools.run_sql(GROSS_MARGIN_SQL, metrics_used=["gross_margin"])
    assert tools.failures == []


def test_first_blocked_reason_wins_across_multiple_calls():
    tools = AgentTools(scope_id="sales_only")
    tools.run_sql(GROSS_MARGIN_SQL, metrics_used=["gross_margin"])
    first_reason = tools.access_denied["reason"]
    tools.run_sql(VIP_SQL, metrics_used=["vip_customers"])
    assert tools.access_denied["reason"] == first_reason  # unchanged


def test_multi_metric_question_one_blocked_refuses_the_whole_call():
    """A single run_sql implementing a MULTI-metric breakdown where any part
    is blocked is refused entirely -- there's no partial execution to trim."""
    tools = AgentTools(scope_id="no_financials")
    result = tools.run_sql(
        "SELECT p.category, SUM(oi.quantity*oi.unit_price) AS revenue, "
        "SUM(oi.quantity*(oi.unit_price-p.unit_cost)) AS gross_profit "
        "FROM order_items oi JOIN products p ON p.product_id = oi.product_id",
        metrics_used=["revenue_by_category", "gross_margin"],
    )
    assert result["policy_blocked"] is True
    assert tools.results == []


# --- full-loop test: mode='access_denied' end to end -------------------------

def _tool_block(name: str, tool_input: dict, block_id: str = "tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=block_id)


def _model_response(stop_reason: str, content: list):
    return SimpleNamespace(
        stop_reason=stop_reason, content=content,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


class FakeClient:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        return self._responses[0] if len(self._responses) == 1 else self._responses.pop(0)


def test_cooperating_model_declines_with_access_denied(monkeypatch):
    """Yossi (sales_only) asks about gross margin: the model (well-behaved,
    reads the scope context) calls run_sql, gets policy_blocked, and responds
    with mode='access_denied' -- the acceptance-criteria scenario."""
    fake = FakeClient(
        [
            _model_response(
                "tool_use",
                [_tool_block("run_sql", {"query": GROSS_MARGIN_SQL, "metrics_used": ["gross_margin"]})],
            ),
            _model_response(
                "tool_use",
                [
                    _tool_block(
                        "present_answer",
                        {
                            "mode": "access_denied",
                            "insight_text": "Gross margin isn't part of your data access.",
                            "follow_up_questions": ["What's our revenue by category?"],
                        },
                        block_id="tu_2",
                    )
                ],
            ),
        ]
    )
    resp = agent.run("What's our gross margin?", client=fake, scope_id="sales_only")
    assert resp["mode"] == "access_denied"
    assert resp["reason_code"] == "data_scope_blocked"
    assert resp["kpis"] == [] and resp["table"] is None  # no analytical furniture


def test_uncooperative_model_is_overridden_to_access_denied(monkeypatch):
    """The model ignores the policy_blocked result and claims a normal
    'answer' anyway -- the deterministic gate must still force
    mode='access_denied', never let a blocked query's answer through."""
    fake = FakeClient(
        [
            _model_response(
                "tool_use",
                [_tool_block("run_sql", {"query": GROSS_MARGIN_SQL, "metrics_used": ["gross_margin"]})],
            ),
            _model_response(
                "tool_use",
                [
                    _tool_block(
                        "present_answer",
                        {"mode": "answer", "insight_text": "", "confidence": "high"},
                        block_id="tu_2",
                    )
                ],
            ),
        ]
    )
    resp = agent.run("What's our gross margin?", client=fake, scope_id="sales_only")
    assert resp["mode"] == "access_denied"
    assert resp["reason_code"] == "data_scope_blocked"
    assert resp["insight_text"]  # fallback copy filled in
    assert resp["confidence"] is None


def test_full_scope_user_gets_a_normal_answer_for_the_same_question(monkeypatch):
    """Avi (full) asks the identical question and gets a real answer -- same
    SQL, different requester scope, different outcome."""
    import pandas as pd

    def fake_run_sql(self, query, metrics_used=None):
        df = pd.DataFrame({"gp": [12345.0]})
        self.results.append({"sql": query, "df": df})
        return {
            "sql_executed": query,
            "columns": ["gp"],
            "row_count": 1,
            "preview_rows": [{"gp": 12345.0}],
            "preview_truncated": False,
        }

    monkeypatch.setattr(agent.AgentTools, "run_sql", fake_run_sql)
    fake = FakeClient(
        [
            _model_response(
                "tool_use",
                [_tool_block("run_sql", {"query": GROSS_MARGIN_SQL, "metrics_used": ["gross_margin"]})],
            ),
            _model_response(
                "tool_use",
                [
                    _tool_block(
                        "present_answer",
                        {
                            "mode": "answer",
                            "insight_text": "Gross profit is $12,345.",
                            "confidence": "high",
                        },
                        block_id="tu_2",
                    )
                ],
            ),
        ]
    )
    resp = agent.run("What's our gross margin?", client=fake, scope_id="full")
    assert resp["mode"] == "answer"


def test_default_scope_id_is_full_and_never_blocks(monkeypatch):
    """agent.run's default (scope_id unspecified) must stay 'full' so every
    existing caller (tests, the router-fallback path) is unaffected."""
    dispatched = []
    monkeypatch.setattr(
        agent.AgentTools,
        "dispatch",
        lambda self, name, ti: dispatched.append(name) or ({"row_count": 0, "preview_rows": [], "columns": []}),
    )
    fake = FakeClient(
        [
            _model_response(
                "tool_use",
                [_tool_block("present_answer", {"mode": "off_topic", "insight_text": "hi"})],
            )
        ]
    )
    agent.run("hello", client=fake)
    assert dispatched == []  # off_topic still runs no tools regardless of scope
