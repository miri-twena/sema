"""
SEMA: data-access scopes -- "what a user may ask about".

A second permission axis alongside role (sema_core.org_user_store): role is
WHAT you can do in the product (client_admin / analyst / viewer); data scope
is WHICH semantic-layer domains and metrics your QUESTIONS may touch. This is
OLS-style (metric/object-level security) -- row-level filtering (e.g. "only
your own region's rows") stays out of scope, reserved for V2 (the `custom`
preset below).

Scope PRESETS are defined here, once, server-side -- never as per-user rows.
Every org_users.data_scope value is one of these ids, and this module is the
single source of truth both the admin UI (GET /api/admin/data-scopes) and the
agent pipeline (sema_core.agent.tools) read from.

No dependency on the Claude API key or the database -- pure, testable logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DataScope = Literal["full", "no_financials", "sales_only", "custom"]

# Keep in sync with sema_core.agent.semantic.VALID_DOMAINS -- every metric
# YAML declares exactly one of these.
DOMAINS = ("sales", "customers", "marketing", "finance")

DOMAIN_LABELS = {
    "sales": "Sales",
    "customers": "Customers",
    "marketing": "Marketing",
    "finance": "Finance",
}


@dataclass(frozen=True)
class ScopePreset:
    id: str
    label: str
    description: str
    # None means "every domain" (the `full` preset). Otherwise the exact set
    # of domains a question under this scope may touch.
    allowed_domains: frozenset[str] | None
    # Even inside an allowed domain, a metric tagged sensitive="financials" is
    # blocked when this is True -- so no_financials blocks Finance twice over
    # (the domain AND the tag), which matters once a sensitive metric ever
    # lives outside the finance domain.
    blocks_sensitive: bool
    # False only for `custom` (V2): the UI disables selecting it and the
    # server rejects a PATCH/invite that tries to set it.
    selectable: bool

    def domain_allowed(self, domain: str) -> bool:
        return self.allowed_domains is None or domain in self.allowed_domains


SCOPE_PRESETS: dict[str, ScopePreset] = {
    "full": ScopePreset(
        id="full",
        label="Full access",
        description="Every domain and metric, including financials. Always on for admins.",
        allowed_domains=None,
        blocks_sensitive=False,
        selectable=True,
    ),
    "no_financials": ScopePreset(
        id="no_financials",
        label="No financials",
        description=(
            "Every domain except Finance. Profitability metrics (gross margin, "
            "cost of goods, and similar) are blocked even if they surface "
            "inside an otherwise-allowed domain."
        ),
        allowed_domains=frozenset({"sales", "customers", "marketing"}),
        blocks_sensitive=True,
        selectable=True,
    ),
    "sales_only": ScopePreset(
        id="sales_only",
        label="Sales only",
        description=(
            "Sales metrics only -- revenue, orders, AOV, category breakdowns. "
            "Customers, Marketing, and Finance are blocked."
        ),
        allowed_domains=frozenset({"sales"}),
        blocks_sensitive=True,
        selectable=True,
    ),
    "custom": ScopePreset(
        id="custom",
        label="Custom",
        description="Per-metric access rules. Reserved for a future release.",
        allowed_domains=frozenset(),
        blocks_sensitive=True,
        selectable=False,
    ),
}

# New invites default to the safer non-financial preset unless the inviter
# picks something else; client_admin is always forced to `full` regardless
# (see org_user_store's admin-always-full guard).
DEFAULT_INVITE_SCOPE: str = "no_financials"


def preset(scope_id: str | None) -> ScopePreset:
    """The preset for a scope id. An unrecognized/missing id fails SAFE to the
    most restrictive real preset rather than the most permissive -- this
    should never happen in practice (org_users.data_scope is validated at the
    API boundary), but a permissions module must never default-open."""
    return SCOPE_PRESETS.get(scope_id or "", SCOPE_PRESETS["sales_only"])


def domain_allowed(domain: str, scope_id: str) -> bool:
    return preset(scope_id).domain_allowed(domain)


def metric_allowed(metric: dict, scope_id: str) -> bool:
    """Whether a single semantic-layer metric dict (with `domain` and
    optional `sensitive`) may be used under this scope."""
    p = preset(scope_id)
    if metric.get("sensitive") and p.blocks_sensitive:
        return False
    return p.domain_allowed(metric.get("domain"))


def blocked_reason(metric: dict, scope_id: str) -> str | None:
    """Human-phrased (not metric-id) reason `metric` is blocked under
    `scope_id`, or None if it's allowed. Sensitivity is checked first: a
    finance metric under no_financials is blocked for containing financial
    data, not merely for its domain -- the more informative reason."""
    p = preset(scope_id)
    label = metric.get("label") or metric.get("name") or "This"
    if metric.get("sensitive") and p.blocks_sensitive:
        return f"{label} includes financial/profitability data, which isn't part of your data access."
    domain = metric.get("domain")
    if not p.domain_allowed(domain):
        domain_label = DOMAIN_LABELS.get(domain, domain)
        return f"{label} is part of the {domain_label} domain, which isn't part of your data access."
    return None


def allowed_metrics(metrics: list[dict], scope_id: str) -> list[dict]:
    return [m for m in metrics if metric_allowed(m, scope_id)]


def blocked_metrics(metrics: list[dict], scope_id: str) -> list[dict]:
    return [m for m in metrics if not metric_allowed(m, scope_id)]


def can_ask_about_summary(metrics: list[dict], scope_id: str) -> str:
    """One-line, human phrasing of what a requester's scope allows -- used in
    the agent's context (to decline early and phrase alternatives) and as the
    UI's "what you can ask" copy. Built from the ACTUAL metric list so it
    never drifts from what get_semantic_layer really returns."""
    p = preset(scope_id)
    if p.allowed_domains is None and not p.blocks_sensitive:
        return "You can ask about any topic this business tracks, including financials."
    allowed_domains = sorted({m["domain"] for m in allowed_metrics(metrics, scope_id)})
    if not allowed_domains:
        return "Your data access doesn't currently include any topics."
    labels = [DOMAIN_LABELS.get(d, d) for d in allowed_domains]
    return "You can ask about " + ", ".join(labels) + " topics."


def catalog() -> list[dict]:
    """The data-scope catalog for the admin UI (GET /api/admin/data-scopes):
    id, label, description, included/excluded domains, and whether it's
    selectable (custom = false, V2). Dict insertion order is preset display
    order (full, no_financials, sales_only, custom)."""
    out = []
    for p in SCOPE_PRESETS.values():
        included = list(DOMAINS) if p.allowed_domains is None else sorted(p.allowed_domains)
        excluded = [] if p.allowed_domains is None else [d for d in DOMAINS if d not in p.allowed_domains]
        out.append(
            {
                "id": p.id,
                "label": p.label,
                "description": p.description,
                "included_domains": included,
                "excluded_domains": excluded,
                "selectable": p.selectable,
            }
        )
    return out
