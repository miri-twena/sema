"""
Two upgrades to the agent core (no live LLM/DB needed):

1. Off-topic mode: witty deflection + a grounded, value-adding redirect
   (system-prompt content + response.py passthrough + build_pulse_context).
2. The recommendation engine: recommended_actions becomes structured
   {action, why, expected_impact, effort} (response.py's _clean_action +
   the present_answer schema + the senior-advisor persona in the prompt).
"""

from __future__ import annotations

from sema_core.agent.prompts import SYSTEM_PROMPT, build_pulse_context
from sema_core.agent.response import PRESENT_ANSWER_TOOL, _clean_action, build_response


class FakeTools:
    def __init__(self):
        self.results = []
        self.failures = []
        self.access_denied = None


# --- persona ------------------------------------------------------------
def test_persona_block_is_present_and_near_the_top():
    """The senior-advisor persona must appear before the multi-turn/tool
    instructions, not buried at the end where a long prompt would dilute it."""
    persona_idx = SYSTEM_PROMPT.lower().find("15+ years")
    multiturn_idx = SYSTEM_PROMPT.lower().find("multi-turn conversation")
    assert persona_idx != -1
    assert persona_idx < multiturn_idx


def test_persona_explicitly_guards_against_inflating_length():
    """A persona instruction with no counterweight tends to make models more
    verbose ("as an expert, let me elaborate...") -- the prompt must say the
    opposite explicitly."""
    assert "never inflate" in SYSTEM_PROMPT.lower() or "shorter" in SYSTEM_PROMPT.lower()


# --- off-topic policy content --------------------------------------------
def test_off_topic_policy_documents_humor_rule():
    text = SYSTEM_PROMPT.lower()
    assert "witty" in text or "quip" in text
    assert "max 2 sentences" in text or "2 sentences of humor" in text
    assert "never mock" in text
    assert "no emojis" in text


def test_off_topic_policy_documents_sensitive_topic_exception():
    text = SYSTEM_PROMPT.lower()
    assert "sensitive" in text
    for topic in ("politics", "religion", "health", "tragedy"):
        assert topic in text
    assert "skip the joke" in text or "no humor" in text


def test_off_topic_policy_requires_grounded_follow_ups():
    text = SYSTEM_PROMPT.lower()
    assert "recent business signals" in text or "sema-context" in text
    assert "evergreen" in text  # the fallback path when there's no pulse context


def test_off_topic_policy_requires_native_language_humor():
    assert "never translate a canned joke" in SYSTEM_PROMPT.lower()


# --- recommendation engine quality bar -----------------------------------
def test_recommended_actions_prompt_documents_quality_bar():
    text = SYSTEM_PROMPT.lower()
    assert "impact-to-effort" in text
    assert "truism" in text
    assert "root cause" in text
    assert "budget/spend" in text or "budget" in text


def test_present_answer_schema_recommended_actions_is_structured():
    props = PRESENT_ANSWER_TOOL["input_schema"]["properties"]["recommended_actions"]
    item_props = props["items"]["properties"]
    assert set(item_props) == {"action", "why", "expected_impact", "effort"}
    assert props["items"]["required"] == ["action"]
    assert item_props["effort"]["enum"] == ["low", "medium", "high"]


def test_present_answer_schema_mode_enum_includes_access_denied():
    mode_enum = PRESENT_ANSWER_TOOL["input_schema"]["properties"]["mode"]["enum"]
    assert "access_denied" in mode_enum
    assert "off_topic" in mode_enum


# --- _clean_action ---------------------------------------------------------
def test_clean_action_accepts_well_formed_object():
    cleaned = _clean_action(
        {"action": "Win back 142 dormant VIPs", "why": "142 VIPs, 60d+ inactive", "expected_impact": "~$180K/yr", "effort": "low"}
    )
    assert cleaned == {
        "action": "Win back 142 dormant VIPs",
        "why": "142 VIPs, 60d+ inactive",
        "expected_impact": "~$180K/yr",
        "effort": "low",
    }


def test_clean_action_accepts_legacy_plain_string():
    assert _clean_action("Do the thing") == {
        "action": "Do the thing", "why": None, "expected_impact": None, "effort": None,
    }


def test_clean_action_drops_entries_with_no_action_text():
    assert _clean_action({"why": "no action given"}) is None
    assert _clean_action({"action": "   "}) is None
    assert _clean_action("") is None
    assert _clean_action(123) is None


def test_clean_action_rejects_invalid_effort_value():
    cleaned = _clean_action({"action": "Do X", "effort": "extreme"})
    assert cleaned["effort"] is None  # invalid enum value -> dropped, not passed through


def test_build_response_drops_malformed_action_entries_but_keeps_good_ones():
    resp = build_response(
        {
            "mode": "answer",
            "insight_text": "x",
            "recommended_actions": [
                {"action": "Do X", "why": "Y"},
                {"why": "no action"},  # dropped
                "",  # dropped
            ],
        },
        FakeTools(),
    )
    assert resp["recommended_actions"] == [{"action": "Do X", "why": "Y", "expected_impact": None, "effort": None}]


# --- off_topic mode keeps its recommendations/follow-ups ------------------
def test_off_topic_mode_keeps_actions_and_follow_ups_but_strips_analytics():
    resp = build_response(
        {
            "mode": "off_topic",
            "insight_text": "quip + bridge",
            "recommended_actions": [{"action": "Review negative-ROI campaigns"}],
            "follow_up_questions": ["What was AOV last week?"],
            "kpis": [{"label": "should be stripped", "value": 1, "format": "number"}],
            "confidence": "high",
        },
        FakeTools(),
    )
    assert resp["mode"] == "off_topic"
    assert resp["recommended_actions"] == [
        {"action": "Review negative-ROI campaigns", "why": None, "expected_impact": None, "effort": None}
    ]
    assert resp["follow_up_questions"] == ["What was AOV last week?"]
    assert resp["kpis"] == []
    assert resp["confidence"] is None


# --- build_pulse_context ---------------------------------------------------
def test_pulse_context_empty_when_nothing_to_offer():
    assert build_pulse_context([], []) == ""


def test_pulse_context_includes_headlines_and_trending():
    ctx = build_pulse_context(["AOV dropped 12% this week"], ["Why is churn high?"])
    assert "AOV dropped 12% this week" in ctx
    assert "Why is churn high?" in ctx


def test_pulse_context_caps_at_three_of_each():
    headlines = [f"signal {i}" for i in range(5)]
    trending = [f"question {i}" for i in range(5)]
    ctx = build_pulse_context(headlines, trending)
    assert ctx.count("- signal") == 3
    trending_line = next(line for line in ctx.splitlines() if line.startswith("Other users"))
    assert trending_line.count("question ") == 3
