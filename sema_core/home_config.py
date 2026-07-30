"""
SEMA: Home screen configuration (spec §1) -- the shape, defaults, KPI
catalog, and validation shared by the store (sema_core.home_config_store),
the API layer, and the serving modules it feeds (overview.py, daily_brief.py,
alerts_engine.py).

Scope note: the KPI catalog below is the set of headline numbers this app
ALREADY knows how to compute deterministically (the same ones
sema_core.overview.build_overview always produced), not a generic "run any
certified semantic-layer metric as a KPI" engine. The chat agent gets its
period-flexibility from the LLM rewriting SQL per question; a metric's
`sql` field is grounding text for that, not a template application code can
safely re-scope to an arbitrary date range on its own. Building that
generically would be a substantial standalone subsystem -- out of scope for
this pass. Three of the four KPIs (revenue/aov/churn_risk) ARE still tied to
a real semantic-layer metric each, so "metric exists and hasn't been
deprecated" validation and deprecated-metric handling (spec items 10 and 13)
are genuine, not simulated -- deliberately NOT gated on "certified" status,
though, since these are pre-vetted, fixed catalog entries (not an open pick
of any metric): churn_risk is intentionally 'draft' in the seeded demo
content and must still work as the app's long-standing default KPI.
"""

from __future__ import annotations

from sema_core.agent.semantic import SemanticLayerError, get_metric, load_semantic_layer

# id -> {label, metric (semantic-layer name this KPI is backed by, or None
# for one with no metric-file backing), supports_delta}.
KPI_CATALOG: dict[str, dict] = {
    "revenue": {"label": "Revenue", "metric": "revenue", "supports_delta": True},
    "orders": {"label": "Orders", "metric": None, "supports_delta": True},
    "aov": {"label": "AOV", "metric": "aov", "supports_delta": True},
    "churn_risk": {"label": "At-Risk Customers", "metric": "churn_risk", "supports_delta": False},
}
DEFAULT_KPI_ORDER = ["revenue", "orders", "aov", "churn_risk"]

VALID_SENSITIVITIES = ("conservative", "balanced", "sensitive")
# Multiplies daily_brief's ANOMALY_THRESHOLD_PCT / MTD_NOTABLE_PCT: a higher
# bar (conservative) means fewer, only-more-notable insights; a lower bar
# (sensitive) surfaces smaller moves too.
SENSITIVITY_MULTIPLIER: dict[str, float] = {"conservative": 1.5, "balanced": 1.0, "sensitive": 0.5}
VALID_PERIOD_MONTHS = (1, 3, 6, 12)
MAX_SUGGESTED_QUESTIONS = 6

DEFAULT_CONFIG: dict = {
    "kpis": {
        "order": list(DEFAULT_KPI_ORDER),
        "deltas": {"revenue": True, "orders": True, "aov": True},
    },
    "default_period_months": 1,
    "daily_brief": {"pulse_enabled": True, "insights_enabled": True, "sensitivity": "balanced"},
    # An empty question list means "use this client's static suggested_questions
    # from config/clients.yaml" -- so a client with no home config published yet
    # behaves exactly as it did before this feature shipped.
    "suggested_questions": {"questions": [], "trending_enabled": True},
    # An empty dict means "every alert enabled at its metric-file default
    # threshold" -- again, unchanged behavior for a client with no config.
    "alerts": {},
}


def _metric(client_id: str, name: str) -> dict | None:
    try:
        return get_metric(name, client_id)
    except SemanticLayerError:
        return None


def _metric_is_usable(client_id: str, name: str) -> bool:
    """Exists and hasn't been deprecated. Used both by validate() (publish
    time) and effective_config() (render time): KPI_CATALOG is a small FIXED
    set of 4 things this app already knows how to compute (see this
    module's docstring) rather than an open pick of any certified metric, so
    a metric merely sitting in 'draft' status -- like churn_risk, deliberately,
    in the seeded demo content -- must stay usable here, not gated the way a
    genuinely open metric picker would gate an unvetted draft. Only an
    actually deprecated or deleted metric counts as drift (spec item 13)."""
    m = _metric(client_id, name)
    return m is not None and m.get("status", "certified") != "deprecated"


