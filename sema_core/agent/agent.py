"""
SEMA agent: the reasoning loop.

This is the orchestrator that replaces the old keyword Intent Router. It
runs the back-and-forth between Claude and our tools:

    send question + tool menu -> model asks for a tool -> we run it ->
    send result back -> ... -> model writes its final answer.

Key behaviors:
- If ANTHROPIC_API_KEY is missing, run() returns a clear, friendly response
  ("Claude API key is not configured yet.") instead of crashing. Everything
  else in the app keeps working.
- The `anthropic` package is imported lazily (inside run), so this module
  loads fine even if the package or key are absent -- useful for tests and
  for the missing-key path.
- A hard MAX_ITERATIONS cap prevents runaway loops (cost/time safety).

The final structured response (KPI cards, chart, table, actions) is assembled
in agent/response.py (step 5). For now run() returns the basic response shape
the UI already understands: insight_text + optional table.
"""

from __future__ import annotations

import json
import os
import time

from sema_core.agent.prompts import SYSTEM_PROMPT
from sema_core.agent.response import PRESENT_ANSWER_TOOL, build_response
from sema_core.agent.tools import TOOL_SCHEMAS, AgentTools
from sema_core.client_registry import active_client_id
from sema_core.obs import get_logger, log_event
from sema_core.settings import settings

logger = get_logger("agent")

# The full tool menu the model sees: the three data tools plus the finishing
# present_answer tool (which carries the structured final answer).
ALL_TOOLS = TOOL_SCHEMAS + [PRESENT_ANSWER_TOOL]

# Tunables now live in settings.py (read from env with these defaults):
#   SEMA_MODEL, SEMA_MAX_ITERATIONS, SEMA_MAX_TOKENS, SEMA_MAX_HISTORY_TURNS.
MODEL = settings.anthropic_model
MAX_ITERATIONS = settings.max_iterations      # safety cap on tool-use rounds
MAX_TOKENS = settings.max_tokens              # multi-turn conversations carry more context
MAX_HISTORY_TURNS = settings.max_history_turns  # keep at most the last N turns

# The response dict shape the UI renders (same contract as insight_builder).
NOT_CONFIGURED_MESSAGE = "Claude API key is not configured yet."


def api_key_configured() -> bool:
    """True if an Anthropic API key is present in the environment."""
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _empty_response() -> dict:
    return {
        "insight_text": "",
        "kpis": [],
        "charts": [],
        "table": None,
        "table_title": None,
        "recommended_actions": [],
    }


def _basic_response(insight_text: str, tools: AgentTools) -> dict:
    """Wrap the agent's text (and last result table) in the response dict.

    Step 5 (agent/response.py) will upgrade this with KPI cards, a chart, and
    structured recommended actions. For now we surface the narrative plus the
    most recent query result as a table so the loop is fully testable.
    """
    resp = _empty_response()
    resp["insight_text"] = insight_text
    if tools.results:
        last = tools.results[-1]["df"]
        if last is not None and not last.empty:
            resp["table"] = last.head(15)
            resp["table_title"] = "Query result"
    return resp


def not_configured_response() -> dict:
    resp = _empty_response()
    resp["insight_text"] = NOT_CONFIGURED_MESSAGE
    return resp


def _api_error_class():
    """The anthropic APIError type, or a stand-in when the SDK isn't installed
    (tests inject a fake client, so the import must stay optional)."""
    try:
        from anthropic import APIError

        return APIError
    except ImportError:

        class _NeverRaised(Exception):
            pass

        return _NeverRaised



# Human-readable status per tool name, shown to the user while the loop runs
# (via on_progress). "run_sql" gets a per-call counter appended ("...2").
_TOOL_STATUS = {
    "get_schema": "Reading the database schema",
    "get_semantic_layer": "Consulting the semantic layer",
    "run_sql": "Running query",
}


