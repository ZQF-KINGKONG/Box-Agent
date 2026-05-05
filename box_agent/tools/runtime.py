"""Skill runtime discovery and prompt/env rendering."""

from __future__ import annotations

import os
import hashlib
import json
import platform
import shutil
import sys
import tarfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from box_agent.tools.jupyter_tool import SandboxEnvironment

RuntimeKind = Literal["python", "node"]
RuntimeProvider = Literal["box_agent", "host", "missing"]
RuntimeStatus = Literal["available", "missing", "unavailable"]

DEFAULT_NODE_RUNTIME_ROOT = Path.home() / ".box-agent" / "runtimes" / "node"
DEFAULT_NODE_VERSION = "v24.15.0"
NODE_DIST_BASE_URL = "https://nodejs.org/dist"
_MAX_RUNTIME_PATH_LEN = 1024


@dataclass(frozen=True)
class SkillRuntime:
    kind: RuntimeKind
    status: RuntimeStatus
    provider: RuntimeProvider
    executable_path: str | None = None
    env_vars: dict[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.status == "available"


@dataclass(frozen=True)
class SkillRuntimeContext:
    runtimes: dict[RuntimeKind, SkillRuntime]

    def get(self, kind: RuntimeKind) -> SkillRuntime:
        return self.runtimes[kind]

    def env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for runtime in self.runtimes.values():
            env.update(runtime.env_vars)
        return env


def build_skill_runtime_context(
    *,
    sandbox_mode: bool,
    env_context: Any | None = None,
    sandbox_env: SandboxEnvironment | None = None,
    node_runtime_root: Path | None = None,
) -> SkillRuntimeContext:
    """Discover runtimes available to skills for this session."""
    host_runtimes = getattr(env_context, "runtimes", {}) if env_context is not None else {}
    return SkillRuntimeContext(
        runtimes={
            "python": _build_python_runtime(sandbox_mode, host_runtimes, sandbox_env),
            "node": _build_node_runtime(host_runtimes, node_runtime_root=node_runtime_root),
        }
    )


def build_skill_runtime_prompt(ctx: SkillRuntimeContext) -> str:
    """Render runtime facts and rules for the ACP/CLI system prompt."""
    python = ctx.get("python")
    node = ctx.get("node")

    lines = ["## Skill Runtime Context", ""]

    lines.append("Python runtime:")
    lines.append(f"- available: {str(python.available).lower()}")
    lines.append(f"- provider: {python.provider}")
    if python.available:
        lines.append("- command: `$BOX_AGENT_PYTHON`")
        lines.append("- Do not use system `python` or `python3` when `$BOX_AGENT_PYTHON` is available.")
    else:
        lines.append("- shell command: unavailable")
        lines.append("- Python code execution may still be available through `execute_code` when the sandbox tool is present.")
    for note in python.notes:
        lines.append(f"- note: {note}")

    lines.append("")
    lines.append("Node runtime:")
    lines.append(f"- available: {str(node.available).lower()}")
    lines.append(f"- provider: {node.provider}")
    if node.available:
        lines.append("- command: `$BOX_AGENT_NODE`")
        lines.append("- npm command: `$BOX_AGENT_NPM` when listed")
        lines.append("- npx command: `$BOX_AGENT_NPX` when listed")
    else:
        lines.append("- unavailable: `node`, `npm`, and `npx` are not available in this session unless explicitly listed above.")
    for note in node.notes:
        lines.append(f"- note: {note}")

    lines.extend(
        [
            "",
            "Rules:",
            "- Python skills must use `$BOX_AGENT_PYTHON` when it is available.",
            "- Node skills must use `$BOX_AGENT_NODE` only when available.",
            "- If Node runtime is missing, report that the skill requires a Node runtime instead of trying system Node.",
            "- Do not run `npm install -g`.",
            "- Do not run `npx --yes`.",
            "- Do not assume system `node`, `npm`, `npx`, `python`, or `python3`.",
        ]
    )
    return "\n".join(lines)


def _build_python_runtime(
    sandbox_mode: bool,
    host_runtimes: Any,
    sandbox_env: SandboxEnvironment | None,
) -> SkillRuntime:
    host = _runtime(host_runtimes, "python")
    if host is not None and bool(getattr(host, "ready", False)) and getattr(host, "path", None):
        path = str(getattr(host, "path"))
        return SkillRuntime(
            kind="python",
            status="available",
            provider="host",
            executable_path=path,
            env_vars={"BOX_AGENT_PYTHON": path, "BOX_AGENT_PYTHON3": path},
            notes=_host_note(host),
        )

    if not sandbox_mode:
        return SkillRuntime(
            kind="python",
            status="missing",
            provider="missing",
            notes=("No Python runtime is configured for shell skills.",),
        )

    if getattr(sys, "frozen", False):
        return SkillRuntime(
            kind="python",
            status="unavailable",
            provider="box_agent",
            notes=("Frozen runtime has no separate shell Python executable; use execute_code for Python code execution.",),
        )

    env = sandbox_env or SandboxEnvironment()
    python_path = Path(env.python_path)
    if python_path.is_file() and os.access(python_path, os.X_OK):
        path = str(python_path)
        return SkillRuntime(
            kind="python",
            status="available",
            provider="box_agent",
            executable_path=path,
            env_vars={"BOX_AGENT_PYTHON": path, "BOX_AGENT_PYTHON3": path},
        )

    return SkillRuntime(
        kind="python",
        status="missing",
        provider="box_agent",
        notes=("Sandbox venv Python executable does not exist yet; use execute_code for Python code execution.",),
    )


class NodeRuntimeManager:
    """Discover Box-Agent's self-managed Node runtime from a manifest."""

    def __init__(self, root: Path | None = None):
        self.root = (root or _bundled_node_runtime_root() or DEFAULT_NODE_RUNTIME_ROOT).expanduser()
        self.manifest_path = self.root / "manifest.json"
        self.downloads_dir = self.root / "downloads"
        self.versions_dir = self.root / "versions"
        state_root = DEFAULT_NODE_RUNTIME_ROOT if _is_bundled_node_runtime_root(self.root) else self.root
        self.sandbox_dir = state_root / "sandbox"
        self.node_modules_dir = self.sandbox_dir / "node_modules"
        self.npm_cache_dir = self.sandbox_dir / "npm-cache"
        self.npm_prefix_dir = self.sandbox_dir / "npm-prefix"

    def install_macos(
        self,
        *,
        version: str = DEFAULT_NODE_VERSION,
        platform_id: str | None = None,
        downloader: Any | None = None,
        base_url: str = NODE_DIST_BASE_URL,
    ) -> SkillRuntime:
        """Install the pinned official Node.js macOS runtime.

        This only supports Darwin arm64/x64. It downloads the official Node
        archive and SHASUMS256.txt, verifies the archive, extracts into this
        manager's ``versions`` directory, then atomically updates manifest.json.
        """
        target = platform_id or _detect_node_macos_platform()
        if target not in {"darwin-arm64", "darwin-x64"}:
            raise NodeRuntimeInstallError(f"Unsupported macOS Node platform: {target}")
        if not version.startswith("v"):
            raise NodeRuntimeInstallError("Node version must include the leading 'v'.")

        archive_name = f"node-{version}-{target}.tar.gz"
        version_dir = self.versions_dir / archive_name.removesuffix(".tar.gz")
        node = version_dir / "bin" / "node"
        npm = version_dir / "bin" / "npm"
        npx = version_dir / "bin" / "npx"

        if all(_is_executable_file(str(path)) for path in (node, npm, npx)):
            self._write_manifest(
                version=version,
                platform_id=target,
                node=node,
                npm=npm,
                npx=npx,
                node_modules=self.node_modules_dir,
            )
            return self.discover()

        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self.downloads_dir / archive_name
        shasums_path = self.downloads_dir / f"SHASUMS256-{version}.txt"
        version_url = f"{base_url.rstrip('/')}/{version}"
        fetch = downloader or _download_url
        fetch(f"{version_url}/{archive_name}", archive_path)
        fetch(f"{version_url}/SHASUMS256.txt", shasums_path)

        expected = _checksum_for_archive(shasums_path.read_text(encoding="utf-8"), archive_name)
        actual = _sha256_file(archive_path)
        if actual != expected:
            raise NodeRuntimeInstallError(
                f"Checksum mismatch for {archive_name}: expected {expected}, got {actual}"
            )

        temp_dir = self.versions_dir / f".{version_dir.name}.tmp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            _safe_extract_tar(archive_path, temp_dir)
            extracted = temp_dir / version_dir.name
            if not extracted.is_dir():
                raise NodeRuntimeInstallError(f"Node archive did not contain {version_dir.name}")
            if version_dir.exists():
                shutil.rmtree(version_dir)
            version_dir.parent.mkdir(parents=True, exist_ok=True)
            extracted.rename(version_dir)
        except Exception as exc:
            if version_dir.exists() and not all(_is_executable_file(str(path)) for path in (node, npm, npx)):
                shutil.rmtree(version_dir)
            if isinstance(exc, NodeRuntimeInstallError):
                raise
            raise NodeRuntimeInstallError(f"Failed to extract Node runtime archive: {exc}") from exc
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

        missing = [name for name, path in (("node", node), ("npm", npm), ("npx", npx)) if not _is_executable_file(str(path))]
        if missing:
            raise NodeRuntimeInstallError(f"Installed Node runtime is incomplete: missing {', '.join(missing)}")

        self._write_manifest(
            version=version,
            platform_id=target,
            node=node,
            npm=npm,
            npx=npx,
            node_modules=self.node_modules_dir,
        )
        return self.discover()

    def discover(self) -> SkillRuntime:
        if not self.manifest_path.exists():
            return SkillRuntime(
                kind="node",
                status="missing",
                provider="missing",
                notes=("No Box-Agent managed Node runtime manifest was found.",),
            )

        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return SkillRuntime(
                kind="node",
                status="unavailable",
                provider="box_agent",
                notes=(f"Box-Agent managed Node runtime manifest is unreadable: {exc}.",),
            )

        active = raw.get("active") if isinstance(raw, dict) else None
        if not isinstance(active, dict):
            return SkillRuntime(
                kind="node",
                status="unavailable",
                provider="box_agent",
                notes=("Box-Agent managed Node runtime manifest has no active runtime.",),
            )

        node = self._managed_path(active.get("node"))
        npm = self._managed_path(active.get("npm"))
        npx = self._managed_path(active.get("npx"))
        node_modules = self._managed_path(active.get("node_modules")) or str(self.node_modules_dir)

        missing = [
            name
            for name, path in (("node", node), ("npm", npm), ("npx", npx))
            if not path or not _is_executable_file(path)
        ]
        if missing:
            return SkillRuntime(
                kind="node",
                status="unavailable",
                provider="box_agent",
                notes=(f"Box-Agent managed Node runtime is incomplete: missing {', '.join(missing)}.",),
            )

        env_vars = self._env_vars(
            node=node,
            npm=npm,
            npx=npx,
            node_modules=node_modules,
        )
        version = active.get("version")
        notes = ()
        if isinstance(version, str) and version:
            notes = (f"Box-Agent managed Node version: {version}.",)
        return SkillRuntime(
            kind="node",
            status="available",
            provider="box_agent",
            executable_path=node,
            env_vars=env_vars,
            notes=notes,
        )

    def _env_vars(self, *, node: str, npm: str, npx: str, node_modules: str) -> dict[str, str]:
        return {
            "BOX_AGENT_NODE": node,
            "BOX_AGENT_NPM": npm,
            "BOX_AGENT_NPX": npx,
            "NODE_PATH": node_modules,
            "npm_config_cache": str(self.npm_cache_dir),
            "npm_config_prefix": str(self.npm_prefix_dir),
        }

    def _managed_path(self, raw: Any) -> str | None:
        path = _safe_manifest_path(raw, base=self.root)
        if path is None:
            return None
        try:
            Path(path).resolve().relative_to(self.root.resolve())
        except ValueError:
            return None
        return path

    def _write_manifest(
        self,
        *,
        version: str,
        platform_id: str,
        node: Path,
        npm: Path,
        npx: Path,
        node_modules: Path,
    ) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "active": {
                "version": version,
                "platform": platform_id,
                "node": str(node),
                "npm": str(npm),
                "npx": str(npx),
                "node_modules": str(node_modules),
            }
        }
        tmp_path = self.manifest_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp_path, self.manifest_path)


