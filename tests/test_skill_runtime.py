"""Tests for skill runtime discovery and prompt rendering."""

from __future__ import annotations

import json
import os
import hashlib
import tarfile
from pathlib import Path

from box_agent.acp.env_context import EnvContext
from box_agent.tools.jupyter_tool import SandboxEnvironment
from box_agent.tools.runtime import (
    DEFAULT_NODE_VERSION,
    NodeRuntimeInstallError,
    NodeRuntimeManager,
    DEFAULT_NODE_RUNTIME_ROOT,
    build_skill_runtime_context,
    build_skill_runtime_prompt,
)


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def _write_node_manifest(root: Path, *, node: Path, npm: Path, npx: Path, node_modules: Path | None = None) -> None:
    active = {
        "version": "v22.99.0-test",
        "node": str(node),
        "npm": str(npm),
        "npx": str(npx),
    }
    if node_modules is not None:
        active["node_modules"] = str(node_modules)
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps({"active": active}), encoding="utf-8")


def _make_node_archive(tmp_path: Path, *, version: str = DEFAULT_NODE_VERSION, platform_id: str = "darwin-arm64") -> tuple[Path, str]:
    archive_root = tmp_path / f"node-{version}-{platform_id}"
    for name in ("node", "npm", "npx"):
        _make_executable(archive_root / "bin" / name)
    archive_path = tmp_path / f"{archive_root.name}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(archive_root, arcname=archive_root.name)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    return archive_path, digest


def _fake_node_downloader(*, archive: Path, checksum: str, archive_name: str, calls: list[str] | None = None):
    def _download(url: str, dest: Path) -> None:
        if calls is not None:
            calls.append(url)
        if url.endswith(archive_name):
            dest.write_bytes(archive.read_bytes())
            return
        if url.endswith("SHASUMS256.txt"):
            dest.write_text(f"{checksum}  {archive_name}\n", encoding="utf-8")
            return
        raise AssertionError(f"unexpected download URL: {url}")

    return _download


def test_python_runtime_uses_existing_sandbox_python(tmp_path: Path) -> None:
    sandbox = SandboxEnvironment(base_dir=tmp_path)
    _make_executable(sandbox.python_path)

    ctx = build_skill_runtime_context(
        sandbox_mode=True,
        sandbox_env=sandbox,
        node_runtime_root=tmp_path / "missing-node",
    )
    python = ctx.get("python")

    assert python.status == "available"
    assert python.provider == "box_agent"
    assert python.executable_path == str(sandbox.python_path)
    assert ctx.env()["BOX_AGENT_PYTHON"] == str(sandbox.python_path)
    assert ctx.env()["BOX_AGENT_PYTHON3"] == str(sandbox.python_path)


def test_frozen_python_runtime_does_not_inject_fake_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("box_agent.tools.runtime.sys.frozen", True, raising=False)

    ctx = build_skill_runtime_context(sandbox_mode=True, node_runtime_root=tmp_path / "missing-node")
    python = ctx.get("python")

    assert python.status == "unavailable"
    assert "BOX_AGENT_PYTHON" not in ctx.env()
    assert "BOX_AGENT_PYTHON3" not in ctx.env()


def test_node_runtime_defaults_missing(tmp_path: Path) -> None:
    ctx = build_skill_runtime_context(sandbox_mode=False, node_runtime_root=tmp_path / "missing-node")
    node = ctx.get("node")

    assert node.status == "missing"
    assert node.provider == "missing"
    assert "BOX_AGENT_NODE" not in ctx.env()


def test_default_node_runtime_root_is_separate_from_python_dirs() -> None:
    assert DEFAULT_NODE_RUNTIME_ROOT == Path.home() / ".box-agent" / "runtimes" / "node"
    assert DEFAULT_NODE_RUNTIME_ROOT != Path.home() / ".box-agent" / "sandbox"
    assert DEFAULT_NODE_RUNTIME_ROOT != Path.home() / ".box-agent" / "runtime-packages"


