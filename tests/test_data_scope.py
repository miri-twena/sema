"""
Data-access scopes (sema_core.data_scope): the preset matrix itself, pure
logic with no DB/API-key dependency. Enforcement wiring (agent tools, admin
API guards, brief/overview/alerts filtering) is covered in their own test
files; this one is about the presets being internally consistent.
"""

from __future__ import annotations

import pytest

from sema_core import data_scope

METRICS = [
    {"name": "revenue", "label": "Revenue", "domain": "sales"},
    {"name": "aov", "label": "AOV", "domain": "sales"},
    {"name": "vip_customers", "label": "VIP Customers", "domain": "customers"},
    {"name": "campaign_roi", "label": "Campaign ROI", "domain": "marketing"},
    {"name": "gross_margin", "label": "Gross Margin", "domain": "finance", "sensitive": "financials"},
]


# --- preset matrix: each scope x each metric --------------------------------
@pytest.mark.parametrize(
    "scope_id,expected_allowed",
    [
        ("full", {"revenue", "aov", "vip_customers", "campaign_roi", "gross_margin"}),
        ("no_financials", {"revenue", "aov", "vip_customers", "campaign_roi"}),
        ("sales_only", {"revenue", "aov"}),
        ("custom", set()),
    ],
)
def test_allowed_metrics_matrix(scope_id, expected_allowed):
    allowed = {m["name"] for m in data_scope.allowed_metrics(METRICS, scope_id)}
    assert allowed == expected_allowed


def test_full_allows_everything_including_sensitive():
    assert data_scope.metric_allowed(METRICS[-1], "full") is True


def test_no_financials_blocks_finance_domain_and_sensitive_tag():
    gross_margin = METRICS[-1]
    assert data_scope.metric_allowed(gross_margin, "no_financials") is False
    reason = data_scope.blocked_reason(gross_margin, "no_financials")
    assert reason is not None and "financial" in reason.lower()


def test_sales_only_blocks_customers_and_marketing_too():
    assert data_scope.metric_allowed({"domain": "customers"}, "sales_only") is False
    assert data_scope.metric_allowed({"domain": "marketing"}, "sales_only") is False
    assert data_scope.metric_allowed({"domain": "sales"}, "sales_only") is True


def test_custom_blocks_every_domain_and_is_not_selectable():
    for domain in data_scope.DOMAINS:
        assert data_scope.domain_allowed(domain, "custom") is False
    assert data_scope.SCOPE_PRESETS["custom"].selectable is False


def test_every_selectable_preset_except_custom_is_selectable():
    selectable_ids = {p.id for p in data_scope.SCOPE_PRESETS.values() if p.selectable}
    assert selectable_ids == {"full", "no_financials", "sales_only"}


def test_unknown_scope_id_fails_safe_not_open():
    """A missing/garbage scope id must never resolve to unrestricted access."""
    p = data_scope.preset("totally-unknown")
    assert p.allowed_domains is not None and len(p.allowed_domains) < len(data_scope.DOMAINS)
    assert data_scope.metric_allowed({"domain": "finance"}, "totally-unknown") is False


# --- blocked_reason phrasing: human topic, not a metric id -------------------
def test_blocked_reason_names_the_label_not_the_id():
    reason = data_scope.blocked_reason(METRICS[2], "sales_only")  # vip_customers
    assert reason is not None
    assert "VIP Customers" in reason
    assert "vip_customers" not in reason  # never the raw metric id


def test_blocked_reason_is_none_when_allowed():
    assert data_scope.blocked_reason(METRICS[0], "full") is None


# --- can_ask_about_summary ----------------------------------------------------
def test_can_ask_about_summary_full_mentions_financials():
    assert "financ" in data_scope.can_ask_about_summary(METRICS, "full").lower()


def test_can_ask_about_summary_sales_only_names_sales():
    summary = data_scope.can_ask_about_summary(METRICS, "sales_only")
    assert "Sales" in summary
    assert "Finance" not in summary
    assert "Customers" not in summary


def test_can_ask_about_summary_empty_when_nothing_allowed():
    """custom currently allows nothing -- the summary must say so plainly,
    never claim a topic it can't actually deliver."""
    summary = data_scope.can_ask_about_summary(METRICS, "custom")
    assert "any topics" in summary or "doesn't currently include" in summary


# --- catalog() -- the admin UI's single source of truth ----------------------
def test_catalog_shape_and_order():
    cat = data_scope.catalog()
    ids = [c["id"] for c in cat]
    assert ids == ["full", "no_financials", "sales_only", "custom"]
    for entry in cat:
        assert set(entry) == {
            "id", "label", "description", "included_domains", "excluded_domains", "selectable",
        }


def test_catalog_full_has_no_excluded_domains():
    full = next(c for c in data_scope.catalog() if c["id"] == "full")
    assert full["excluded_domains"] == []
    assert set(full["included_domains"]) == set(data_scope.DOMAINS)


def test_catalog_sales_only_excludes_the_other_three():
    sales_only = next(c for c in data_scope.catalog() if c["id"] == "sales_only")
    assert sales_only["included_domains"] == ["sales"]
    assert set(sales_only["excluded_domains"]) == {"customers", "marketing", "finance"}


def test_catalog_custom_is_not_selectable():
    custom = next(c for c in data_scope.catalog() if c["id"] == "custom")
    assert custom["selectable"] is False
