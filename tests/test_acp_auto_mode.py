"""Integration tests for automatic session_mode classification in ACP."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from box_agent.acp import BoxACPAgent
from box_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from box_agent.schema import LLMResponse


class _DummyConn:
    def __init__(self):
        self.updates = []

    async def sessionUpdate(self, payload):
        self.updates.append(payload)


class _TrackingLLM:
    """LLM stub that records classifier vs main-loop calls.

    Behavior:
    - First call (no tools) is treated as the classifier: returns ``mode_label``.
    - Subsequent calls are main-loop turns: return ``end_turn`` with no tools
      so the agent stops after one step.
    """

    def __init__(self, mode_label: str = "general"):
        self.classifier_calls = 0
        self.main_calls = 0
        self._mode_label = mode_label
        self.raise_in_classifier = False

    async def generate(self, messages, tools=None):
        if tools is None:
            self.classifier_calls += 1
            if self.raise_in_classifier:
                raise RuntimeError("classifier boom")
            return LLMResponse(content=self._mode_label, finish_reason="stop")
        self.main_calls += 1
        return LLMResponse(content="ok", finish_reason="stop")

    async def generate_stream(self, messages, tools=None, **_):
        self.main_calls += 1
        from box_agent.schema import StreamEvent
        yield StreamEvent(type="text", delta="ok")
        yield StreamEvent(type="finish", finish_reason="stop")


def _make_agent(tmp_path, llm: _TrackingLLM) -> tuple[BoxACPAgent, _DummyConn]:
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=2, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    conn = _DummyConn()
    agent = BoxACPAgent(conn, config, llm, [], "base system")
    return agent, conn


@pytest.mark.asyncio
async def test_explicit_mode_skips_classifier(tmp_path):
    """Caller-supplied session_mode must bypass auto-classification."""
    llm = _TrackingLLM(mode_label="ppt_outline")
    agent, _ = _make_agent(tmp_path, llm)

    session = await agent.newSession(
        SimpleNamespace(cwd=str(tmp_path), field_meta={"session_mode": "data_analysis"})
    )
    state = agent._sessions[session.sessionId]
    assert state.auto_classify_pending is False
    assert state.session_mode == "data_analysis"

    prompt = SimpleNamespace(
        sessionId=session.sessionId, prompt=[{"text": "show me a chart"}]
    )
    await agent.prompt(prompt)

    assert llm.classifier_calls == 0, "classifier must not run when mode is explicit"
    assert state.session_mode == "data_analysis"


@pytest.mark.asyncio
async def test_missing_mode_ignores_legacy_ppt_classification(tmp_path):
    """No session_mode → legacy PPT labels fall back to the general agent."""
    llm = _TrackingLLM(mode_label="ppt_outline")
    agent, _ = _make_agent(tmp_path, llm)

    session = await agent.newSession(SimpleNamespace(cwd=str(tmp_path)))
    state = agent._sessions[session.sessionId]
    assert state.auto_classify_pending is True
    assert state.session_mode is None

    await agent.prompt(
        SimpleNamespace(
            sessionId=session.sessionId,
            prompt=[{"text": "帮我做个 AI 主题的 PPT 大纲"}],
        )
    )

    assert llm.classifier_calls == 0
    assert state.session_mode is None
    assert state.auto_classify_pending is False
    # Legacy PPT events are not emitted unless the caller explicitly opts in.
    assert "ppt_emit_outline" not in state.agent.tools
    # System message remains general (base prompt was "base system").
    assert state.agent.messages[0].role == "system"


@pytest.mark.asyncio
async def test_classification_runs_only_once(tmp_path):
    """Classifier must not re-run on subsequent turns of the same session."""
    llm = _TrackingLLM(mode_label="data_analysis")
    agent, _ = _make_agent(tmp_path, llm)

    session = await agent.newSession(SimpleNamespace(cwd=str(tmp_path)))

    for msg in ["分析第一个表格", "再看看第二份数据"]:
        await agent.prompt(
            SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": msg}])
        )

    assert llm.classifier_calls == 1
    assert agent._sessions[session.sessionId].session_mode == "data_analysis"


@pytest.mark.asyncio
async def test_classification_failure_falls_back_to_general(tmp_path):
    """Classifier exception must not break the session — falls back to general."""
    llm = _TrackingLLM(mode_label="ppt_outline")
    llm.raise_in_classifier = True
    agent, _ = _make_agent(tmp_path, llm)

    session = await agent.newSession(SimpleNamespace(cwd=str(tmp_path)))
    response = await agent.prompt(
        SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": "hello"}])
    )

    state = agent._sessions[session.sessionId]
    assert state.session_mode is None  # general
    assert state.auto_classify_pending is False
    assert response.stopReason == "end_turn"
    # No PPT tool should have been registered
    assert "ppt_emit_outline" not in state.agent.tools


@pytest.mark.asyncio
async def test_classifier_returns_general_keeps_session_general(tmp_path):
    """Classifier returning 'general' should leave the session unchanged."""
    llm = _TrackingLLM(mode_label="general")
    agent, _ = _make_agent(tmp_path, llm)

    session = await agent.newSession(SimpleNamespace(cwd=str(tmp_path)))
    await agent.prompt(
        SimpleNamespace(sessionId=session.sessionId, prompt=[{"text": "随便聊聊"}])
    )

    state = agent._sessions[session.sessionId]
    assert llm.classifier_calls == 1
    assert state.session_mode is None
    assert state.auto_classify_pending is False
    # System message should still reflect the base prompt (no mode-specific prompt injected)
    assert "base system" in state.agent.messages[0].content


def test_data_analysis_prompt_includes_plot_contract_and_general_prompt_does_not(tmp_path):
    llm = _TrackingLLM(mode_label="general")
    agent, _ = _make_agent(tmp_path, llm)
    agent._system_prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    general_prompt = agent._build_session_prompt("general", workspace=tmp_path)
    analysis_prompt = agent._build_session_prompt("data_analysis", workspace=tmp_path)

    assert "文件交付规则" in general_prompt
    assert "zip -r output.zip" in general_prompt
    assert "Interactive Chart Data Output" not in general_prompt
    assert "<!--PLOT_DATA:" not in general_prompt

    assert "文件交付规则" in analysis_prompt
    assert "Interactive Chart Data Output" in analysis_prompt
    assert "<!--PLOT_DATA:" in analysis_prompt
    assert "sandbox:/mnt/data/<filename>" in analysis_prompt
