"""Integration tests for the Box ACP adapter."""

import json
from types import SimpleNamespace

import pytest

from box_agent.acp import BoxACPAgent, _inject_item_id
from box_agent.config import (
    AgentConfig,
    Config,
    FilesystemPermissions,
    LLMConfig,
    Officev3Config,
    Officev3Paths,
    Officev3Permissions,
    ToolsConfig,
)
from box_agent.memory import MemoryManager
from box_agent.schema import FunctionCall, LLMResponse, StreamEvent, ToolCall
from box_agent.tools.base import Tool, ToolResult
from box_agent.tools.setup import SANDBOX_INFO_PROMPT, build_sandbox_info_prompt


class DummyConn:
    def __init__(self):
        self.updates = []

    async def sessionUpdate(self, payload):
        self.updates.append(payload)


class DummyLLM:
    def __init__(self):
        self.calls = 0

    async def generate(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                thinking="calling echo",
                tool_calls=[
                    ToolCall(
                        id="tool1",
                        type="function",
                        function=FunctionCall(name="echo", arguments={"text": "ping"}),
                    )
                ],
                finish_reason="tool",
            )
        return LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")

    async def generate_stream(self, messages, tools, **_):
        self.calls += 1
        if self.calls == 1:
            yield StreamEvent(type="thinking", delta="calling echo")
            yield StreamEvent(type="text", delta="calling tool")
            yield StreamEvent(
                type="finish",
                finish_reason="tool",
                tool_calls=[
                    ToolCall(
                        id="tool1",
                        type="function",
                        function=FunctionCall(name="echo", arguments={"text": "ping"}),
                    )
                ],
            )
        else:
            yield StreamEvent(type="text", delta="done")
            yield StreamEvent(type="finish", finish_reason="stop")


def test_sandbox_prompt_requires_execute_code_for_explicit_python_results():
    assert "用户要求“用/使用/运行 Python”得到一个具体结果" in SANDBOX_INFO_PROMPT
    assert "必须调用 `execute_code` 返回真实执行结果" in SANDBOX_INFO_PROMPT
    assert "不要只给代码示例" in SANDBOX_INFO_PROMPT


def test_sandbox_prompt_limits_single_execute_code_argument_size():
    assert "每次 `execute_code(code=...)` 控制在 8000 字符以内" in SANDBOX_INFO_PROMPT
    assert "不要把大段内容塞进一个工具参数" in SANDBOX_INFO_PROMPT


def test_project_sandbox_prompt_does_not_point_at_output_dir():
    prompt = build_sandbox_info_prompt(use_output_dir=False)

    assert "当前工作区/代码项目根目录" in prompt
    assert "不要默认创建或使用 `output/`" in prompt
    assert "cwd 已是 `{workspace}/output/`" not in prompt


class TodoLLM:
    def __init__(self):
        self.calls = 0

    async def generate_stream(self, messages, tools, **_):
        self.calls += 1
        if self.calls == 1:
            yield StreamEvent(
                type="finish",
                finish_reason="tool_use",
                tool_calls=[
                    ToolCall(
                        id="todo1",
                        type="function",
                        function=FunctionCall(
                            name="todo_write",
                            arguments={"action": "create", "task": "Plan host integration"},
                        ),
                    )
                ],
            )
        else:
            yield StreamEvent(type="text", delta="done")
            yield StreamEvent(type="finish", finish_reason="stop")

    async def generate(self, messages, tools=None):
        return LLMResponse(content="general", finish_reason="stop")


class PlanLLM:
    def __init__(self):
        self.calls = 0

    async def generate_stream(self, messages, tools, **_):
        self.calls += 1
        if self.calls == 1:
            yield StreamEvent(
                type="finish",
                finish_reason="tool_use",
                tool_calls=[
                    ToolCall(
                        id="plan1",
                        type="function",
                        function=FunctionCall(
                            name="plan_write",
                            arguments={
                                "action": "set",
                                "title": "Plan host integration",
                                "objective": "Render plans separately from todo progress.",
                                "steps": [{"title": "Add plan_snapshot handling"}],
                                "verification": ["Check rawOutput.type"],
                            },
                        ),
                    )
                ],
            )
        else:
            yield StreamEvent(type="text", delta="done")
            yield StreamEvent(type="finish", finish_reason="stop")

    async def generate(self, messages, tools=None):
        return LLMResponse(content="general", finish_reason="stop")


