"""Tests for the opt-in completion gate (CompletionGate / run_agent_loop).

The gate is evidence-based: it inspects which tools produced a usable
result and which artifact files exist — never the assistant's wording.
A bounded continuation count plus an optional deadline guarantee the gate
always releases rather than trapping the agent forever.
"""

import pytest

from box_agent.core import run_agent_loop
from box_agent.loop_guards import (
    CompletionGate,
    completion_gate_gaps,
    completion_gate_text,
)
from box_agent.events import DoneEvent, InjectedMessageEvent, StopReason
from box_agent.schema import FunctionCall, LLMResponse, Message, StreamEvent, ToolCall
from box_agent.tools.base import Tool, ToolResult


# ── Helpers ─────────────────────────────────────────────────────


class MockLLM:
    """Deterministic LLM that yields pre-configured responses in order."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self._idx = 0

    async def generate_stream(self, messages, tools=None, **_):
        resp = self._responses[self._idx]
        self._idx += 1
        if resp.content:
            yield StreamEvent(type="text", delta=resp.content)
        yield StreamEvent(
            type="finish",
            finish_reason=resp.finish_reason,
            usage=resp.usage,
            tool_calls=resp.tool_calls,
        )


class EchoTool(Tool):
    @property
    def name(self):
        return "echo"

    @property
    def description(self):
        return "Echoes text back"

    @property
    def parameters(self):
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, text: str = ""):
        return ToolResult(success=True, content=f"echo:{text}")


def _echo_call(call_id: str = "t1"):
    return LLMResponse(
        content="calling tool",
        tool_calls=[
            ToolCall(
                id=call_id,
                type="function",
                function=FunctionCall(name="echo", arguments={"text": "x"}),
            )
        ],
        finish_reason="tool",
    )


def _final(text: str = "done"):
    return LLMResponse(content=text, finish_reason="stop")


def _msgs():
    return [
        Message(role="system", content="sys"),
        Message(role="user", content="hi"),
    ]


async def collect(gen) -> list:
    return [ev async for ev in gen]


def _run(llm, gate, **kw):
    return run_agent_loop(
        llm=llm,
        messages=_msgs(),
        tools={"echo": EchoTool()},
        max_steps=20,
        completion_gate=gate,
        **kw,
    )


# ── Pure-function: _completion_gate_gaps ─────────────────────────


def test_gaps_empty_when_all_requirements_met(tmp_path):
    artifact = tmp_path / "out.txt"
    artifact.write_text("content")
    gate = CompletionGate(
        required_tools=frozenset({"echo"}),
        required_artifacts=("out.txt",),
    )
    gaps = completion_gate_gaps(gate, {"echo"}, str(tmp_path))
    assert gaps == []


def test_gaps_reports_missing_tool():
    gate = CompletionGate(required_tools=frozenset({"echo", "search"}))
    gaps = completion_gate_gaps(gate, {"echo"}, None)
    assert len(gaps) == 1
    assert "search" in gaps[0]


def test_gaps_reports_missing_and_empty_artifact(tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("")  # exists but zero bytes → still a gap
    gate = CompletionGate(required_artifacts=("empty.txt", "missing.txt"))
    gaps = completion_gate_gaps(gate, set(), str(tmp_path))
    assert len(gaps) == 2
    assert any("empty.txt" in g for g in gaps)
    assert any("missing.txt" in g for g in gaps)


def test_gaps_absolute_artifact_path(tmp_path):
    artifact = tmp_path / "abs.txt"
    artifact.write_text("data")
    gate = CompletionGate(required_artifacts=(str(artifact),))
    # workspace_dir is irrelevant for an absolute path
    assert completion_gate_gaps(gate, set(), None) == []


def test_gate_text_lists_each_gap():
    text = completion_gate_text(["缺口A", "缺口B"])
    assert "缺口A" in text and "缺口B" in text


# ── Loop behaviour ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gate_injects_continuation_until_tool_satisfied():
    """Unmet tool requirement → first END_TURN is intercepted; once the tool
    succeeds, the next END_TURN is allowed."""
    gate = CompletionGate(required_tools=frozenset({"echo"}), max_continuations=3)
    # 1) no tool call → gate injects (echo unmet)
    # 2) echo call → success records evidence
    # 3) no tool call → gate satisfied → END_TURN
    llm = MockLLM([_final("premature"), _echo_call(), _final("real done")])
    events = await collect(_run(llm, gate))

    injected = [e for e in events if isinstance(e, InjectedMessageEvent)]
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert len(injected) == 1
    assert "echo" in injected[0].content
    assert len(done) == 1
    assert done[0].stop_reason == StopReason.END_TURN
    assert done[0].final_content == "real done"


@pytest.mark.asyncio
async def test_gate_releases_after_max_continuations():
    """Requirement never met → gate injects exactly max_continuations times,
    then releases and lets the turn end (safety valve)."""
    gate = CompletionGate(required_tools=frozenset({"echo"}), max_continuations=2)
    # All three turns emit no tool call; echo is never satisfied.
    llm = MockLLM([_final("a"), _final("b"), _final("c")])
    events = await collect(_run(llm, gate))

    injected = [e for e in events if isinstance(e, InjectedMessageEvent)]
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert len(injected) == 2  # bounded by max_continuations
    assert len(done) == 1
    assert done[0].stop_reason == StopReason.END_TURN


@pytest.mark.asyncio
async def test_gate_releases_when_deadline_exceeded():
    """deadline_seconds already elapsed → gate releases on the first END_TURN
    even though the requirement is unmet."""
    gate = CompletionGate(
        required_tools=frozenset({"echo"}),
        max_continuations=5,
        deadline_seconds=0.0,  # run_start is in the past → immediately exceeded
    )
    llm = MockLLM([_final("done")])
    events = await collect(_run(llm, gate))

    assert not [e for e in events if isinstance(e, InjectedMessageEvent)]
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert len(done) == 1
    assert done[0].stop_reason == StopReason.END_TURN


@pytest.mark.asyncio
async def test_no_gate_is_unchanged_behaviour():
    """completion_gate=None → first no-tool response ends the turn, no
    injection (regression guard for default behaviour)."""
    llm = MockLLM([_final("done")])
    events = await collect(_run(llm, gate=None))

    assert not [e for e in events if isinstance(e, InjectedMessageEvent)]
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert len(done) == 1
    assert done[0].stop_reason == StopReason.END_TURN
    assert done[0].final_content == "done"


@pytest.mark.asyncio
async def test_gate_satisfied_by_artifact(tmp_path):
    """Requirement satisfied by an artifact the tool writes — gate allows the
    very first END_TURN because the file already exists."""
    artifact = tmp_path / "result.txt"
    artifact.write_text("ready")
    gate = CompletionGate(required_artifacts=("result.txt",))
    llm = MockLLM([_final("done")])
    events = await collect(_run(llm, gate, workspace_dir=str(tmp_path)))

    assert not [e for e in events if isinstance(e, InjectedMessageEvent)]
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done[0].stop_reason == StopReason.END_TURN
