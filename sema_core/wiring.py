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

from sema_core import insight_builder
from sema_core.agent import agent
from sema_core.client_registry import active_client_id
from sema_core.obs import get_logger, log_event
from sema_core.query_router import detect_intent

logger = get_logger("wiring")

# Shown when we answer via the old rule-based router because the agent is
# offline (no API key), so the user isn't misled into thinking the LLM ran.
FALLBACK_NOTE = (
    "_Showing a built-in report — the Claude agent is offline because no "
    "API key is configured yet._\n\n"
)


def get_response(
    question: str,
    history: list[dict] | None = None,
    request_id: str | None = None,
    on_progress=None,
    internal_context: str | None = None,
) -> dict:
    """Return the response dict for a question (agent first, router fallback).

    `history` is the prior conversation (Claude API format) for multi-turn
    follow-ups; it's only used by the agent. The rule-based fallback answers
    each known question standalone, so it ignores history and `on_progress`
    (it's instant -- no meaningful progress to report). `request_id`
    correlates this call with the API request's log lines. `internal_context`
    is SERVER-built drill-down framing (never client free text) -- see
    agent.run.
    """
    # True when the agent was configured but crashed, so the router is a
    # DEGRADED path (not the normal no-key path) -- surfaced to the user.
    agent_failed = False
    if agent.api_key_configured():
        try:
            return agent.run(
                question,
                history=history,
                request_id=request_id,
                on_progress=on_progress,
                internal_context=internal_context,
            )
        except Exception:
            # Don't swallow silently: record the traceback AND flag the run so
            # the answer discloses that a built-in report stood in for the agent.
            agent_failed = True
            logger.exception("agent.run failed; falling back to rule-based router (request_id=%s)", request_id)
            log_event(
                logger,
                "fallback",
                request_id=request_id,
                client_id=active_client_id(),
                kind="router",
                reason="agent_exception",
            )

    intent_id = detect_intent(question)
    if intent_id is not None:
        response = dict(insight_builder.build(intent_id))
        if agent_failed:
            # The agent errored: a visible amber badge, not a silent swap.
            response["notices"] = [{"kind": "router_fallback"}]
        elif not agent.api_key_configured():
            response["insight_text"] = FALLBACK_NOTE + response["insight_text"]
        return response

    if not agent.api_key_configured():
        return agent.not_configured_response()
    return insight_builder.unsupported_response()