class PlanAfterRetryLLM:
    def __init__(self):
        self.calls = 0

    async def generate_stream(self, messages, tools, **_):
        self.calls += 1
        if self.calls == 1:
            yield StreamEvent(type="text", delta="draft answer")
            yield StreamEvent(type="finish", finish_reason="stop")
        elif self.calls == 2:
            yield StreamEvent(
                type="finish",
                finish_reason="tool_use",
                tool_calls=[
                    ToolCall(
                        id="plan-retry",
                        type="function",
                        function=FunctionCall(
                            name="plan_write",
                            arguments={
                                "action": "set",
                                "title": "Forced host plan",
                                "objective": "Render a full plan after a forced host request.",
                                "steps": [{"title": "Publish plan_write"}],
                            },
                        ),
                    )
                ],
            )
        else:
            yield StreamEvent(type="text", delta="done")
            yield StreamEvent(type="finish", finish_reason="stop")

    async def generate(self, messages, tools=None):
        return LLMResponse(content="general", finish_reason="stop")


class DoneLLM:
    async def generate_stream(self, messages, tools=None, **_):
        yield StreamEvent(type="text", delta="done")
        yield StreamEvent(type="finish", finish_reason="stop")

    async def generate(self, messages, tools=None):
        return LLMResponse(content="done", finish_reason="stop")


class PrematurePptLLM:
    def __init__(self):
        self.calls = 0

    async def generate_stream(self, messages, tools=None, **_):
        self.calls += 1
        if self.calls == 1:
            yield StreamEvent(type="text", delta="现在开始制作 PPT：")
            yield StreamEvent(type="finish", finish_reason="stop")
        elif self.calls == 2:
            yield StreamEvent(
                type="finish",
                finish_reason="tool",
                tool_calls=[
                    ToolCall(
                        id="ppt-write",
                        type="function",
                        function=FunctionCall(
                            name="write_file",
                            arguments={
                                "path": "output/bid-proposal.pptx",
                                "content": "fake pptx payload",
                            },
                        ),
                    )
                ],
            )
        else:
            yield StreamEvent(type="text", delta="PPT 已生成。")
            yield StreamEvent(type="finish", finish_reason="stop")

    async def generate(self, messages, tools=None):
        return LLMResponse(content="done", finish_reason="stop")


class UsageLLM:
    """Mimics the ``LLMClient`` choke point: records usage on each finish.

    Used to verify the per-turn token meter flows into the prompt
    response ``_meta.usage`` without depending on a live provider.
    """

    def __init__(self, per_call_total: int = 30):
        self._per_call_total = per_call_total

    async def generate_stream(self, messages, tools=None, **_):
        from box_agent.llm.token_meter import record_usage
        from box_agent.schema import TokenUsage

        yield StreamEvent(type="text", delta="done")
        usage = TokenUsage(total_tokens=self._per_call_total)
        record_usage(usage)
        yield StreamEvent(type="finish", finish_reason="stop", usage=usage)

    async def generate(self, messages, tools=None):
        return LLMResponse(content="done", finish_reason="stop")


class LongAnswerLLM:
    async def generate_stream(self, messages, tools=None, **_):
        for chunk in ["李白是唐代诗人，" * 20, "他的诗歌想象瑰丽，" * 20, "后世称他为诗仙。"]:
            yield StreamEvent(type="text", delta=chunk)
        yield StreamEvent(type="finish", finish_reason="stop")

    async def generate(self, messages, tools=None):
        return LLMResponse(content="", finish_reason="stop")


class SubAgentLLM:
    def __init__(self):
        self.calls = 0

    async def generate_stream(self, messages, tools, **_):
        self.calls += 1
        if self.calls == 1:
            yield StreamEvent(
                type="finish",
                finish_reason="tool_use",
                tool_calls=[
                    ToolCall(
                        id="sub1",
                        type="function",
                        function=FunctionCall(name="sub_agent", arguments={"task": "Inspect one file", "title": "file probe"}),
                    )
                ],
            )
        elif self.calls == 2:
            yield StreamEvent(
                type="finish",
                finish_reason="tool_use",
                tool_calls=[
                    ToolCall(
                        id="child1",
                        type="function",
                        function=FunctionCall(name="echo", arguments={"text": "child"}),
                    )
                ],
            )
        elif self.calls == 3:
            yield StreamEvent(type="text", delta="child summary")
            yield StreamEvent(type="finish", finish_reason="stop")
        else:
            yield StreamEvent(type="text", delta="parent done")
            yield StreamEvent(type="finish", finish_reason="stop")

    async def generate(self, messages, tools=None):
        return LLMResponse(content="general", finish_reason="stop")


