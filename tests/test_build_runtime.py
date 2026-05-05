"""Tests for standalone runtime packaging helpers."""

from __future__ import annotations

import json
from pathlib import Path

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
