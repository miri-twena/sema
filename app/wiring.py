"""
SEMA: request routing (wiring layer).

Decides how a question gets answered, bridging the new LLM agent and the
original rule-based router. Kept separate from main.py so it can be unit
tested without starting Streamlit.

Routing:
  - API key set:    the LLM agent answers. If it errors at runtime, we fall
                    back to the keyword router so the app still responds.
  - API key missing: the 7 known questions still work via the old router
                    (with a visible "agent offline" note); anything else
                    shows "Claude API key is not configured yet."
"""

from __future__ import annotations

import insight_builder
from agent import agent
from query_router import detect_intent

# Shown when we answer via the old rule-based router because the agent is
# offline (no API key), so the user isn't misled into thinking the LLM ran.
FALLBACK_NOTE = (
    "_Showing a built-in report — the Claude agent is offline because no "
    "API key is configured yet._\n\n"
)


def get_response(question: str, history: list[dict] | None = None) -> dict:
    """Return the response dict for a question (agent first, router fallback).

    `history` is the prior conversation (Claude API format) for multi-turn
    follow-ups; it's only used by the agent. The rule-based fallback answers
    each known question standalone, so it ignores history.
    """
    if agent.api_key_configured():
        try:
            return agent.run(question, history=history)
        except Exception:
            pass  # fall through to the rule-based router below

    intent_id = detect_intent(question)
    if intent_id is not None:
        response = insight_builder.build(intent_id)
        if not agent.api_key_configured():
            response = dict(response)
            response["insight_text"] = FALLBACK_NOTE + response["insight_text"]
        return response

    if not agent.api_key_configured():
        return agent.not_configured_response()
    return insight_builder.unsupported_response()
