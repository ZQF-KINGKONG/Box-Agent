"""Regression tests for tool_call/tool_result closure invariants.

Ensures that interrupted, cancelled, or otherwise abnormally-terminated
tool executions still leave the model-facing message history in a state
where every ``assistant.tool_calls[i].id`` is followed by a matching
``role:"tool"`` message — the precondition both OpenAI and Anthropic
APIs enforce on the next request.
"""

from __future__ import annotations

from box_agent.core import _sanitize_dangling_tool_calls
from box_agent.schema import FunctionCall, Message, ToolCall


def _mk_tool_call(tc_id: str, name: str = "noop") -> ToolCall:
    return ToolCall(id=tc_id, type="function", function=FunctionCall(name=name, arguments={}))


def test_sanitize_no_op_when_balanced() -> None:
    messages = [
        Message(role="user", content="hi"),
        Message(
            role="assistant",
            content="",
            tool_calls=[_mk_tool_call("call_a"), _mk_tool_call("call_b")],
        ),
        Message(role="tool", content="ok", tool_call_id="call_a", name="noop"),
        Message(role="tool", content="ok", tool_call_id="call_b", name="noop"),
    ]
    assert _sanitize_dangling_tool_calls(messages) == 0
    assert len(messages) == 4


def test_sanitize_synthesizes_missing_tool_replies() -> None:
    messages = [
        Message(
            role="assistant",
            content="",
            tool_calls=[
                _mk_tool_call("call_a"),
                _mk_tool_call("call_b"),
                _mk_tool_call("call_c"),
                _mk_tool_call("call_d"),
            ],
        ),
        # Only call_a has a response — simulating the SIGKILL-during-gather case
        Message(role="tool", content="ok", tool_call_id="call_a", name="noop"),
    ]
    synthesized = _sanitize_dangling_tool_calls(messages)
    assert synthesized == 3
    tool_ids = [m.tool_call_id for m in messages if m.role == "tool"]
    assert tool_ids == ["call_a", "call_b", "call_c", "call_d"]
    # Stub bodies must be non-empty so providers don't reject the message
    for m in messages:
        if m.role == "tool" and m.tool_call_id != "call_a":
            assert m.content.strip()


def test_sanitize_handles_multiple_assistant_turns() -> None:
    messages = [
        Message(role="assistant", content="", tool_calls=[_mk_tool_call("call_1")]),
        Message(role="tool", content="ok", tool_call_id="call_1", name="noop"),
        Message(role="assistant", content="", tool_calls=[_mk_tool_call("call_2")]),
        # call_2 has no response — interrupted
        Message(role="user", content="follow-up"),
    ]
    synthesized = _sanitize_dangling_tool_calls(messages)
    assert synthesized == 1
    # call_2 stub must be inserted before the user follow-up
    assistant_2_idx = next(
        i for i, m in enumerate(messages)
        if m.role == "assistant" and m.tool_calls and m.tool_calls[0].id == "call_2"
    )
    assert messages[assistant_2_idx + 1].role == "tool"
    assert messages[assistant_2_idx + 1].tool_call_id == "call_2"