def _build_node_runtime(host_runtimes: Any, *, node_runtime_root: Path | None = None) -> SkillRuntime:
    host = _runtime(host_runtimes, "node")
    if host is not None and bool(getattr(host, "ready", False)) and getattr(host, "path", None):
        env_vars = {"BOX_AGENT_NODE": str(getattr(host, "path"))}
        if getattr(host, "npm", None):
            env_vars["BOX_AGENT_NPM"] = str(getattr(host, "npm"))
        if getattr(host, "npx", None):
            env_vars["BOX_AGENT_NPX"] = str(getattr(host, "npx"))
        if getattr(host, "node_modules", None):
            env_vars["NODE_PATH"] = str(getattr(host, "node_modules"))
        return SkillRuntime(
            kind="node",
            status="available",
            provider="host",
            executable_path=env_vars["BOX_AGENT_NODE"],
            env_vars=env_vars,
            notes=_host_note(host),
        )

    return NodeRuntimeManager(root=node_runtime_root).discover()


def _runtime(host_runtimes: Any, kind: RuntimeKind) -> Any | None:
    if isinstance(host_runtimes, dict):
        return host_runtimes.get(kind)
    return getattr(host_runtimes, kind, None)


def _host_note(host: Any) -> tuple[str, ...]:
    provider = getattr(host, "provider", None)
    if provider:
        return (f"Host runtime provider: {provider}.",)
    return ()