class EchoTool(Tool):
    @property
    def name(self):
        return "echo"

    @property
    def description(self):
        return "Echo helper"

    @property
    def parameters(self):
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, text: str):
        return ToolResult(success=True, content=f"tool:{text}")


class CountingWebSearchTool(Tool):
    def __init__(self):
        self.calls = 0

    @property
    def name(self):
        return "web_search"

    @property
    def description(self):
        return "Searches the web"

    @property
    def parameters(self):
        return {"type": "object", "properties": {"query": {"type": "string"}}}

    async def execute(self, query: str = ""):
        self.calls += 1
        return ToolResult(success=True, content=f"result:{query}")


class WebBudgetLLM:
    def __init__(self):
        self.calls = 0

    async def generate_stream(self, messages, tools=None, **_):
        self.calls += 1
        if self.calls <= 25:
            index = self.calls - 1
            yield StreamEvent(
                type="finish",
                finish_reason="tool",
                tool_calls=[
                    ToolCall(
                        id=f"web-{index}",
                        type="function",
                        function=FunctionCall(name="web_search", arguments={"query": f"q{index}"}),
                    )
                ],
            )
        else:
            yield StreamEvent(type="text", delta="final from gathered evidence")
            yield StreamEvent(type="finish", finish_reason="stop")

    async def generate(self, messages, tools=None):
        return LLMResponse(content="final from gathered evidence", finish_reason="stop")


@pytest.fixture
def acp_agent(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, DummyLLM(), [EchoTool()], "system")
    return agent, conn


@pytest.mark.asyncio
async def test_acp_turn_executes_tool(acp_agent):
    agent, conn = acp_agent
    # Explicit session_mode is consumed at session creation; DummyLLM's first
    # response is consumed by the main agent loop as designed.
    session = await agent.newSession(
        SimpleNamespace(cwd=None, field_meta={"session_mode": "general"})
    )
    prompt = SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": "hello"}])
    response = await agent.prompt(prompt)
    assert response.stopReason == "end_turn"
    assert any("tool:ping" in str(update) for update in conn.updates)
    llm_outputs = [
        update.update.rawOutput
        for update in conn.updates
        if getattr(update.update, "rawOutput", None)
        and isinstance(update.update.rawOutput, dict)
        and update.update.rawOutput.get("type") == "llm_output"
    ]
    assert [item["finish_reason"] for item in llm_outputs] == ["tool", "stop"]
    assert llm_outputs[0]["content"] == "calling tool"
    assert llm_outputs[0]["thinking"] == "calling echo"
    assert llm_outputs[0]["tool_calls"][0]["function"]["name"] == "echo"
    assert llm_outputs[1]["content"] == "done"
    message_chunks = [
        (i, update.update.content.text)
        for i, update in enumerate(conn.updates)
        if getattr(update.update, "sessionUpdate", None) == "agent_message_chunk"
    ]
    assert "calling tool" in [text for _, text in message_chunks]
    tool_index = _first_tool_call_index(conn.updates)
    assert tool_index != -1
    assert next(i for i, text in message_chunks if text == "calling tool") < tool_index
    progress_outputs = [
        update.update.rawOutput
        for update in conn.updates
        if getattr(update.update, "rawOutput", None)
        and isinstance(update.update.rawOutput, dict)
        and update.update.rawOutput.get("type") == "agent_progress"
    ]
    assert progress_outputs == []
    await agent.cancel(SimpleNamespace(sessionId=session.sessionId))
    assert agent._sessions[session.sessionId].cancelled


@pytest.mark.asyncio
async def test_acp_project_artifact_mode_does_not_create_output(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=1, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, DoneLLM(), [], "system {SANDBOX_INFO}")

    session = await agent.newSession(
        SimpleNamespace(cwd=str(tmp_path), field_meta={"artifact_mode": "project"})
    )
    state = agent._sessions[session.sessionId]

    assert not (tmp_path / "output").exists()
    assert state.output_dir is None
    assert state.artifact_mode == "project"
    assert "Do not create or use an `output/` folder" in state.agent.system_prompt
    assert "当前工作区/代码项目根目录" in state.agent.system_prompt
    assert "{SANDBOX_INFO}" not in state.agent.system_prompt
    assert session.field_meta["artifact_mode"] == "project"


