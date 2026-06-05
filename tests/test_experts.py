from types import SimpleNamespace

import pytest

from box_agent.acp import BoxACPAgent
from box_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from box_agent.experts import ExpertSessionContext
from box_agent.schema import LLMResponse, StreamEvent


class DoneLLM:
    async def generate_stream(self, messages, tools=None, **_):
        yield StreamEvent(type="text", delta="done")
        yield StreamEvent(type="finish", finish_reason="stop")

    async def generate(self, messages, tools=None):
        return LLMResponse(content="done", finish_reason="stop")


class DummyConn:
    def __init__(self):
        self.updates = []

    async def sessionUpdate(self, payload):
        self.updates.append(payload)


def test_expert_session_context_parses_camel_and_snake_case() -> None:
    ctx = ExpertSessionContext.from_meta(
        {
            "expert": {
                "id": "researcher",
                "name": "行业研究员",
                "role": "拆解行业问题",
                "defaultSkills": ["web-research", "pptx"],
                "outputFormat": "先给结论，再给证据。",
            },
            "expertTeam": {
                "id": "industry-report",
                "name": "行业研究专家团",
                "executionMode": "orchestrated",
                "members": [
                    {"id": "researcher", "name": "研究员", "default_skills": ["web-research"]},
                    {"id": "analyst", "name": "分析师", "role": "数据核验"},
                ],
                "orchestration": {
                    "trigger": "复杂行业研究任务启用",
                    "stages": [
                        {
                            "id": "briefing",
                            "title": "团长定题",
                            "owner": "researcher",
                            "goal": "明确范围和证据标准",
                            "deliverable": "任务边界",
                        }
                    ],
                    "workstreams": [
                        {
                            "memberId": "researcher",
                            "title": "行业研究线",
                            "brief": "形成市场判断",
                            "deliverable": "核心结论",
                            "required": True,
                        }
                    ],
                    "reviewChecklist": ["事实与推断必须分开"],
                },
                "reviewRules": ["结论必须有证据支撑"],
            },
        }
    )

    assert ctx is not None
    rendered = ctx.render_prompt()
    assert "行业研究员" in rendered
    assert "web-research, pptx" in rendered
    assert "行业研究专家团" in rendered
    assert "Execution mode: orchestrated" in rendered
    assert "Mandatory orchestration protocol" in rendered
    assert "Leader framing" in rendered
    assert "Orchestration contract" in rendered
    assert "团长定题" in rendered
    assert "Delegation task template" in rendered
    assert "Required workstreams for non-trivial tasks: 行业研究线" in rendered
    assert "Visible member-output contract" in rendered
    assert "专家动作" in rendered
    assert "Do not hide member work only in tool progress" in rendered
    assert "Review panel" in rendered
    assert "结论必须有证据支撑" in rendered
    assert ctx.to_metadata()["expert_team"]["execution_mode"] == "orchestrated"
    assert ctx.to_metadata()["expert_team"]["orchestration"]["stage_count"] == 1
    required_workstreams = ctx.to_metadata()["expert_team"]["orchestration"]["required_workstreams"]
    assert required_workstreams[0]["member_id"] == "researcher"


@pytest.mark.asyncio
async def test_acp_session_injects_expert_prompt_and_returns_meta(tmp_path) -> None:
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=2, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(enable_mcp=False),
    )
    agent = BoxACPAgent(DummyConn(), config, DoneLLM(), [], "base system")

    session = await agent.newSession(
        SimpleNamespace(
            cwd=str(tmp_path),
            field_meta={
                "session_mode": "general",
                "expert": {
                    "id": "ppt-designer",
                    "name": "PPT 设计师",
                    "instructions": ["先统一结构，再做页面表达"],
                    "defaultSkills": ["pptx"],
                },
            },
        )
    )

    state = agent._sessions[session.sessionId]
    assert "## Expert Profile" in state.agent.system_prompt
    assert "PPT 设计师" in state.agent.system_prompt
    assert "先统一结构" in state.agent.system_prompt
    assert session.field_meta["expert_context"]["expert"]["id"] == "ppt-designer"