def _safe_manifest_path(raw: Any, *, base: Path) -> str | None:
    if not isinstance(raw, str):
        return None
    if not raw or len(raw) > _MAX_RUNTIME_PATH_LEN:
        return None
    if "`" in raw or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw):
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base / path
    if not path.is_absolute():
        return None
    return str(path)


def _is_executable_file(path: str) -> bool:
    return Path(path).is_file() and os.access(path, os.X_OK)


def _bundled_node_runtime_root() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    candidate = Path(sys.executable).resolve().parent.parent / "runtimes" / "node"
    if (candidate / "manifest.json").exists():
        return candidate
    return None


def _is_bundled_node_runtime_root(root: Path) -> bool:
    bundled = _bundled_node_runtime_root()
    if bundled is None:
        return False
    try:
        return root.resolve() == bundled.resolve()
    except OSError:
        return False


class NodeRuntimeInstallError(RuntimeError):
    """Node runtime installation failed without changing the active runtime."""


def _detect_node_macos_platform() -> str:
    if sys.platform != "darwin":
        raise NodeRuntimeInstallError(f"Node auto-install currently supports macOS only, got {sys.platform}.")
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "darwin-arm64"
    if machine in {"x86_64", "amd64"}:
        return "darwin-x64"
    raise NodeRuntimeInstallError(f"Unsupported macOS CPU architecture for Node runtime: {machine}")


def _download_url(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        with urllib.request.urlopen(url, timeout=120) as response, tmp.open("wb") as f:
            shutil.copyfileobj(response, f)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def _checksum_for_archive(shasums: str, archive_name: str) -> str:
    for line in shasums.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[1] == archive_name:
            return parts[0].lower()
    raise NodeRuntimeInstallError(f"No SHA256 entry found for {archive_name}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract_tar(archive_path: Path, dest: Path) -> None:
    dest_resolved = dest.resolve()
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            try:
                target.relative_to(dest_resolved)
            except ValueError as exc:
                raise NodeRuntimeInstallError(f"Unsafe path in Node archive: {member.name}") from exc
            if member.issym() or member.islnk():
                link_target = (target.parent / member.linkname).resolve()
                try:
                    link_target.relative_to(dest_resolved)
                except ValueError as exc:
                    raise NodeRuntimeInstallError(f"Unsafe link in Node archive: {member.name}") from exc
        tar.extractall(dest)