@pytest.mark.asyncio
async def test_acp_default_artifact_mode_creates_output(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=1, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, DoneLLM(), [], "system {SANDBOX_INFO}")

    session = await agent.newSession(
        SimpleNamespace(cwd=str(tmp_path), field_meta={"session_mode": "general"})
    )
    state = agent._sessions[session.sessionId]

    assert (tmp_path / "output").is_dir()
    assert state.output_dir == str(tmp_path / "output")
    assert state.artifact_mode == "output"
    assert "cwd 已是 `{workspace}/output/`" in state.agent.system_prompt
    assert session.field_meta is None


@pytest.mark.asyncio
async def test_acp_streams_long_plain_answer_chunks(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=2, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, LongAnswerLLM(), [], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=None, field_meta={"session_mode": "general"})
    )
    response = await agent.prompt(
        SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": "介绍李白"}])
    )

    assert response.stopReason == "end_turn"
    message_chunks = [
        update
        for update in conn.updates
        if getattr(update.update, "sessionUpdate", None) == "agent_message_chunk"
    ]
    assert message_chunks
    streamed_text = "".join(chunk.update.content.text for chunk in message_chunks)
    assert "李白是唐代诗人" in streamed_text
    assert "后世称他为诗仙" in streamed_text


@pytest.mark.asyncio
async def test_acp_marks_injected_message_at_step_boundary(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, DoneLLM(), [], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=None, field_meta={"session_mode": "general"})
    )
    state = agent._sessions[session.sessionId]
    await state.inject_queue.put({"id": "inj-1", "content": "生成10页就可以了"})

    stop_reason = await agent._run_turn(state, session.sessionId)

    assert stop_reason == "end_turn"
    rendered = "\n".join(str(update) for update in conn.updates)
    assert "[Injected:inj-1] 生成10页就可以了" in rendered
    assert "done" in rendered


@pytest.mark.asyncio
async def test_acp_auto_completion_gate_continues_until_ppt_artifact(tmp_path):
    old = tmp_path / "output" / "old.html"
    old.parent.mkdir()
    old.write_text("old")
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=5, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    conn = DummyConn()
    llm = PrematurePptLLM()
    agent = BoxACPAgent(conn, config, llm, [], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=None, field_meta={"session_mode": "general"})
    )
    response = await agent.prompt(
        SimpleNamespace(
            sessionId=session.sessionId,
            prompt=[{"text": "做一份 15 页售前竞标方案 PPT"}],
        )
    )

    assert response.stopReason == "end_turn"
    assert llm.calls == 3
    assert (tmp_path / "output" / "bid-proposal.pptx").read_text() == "fake pptx payload"
    rendered = "\n".join(str(update) for update in conn.updates)
    assert "PPT 已生成" in rendered
    assert "尚未满足完成条件" not in rendered


@pytest.mark.asyncio
async def test_acp_hides_internal_web_search_budget_injection(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=30, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    conn = DummyConn()
    web_search = CountingWebSearchTool()
    agent = BoxACPAgent(conn, config, WebBudgetLLM(), [web_search], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=None, field_meta={"session_mode": "general"})
    )
    state = agent._sessions[session.sessionId]

    stop_reason = await agent._run_turn(state, session.sessionId)

    assert stop_reason == "end_turn"
    assert web_search.calls == 24
    rendered = "\n".join(str(update) for update in conn.updates)
    assert "final from gathered evidence" in rendered
    assert "web_search 调用已达到预算上限" not in rendered
    assert "Tool call budget reached" not in rendered
    assert "Search batch controller update" not in rendered
    assert "[Injected" not in rendered


@pytest.mark.asyncio
async def test_acp_can_cancel_pending_injected_message(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, DoneLLM(), [], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=None, field_meta={"session_mode": "general"})
    )
    state = agent._sessions[session.sessionId]
    state.turn_active = True

    injected = await agent.extMethod(
        "inject",
        {
            "sessionId": session.sessionId,
            "text": "生成10页就可以了",
            "injectionId": "inj-2",
        },
    )
    cancelled = await agent.extMethod(
        "cancel_inject",
        {"sessionId": session.sessionId, "injectionId": "inj-2"},
    )

    assert injected == {"ok": True, "injectionId": "inj-2"}
    assert cancelled == {"ok": True}
    assert state.inject_queue.empty()


