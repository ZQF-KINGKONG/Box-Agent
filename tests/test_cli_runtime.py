"""CLI-mode runtime wiring tests."""

from __future__ import annotations

import json
from pathlib import Path

from box_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from box_agent.tools.runtime import build_skill_runtime_context, build_skill_runtime_prompt
from box_agent.tools.setup import add_workspace_tools


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def test_cli_workspace_tools_receive_self_managed_node_runtime(tmp_path: Path) -> None:
    node_root = tmp_path / ".box-agent" / "runtimes" / "node"
    node_bin = node_root / "versions" / "node-v22-test-darwin-arm64" / "bin"
    node = node_bin / "node"
    npm = node_bin / "npm"
    npx = node_bin / "npx"
    for path in (node, npm, npx):
        _make_executable(path)
    node_root.mkdir(parents=True, exist_ok=True)
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

    runtime_context = build_skill_runtime_context(
        sandbox_mode=False,
        node_runtime_root=node_root,
    )
    tools = []
    add_workspace_tools(
        tools,
        Config(
            llm=LLMConfig(api_key="test-key"),
            agent=AgentConfig(workspace_dir=str(tmp_path / "workspace")),
            tools=ToolsConfig(enable_file_tools=False, enable_todo=False),
        ),
        tmp_path / "workspace",
        sandbox_mode=False,
        output=lambda _msg: None,
        skill_runtime_context=runtime_context,
    )

    bash_tool = next(tool for tool in tools if tool.name == "bash")
    assert bash_tool._subprocess_env["BOX_AGENT_NODE"] == str(node)
    assert bash_tool._subprocess_env["BOX_AGENT_NPM"] == str(npm)
    assert bash_tool._subprocess_env["BOX_AGENT_NPX"] == str(npx)
    assert bash_tool._subprocess_env["NODE_PATH"] == str(node_root / "sandbox" / "node_modules")
    assert bash_tool._subprocess_env["npm_config_cache"] == str(node_root / "sandbox" / "npm-cache")
    assert bash_tool._subprocess_env["npm_config_prefix"] == str(node_root / "sandbox" / "npm-prefix")

    prompt = build_skill_runtime_prompt(runtime_context)
    assert "Node runtime:" in prompt
    assert "available: true" in prompt
    assert "$BOX_AGENT_NODE" in prompt
