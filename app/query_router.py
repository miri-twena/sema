"""
SEMA: intent detection (rule-based "router").

This is the stand-in for what will later be an LLM-based orchestrator.
For Phase 1, we map user questions to one of a fixed set of "intents"
using simple keyword/phrase matching -- think of it like a CASE WHEN over
the user's text. Each intent corresponds to one predefined report built in
insight_builder.py.

Matching strategy:
1. Exact match against SUGGESTED_QUESTIONS (the sidebar buttons send these
   strings verbatim, so we can match them exactly first).
2. Otherwise, fall through an ordered list of (intent_id, keywords) and
   return the first intent where ALL keywords for that intent are found in
   the user's text (case-insensitive). Order matters: more specific intents
   are checked before broad ones (e.g. "march_dip" before "revenue_trend",
   since both mention "revenue").
"""

from __future__ import annotations

SUGGESTED_QUESTIONS: list[str] = [
    "Why did revenue drop in March 2026?",
    "Who are our most valuable customers?",
    "Show revenue trend by month.",
    "Which campaign performs best?",
    "Which customers are at risk?",
    "Show revenue by product category.",
    "What percentage of revenue comes from the top 5% of customers?",
]

# Maps each suggested question to its intent id, for exact-match lookups.
_EXACT_INTENT_MAP: dict[str, str] = {
    "Why did revenue drop in March 2026?": "march_dip",
    "Who are our most valuable customers?": "top_customers",
    "Show revenue trend by month.": "revenue_trend",
    "Which campaign performs best?": "campaign_performance",
    "Which customers are at risk?": "at_risk",
    "Show revenue by product category.": "revenue_by_category",
    "What percentage of revenue comes from the top 5% of customers?": "pareto",
}

# Ordered fallback rules: (intent_id, list of keywords that must ALL appear).
# Checked top to bottom; the first full match wins.
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("march_dip", ["march", "2026"]),
    ("march_dip", ["march", "drop"]),
    ("pareto", ["top 5%"]),
    ("pareto", ["percentage", "top"]),
    ("at_risk", ["at risk"]),
    ("at_risk", ["inactive"]),
    ("at_risk", ["churn"]),
    ("campaign_performance", ["campaign"]),
    ("revenue_by_category", ["category"]),
    ("top_customers", ["valuable", "customer"]),
    ("top_customers", ["best customer"]),
    ("top_customers", ["top customer"]),
    ("revenue_trend", ["revenue", "trend"]),
    ("revenue_trend", ["revenue", "month"]),
]


def detect_intent(user_text: str) -> str | None:
    """Return an intent id, or None if no rule matches."""
    if user_text in _EXACT_INTENT_MAP:
        return _EXACT_INTENT_MAP[user_text]

    text = user_text.lower()
    for intent_id, keywords in _KEYWORD_RULES:
        if all(keyword.lower() in text for keyword in keywords):
            return intent_id

    return None
