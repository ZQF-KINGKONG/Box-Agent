"""Integration tests for the Box ACP adapter."""

import json
from types import SimpleNamespace

import pytest

from box_agent.acp import BoxACPAgent
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
                        function=FunctionCall(name="sub_agent", arguments={"task": "Inspect one file"}),
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
    # Explicit session_mode skips auto-classification so DummyLLM's first
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
    assert llm_outputs[0]["thinking"] == "calling echo"
    assert llm_outputs[0]["tool_calls"][0]["function"]["name"] == "echo"
    assert llm_outputs[1]["content"] == "done"
    await agent.cancel(SimpleNamespace(sessionId=session.sessionId))
    assert agent._sessions[session.sessionId].cancelled


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
    # Provide an explicit mode via the auto-created session by monkeypatching
    # the default newSession call path — not available here, so we instead
    # ensure the DummyLLM is resilient: the classifier's first response is
    # the tool-call one, which parses to no mode → general. The main loop
    # then sees a fresh LLM (second) call returning "done", so there's no
    # tool invocation to assert on. We only check stopReason.
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
    assert "Node runtime:" in prompt
    assert "available: false" in prompt
    assert "provider: missing" in prompt
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

    assert "Node runtime:" in prompt
    assert "available: true" in prompt
    assert "provider: box_agent" in prompt
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

    assert "provider: box_agent" in state.agent.system_prompt
    assert "shell command: unavailable" in state.agent.system_prompt
    assert state.agent.tools["bash"]._subprocess_env["BOX_AGENT_NODE"] == str(node)


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
    assert any(item["event"] == "tool_start" and item["tool_name"] == "echo" for item in progress)
    assert any(item["event"] == "llm_output" and item["content"] == "child summary" for item in progress)
