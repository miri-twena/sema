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
    # build_response cleans every entry into the structured shape (even a
    # bare string the model sent, accepted rather than dropped) -- see
    # response._clean_action.
    assert resp["recommended_actions"] == [
        {"action": "Keep going", "why": None, "expected_impact": None, "effort": None}
    ]
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


# --- fallback visibility ----------------------------------------------------
# The agent must never fail silently: a model failover and a self-corrected
# query each attach a structured `notice` the UI turns into an amber badge.


class FakeAPIError(Exception):
    """Stand-in for anthropic.APIError so the loop's except-branch triggers
    without the SDK installed (agent._api_error_class is monkeypatched to it)."""


class ScriptedClient:
    """Like FakeClient, but an action may be an Exception to RAISE (so we can
    script "primary model errors, backup model answers"). Records the `model`
    each call used, to prove the failover actually switched models."""

    def __init__(self, actions: list):
        self._actions = list(actions)
        self.calls = 0
        self.models: list[str] = []
        self.systems: list = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        self.models.append(kwargs.get("model"))
        self.systems.append(kwargs.get("system"))
        action = self._actions.pop(0) if len(self._actions) > 1 else self._actions[0]
        if isinstance(action, BaseException):
            raise action
        return action


def _present(text: str):
    return _response("tool_use", [_tool_block("present_answer", {"insight_text": text})])


def test_model_failover_attaches_notice(monkeypatch):
    # Primary model API-errors on the first call; the loop retries the same
    # request on FALLBACK_MODEL, which answers -- and the answer discloses it.
    monkeypatch.setattr(agent, "_api_error_class", lambda: FakeAPIError)
    monkeypatch.setattr(agent, "FALLBACK_MODEL", "backup-model")
    fake = ScriptedClient([FakeAPIError("overloaded"), _present("Revenue is up.")])

    resp = agent.run("How is revenue?", client=fake)

    assert resp["insight_text"] == "Revenue is up."
    assert {"kind": "fallback_model"} in resp["notices"]
    # Proof the swap really happened: primary first, backup second.
    assert fake.models == [agent.MODEL, "backup-model"]
    # hebrew_output_quality_prompt.md item 2: the fallback call must carry the
    # SAME system prompt (all language/language-integrity rules included) --
    # verified here, not assumed, since a silently different prompt on the
    # fallback path is exactly how the reported leak could recur unnoticed.
    assert fake.systems[0] == fake.systems[1] == agent.CACHED_SYSTEM


def test_both_models_down_is_unavailable_without_false_notice(monkeypatch):
    # Primary AND backup error -> the friendly unavailable answer, and NO
    # fallback_model badge (nothing actually answered via the backup).
    monkeypatch.setattr(agent, "_api_error_class", lambda: FakeAPIError)
    monkeypatch.setattr(agent, "FALLBACK_MODEL", "backup-model")
    fake = ScriptedClient([FakeAPIError("primary down"), FakeAPIError("backup down")])

    resp = agent.run("How is revenue?", client=fake)

    assert "temporarily unavailable" in resp["insight_text"]
    assert resp["notices"] == []


def test_build_notices_sql_retried():
    # A failed query alongside a successful one = the agent self-corrected.
    tools = SimpleNamespace(
        failures=[{"stage": "execution", "error": "boom"}],
        results=[{"sql": "SELECT 1", "df": None}],
    )
    assert {"kind": "sql_retried", "attempts": 1} in agent._build_notices(tools, False)


def test_build_notices_clean_run_has_none():
    # No failures and no fallback -> no notices (the common, honest case).
    tools = SimpleNamespace(failures=[], results=[{"sql": "SELECT 1", "df": None}])
    assert agent._build_notices(tools, used_fallback_model=False) == []


# --- script-leak guard retry path (hebrew_output_quality_prompt.md) --------


def test_script_leak_is_retried_once_then_the_clean_answer_is_used():
    # First present_answer leaks Arabic into a Hebrew answer; the retried
    # present_answer is clean -- the clean one wins, no degradation.
    fake = ScriptedClient(
        [
            _present("ההכנסות עלו الأسعار השנה"),
            _present("ההכנסות עלו השנה"),
        ]
    )
    resp = agent.run("מה ההכנסות השנה?", client=fake)
    assert resp["insight_text"] == "ההכנסות עלו השנה"
    assert resp["confidence"] != "low"
    assert resp["notices"] == []
    assert fake.calls == 2


def test_script_leak_still_present_after_retry_is_shipped_degraded():
    # Both attempts leak -- the (still-leaky) answer ships anyway rather than
    # being discarded or looped again, but flagged: low confidence + notice.
    fake = ScriptedClient(
        [
            _present("ההכנסות עלו الأسعار השנה"),
            _present("ההכנסות ירדו الأسعار השנה"),
        ]
    )
    resp = agent.run("מה ההכנסות השנה?", client=fake)
    assert resp["insight_text"] == "ההכנסות ירדו الأسعار השנה"
    assert resp["confidence"] == "low"
    assert {"kind": "script_leak"} in resp["notices"]
    assert fake.calls == 2


def test_clean_answer_is_not_retried():
    # The common case -- no leak, no retry, exactly one model call.
    fake = ScriptedClient([_present("ההכנסות עלו השנה")])
    resp = agent.run("מה ההכנסות השנה?", client=fake)
    assert resp["insight_text"] == "ההכנסות עלו השנה"
    assert resp["notices"] == []
    assert fake.calls == 1


def test_arabic_question_gets_arabic_answer_without_a_false_retry():
    # An Arabic-scripted question legitimately gets an Arabic answer -- the
    # guard must not mistake that for a leak and waste a retry on it.
    fake = ScriptedClient([_present("الإيرادات ارتفعت هذا الشهر.")])
    resp = agent.run("ما هي الإيرادات هذا الشهر؟", client=fake)
    assert resp["insight_text"] == "الإيرادات ارتفعت هذا الشهر."
    assert resp["notices"] == []
    assert fake.calls == 1