@pytest.mark.asyncio
async def test_acp_inject_same_id_is_idempotent(tmp_path):
    """Retrying inject with the same injectionId must not enqueue/run twice."""
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, DoneLLM(), [], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=None, field_meta={"session_mode": "general"})
    )
    state = agent._sessions[session.sessionId]
    state.turn_active = True

    args = {"sessionId": session.sessionId, "text": "只做5页", "injectionId": "dup-1"}

    first = await agent.extMethod("inject", args)
    second = await agent.extMethod("inject", dict(args))  # retry, same id

    assert first == {"ok": True, "injectionId": "dup-1"}
    assert second == {"ok": True, "injectionId": "dup-1", "deduplicated": True}
    # Still exactly one queued item despite two calls.
    assert state.inject_queue.qsize() == 1

    # Even after the item is consumed (drained by the loop), a retry stays deduped.
    consumed = state.inject_queue.get_nowait()
    assert _inject_item_id(consumed) == "dup-1"
    third = await agent.extMethod("inject", dict(args))
    assert third == {"ok": True, "injectionId": "dup-1", "deduplicated": True}
    assert state.inject_queue.empty()

    # An explicit cancel clears the id so the host may deliberately re-inject it.
    await agent.extMethod(
        "cancel_inject",
        {"sessionId": session.sessionId, "injectionId": "dup-1"},
    )
    fourth = await agent.extMethod("inject", dict(args))
    assert fourth == {"ok": True, "injectionId": "dup-1"}
    assert state.inject_queue.qsize() == 1


@pytest.mark.asyncio
async def test_acp_new_session_injects_core_memory_without_returning_it(tmp_path):
    memory_mgr = MemoryManager(memory_dir=str(tmp_path / "memory"))
    memory_mgr.write_core("- User prefers concise Chinese responses\n- User works on officev3")
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path), memory_dir=str(tmp_path / "memory")),
        tools=ToolsConfig(),
    )
    agent = BoxACPAgent(DummyConn(), config, DummyLLM(), [EchoTool()], "system", memory_manager=memory_mgr)

    session = await agent.newSession(
        SimpleNamespace(cwd=None, field_meta={"session_mode": "general"})
    )

    assert session.field_meta is None
    assert "--- MEMORY START ---" in agent._sessions[session.sessionId].agent.system_prompt
    assert "User prefers concise Chinese responses" in agent._sessions[session.sessionId].agent.system_prompt


@pytest.mark.asyncio
async def test_acp_invalid_session(acp_agent):
    """Auto-creates session when sessionId is not found (compatibility)."""
    agent, _ = acp_agent
    # Auto-created sessions without metadata stay on the general prompt. The
    # DummyLLM returns one normal assistant response, so we only check stopReason.
    prompt = SimpleNamespace(sessionId="missing", prompt=[{"text": "?"}])
    response = await agent.prompt(prompt)
    assert response.stopReason == "end_turn"


@pytest.mark.asyncio
async def test_acp_prompt_lists_officev3_allowed_directories(tmp_path):
    allowed = tmp_path / "Documents"
    allowed.mkdir()
    workspace = tmp_path / "workspace"

    officev3 = Officev3Config(
        permissions=Officev3Permissions(
            filesystem=FilesystemPermissions(
                scope="session_workspace",
                allowed_directories=[str(allowed)],
            )
        ),
        paths=Officev3Paths(session_workspace_root=str(tmp_path / "office-raccoon")),
    )
    officev3._present = True
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(workspace)),
        tools=ToolsConfig(),
        officev3=officev3,
    )
    agent = BoxACPAgent(DummyConn(), config, DummyLLM(), [EchoTool()], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=str(workspace), field_meta={"session_mode": "general"})
    )
    prompt = agent._sessions[session.sessionId].agent.system_prompt

    assert "## File Access Context" in prompt
    assert "configured allowed directories are allowed" in prompt
    assert str(allowed) in prompt
    assert "Do not claim you can only access the workspace" in prompt


@pytest.mark.asyncio
async def test_acp_prompt_includes_skill_runtime_context(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    sandbox_base = tmp_path / "sandbox-runtime"
    python_path = sandbox_base / "venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_path.chmod(0o755)

    from box_agent.tools.jupyter_tool import SandboxEnvironment

    monkeypatch.setattr(
        "box_agent.tools.runtime.SandboxEnvironment",
        lambda: SandboxEnvironment(base_dir=sandbox_base),
    )
    monkeypatch.setattr("box_agent.tools.runtime.DEFAULT_NODE_RUNTIME_ROOT", tmp_path / "missing-node")

    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(workspace)),
        tools=ToolsConfig(),
    )
    agent = BoxACPAgent(DummyConn(), config, DummyLLM(), [EchoTool()], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=str(workspace), field_meta={"session_mode": "general"})
    )
    prompt = agent._sessions[session.sessionId].agent.system_prompt

    assert "## Skill Runtime Context" in prompt
    assert "$BOX_AGENT_PYTHON" in prompt
    assert "- Node:" in prompt
    assert "不可用" in prompt
    assert "npm install -g" in prompt
    assert "npx --yes" in prompt

    bash_tool = agent._sessions[session.sessionId].agent.tools["bash"]
    assert bash_tool._subprocess_env["BOX_AGENT_PYTHON"] == str(python_path)
    assert bash_tool._subprocess_env["BOX_AGENT_PYTHON3"] == str(python_path)