def known_alert_ids(client_id: str) -> set[str]:
    try:
        metrics = load_semantic_layer(client_id)
    except SemanticLayerError:
        return set()
    return {a["id"] for m in metrics for a in (m.get("alerts") or [])}


def validate(client_id: str, config: dict) -> list[str]:
    """Publish-time validation (spec item 10): metrics exist (and haven't
    been deprecated), KPI count in range, thresholds well-formed. Returns a
    list of human error messages -- empty means the config may be published."""
    errors: list[str] = []

    kpis = config.get("kpis") or {}
    order = kpis.get("order") or []
    if not isinstance(order, list) or not (1 <= len(order) <= len(KPI_CATALOG)):
        errors.append(f"Choose between 1 and {len(KPI_CATALOG)} KPIs.")
    for kpi_id in order:
        entry = KPI_CATALOG.get(kpi_id)
        if entry is None:
            errors.append(f"Unknown KPI: {kpi_id}")
            continue
        metric_name = entry["metric"]
        if metric_name and not _metric_is_usable(client_id, metric_name):
            errors.append(f"\"{entry['label']}\" needs its '{metric_name}' metric to exist and not be deprecated.")

    if config.get("default_period_months") not in VALID_PERIOD_MONTHS:
        errors.append("Default period must be 1, 3, 6, or 12 months.")

    brief = config.get("daily_brief") or {}
    if brief.get("sensitivity") not in VALID_SENSITIVITIES:
        errors.append("Daily brief sensitivity must be conservative, balanced, or sensitive.")

    questions = (config.get("suggested_questions") or {}).get("questions", [])
    if not isinstance(questions, list) or len(questions) > MAX_SUGGESTED_QUESTIONS:
        errors.append(f"Choose at most {MAX_SUGGESTED_QUESTIONS} suggested questions.")
    else:
        for q in questions:
            if not isinstance(q, str) or not (1 <= len(q.strip()) <= 200):
                errors.append("Each suggested question must be 1-200 characters.")
                break

    known_ids = known_alert_ids(client_id)
    for alert_id, alert_cfg in (config.get("alerts") or {}).items():
        if alert_id not in known_ids:
            errors.append(f"Unknown alert: {alert_id}")
            continue
        threshold = (alert_cfg or {}).get("threshold")
        if threshold is not None and not isinstance(threshold, (int, float)):
            errors.append(f"Alert '{alert_id}' threshold must be a number.")

    return errors


def _deep_merge(default: dict, override: dict) -> dict:
    """One level deep: each top-level key's DICT value is shallow-merged
    (override's sub-keys win), everything else is replaced outright. The
    config is small and flat enough that one level is all that's needed."""
    out = {}
    for key, default_value in default.items():
        override_value = override.get(key, default_value)
        if isinstance(default_value, dict) and isinstance(override_value, dict):
            out[key] = {**default_value, **override_value}
        else:
            out[key] = override_value
    return out


def effective_config(client_id: str, stored: dict | None) -> tuple[dict, list[str]]:
    """Merge a stored (draft or published) config over DEFAULT_CONFIG, and
    drop any KPI whose backing metric has since been deprecated or deleted
    (spec item 13) -- render-time graceful degradation for drift AFTER
    publish, distinct from validate()'s publish-time gate. Returns
    (effective_config, warnings) -- warnings surface as the editor's warning
    badge; render always gets a config with at least one KPI."""
    cfg = _deep_merge(DEFAULT_CONFIG, stored or {})
    warnings: list[str] = []
    kept = []
    for kpi_id in cfg["kpis"]["order"]:
        entry = KPI_CATALOG.get(kpi_id)
        if entry is None:
            warnings.append(f"Removed unknown KPI '{kpi_id}'.")
            continue
        metric_name = entry["metric"]
        if metric_name and not _metric_is_usable(client_id, metric_name):
            warnings.append(f"\"{entry['label']}\" was dropped: its metric was deprecated or removed.")
            continue
        kept.append(kpi_id)
    cfg["kpis"]["order"] = kept or list(DEFAULT_KPI_ORDER)
    return cfg, warnings
