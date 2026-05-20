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
