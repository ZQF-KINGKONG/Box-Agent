from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import yaml

import box_agent.cli as cli


def _write_config(path: Path, api_key: str = "sk-test-key") -> None:
    path.write_text(
        "\n".join(
            [
                f'api_key: "{api_key}"',
                'api_base: "https://api.openai.com/v1"',
                'model: "gpt-4o"',
                'provider: "openai"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_cmd_config_get_reads_expanded_config_defaults(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    monkeypatch.setattr(cli.Config, "find_config_file", lambda _name: config_path)

    exit_code = cli.cmd_config(get_key="llm.max_output_tokens")

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "63999"


def test_cmd_config_set_bootstraps_and_updates_raw_yaml(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, api_key="YOUR_API_KEY_HERE")
    monkeypatch.setattr(cli.Config, "find_config_file", lambda _name: None)
    monkeypatch.setattr(cli.Config, "_ensure_user_config", lambda: config_path)

    exit_code = cli.cmd_config(set_pair=("api_key", "sk-new-key"))

    assert exit_code == 0
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["api_key"] == "sk-new-key"


def test_cmd_config_set_rolls_back_invalid_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    original = config_path.read_text(encoding="utf-8")
    monkeypatch.setattr(cli.Config, "find_config_file", lambda _name: config_path)

    exit_code = cli.cmd_config(set_pair=("context_window", "not-an-int"))

    assert exit_code == 1
    assert config_path.read_text(encoding="utf-8") == original


def test_cmd_config_json_masks_secret_values(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, api_key="sk-secret-token")
    monkeypatch.setattr(cli.Config, "find_config_file", lambda _name: config_path)

    exit_code = cli.cmd_config(json_output=True)

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["llm"]["api_key"] == "sk-s****oken"


def test_cmd_doctor_json_returns_structured_status(monkeypatch, capsys) -> None:
    async def fake_api_status(_config):
        return cli._doctor_check("ok", "api ok")

    monkeypatch.setattr(cli, "_doctor_config_status", lambda: (cli._doctor_check("ok", "config ok"), object()))
    monkeypatch.setattr(cli, "_doctor_api_status", fake_api_status)
    monkeypatch.setattr(cli, "_doctor_sandbox_status", lambda: cli._doctor_check("ok", "sandbox ok"))
    monkeypatch.setattr(cli, "_doctor_mcp_status", lambda: cli._doctor_check("warning", "mcp missing"))
    monkeypatch.setattr(cli, "_doctor_browser_status", lambda: cli._doctor_check("warning", "browser missing"))
    monkeypatch.setattr(cli, "_doctor_obsidian_status", lambda: cli._doctor_check("warning", "obsidian missing"))

    exit_code = asyncio.run(cli.cmd_doctor(json_output=True))

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["checks"]["api"]["message"] == "api ok"


def test_cmd_doctor_json_returns_nonzero_on_error(monkeypatch, capsys) -> None:
    async def fake_api_status(_config):
        return cli._doctor_check("skipped", "no config")

    monkeypatch.setattr(cli, "_doctor_config_status", lambda: (cli._doctor_check("error", "missing"), None))
    monkeypatch.setattr(cli, "_doctor_api_status", fake_api_status)
    monkeypatch.setattr(cli, "_doctor_sandbox_status", lambda: cli._doctor_check("ok", "sandbox ok"))
    monkeypatch.setattr(cli, "_doctor_mcp_status", lambda: cli._doctor_check("warning", "mcp missing"))
    monkeypatch.setattr(cli, "_doctor_browser_status", lambda: cli._doctor_check("warning", "browser missing"))
    monkeypatch.setattr(cli, "_doctor_obsidian_status", lambda: cli._doctor_check("warning", "obsidian missing"))

    exit_code = asyncio.run(cli.cmd_doctor(json_output=True))

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["checks"]["config"]["status"] == "error"


def test_main_returns_run_agent_exit_code(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    async def fake_run_agent(*args, **kwargs):
        assert args[0] == tmp_path
        assert kwargs["task"] == "do work"
        assert kwargs["verify_api"] is False
        assert kwargs["json_summary"] is True
        assert kwargs["deep_think"] is True
        assert kwargs["force_plan_start"] is True
        assert kwargs["completion_gate_enabled"] is False
        return 7

    monkeypatch.setattr(cli, "parse_args", lambda: argparse.Namespace(
        command=None,
        workspace=str(tmp_path),
        task="do work",
        json=True,
        no_verify_api=True,
        deep_think=True,
        force_plan_start=True,
        no_completion_gate=True,
        no_sandbox=False,
    ))
    monkeypatch.setattr(cli.Config, "_ensure_user_config", lambda: config_path)
    monkeypatch.setattr(
        cli.Config,
        "from_yaml",
        lambda _path: SimpleNamespace(llm=SimpleNamespace(api_key="sk-test-key")),
    )
    monkeypatch.setattr(cli, "run_agent", fake_run_agent)

    assert cli.main() == 7
