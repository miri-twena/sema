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

from agent.prompts import SYSTEM_PROMPT
from agent.response import PRESENT_ANSWER_TOOL, build_response
from agent.tools import TOOL_SCHEMAS, AgentTools

# The full tool menu the model sees: the three data tools plus the finishing
# present_answer tool (which carries the structured final answer).
ALL_TOOLS = TOOL_SCHEMAS + [PRESENT_ANSWER_TOOL]

MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 8       # safety cap on tool-use rounds
MAX_TOKENS = 4000        # larger: multi-turn conversations carry more context
MAX_HISTORY_TURNS = 10   # keep at most the last 10 turns (20 user/assistant entries)

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


def run(question: str, history: list[dict] | None = None, client=None) -> dict:
    """Answer a business question via the agent loop.

    `history` is the prior conversation in Claude API format (alternating
    user/assistant text turns), so follow-up questions like "break that down
    by category" have context. `client` is injectable for testing; in
    production it's built from the ANTHROPIC_API_KEY. Returns the response
    dict the UI renders.
    """
    # Missing-key guard: only relevant when we'd build a real client.
    if client is None and not api_key_configured():
        return not_configured_response()

    if client is None:
        # Imported lazily so this module works without the package installed.
        from anthropic import Anthropic

        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    tools = AgentTools()
    # Start from the prior turns, capped to the most recent ones so a long
    # session can't blow the context window. History is whole turns (each a
    # user+assistant pair), so slicing an even count keeps it starting on a
    # user message -- which the Claude API requires.
    prior = list(history or [])
    if len(prior) > MAX_HISTORY_TURNS * 2:
        prior = prior[-(MAX_HISTORY_TURNS * 2):]
    messages: list[dict] = prior + [{"role": "user", "content": question}]

    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            # The model answered in prose without calling present_answer.
            # Fall back to wrapping that text (still a valid response).
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            return _basic_response(final_text, tools)

        # Record the model's turn before acting on it.
        messages.append({"role": "assistant", "content": response.content})

        # If the model called present_answer, that's the finish line: build the
        # structured response and return immediately (no tool result needed).
        for block in response.content:
            if block.type == "tool_use" and block.name == PRESENT_ANSWER_TOOL["name"]:
                return build_response(block.input, tools)

        # Otherwise run the data tools and send results back for the next turn.
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
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
    return _basic_response(
        "I wasn't able to finish the analysis within the allowed number of "
        "steps. Please try rephrasing the question.",
        tools,
    )
