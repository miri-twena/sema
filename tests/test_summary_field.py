"""
The `summary` field: the executive takeaway rendered above an answer.

Its defining property is ARCHITECTURAL -- it is produced by the agent as a
structured field and carried through unchanged. Nothing anywhere derives it by
slicing or parsing `insight_text`, so these tests pin the contract at each hop:
present_answer schema -> build_response -> to_chat_response -> stored payload.
"""

from __future__ import annotations

import pandas as pd

from api.models import ChatResponse
from api.serialize import to_chat_response
from sema_core.agent.response import PRESENT_ANSWER_TOOL, build_response


class FakeTools:
    def __init__(self, dfs: list[pd.DataFrame]):
        self.results = [{"sql": f"SELECT {i}", "df": df} for i, df in enumerate(dfs)]


def _df(n: int = 2) -> pd.DataFrame:
    return pd.DataFrame({"month": [f"2026-0{i + 1}" for i in range(n)], "revenue": range(1, n + 1)})


SUMMARY = "Revenue rose 4.4%, as a 30.2% rise in orders offset a 19.8% AOV decline."


# --- the tool schema ---------------------------------------------------------
def test_present_answer_exposes_summary_as_an_optional_string():
    props = PRESENT_ANSWER_TOOL["input_schema"]["properties"]
    assert props["summary"]["type"] == "string"
    # Optional on purpose: a model that omits it must still produce a valid
    # answer rather than failing tool validation.
    assert "summary" not in PRESENT_ANSWER_TOOL["input_schema"]["required"]


# --- build_response ----------------------------------------------------------
def test_summary_is_carried_through_verbatim():
    resp = build_response(
        {"mode": "answer", "insight_text": "long analysis", "summary": SUMMARY},
        FakeTools([_df()]),
    )
    assert resp["summary"] == SUMMARY
    # The full analysis is NOT replaced by the summary.
    assert resp["insight_text"] == "long analysis"


def test_summary_is_trimmed_and_blank_becomes_none():
    resp = build_response(
        {"mode": "answer", "insight_text": "x", "summary": f"  {SUMMARY}  "},
        FakeTools([_df()]),
    )
    assert resp["summary"] == SUMMARY

    blank = build_response(
        {"mode": "answer", "insight_text": "x", "summary": "   "}, FakeTools([_df()])
    )
    # Whitespace-only must not reach the UI as an empty tinted block.
    assert blank["summary"] is None


def test_missing_summary_is_none_not_derived_from_the_answer():
    """The absence of a summary must never be papered over by extracting one."""
    resp = build_response(
        {"mode": "answer", "insight_text": "Revenue rose 4.4% this month."},
        FakeTools([_df()]),
    )
    assert resp["summary"] is None


def test_non_answer_modes_never_carry_a_summary():
    """An 'In short' takeaway above a question we did NOT answer is exactly the
    false-confidence signal the mode gate exists to remove."""
    for mode in ("clarification", "cannot_answer", "off_topic"):
        resp = build_response(
            {"mode": mode, "insight_text": "I need one detail.", "summary": SUMMARY},
            FakeTools([_df()]),
        )
        assert resp["mode"] == mode
        assert resp["summary"] is None


def test_summary_is_stripped_when_grounding_downgrades_the_mode():
    """mode='answer' with no executed SQL is downgraded to cannot_answer -- the
    summary must be dropped along with the KPIs and confidence badge."""
    resp = build_response(
        {"mode": "answer", "insight_text": "Revenue rose.", "summary": SUMMARY},
        FakeTools([]),  # nothing ran
    )
    assert resp["mode"] == "cannot_answer"
    assert resp["summary"] is None


# --- API contract ------------------------------------------------------------
def test_serializer_exposes_summary():
    out = to_chat_response(
        {
            "mode": "answer",
            "insight_text": "long analysis",
            "summary": SUMMARY,
            "kpis": [],
            "charts": [],
            "table": None,
            "table_title": None,
            "recommended_actions": [],
        }
    )
    assert out.summary == SUMMARY


def test_serializer_defaults_summary_to_none():
    out = to_chat_response(
        {
            "insight_text": "answer",
            "kpis": [],
            "charts": [],
            "table": None,
            "table_title": None,
            "recommended_actions": [],
        }
    )
    assert out.summary is None


# --- durability / backward compatibility -------------------------------------
def test_summary_survives_a_payload_round_trip():
    """Stored conversations keep the rendered ChatResponse as JSON, so reopening
    a chat must restore the same summary."""
    original = ChatResponse(answer="long analysis", summary=SUMMARY)
    restored = ChatResponse.model_validate_json(original.model_dump_json())
    assert restored.summary == SUMMARY


def test_payload_written_before_summary_existed_still_parses():
    """Older stored payloads have no `summary` key at all -- they must remain
    readable rather than making the whole chat unopenable."""
    legacy = '{"answer": "an older stored answer", "kpis": [], "actions": []}'
    restored = ChatResponse.model_validate_json(legacy)
    assert restored.summary is None
    assert restored.answer == "an older stored answer"
