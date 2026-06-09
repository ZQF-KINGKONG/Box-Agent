"""Tests for standalone runtime packaging helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_runtime
from scripts.build_runtime import _relativize_node_manifest


def test_relativize_node_manifest_rewrites_paths_under_node_root(tmp_path: Path) -> None:
    node_root = tmp_path / "box-agent-runtime" / "runtimes" / "node"
    bin_dir = node_root / "versions" / "node-v24-test-darwin-arm64" / "bin"
    bin_dir.mkdir(parents=True)
    manifest = {
        "active": {
            "version": "v24-test",
            "node": str(bin_dir / "node"),
            "npm": str(bin_dir / "npm"),
            "npx": str(bin_dir / "npx"),
            "node_modules": str(node_root / "sandbox" / "node_modules"),
        }
    }
    (node_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    _relativize_node_manifest(node_root)

    active = json.loads((node_root / "manifest.json").read_text(encoding="utf-8"))["active"]
    assert active["node"] == "versions/node-v24-test-darwin-arm64/bin/node"
    assert active["npm"] == "versions/node-v24-test-darwin-arm64/bin/npm"
    assert active["npx"] == "versions/node-v24-test-darwin-arm64/bin/npx"
    assert active["node_modules"] == "sandbox/node_modules"


def test_parse_target_accepts_darwin_x64() -> None:
    assert build_runtime.parse_target("darwin-x64") == ("darwin", "x64")


def test_parse_target_accepts_arch_shortcut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_runtime, "detect_platform", lambda: ("darwin", "arm64"))

    assert build_runtime.parse_target("x64") == ("darwin", "x64")


def test_parse_target_rejects_unsupported_target() -> None:
    with pytest.raises(ValueError, match="Unsupported target"):
        build_runtime.parse_target("darwin-ppc")


def test_require_supported_build_process_allows_matching_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_runtime, "detect_platform", lambda: ("darwin", "x64"))

    build_runtime.require_supported_build_process("darwin", "x64")


def test_require_supported_build_process_allows_macos_arch_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_runtime, "detect_platform", lambda: ("darwin", "arm64"))

    build_runtime.require_supported_build_process("darwin", "x64")


def test_require_supported_build_process_rejects_mismatched_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_runtime, "detect_platform", lambda: ("darwin", "arm64"))

    with pytest.raises(RuntimeError, match="matching target platform"):
        build_runtime.require_supported_build_process("linux", "arm64")


def test_pyinstaller_target_arch_args_maps_darwin_x64() -> None:
    assert build_runtime.pyinstaller_target_arch_args(plat="darwin", arch="x64") == [
        "--target-arch",
        "x86_64",
    ]


def test_pyinstaller_target_arch_args_omits_non_macos() -> None:
    assert build_runtime.pyinstaller_target_arch_args(plat="linux", arch="x64") == []


def test_bundled_stable_runtime_components_default_platforms() -> None:
    assert build_runtime.bundled_stable_runtime_components(
        plat="darwin",
        arch="arm64",
    ) == ()


def test_bundled_stable_runtime_components_empty_for_external_python_mode() -> None:
    assert build_runtime.bundled_stable_runtime_components(
        plat="darwin",
        arch="arm64",
        external_python_sandbox=True,
    ) == ()


def test_pyinstaller_args_keep_bundled_sandbox_by_default() -> None:
    hidden = build_runtime.pyinstaller_hidden_imports()
    collect = build_runtime.pyinstaller_collect_args()
    exclude = build_runtime.pyinstaller_exclude_args()
    collect_pairs = list(zip(collect[0::2], collect[1::2]))

    assert "ipykernel" in hidden
    assert "pandas" in hidden
    assert "pip._internal.cli.main" in hidden
    assert ("--collect-all", "ipykernel") in collect_pairs
    assert ("--collect-submodules", "pandas") in collect_pairs
    assert ("--collect-submodules", "pip") in collect_pairs
    assert exclude == []


def test_pyinstaller_args_drop_sandbox_stack_for_external_python_mode() -> None:
    hidden = build_runtime.pyinstaller_hidden_imports(external_python_sandbox=True)
    collect = build_runtime.pyinstaller_collect_args(external_python_sandbox=True)
    exclude = build_runtime.pyinstaller_exclude_args(external_python_sandbox=True)
    collect_pairs = list(zip(collect[0::2], collect[1::2]))
    exclude_pairs = list(zip(exclude[0::2], exclude[1::2]))

    assert "jupyter_client" in hidden
    assert "box_agent.tools.jupyter_tool" in hidden
    assert "jupyter_core" in hidden
    assert "dateutil" in hidden
    assert "dateutil.parser" in hidden
    assert "ipykernel" not in hidden
    assert "pandas" not in hidden
    assert "pip._internal.cli.main" not in hidden
    assert ("--collect-all", "jupyter_client") in collect_pairs
    assert ("--collect-all", "jupyter_core") in collect_pairs
    assert ("--collect-all", "ipykernel") not in collect_pairs
    assert ("--collect-submodules", "pandas") not in collect_pairs
    assert ("--collect-submodules", "pip") not in collect_pairs
    assert ("--exclude-module", "ipykernel") in exclude_pairs
    assert ("--exclude-module", "pandas") in exclude_pairs
    assert ("--exclude-module", "pip") in exclude_pairs
    assert ("--exclude-module", "jupyter_client") not in exclude_pairs
    assert ("--exclude-module", "dateutil") not in exclude_pairs
