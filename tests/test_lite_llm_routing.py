"""Lite LLM routing: fallback when unconfigured, separate client when present."""

from pathlib import Path

import pytest
import yaml

from box_agent.acp import BoxACPAgent
from box_agent.config import (
    AgentConfig,
    Config,
    LiteLLMConfig,
    LLMConfig,
    ToolsConfig,
)
from box_agent.schema import LLMResponse


class _DummyLLM:
    """Minimal LLMClient stub; only attributes touched by the ACP layer."""

    def __init__(self, label: str):
        self.label = label
        self.provider = "openai"
        self.model = f"model-{label}"
        self.last_messages = None
        self.last_kwargs = None

    async def generate(self, messages, tools=None, **kwargs):
        self.last_messages = messages
        self.last_kwargs = kwargs
        return LLMResponse(
            content=f"reply-from-{self.label}",
            thinking=None,
            tool_calls=None,
            finish_reason="stop",
        )


class _DummyConn:
    async def sessionUpdate(self, payload):
        pass


def _make_agent(tmp_path: Path, *, lite: bool):
    config = Config(
        llm=LLMConfig(api_key="main-key"),
        agent=AgentConfig(max_steps=1, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    main = _DummyLLM("main")
    if lite:
        lite_client = _DummyLLM("lite")
        agent = BoxACPAgent(
            _DummyConn(),
            config,
            main,
            [],
            "system",
            lite_llm=lite_client,
        )
        return agent, main, lite_client
    agent = BoxACPAgent(_DummyConn(), config, main, [], "system")
    return agent, main, main


def test_lite_llm_aliases_main_when_omitted(tmp_path):
    agent, main, lite = _make_agent(tmp_path, lite=False)
    assert agent._lite_llm is main
    assert agent._lite_llm is lite  # same object


def test_lite_llm_distinct_when_provided(tmp_path):
    agent, main, lite = _make_agent(tmp_path, lite=False)
    other = _DummyLLM("other")
    agent2 = BoxACPAgent(
        _DummyConn(),
        agent._config,
        main,
        [],
        "system",
        lite_llm=other,
    )
    assert agent2._llm is main
    assert agent2._lite_llm is other
    assert agent2._lite_llm is not main


@pytest.mark.asyncio
async def test_llm_prompt_routes_to_lite_client(tmp_path):
    agent, main, lite = _make_agent(tmp_path, lite=True)
    result = await agent._llm_prompt({"prompt": "title this"})
    assert "error" not in result
    assert result["text"] == "reply-from-lite"
    assert lite.last_messages is not None
    assert main.last_messages is None  # main untouched


@pytest.mark.asyncio
async def test_llm_prompt_threads_meta_session_id_to_lite_client(tmp_path):
    agent, _main, lite = _make_agent(tmp_path, lite=True)
    result = await agent._llm_prompt({
        "prompt": "title this",
        "_meta": {"session_id": "office-session-1"},
    })

    assert "error" not in result
    assert lite.last_kwargs["session_id"] == "office-session-1"


def test_config_lite_llm_absent_marks_not_present():
    cfg = LiteLLMConfig()
    assert cfg._present is False


def test_config_lite_llm_parses_when_block_present(tmp_path):
    yaml_text = {
        "api_key": "main-key",
        "api_base": "https://api.anthropic.com",
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "lite_llm": {
            "provider": "openai",
            "api_base": "https://api.openai.com/v1",
            "api_key": "lite-key",
            "model": "gpt-4o-mini",
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(yaml_text), encoding="utf-8")
    cfg = Config.from_yaml(config_path)
    assert cfg.lite_llm._present is True
    assert cfg.lite_llm.api_base == "https://api.openai.com/v1"
    assert cfg.lite_llm.api_key == "lite-key"
    assert cfg.lite_llm.model == "gpt-4o-mini"
    assert cfg.lite_llm.provider == "openai"


def test_config_lite_llm_block_absent_keeps_default(tmp_path):
    yaml_text = {
        "api_key": "main-key",
        "api_base": "https://api.anthropic.com",
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(yaml_text), encoding="utf-8")
    cfg = Config.from_yaml(config_path)
    assert cfg.lite_llm._present is False
    assert cfg.lite_llm.api_base == ""


def test_config_lite_llm_requires_api_base(tmp_path):
    yaml_text = {
        "api_key": "main-key",
        "api_base": "https://api.anthropic.com",
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "lite_llm": {"provider": "openai", "api_key": "x", "model": "y"},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(yaml_text), encoding="utf-8")
    with pytest.raises(ValueError, match="lite_llm.api_base"):
        Config.from_yaml(config_path)


def test_lite_llm_default_max_output_tokens():
    cfg = LiteLLMConfig()
    assert cfg.max_output_tokens == 63999


def test_config_lite_llm_max_output_tokens_parsed(tmp_path):
    yaml_text = {
        "api_key": "main-key",
        "api_base": "https://api.anthropic.com",
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "lite_llm": {
            "provider": "openai",
            "api_base": "https://api.openai.com/v1",
            "api_key": "lite-key",
            "model": "gpt-4o-mini",
            "max_output_tokens": 32000,
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(yaml_text), encoding="utf-8")
    cfg = Config.from_yaml(config_path)
    assert cfg.lite_llm.max_output_tokens == 32000


def test_config_lite_llm_max_output_tokens_rejects_ceiling(tmp_path):
    yaml_text = {
        "api_key": "main-key",
        "api_base": "https://api.anthropic.com",
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "lite_llm": {
            "provider": "openai",
            "api_base": "https://api.openai.com/v1",
            "api_key": "lite-key",
            "model": "gpt-4o-mini",
            "max_output_tokens": 65537,
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(yaml_text), encoding="utf-8")
    with pytest.raises(ValueError, match="65536 ceiling"):
        Config.from_yaml(config_path)
