from __future__ import annotations

from pathlib import Path

import pytest

import box_agent.agent as agent_module
from box_agent.agent import Agent
from box_agent.events import DoneEvent, StopReason
from box_agent.loop_guards import CompletionGate


class DummyLLM:
    pass


@pytest.mark.asyncio
async def test_agent_run_forwards_core_execution_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    async def fake_run_agent_loop(**kwargs):
        captured.update(kwargs)
        yield DoneEvent(stop_reason=StopReason.END_TURN, final_content="done")

    monkeypatch.setattr(agent_module, "run_agent_loop", fake_run_agent_loop)

    gate = CompletionGate(required_changed_artifact_globs=("output/**/*.md",))
    agent = Agent(
        llm_client=DummyLLM(),
        system_prompt="system",
        tools=[],
        workspace_dir=str(tmp_path),
    )

    result = await agent.run(
        force_plan_start=True,
        completion_gate=gate,
        artifact_detection_enabled=False,
    )

    assert result == "done"
    assert captured["force_plan_start"] is True
    assert captured["completion_gate"] is gate
    assert captured["artifact_detection_enabled"] is False