@pytest.mark.asyncio
async def test_acp_prompt_and_bash_env_include_self_managed_node_runtime(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    node_root = tmp_path / ".box-agent" / "runtimes" / "node"
    node_bin = node_root / "versions" / "node-v22-test-darwin-arm64" / "bin"
    node = node_bin / "node"
    npm = node_bin / "npm"
    npx = node_bin / "npx"
    for path in (node, npm, npx):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    (node_root / "manifest.json").write_text(
        json.dumps(
            {
                "active": {
                    "version": "v22-test",
                    "node": str(node),
                    "npm": str(npm),
                    "npx": str(npx),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("box_agent.tools.runtime.DEFAULT_NODE_RUNTIME_ROOT", node_root)

    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(workspace)),
        tools=ToolsConfig(),
    )
    agent = BoxACPAgent(DummyConn(), config, DummyLLM(), [EchoTool()], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=str(workspace), field_meta={"session_mode": "general"})
    )
    state = agent._sessions[session.sessionId]
    prompt = state.agent.system_prompt
    bash_tool = state.agent.tools["bash"]

    assert "- Node:" in prompt
    assert "via `$BOX_AGENT_NODE`" in prompt
    assert "box_agent" in prompt
    assert "$BOX_AGENT_NODE" in prompt
    assert bash_tool._subprocess_env["BOX_AGENT_NODE"] == str(node)
    assert bash_tool._subprocess_env["BOX_AGENT_NPM"] == str(npm)
    assert bash_tool._subprocess_env["BOX_AGENT_NPX"] == str(npx)
    assert bash_tool._subprocess_env["NODE_PATH"] == str(node_root / "sandbox" / "node_modules")
    assert bash_tool._subprocess_env["npm_config_cache"] == str(node_root / "sandbox" / "npm-cache")
    assert bash_tool._subprocess_env["npm_config_prefix"] == str(node_root / "sandbox" / "npm-prefix")


@pytest.mark.asyncio
async def test_acp_frozen_mode_still_discovers_self_managed_node_runtime(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    node_root = tmp_path / "node-runtime"
    node_bin = node_root / "versions" / "node-v22-test-darwin-arm64" / "bin"
    node = node_bin / "node"
    npm = node_bin / "npm"
    npx = node_bin / "npx"
    for path in (node, npm, npx):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    (node_root / "manifest.json").write_text(
        json.dumps(
            {
                "active": {
                    "version": "v22-test",
                    "node": str(node),
                    "npm": str(npm),
                    "npx": str(npx),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("box_agent.tools.runtime.DEFAULT_NODE_RUNTIME_ROOT", node_root)
    monkeypatch.setattr("box_agent.tools.runtime.sys.frozen", True, raising=False)
    monkeypatch.setattr("box_agent.tools.setup.sys.frozen", True, raising=False)

    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(workspace)),
        tools=ToolsConfig(),
    )
    agent = BoxACPAgent(DummyConn(), config, DummyLLM(), [EchoTool()], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=str(workspace), field_meta={"session_mode": "general"})
    )
    state = agent._sessions[session.sessionId]

    assert "box_agent" in state.agent.system_prompt
    assert "execute_code" in state.agent.system_prompt or "shell python" in state.agent.system_prompt
    assert state.agent.tools["bash"]._subprocess_env["BOX_AGENT_NODE"] == str(node)


@pytest.mark.asyncio
async def test_acp_host_env_context_feeds_bash_and_execute_code_runtime_env(tmp_path):
    workspace = tmp_path / "workspace"
    python_path = tmp_path / "officev3" / "python" / "python.exe"
    node_path = tmp_path / "officev3" / "node" / "node.exe"
    npm_path = tmp_path / "officev3" / "node" / "npm.cmd"
    npx_path = tmp_path / "officev3" / "node" / "npx.cmd"
    node_modules = tmp_path / "officev3" / "node_modules"
    for runtime_path in (python_path, node_path, npm_path, npx_path):
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        runtime_path.chmod(0o755)
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(workspace)),
        tools=ToolsConfig(),
    )
    agent = BoxACPAgent(DummyConn(), config, DummyLLM(), [EchoTool()], "system")

    env_context = {
        "runtimes": {
            "python": {
                "path": str(python_path),
                "ready": True,
                "provider": "officev3",
            },
            "node": {
                "path": str(node_path),
                "npm": str(npm_path),
                "npx": str(npx_path),
                "node_modules": str(node_modules),
                "ready": True,
                "provider": "officev3",
            },
        }
    }

    session = await agent.newSession(
        SimpleNamespace(
            cwd=str(workspace),
            field_meta={"session_mode": "general", "env_context": env_context},
        )
    )
    state = agent._sessions[session.sessionId]
    bash_env = state.agent.tools["bash"]._subprocess_env
    execute_code_env = state.agent.tools["execute_code"].runtime_env

    assert bash_env["BOX_AGENT_PYTHON"] == str(python_path)
    assert bash_env["BOX_AGENT_SANDBOX_PYTHON"] == str(python_path)
    assert bash_env["BOX_AGENT_NODE"] == str(node_path)
    assert bash_env["BOX_AGENT_NPM"] == str(npm_path)
    assert bash_env["BOX_AGENT_NPX"] == str(npx_path)
    assert bash_env["NODE_PATH"] == str(node_modules)
    assert execute_code_env["BOX_AGENT_SANDBOX_PYTHON"] == str(python_path)


@pytest.mark.asyncio
async def test_acp_emits_todo_snapshot_raw_output(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(enable_sub_agent=False),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, TodoLLM(), [], "system")

    session = await agent.newSession(SimpleNamespace(cwd=None, field_meta={"session_mode": "general"}))
    response = await agent.prompt(SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": "plan"}]))

    assert response.stopReason == "end_turn"
    assert any(
        getattr(update.update, "rawOutput", None)
        and update.update.rawOutput.get("type") == "todo_snapshot"
        and update.update.rawOutput["items"][0]["task"] == "Plan host integration"
        for update in conn.updates
    )


@pytest.mark.asyncio
async def test_acp_emits_plan_snapshot_raw_output(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(enable_sub_agent=False),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, PlanLLM(), [], "system")

    session = await agent.newSession(SimpleNamespace(cwd=None, field_meta={"session_mode": "general"}))
    response = await agent.prompt(
        SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": "开发一个 React 个人介绍网站，先做规划"}])
    )

    assert response.stopReason == "end_turn"
    plan_update_indexes = [
        index
        for index, update in enumerate(conn.updates)
        if getattr(update.update, "rawOutput", None)
        and isinstance(update.update.rawOutput, dict)
        and update.update.rawOutput.get("type") == "plan_snapshot"
    ]
    assert plan_update_indexes
    first_plan_update = conn.updates[plan_update_indexes[0]].update
    first_plan_tool_id = first_plan_update.toolCallId
    assert first_plan_update.status == "completed"
    assert any(
        index < plan_update_indexes[0]
        and getattr(update.update, "sessionUpdate", None) == "tool_call"
        and update.update.toolCallId == first_plan_tool_id
        for index, update in enumerate(conn.updates)
    )
    plan_outputs = [
        update.update.rawOutput
        for update in conn.updates
        if getattr(update.update, "rawOutput", None)
        and isinstance(update.update.rawOutput, dict)
        and update.update.rawOutput.get("type") == "plan_snapshot"
    ]
    assert plan_outputs[0]["action"] == "start"
    assert plan_outputs[0]["plan"]["status"] == "draft"
    assert any(
        output.get("action") == "set"
        and output["plan"]["title"] == "Plan host integration"
        and output["summary"]["steps"] == 1
        for output in plan_outputs
    )


@pytest.mark.asyncio
async def test_acp_prompt_meta_force_plan_start_emits_snapshot_without_trigger(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(enable_sub_agent=False),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, PlanAfterRetryLLM(), [], "system")

    session = await agent.newSession(SimpleNamespace(cwd=None, field_meta={"session_mode": "general"}))
    response = await agent.prompt(
        SimpleNamespace(
            sessionId=session.sessionId,
            prompt=[{"text": "hello"}],
            field_meta={"forcePlanStart": True},
        )
    )

    assert response.stopReason == "end_turn"
    plan_outputs = [
        update.update.rawOutput
        for update in conn.updates
        if getattr(update.update, "rawOutput", None)
        and isinstance(update.update.rawOutput, dict)
        and update.update.rawOutput.get("type") == "plan_snapshot"
    ]
    assert plan_outputs
    assert plan_outputs[0]["action"] == "start"
    assert any(
        output.get("action") == "set"
        and output["plan"]["title"] == "Forced host plan"
        for output in plan_outputs
    )


@pytest.mark.asyncio
async def test_acp_sub_agent_progress_has_stable_grouping_fields(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=5, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(enable_todo=False),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, SubAgentLLM(), [EchoTool()], "system")

    session = await agent.newSession(SimpleNamespace(cwd=None, field_meta={"session_mode": "general"}))
    response = await agent.prompt(SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": "delegate"}]))

    assert response.stopReason == "end_turn"
    progress = [
        update.update.rawOutput
        for update in conn.updates
        if getattr(update.update, "rawOutput", None)
        and isinstance(update.update.rawOutput, dict)
        and update.update.rawOutput.get("type") == "sub_agent_progress"
    ]
    assert progress
    assert {item["parent_tool_call_id"] for item in progress} == {"sub1"}
    assert all(item["sub_agent_id"].startswith("subagent-") for item in progress)
    assert {item["sub_agent_id"] for item in progress}
    # Short distinct label is forwarded for host-side rendering.
    assert all(item["title"] == "file probe" for item in progress)
    assert any(item["event"] == "tool_start" and item["tool_name"] == "echo" for item in progress)
    assert any(item["event"] == "llm_output" and item["content"] == "child summary" for item in progress)


@pytest.mark.asyncio
async def test_acp_prompt_response_reports_turn_token_total(tmp_path):
    """The prompt response carries the per-turn token total in _meta.usage."""
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(enable_todo=False),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, UsageLLM(per_call_total=30), [EchoTool()], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=None, field_meta={"session_mode": "general"})
    )
    response = await agent.prompt(
        SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": "hello"}])
    )

    assert response.stopReason == "end_turn"
    assert response.field_meta == {"usage": {"totalTokens": 30}}


@pytest.mark.asyncio
async def test_acp_token_meter_resets_between_turns(tmp_path):
    """Each turn reports only its own tokens, not a cumulative running sum."""
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(enable_todo=False),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, UsageLLM(per_call_total=25), [EchoTool()], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=None, field_meta={"session_mode": "general"})
    )
    first = await agent.prompt(
        SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": "one"}])
    )
    second = await agent.prompt(
        SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": "two"}])
    )

    assert first.field_meta == {"usage": {"totalTokens": 25}}
    assert second.field_meta == {"usage": {"totalTokens": 25}}