def run(
    question: str,
    history: list[dict] | None = None,
    client=None,
    request_id: str | None = None,
    on_progress=None,
) -> dict:
    """Answer a business question via the agent loop.

    `history` is the prior conversation in Claude API format (alternating
    user/assistant text turns), so follow-up questions like "break that down
    by category" have context. `client` is injectable for testing; in
    production it's built from the ANTHROPIC_API_KEY. `request_id` correlates
    this run's log line with the API request. `on_progress`, if given, is
    called with a short status string (e.g. "Running query 2") before each
    tool dispatch -- the streaming endpoint uses this to send SSE progress
    events; the non-streaming caller simply doesn't pass it. Returns the
    response dict the UI renders.
    """
    if on_progress is None:
        on_progress = lambda _msg: None  # no-op: identical code path either way
    # Missing-key guard: only relevant when we'd build a real client.
    if client is None and not api_key_configured():
        return not_configured_response()

    if client is None:
        # Imported lazily so this module works without the package installed.
        from anthropic import Anthropic

        # Explicit timeout + retries so a slow/flaky API call can't hang a
        # request indefinitely (defaults live in settings.py).
        client = Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            timeout=settings.anthropic_timeout_s,
            max_retries=settings.anthropic_max_retries,
        )

    tools = AgentTools()

    # Observability counters -- logged once when the run finishes (any exit).
    started = time.perf_counter()
    input_tokens = 0
    output_tokens = 0
    tool_calls = 0
    rounds = 0
    last_stop: str | None = None

    def _finish(resp: dict, outcome: str) -> dict:
        """Emit one structured log line summarizing the run, then return resp."""
        log_event(
            logger,
            "agent_run",
            request_id=request_id,
            client_id=active_client_id(),
            question_len=len(question),
            duration_ms=round((time.perf_counter() - started) * 1000),
            outcome=outcome,
            rounds=rounds,
            tool_calls=tool_calls,
            sql_statements=len(tools.results),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=last_stop,
        )
        return resp

    # Start from the prior turns, capped to the most recent ones so a long
    # session can't blow the context window. History is whole turns (each a
    # user+assistant pair), so slicing an even count keeps it starting on a
    # user message -- which the Claude API requires.
    prior = list(history or [])
    if len(prior) > MAX_HISTORY_TURNS * 2:
        prior = prior[-(MAX_HISTORY_TURNS * 2):]
    messages: list[dict] = prior + [{"role": "user", "content": question}]

    api_error = _api_error_class()

    for _ in range(MAX_ITERATIONS):
        rounds += 1
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=ALL_TOOLS,
                messages=messages,
            )
        except api_error:
            # AI-service failure (overloaded, 5xx, auth): a friendly answer,
            # not the generic error path -- and logged as an availability
            # event, not a code bug.
            logger.exception("Anthropic API error (request_id=%s)", request_id)
            return _finish(
                _basic_response(
                    "The AI service is temporarily unavailable. Please try "
                    "again in a moment.",
                    tools,
                ),
                "api_error",
            )

        # Accumulate token usage + stop_reason for cost/observability logging.
        last_stop = response.stop_reason
        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens += getattr(usage, "input_tokens", 0) or 0
            output_tokens += getattr(usage, "output_tokens", 0) or 0

        if response.stop_reason != "tool_use":
            # The model answered in prose without calling present_answer.
            # Fall back to wrapping that text (still a valid response).
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            return _finish(_basic_response(final_text, tools), "prose_answer")

        # Record the model's turn before acting on it.
        messages.append({"role": "assistant", "content": response.content})

        # If the model called present_answer, that's the finish line: build the
        # structured response and return immediately (no tool result needed).
        for block in response.content:
            if block.type == "tool_use" and block.name == PRESENT_ANSWER_TOOL["name"]:
                tool_calls += 1
                on_progress("Writing the answer")
                return _finish(build_response(block.input, tools), "present_answer")

        # Otherwise run the data tools and send results back for the next turn.
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_calls += 1
                status = _TOOL_STATUS.get(block.name, block.name)
                if block.name == "run_sql":
                    status = f"{status} {len(tools.results) + 1}"
                on_progress(status)
                result = tools.dispatch(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    }
                )
        messages.append({"role": "user", "content": tool_results})

    # Ran out of iterations without a final answer.
    return _finish(
        _basic_response(
            "I wasn't able to finish the analysis within the allowed number of "
            "steps. Please try rephrasing the question.",
            tools,
        ),
        "max_iterations",
    )