def test_self_managed_node_runtime_from_manifest(tmp_path: Path) -> None:
    root = tmp_path / ".box-agent" / "runtimes" / "node"
    version_dir = root / "versions" / "node-v22.99.0-test-darwin-arm64" / "bin"
    node = version_dir / "node"
    npm = version_dir / "npm"
    npx = version_dir / "npx"
    for path in (node, npm, npx):
        _make_executable(path)
    _write_node_manifest(root, node=node, npm=npm, npx=npx)

    ctx = build_skill_runtime_context(sandbox_mode=False, node_runtime_root=root)
    runtime = ctx.get("node")
    env = ctx.env()

    assert runtime.status == "available"
    assert runtime.provider == "box_agent"
    assert runtime.executable_path == str(node)
    assert env["BOX_AGENT_NODE"] == str(node)
    assert env["BOX_AGENT_NPM"] == str(npm)
    assert env["BOX_AGENT_NPX"] == str(npx)
    assert env["NODE_PATH"] == str(root / "sandbox" / "node_modules")
    assert env["npm_config_cache"] == str(root / "sandbox" / "npm-cache")
    assert env["npm_config_prefix"] == str(root / "sandbox" / "npm-prefix")
    assert ".npm" not in env["npm_config_cache"]


def test_self_managed_node_runtime_accepts_relative_manifest_paths(tmp_path: Path) -> None:
    root = tmp_path / "node-runtime"
    version_dir = root / "versions" / "node-v22-test-darwin-arm64" / "bin"
    for name in ("node", "npm", "npx"):
        _make_executable(version_dir / name)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "active": {
                    "version": "v22-test",
                    "node": "versions/node-v22-test-darwin-arm64/bin/node",
                    "npm": "versions/node-v22-test-darwin-arm64/bin/npm",
                    "npx": "versions/node-v22-test-darwin-arm64/bin/npx",
                    "node_modules": "sandbox/node_modules",
                }
            }
        ),
        encoding="utf-8",
    )

    ctx = build_skill_runtime_context(sandbox_mode=False, node_runtime_root=root)

    assert ctx.get("node").status == "available"
    assert ctx.env()["BOX_AGENT_NODE"] == str(version_dir / "node")