class SpeakThenToolLLM:
    """Emits a short visible preface before any tool."""

    async def generate_stream(self, messages, tools, **_):
        if not getattr(self, "_spoke", False):
            self._spoke = True
            yield StreamEvent(type="text", delta="我先打开页面检查一下。")
            yield StreamEvent(
                type="finish",
                finish_reason="tool",
                tool_calls=[
                    ToolCall(
                        id="tool1",
                        type="function",
                        function=FunctionCall(name="echo", arguments={"text": "ping"}),
                    )
                ],
            )
        else:
            yield StreamEvent(type="text", delta="done")
            yield StreamEvent(type="finish", finish_reason="stop")

    async def generate(self, messages, tools=None):
        return LLMResponse(content="done", finish_reason="stop")


def _first_tool_call_index(updates):
    for i, update in enumerate(updates):
        if getattr(update.update, "sessionUpdate", None) == "tool_call":
            return i
    return -1


@pytest.mark.asyncio
async def test_acp_streams_short_model_preface_before_tool(tmp_path):
    """Short model-authored pre-tool text is streamed before the tool call."""
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(enable_todo=False, enable_sub_agent=False),
    )
    conn = DummyConn()
    agent = BoxACPAgent(conn, config, SpeakThenToolLLM(), [EchoTool()], "system")

    session = await agent.newSession(
        SimpleNamespace(cwd=None, field_meta={"session_mode": "general"})
    )
    response = await agent.prompt(
        SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": "打开页面"}])
    )

    assert response.stopReason == "end_turn"
    message_chunks = [
        (i, update.update.content.text)
        for i, update in enumerate(conn.updates)
        if getattr(update.update, "sessionUpdate", None) == "agent_message_chunk"
    ]
    preface_index = next(
        i for i, text in message_chunks if text == "我先打开页面检查一下。"
    )
    tool_index = _first_tool_call_index(conn.updates)
    assert tool_index != -1
    assert preface_index < tool_index
