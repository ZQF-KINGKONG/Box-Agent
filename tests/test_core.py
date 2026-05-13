"""Tests for the shared agent execution core (box_agent.core)."""

import asyncio

import pytest

from box_agent.core import _detect_artifacts, run_agent_loop
from box_agent.events import (
    ArtifactEvent,
    ContentEvent,
    DoneEvent,
    ErrorEvent,
    StepEnd,
    StepStart,
    StopReason,
    ThinkingEvent,
    ToolCallResult,
    ToolCallStart,
)
from box_agent.schema import FunctionCall, LLMResponse, Message, StreamEvent, ToolCall
from box_agent.tools.base import Tool, ToolResult
from box_agent.tools.file_tools import EditTool, ReadTool, WriteTool


# ── Helpers ─────────────────────────────────────────────────────


class MockLLM:
    """Deterministic LLM that yields pre-configured responses in order."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self._idx = 0

    async def generate(self, messages, tools=None):
        resp = self._responses[self._idx]
        self._idx += 1
        return resp

    async def generate_stream(self, messages, tools=None, **_):
        resp = self._responses[self._idx]
        self._idx += 1
        if resp.thinking:
            yield StreamEvent(type="thinking", delta=resp.thinking)
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


class RawOutputTool(Tool):
    @property
    def name(self):
        return "raw"

    @property
    def description(self):
        return "Returns a structured raw_output payload"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self):
        return ToolResult(
            success=True,
            content="structured result",
            raw_output={"type": "memory_search", "matched_memories": [{"text": "- remembered"}]},
        )


class ModelContextTool(Tool):
    @property
    def name(self):
        return "model_context"

    @property
    def description(self):
        return "Returns full content plus compact model context"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self):
        return ToolResult(
            success=True,
            content="FULL_VISIBLE_OUTPUT_SECRET",
            model_context="COMPACT_MODEL_CONTEXT",
        )


class FailTool(Tool):
    @property
    def name(self):
        return "fail"

    @property
    def description(self):
        return "Always fails"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        raise RuntimeError("boom")


async def collect(gen) -> list:
    return [ev async for ev in gen]


def _msgs():
    return [
        Message(role="system", content="sys"),
        Message(role="user", content="hi"),
    ]


class MemoryManagerStub:
    def __init__(self, matches):
        self.matches = matches

    def auto_match_context(self, query: str):
        self.query = query
        return self.matches


# ── Tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simple_conversation():
    """No tool calls — should yield StepStart, Content, StepEnd, Done."""
    llm = MockLLM([LLMResponse(content="hello", finish_reason="stop")])
    events = await collect(run_agent_loop(llm=llm, messages=_msgs(), tools={}, max_steps=5))

    types = [type(e) for e in events]
    assert StepStart in types
    assert ContentEvent in types
    assert StepEnd in types
    assert DoneEvent in types

    done = [e for e in events if isinstance(e, DoneEvent)][0]
    assert done.stop_reason == StopReason.END_TURN
    assert done.final_content == "hello"


@pytest.mark.asyncio
async def test_thinking_event():
    """LLM with thinking should yield ThinkingEvent."""
    llm = MockLLM([LLMResponse(content="ok", thinking="let me think", finish_reason="stop")])
    events = await collect(run_agent_loop(llm=llm, messages=_msgs(), tools={}, max_steps=5))

    thinking = [e for e in events if isinstance(e, ThinkingEvent)]
    assert len(thinking) >= 1
    # With streaming, thinking content is in delta events
    thinking_text = "".join(e.content for e in thinking)
    assert "let me think" in thinking_text


@pytest.mark.asyncio
async def test_tool_call_cycle():
    """One tool call then a final response."""
    llm = MockLLM([
        LLMResponse(
            content="calling tool",
            tool_calls=[ToolCall(id="t1", type="function", function=FunctionCall(name="echo", arguments={"text": "ping"}))],
            finish_reason="tool",
        ),
        LLMResponse(content="done", finish_reason="stop"),
    ])
    events = await collect(run_agent_loop(llm=llm, messages=_msgs(), tools={"echo": EchoTool()}, max_steps=5))

    starts = [e for e in events if isinstance(e, ToolCallStart)]
    results = [e for e in events if isinstance(e, ToolCallResult)]
    assert len(starts) == 1
    assert starts[0].tool_name == "echo"
    assert len(results) == 1
    assert results[0].success is True
    assert "echo:ping" in results[0].content


@pytest.mark.asyncio
async def test_tool_result_preserves_raw_output_for_cli_and_hosts():
    llm = MockLLM([
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="t1", type="function", function=FunctionCall(name="raw", arguments={}))],
            finish_reason="tool",
        ),
        LLMResponse(content="done", finish_reason="stop"),
    ])
    events = await collect(run_agent_loop(llm=llm, messages=_msgs(), tools={"raw": RawOutputTool()}, max_steps=5))

    results = [e for e in events if isinstance(e, ToolCallResult)]
    assert len(results) == 1
    assert results[0].raw_output == {
        "type": "memory_search",
        "matched_memories": [{"text": "- remembered"}],
    }


@pytest.mark.asyncio
async def test_tool_model_context_is_used_only_for_message_history():
    msgs = _msgs()
    llm = MockLLM([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="t1",
                    type="function",
                    function=FunctionCall(name="model_context", arguments={}),
                )
            ],
            finish_reason="tool",
        ),
        LLMResponse(content="done", finish_reason="stop"),
    ])
    events = await collect(
        run_agent_loop(
            llm=llm,
            messages=msgs,
            tools={"model_context": ModelContextTool()},
            max_steps=5,
        )
    )

    result = next(e for e in events if isinstance(e, ToolCallResult))
    assert result.content == "FULL_VISIBLE_OUTPUT_SECRET"

    tool_msg = next(m for m in msgs if m.role == "tool")
    assert tool_msg.content == "COMPACT_MODEL_CONTEXT"


@pytest.mark.asyncio
async def test_read_file_artifact_keeps_full_event_but_compacts_model_history(tmp_path):
    marker = "SHOULD_NOT_STAY_IN_MODEL_HISTORY"
    deck = tmp_path / "deck.html"
    deck.write_text(
        "\n".join(["<html>", "<body>"] + [f"<section>slide {i}</section>" for i in range(70)] + [marker, "</body>", "</html>"]),
        encoding="utf-8",
    )
    msgs = _msgs()
    llm = MockLLM([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="t1",
                    type="function",
                    function=FunctionCall(name="read_file", arguments={"path": "deck.html"}),
                )
            ],
            finish_reason="tool",
        ),
        LLMResponse(content="done", finish_reason="stop"),
    ])
    events = await collect(
        run_agent_loop(
            llm=llm,
            messages=msgs,
            tools={"read_file": ReadTool(workspace_dir=str(tmp_path))},
            max_steps=5,
            workspace_dir=str(tmp_path),
        )
    )

    result = next(e for e in events if isinstance(e, ToolCallResult))
    assert marker in result.content

    tool_msg = next(m for m in msgs if m.role == "tool")
    assert "[Full file content omitted from model history]" in tool_msg.content
    assert "deck.html" in tool_msg.content
    assert marker not in tool_msg.content


@pytest.mark.asyncio
async def test_write_file_large_artifact_arguments_are_compacted_in_model_history(tmp_path):
    marker = "SHOULD_NOT_STAY_IN_ASSISTANT_TOOL_ARGS"
    html = "\n".join(
        ["<!doctype html>", "<html>", "<body>"]
        + [f"<section class='slide'>slide {i}</section>" for i in range(80)]
        + [marker, "</body>", "</html>"]
    )
    msgs = _msgs()
    llm = MockLLM([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="t1",
                    type="function",
                    function=FunctionCall(name="write_file", arguments={"path": "deck.html", "content": html}),
                )
            ],
            finish_reason="tool",
        ),
        LLMResponse(content="done", finish_reason="stop"),
    ])

    events = await collect(
        run_agent_loop(
            llm=llm,
            messages=msgs,
            tools={"write_file": WriteTool(workspace_dir=str(tmp_path))},
            max_steps=5,
            workspace_dir=str(tmp_path),
        )
    )

    start = next(e for e in events if isinstance(e, ToolCallStart))
    assert marker in start.arguments["content"]
    assert (tmp_path / "deck.html").read_text(encoding="utf-8") == html

    assistant_msg = next(m for m in msgs if m.role == "assistant" and m.tool_calls)
    stored_args = assistant_msg.tool_calls[0].function.arguments
    assert "[Full tool-call argument omitted from model history]" in stored_args["content"]
    assert "deck.html" in stored_args["content"]
    assert marker not in stored_args["content"]


@pytest.mark.asyncio
async def test_write_file_qa_json_arguments_are_compacted_even_when_small(tmp_path):
    marker = "SHOULD_NOT_STAY_IN_QA_TOOL_ARGS"
    content = f'{{"ok": false, "details": "{marker}"}}'
    msgs = _msgs()
    llm = MockLLM([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="t1",
                    type="function",
                    function=FunctionCall(name="write_file", arguments={"path": "qa.json", "content": content}),
                )
            ],
            finish_reason="tool",
        ),
        LLMResponse(content="done", finish_reason="stop"),
    ])

    await collect(
        run_agent_loop(
            llm=llm,
            messages=msgs,
            tools={"write_file": WriteTool(workspace_dir=str(tmp_path))},
            max_steps=5,
            workspace_dir=str(tmp_path),
        )
    )

    assert (tmp_path / "qa.json").read_text(encoding="utf-8") == content
    assistant_msg = next(m for m in msgs if m.role == "assistant" and m.tool_calls)
    stored_args = assistant_msg.tool_calls[0].function.arguments
    assert "[Full tool-call argument omitted from model history]" in stored_args["content"]
    assert "qa.json" in stored_args["content"]
    assert marker not in stored_args["content"]


@pytest.mark.asyncio
async def test_edit_file_large_artifact_arguments_omit_previews_in_model_history(tmp_path):
    old_marker = "OLD_HTML_SHOULD_NOT_STAY_IN_ASSISTANT_TOOL_ARGS"
    new_marker = "NEW_HTML_SHOULD_NOT_STAY_IN_ASSISTANT_TOOL_ARGS"
    original = "\n".join(
        ["<!doctype html>", "<html>", "<body>"]
        + [f"<section class='slide'>slide {i}</section>" for i in range(80)]
        + [old_marker, "</body>", "</html>"]
    )
    updated = original.replace(old_marker, new_marker)
    (tmp_path / "deck.html").write_text(original, encoding="utf-8")

    msgs = _msgs()
    llm = MockLLM([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="t1",
                    type="function",
                    function=FunctionCall(
                        name="edit_file",
                        arguments={"path": "deck.html", "old_str": original, "new_str": updated},
                    ),
                )
            ],
            finish_reason="tool",
        ),
        LLMResponse(content="done", finish_reason="stop"),
    ])

    events = await collect(
        run_agent_loop(
            llm=llm,
            messages=msgs,
            tools={"edit_file": EditTool(workspace_dir=str(tmp_path))},
            max_steps=5,
            workspace_dir=str(tmp_path),
        )
    )

    start = next(e for e in events if isinstance(e, ToolCallStart))
    assert old_marker in start.arguments["old_str"]
    assert new_marker in start.arguments["new_str"]
    assert (tmp_path / "deck.html").read_text(encoding="utf-8") == updated

    assistant_msg = next(m for m in msgs if m.role == "assistant" and m.tool_calls)
    stored_args = assistant_msg.tool_calls[0].function.arguments
    assert "[Full tool-call argument omitted from model history]" in stored_args["old_str"]
    assert "[Full tool-call argument omitted from model history]" in stored_args["new_str"]
    assert old_marker not in stored_args["old_str"]
    assert new_marker not in stored_args["new_str"]
    assert "Preview first" not in stored_args["old_str"]
    assert "Preview first" not in stored_args["new_str"]


@pytest.mark.asyncio
async def test_auto_memory_match_injects_weak_context_before_llm_call():
    llm = MockLLM([LLMResponse(content="done", finish_reason="stop")])
    messages = _msgs()
    memory = MemoryManagerStub([
        {
            "id": "context:7",
            "source": "context",
            "category": "context",
            "text": "- 科技公司入职培训 PPT 已生成预览。",
        }
    ])

    events = await collect(
        run_agent_loop(llm=llm, messages=messages, tools={}, max_steps=5, memory_manager=memory)
    )

    results = [e for e in events if isinstance(e, ToolCallResult)]
    assert len(results) == 1
    assert results[0].tool_call_id == "memory-auto-match"
    assert results[0].raw_output == {
        "type": "memory_search",
        "trigger": "auto",
        "query": "hi",
        "matched_memories": [
            {
                "id": "context:7",
                "source": "context",
                "category": "context",
                "text": "- 科技公司入职培训 PPT 已生成预览。",
            }
        ],
    }
    user_message = next(msg for msg in messages if msg.role == "user")
    assert "Possibly relevant memory" in user_message.content
    assert "Use them only if they are clearly relevant" in user_message.content
    assert "ignore them and do not assume continuity" in user_message.content


@pytest.mark.asyncio
async def test_unknown_tool():
    """Tool call to non-existent tool yields ToolCallResult(success=False)."""
    llm = MockLLM([
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="t1", type="function", function=FunctionCall(name="nope", arguments={}))],
            finish_reason="tool",
        ),
        LLMResponse(content="ok", finish_reason="stop"),
    ])
    events = await collect(run_agent_loop(llm=llm, messages=_msgs(), tools={"echo": EchoTool()}, max_steps=5))

    results = [e for e in events if isinstance(e, ToolCallResult)]
    assert len(results) == 1
    assert results[0].success is False
    assert "Unknown tool" in (results[0].error or "")


@pytest.mark.asyncio
async def test_tool_exception():
    """Tool that raises should yield ToolCallResult(success=False), not crash."""
    llm = MockLLM([
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="t1", type="function", function=FunctionCall(name="fail", arguments={}))],
            finish_reason="tool",
        ),
        LLMResponse(content="recovered", finish_reason="stop"),
    ])
    events = await collect(run_agent_loop(llm=llm, messages=_msgs(), tools={"fail": FailTool()}, max_steps=5))

    results = [e for e in events if isinstance(e, ToolCallResult)]
    assert len(results) == 1
    assert results[0].success is False
    assert "boom" in (results[0].error or "")


@pytest.mark.asyncio
async def test_cancellation_at_step_start():
    """Cancellation before first LLM call yields Done(CANCELLED)."""
    llm = MockLLM([LLMResponse(content="should not reach", finish_reason="stop")])
    events = await collect(
        run_agent_loop(llm=llm, messages=_msgs(), tools={}, max_steps=5, is_cancelled=lambda: True)
    )

    done = [e for e in events if isinstance(e, DoneEvent)]
    assert len(done) == 1
    assert done[0].stop_reason == StopReason.CANCELLED


@pytest.mark.asyncio
async def test_cancellation_after_tool():
    """Cancellation after a tool call stops the loop."""
    tool_executed = []

    class TrackingEchoTool(Tool):
        @property
        def name(self):
            return "echo"

        @property
        def description(self):
            return "Echoes text"

        @property
        def parameters(self):
            return {"type": "object", "properties": {"text": {"type": "string"}}}

        async def execute(self, text: str = ""):
            tool_executed.append(True)
            return ToolResult(success=True, content=f"echo:{text}")

    llm = MockLLM([
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="t1", type="function", function=FunctionCall(name="echo", arguments={"text": "x"}))],
            finish_reason="tool",
        ),
        LLMResponse(content="unreachable", finish_reason="stop"),
    ])
    events = await collect(
        run_agent_loop(
            llm=llm,
            messages=_msgs(),
            tools={"echo": TrackingEchoTool()},
            max_steps=5,
            is_cancelled=lambda: len(tool_executed) > 0,  # cancel once tool has run
        )
    )

    done = [e for e in events if isinstance(e, DoneEvent)]
    assert len(done) == 1
    assert done[0].stop_reason == StopReason.CANCELLED


@pytest.mark.asyncio
async def test_max_steps():
    """Reaching max_steps yields Done(MAX_STEPS)."""
    # Each response has a tool call, so the loop continues
    responses = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id=f"t{i}", type="function", function=FunctionCall(name="echo", arguments={"text": str(i)}))],
            finish_reason="tool",
        )
        for i in range(3)
    ]
    llm = MockLLM(responses)
    events = await collect(
        run_agent_loop(llm=llm, messages=_msgs(), tools={"echo": EchoTool()}, max_steps=3)
    )

    done = [e for e in events if isinstance(e, DoneEvent)]
    assert len(done) == 1
    assert done[0].stop_reason == StopReason.MAX_STEPS


@pytest.mark.asyncio
async def test_llm_error():
    """LLM exception yields ErrorEvent + Done(ERROR)."""

    class FailLLM:
        async def generate(self, messages, tools=None):
            raise ConnectionError("network down")

        async def generate_stream(self, messages, tools=None, **_):
            raise ConnectionError("network down")
            yield  # make it a valid async generator  # noqa: E501

    events = await collect(run_agent_loop(llm=FailLLM(), messages=_msgs(), tools={}, max_steps=5))

    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    assert errors[0].is_fatal
    assert "network down" in errors[0].message

    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done[0].stop_reason == StopReason.ERROR


@pytest.mark.asyncio
async def test_messages_mutated_in_place():
    """Core appends assistant + tool messages to the passed-in list."""
    msgs = _msgs()
    llm = MockLLM([
        LLMResponse(
            content="using tool",
            tool_calls=[ToolCall(id="t1", type="function", function=FunctionCall(name="echo", arguments={"text": "hi"}))],
            finish_reason="tool",
        ),
        LLMResponse(content="done", finish_reason="stop"),
    ])
    await collect(run_agent_loop(llm=llm, messages=msgs, tools={"echo": EchoTool()}, max_steps=5))

    roles = [m.role for m in msgs]
    # system, user, assistant (tool call), tool, assistant (final)
    assert roles == ["system", "user", "assistant", "tool", "assistant"]


# ── Artifact detection tests ─────────────────────────────────


def test_artifact_detect_workspace_root(tmp_path):
    """File at workspace root is found."""
    (tmp_path / "chart.png").write_bytes(b"\x89PNG")
    arts = _detect_artifacts("t1", "jupyter", "Here is the result [chart.png]", str(tmp_path))
    assert len(arts) == 1
    assert arts[0].filename == "chart.png"
    assert arts[0].artifact_type == "image"
    assert arts[0].mime_type == "image/png"
    assert arts[0].size_bytes == 4


def test_artifact_detect_sandbox_session_subdir(tmp_path):
    """File at workspace/sandbox/<session_id>/ is found (Jupyter's actual path)."""
    session_dir = tmp_path / "sandbox" / "abc123"
    session_dir.mkdir(parents=True)
    (session_dir / "output.csv").write_text("a,b\n1,2")
    arts = _detect_artifacts("t2", "jupyter", "Saved to [output.csv]", str(tmp_path))
    assert len(arts) == 1
    assert arts[0].filename == "output.csv"
    assert arts[0].artifact_type == "file"
    assert "csv" in arts[0].mime_type


def test_artifact_detect_no_match(tmp_path):
    """No artifact when file doesn't exist."""
    arts = _detect_artifacts("t3", "jupyter", "See [missing.png]", str(tmp_path))
    assert arts == []


def test_artifact_detect_multiple(tmp_path):
    """Multiple file references in one output."""
    (tmp_path / "a.png").write_bytes(b"\x89PNG")
    (tmp_path / "b.pdf").write_bytes(b"%PDF")
    arts = _detect_artifacts("t4", "jupyter", "Results: [a.png] and [b.pdf]", str(tmp_path))
    assert len(arts) == 2
    names = {a.filename for a in arts}
    assert names == {"a.png", "b.pdf"}


# ── Micro-compact tests ──────────────────────────────────────────


from box_agent.core import _micro_compact, _KEEP_RECENT_TOOL_RESULTS, _MIN_COMPACT_LEN


def _make_tool_msg(name: str, content: str, tc_id: str = "tc-0") -> Message:
    return Message(role="tool", content=content, tool_call_id=tc_id, name=name)


def test_micro_compact_no_op_when_few_tool_msgs():
    """Should not compact when tool messages <= KEEP_RECENT."""
    msgs = [
        Message(role="system", content="sys"),
        Message(role="user", content="hi"),
        Message(role="assistant", content="ok"),
        _make_tool_msg("bash", "x" * 500, "tc-1"),
        _make_tool_msg("bash", "y" * 500, "tc-2"),
        _make_tool_msg("bash", "z" * 500, "tc-3"),
    ]
    assert _micro_compact(msgs) == 0
    # Content should be unchanged
    assert msgs[3].content == "x" * 500


def test_micro_compact_replaces_old_tool_results():
    """Old tool results beyond KEEP_RECENT should be compacted."""
    msgs = [
        Message(role="system", content="sys"),
        Message(role="user", content="analyze data"),
        Message(role="assistant", content="calling tools"),
        _make_tool_msg("execute_code", "DataFrame with 1000 rows\n" + "x" * 500, "tc-1"),
        _make_tool_msg("execute_code", "Statistical summary\n" + "y" * 500, "tc-2"),
        Message(role="assistant", content="more analysis"),
        _make_tool_msg("bash", "file list\n" + "z" * 500, "tc-3"),
        _make_tool_msg("execute_code", "Final chart\n" + "w" * 500, "tc-4"),
        _make_tool_msg("read", "recent content\n" + "v" * 500, "tc-5"),
        _make_tool_msg("execute_code", "latest result\n" + "u" * 500, "tc-6"),
    ]
    # 6 tool messages, keep last 3 → compact first 3
    compacted = _micro_compact(msgs)
    assert compacted == 3

    # First 3 tool messages should be compacted
    assert msgs[3].content.startswith("[Previous result from execute_code:")
    assert msgs[4].content.startswith("[Previous result from execute_code:")
    assert msgs[6].content.startswith("[Previous result from bash:")

    # Last 3 tool messages should be intact
    assert msgs[7].content.startswith("Final chart")
    assert msgs[8].content.startswith("recent content")
    assert msgs[9].content.startswith("latest result")


def test_micro_compact_preserves_short_content():
    """Tool results shorter than MIN_COMPACT_LEN should not be compacted."""
    msgs = [
        Message(role="system", content="sys"),
        _make_tool_msg("bash", "short", "tc-1"),  # short, should be skipped
        _make_tool_msg("execute_code", "x" * 500, "tc-2"),  # long, should be compacted
        _make_tool_msg("bash", "z" * 500, "tc-3"),
        _make_tool_msg("read", "a" * 500, "tc-4"),
        _make_tool_msg("execute_code", "b" * 500, "tc-5"),
    ]
    compacted = _micro_compact(msgs)
    # First 2 are candidates; tc-1 is short so only tc-2 gets compacted
    assert compacted == 1
    assert msgs[1].content == "short"  # preserved
    assert msgs[2].content.startswith("[Previous result from execute_code:")


def test_micro_compact_preserves_tool_call_id():
    """Compacted messages must keep tool_call_id and name for protocol correctness."""
    msgs = [
        Message(role="system", content="sys"),
        _make_tool_msg("bash", "x" * 500, "tc-42"),
        _make_tool_msg("read", "y" * 500, "tc-43"),
        _make_tool_msg("bash", "z" * 500, "tc-44"),
        _make_tool_msg("read", "w" * 500, "tc-45"),
    ]
    _micro_compact(msgs)
    # First message should be compacted but retain metadata
    assert msgs[1].tool_call_id == "tc-42"
    assert msgs[1].name == "bash"


def test_micro_compact_first_line_hint():
    """Compacted placeholder should include the first line as a hint."""
    msgs = [
        Message(role="system", content="sys"),
        _make_tool_msg("execute_code", "Revenue: $1.2M\nRow 1: ...\n" + "x" * 500, "tc-1"),
        _make_tool_msg("bash", "ok", "tc-2"),
        _make_tool_msg("read", "a" * 500, "tc-3"),
        _make_tool_msg("bash", "b" * 500, "tc-4"),
    ]
    _micro_compact(msgs)
    assert "Revenue: $1.2M" in msgs[1].content