def test_frozen_runtime_discovers_bundled_node_and_uses_user_state_dirs(tmp_path: Path, monkeypatch) -> None:
    runtime_dir = tmp_path / "box-agent-runtime"
    exe = runtime_dir / "bin" / "box-agent-acp"
    _make_executable(exe)
    node_root = runtime_dir / "runtimes" / "node"
    version_dir = node_root / "versions" / "node-v22-test-darwin-arm64" / "bin"
    for name in ("node", "npm", "npx"):
        _make_executable(version_dir / name)
    (node_root / "manifest.json").write_text(
        json.dumps(
            {
                "active": {
                    "version": "v22-test",
                    "node": "versions/node-v22-test-darwin-arm64/bin/node",
                    "npm": "versions/node-v22-test-darwin-arm64/bin/npm",
                    "npx": "versions/node-v22-test-darwin-arm64/bin/npx",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("box_agent.tools.runtime.sys.frozen", True, raising=False)
    monkeypatch.setattr("box_agent.tools.runtime.sys.executable", str(exe))

    ctx = build_skill_runtime_context(sandbox_mode=False)
    env = ctx.env()

    assert ctx.get("node").status == "available"
    assert env["BOX_AGENT_NODE"] == str(version_dir / "node")
    assert env["npm_config_cache"] == str(DEFAULT_NODE_RUNTIME_ROOT / "sandbox" / "npm-cache")
    assert env["npm_config_prefix"] == str(DEFAULT_NODE_RUNTIME_ROOT / "sandbox" / "npm-prefix")


def test_install_macos_downloads_verifies_extracts_and_writes_manifest(tmp_path: Path) -> None:
    root = tmp_path / ".box-agent" / "runtimes" / "node"
    archive_name = f"node-{DEFAULT_NODE_VERSION}-darwin-arm64.tar.gz"
    archive, checksum = _make_node_archive(tmp_path, platform_id="darwin-arm64")

    runtime = NodeRuntimeManager(root=root).install_macos(
        platform_id="darwin-arm64",
        downloader=_fake_node_downloader(archive=archive, checksum=checksum, archive_name=archive_name),
    )

    active = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["active"]
    version_dir = root / "versions" / archive_name.removesuffix(".tar.gz")
    assert runtime.status == "available"
    assert runtime.provider == "box_agent"
    assert active["version"] == DEFAULT_NODE_VERSION
    assert active["platform"] == "darwin-arm64"
    assert active["node"] == str(version_dir / "bin" / "node")
    assert active["npm"] == str(version_dir / "bin" / "npm")
    assert active["npx"] == str(version_dir / "bin" / "npx")
    assert runtime.env_vars["BOX_AGENT_NODE"] == active["node"]
    assert not (tmp_path / ".box-agent" / "sandbox").exists()
    assert not (tmp_path / ".box-agent" / "runtime-packages").exists()


def test_install_macos_checksum_mismatch_does_not_write_manifest(tmp_path: Path) -> None:
    root = tmp_path / "node-runtime"
    archive_name = f"node-{DEFAULT_NODE_VERSION}-darwin-arm64.tar.gz"
    archive, _checksum = _make_node_archive(tmp_path, platform_id="darwin-arm64")

    try:
        NodeRuntimeManager(root=root).install_macos(
            platform_id="darwin-arm64",
            downloader=_fake_node_downloader(
                archive=archive,
                checksum="0" * 64,
                archive_name=archive_name,
            ),
        )
    except NodeRuntimeInstallError:
        pass
    else:
        raise AssertionError("checksum mismatch should fail")

    assert not (root / "manifest.json").exists()
    assert not (root / "versions" / archive_name.removesuffix(".tar.gz")).exists()


def test_install_macos_failure_preserves_existing_manifest(tmp_path: Path) -> None:
    root = tmp_path / "node-runtime"
    old_bin = root / "versions" / "old-node" / "bin"
    old_node = old_bin / "node"
    old_npm = old_bin / "npm"
    old_npx = old_bin / "npx"
    for path in (old_node, old_npm, old_npx):
        _make_executable(path)
    _write_node_manifest(root, node=old_node, npm=old_npm, npx=old_npx)
    old_manifest = (root / "manifest.json").read_text(encoding="utf-8")

    archive_name = f"node-{DEFAULT_NODE_VERSION}-darwin-arm64.tar.gz"

    def broken_downloader(url: str, dest: Path) -> None:
        if url.endswith(archive_name):
            dest.write_text("not a tarball", encoding="utf-8")
            return
        dest.write_text(f"{hashlib.sha256(b'not a tarball').hexdigest()}  {archive_name}\n", encoding="utf-8")

    try:
        NodeRuntimeManager(root=root).install_macos(
            platform_id="darwin-arm64",
            downloader=broken_downloader,
        )
    except NodeRuntimeInstallError:
        pass
    else:
        raise AssertionError("broken archive should fail")

    assert (root / "manifest.json").read_text(encoding="utf-8") == old_manifest
    assert NodeRuntimeManager(root=root).discover().env_vars["BOX_AGENT_NODE"] == str(old_node)


def test_install_macos_skips_download_when_version_already_installed(tmp_path: Path) -> None:
    root = tmp_path / "node-runtime"
    archive_name = f"node-{DEFAULT_NODE_VERSION}-darwin-arm64.tar.gz"
    version_dir = root / "versions" / archive_name.removesuffix(".tar.gz")
    for name in ("node", "npm", "npx"):
        _make_executable(version_dir / "bin" / name)
    calls: list[str] = []

    runtime = NodeRuntimeManager(root=root).install_macos(
        platform_id="darwin-arm64",
        downloader=lambda url, dest: calls.append(url),
    )

    assert calls == []
    assert runtime.status == "available"
    assert (root / "manifest.json").exists()


def test_install_macos_rejects_unsupported_platform(tmp_path: Path) -> None:
    try:
        NodeRuntimeManager(root=tmp_path / "node-runtime").install_macos(platform_id="linux-x64")
    except NodeRuntimeInstallError as exc:
        assert "Unsupported macOS Node platform" in str(exc)
    else:
        raise AssertionError("unsupported platform should fail")


def test_install_macos_rejects_tar_path_traversal(tmp_path: Path) -> None:
    root = tmp_path / "node-runtime"
    archive_name = f"node-{DEFAULT_NODE_VERSION}-darwin-arm64.tar.gz"
    archive_path = tmp_path / archive_name
    evil_file = tmp_path / "evil"
    evil_file.write_text("boom", encoding="utf-8")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(evil_file, arcname="../evil")
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()

    try:
        NodeRuntimeManager(root=root).install_macos(
            platform_id="darwin-arm64",
            downloader=_fake_node_downloader(archive=archive_path, checksum=checksum, archive_name=archive_name),
        )
    except NodeRuntimeInstallError as exc:
        assert "Unsafe path" in str(exc)
    else:
        raise AssertionError("unsafe tar path should fail")

    assert not (root / "manifest.json").exists()


def test_self_managed_node_runtime_ignores_unsafe_manifest_paths(tmp_path: Path) -> None:
    root = tmp_path / "node-runtime"
    good = root / "versions" / "node" / "bin" / "node"
    _make_executable(good)
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "active": {
                    "version": "v22.99.0-test",
                    "node": str(good),
                    "npm": "relative/npm",
                    "npx": f"{root}/bin/`npx`",
                }
            }
        ),
        encoding="utf-8",
    )

    ctx = build_skill_runtime_context(sandbox_mode=False, node_runtime_root=root)
    runtime = ctx.get("node")

    assert runtime.status == "unavailable"
    assert runtime.provider == "box_agent"
    assert "BOX_AGENT_NODE" not in ctx.env()


def test_self_managed_node_runtime_rejects_paths_outside_runtime_root(tmp_path: Path) -> None:
    root = tmp_path / ".box-agent" / "runtimes" / "node"
    outside = tmp_path / "system-node"
    node = outside / "node"
    npm = outside / "npm"
    npx = outside / "npx"
    for path in (node, npm, npx):
        _make_executable(path)
    _write_node_manifest(root, node=node, npm=npm, npx=npx)

    ctx = build_skill_runtime_context(sandbox_mode=False, node_runtime_root=root)

    assert ctx.get("node").status == "unavailable"
    assert "BOX_AGENT_NODE" not in ctx.env()


def test_self_managed_node_runtime_does_not_touch_python_runtime_dirs(tmp_path: Path) -> None:
    root = tmp_path / ".box-agent" / "runtimes" / "node"
    node = root / "versions" / "node" / "bin" / "node"
    npm = root / "versions" / "node" / "bin" / "npm"
    npx = root / "versions" / "node" / "bin" / "npx"
    for path in (node, npm, npx):
        _make_executable(path)
    _write_node_manifest(root, node=node, npm=npm, npx=npx)

    build_skill_runtime_context(sandbox_mode=False, node_runtime_root=root)

    assert not (tmp_path / ".box-agent" / "sandbox").exists()
    assert not (tmp_path / ".box-agent" / "runtime-packages").exists()


def test_host_node_runtime_can_be_available() -> None:
    env_context = EnvContext.from_meta(
        {
            "runtimes": {
                "node": {
                    "path": "/opt/node/bin/node",
                    "npm": "/opt/node/bin/npm",
                    "npx": "/opt/node/bin/npx",
                    "node_modules": "/opt/node/lib/node_modules",
                    "ready": True,
                    "provider": "officev3",
                }
            }
        }
    )

    ctx = build_skill_runtime_context(sandbox_mode=False, env_context=env_context)
    env = ctx.env()

    assert ctx.get("node").status == "available"
    assert ctx.get("node").provider == "host"
    assert env["BOX_AGENT_NODE"] == "/opt/node/bin/node"
    assert env["BOX_AGENT_NPM"] == "/opt/node/bin/npm"
    assert env["BOX_AGENT_NPX"] == "/opt/node/bin/npx"
    assert env["NODE_PATH"] == "/opt/node/lib/node_modules"


def test_host_node_runtime_takes_precedence_over_self_managed_node(tmp_path: Path) -> None:
    root = tmp_path / "node-runtime"
    node = root / "versions" / "node" / "bin" / "node"
    npm = root / "versions" / "node" / "bin" / "npm"
    npx = root / "versions" / "node" / "bin" / "npx"
    for path in (node, npm, npx):
        _make_executable(path)
    _write_node_manifest(root, node=node, npm=npm, npx=npx)

    env_context = EnvContext.from_meta(
        {
            "runtimes": {
                "node": {
                    "path": "/opt/host/node",
                    "npm": "/opt/host/npm",
                    "npx": "/opt/host/npx",
                    "ready": True,
                    "provider": "officev3",
                }
            }
        }
    )

    ctx = build_skill_runtime_context(
        sandbox_mode=False,
        env_context=env_context,
        node_runtime_root=root,
    )

    assert ctx.get("node").provider == "host"
    assert ctx.env()["BOX_AGENT_NODE"] == "/opt/host/node"


def test_runtime_prompt_mentions_python_node_and_npm_rules(tmp_path: Path) -> None:
    sandbox = SandboxEnvironment(base_dir=tmp_path)
    _make_executable(sandbox.python_path)

    ctx = build_skill_runtime_context(
        sandbox_mode=True,
        sandbox_env=sandbox,
        node_runtime_root=tmp_path / "missing-node",
    )
    out = build_skill_runtime_prompt(ctx)

    assert "## Skill Runtime Context" in out
    assert "Python runtime:" in out
    assert "available: true" in out
    assert "$BOX_AGENT_PYTHON" in out
    assert "Node runtime:" in out
    assert "available: false" in out
    assert "provider: missing" in out
    assert "unavailable" in out
    assert "npm install -g" in out
    assert "npx --yes" in out
    assert "system `node`, `npm`, `npx`, `python`, or `python3`" in out


def test_runtime_prompt_mentions_available_self_managed_node(tmp_path: Path) -> None:
    root = tmp_path / "node-runtime"
    node = root / "versions" / "node" / "bin" / "node"
    npm = root / "versions" / "node" / "bin" / "npm"
    npx = root / "versions" / "node" / "bin" / "npx"
    for path in (node, npm, npx):
        _make_executable(path)
    _write_node_manifest(root, node=node, npm=npm, npx=npx)

    ctx = build_skill_runtime_context(sandbox_mode=False, node_runtime_root=root)
    out = build_skill_runtime_prompt(ctx)

    assert "Node runtime:" in out
    assert "available: true" in out
    assert "provider: box_agent" in out
    assert "$BOX_AGENT_NODE" in out
    assert "$BOX_AGENT_NPM" in out
    assert "$BOX_AGENT_NPX" in out


def test_runtime_env_only_contains_existing_python_path(tmp_path: Path) -> None:
    sandbox = SandboxEnvironment(base_dir=tmp_path)
    assert not os.path.exists(sandbox.python_path)

    ctx = build_skill_runtime_context(
        sandbox_mode=True,
        sandbox_env=sandbox,
        node_runtime_root=tmp_path / "missing-node",
    )

    assert ctx.get("python").status == "missing"
    assert ctx.env() == {}
