"""
Item 10: agent.run with a fake Anthropic client (scripted responses).

No API key, no network, no DB: the fake client returns pre-scripted
"model turns", proving the loop's three exits -- present_answer (happy path),
prose answer, and the max-iterations cap.
"""

from __future__ import annotations

from types import SimpleNamespace

from sema_core.agent import agent


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_block(name: str, tool_input: dict, block_id: str = "tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=block_id)


def _response(stop_reason: str, content: list):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50),
    )


class FakeClient:
    """Plays back scripted responses; repeats the last one if the loop asks again."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def test_happy_path_present_answer():
    fake = FakeClient(
        [
            _response(
                "tool_use",
                [
                    _tool_block(
                        "present_answer",
                        {
                            "insight_text": "Revenue is up 12%.",
                            "recommended_actions": ["Keep going"],
                        },
                    )
                ],
            )
        ]
    )
    resp = agent.run("How is revenue?", client=fake)
    assert resp["insight_text"] == "Revenue is up 12%."
    assert resp["recommended_actions"] == ["Keep going"]
    assert fake.calls == 1


def test_prose_answer_fallback():
    fake = FakeClient([_response("end_turn", [_text_block("Plain prose answer.")])])
    resp = agent.run("Hello", client=fake)
    assert resp["insight_text"] == "Plain prose answer."


def test_max_iterations_cap():
    # The model "asks" for the semantic layer forever (a real, DB-free tool);
    # the loop must stop at MAX_ITERATIONS and return the fallback message.
    fake = FakeClient(
        [_response("tool_use", [_tool_block("get_semantic_layer", {})])]
    )
    resp = agent.run("Loop forever", client=fake)
    assert "wasn't able to finish" in resp["insight_text"]
    assert fake.calls == agent.MAX_ITERATIONS
