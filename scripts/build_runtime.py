#!/usr/bin/env python3
"""Build a standalone box-agent-runtime artifact for the current platform.

Usage:
    python scripts/build_runtime.py [--version 0.3.2] [--output dist/runtime]

Produces:
    dist/runtime/box-agent-runtime-v{version}-{platform}-{arch}.tar.gz

Requires:
    pip install pyinstaller
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

# Make `python scripts/build_runtime.py` work from a source checkout even when
# the package has not been installed into the active environment.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from box_agent.tools.runtime import DEFAULT_NODE_VERSION, NodeRuntimeManager

# ── Win-only bundled tool versions ────────────────────────────
# bash + coreutils. PortableGit ships as a 7-Zip self-extracting .exe.
PORTABLE_GIT_VERSION = "2.46.0"
PORTABLE_GIT_TAG = "v2.46.0.windows.1"
PORTABLE_GIT_URL = (
    f"https://github.com/git-for-windows/git/releases/download/"
    f"{PORTABLE_GIT_TAG}/PortableGit-{PORTABLE_GIT_VERSION}-64-bit.7z.exe"
)
# Standalone CPython distribution with full stdlib + venv + ensurepip.
# install_only build is what we need.
PYTHON_STANDALONE_VERSION = "3.12.6"
PYTHON_STANDALONE_RELEASE = "20240909"
PYTHON_STANDALONE_URL = (
    f"https://github.com/indygreg/python-build-standalone/releases/download/"
    f"{PYTHON_STANDALONE_RELEASE}/cpython-{PYTHON_STANDALONE_VERSION}+"
    f"{PYTHON_STANDALONE_RELEASE}-x86_64-pc-windows-msvc-install_only.tar.gz"
)
BUILD_TOOLS_CACHE = Path.home() / ".cache" / "box-agent-build-tools"

# ── Platform detection ───────────────────────────────────────

def detect_platform() -> tuple[str, str]:
    """Return (platform, arch) in Electron naming convention."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        plat = "darwin"
    elif system == "linux":
        plat = "linux"
    elif system == "windows":
        plat = "win32"
    else:
        plat = system

    arch_map = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    arch = arch_map.get(machine, machine)

    return plat, arch


# ── Build ────────────────────────────────────────────────────


def build_runtime(version: str, output_dir: Path) -> Path:
    """Build the runtime artifact and return the archive path."""
    plat, arch = detect_platform()
    project_root = PROJECT_ROOT

    print(f"Building box-agent-runtime v{version} for {plat}-{arch}")
    print(f"Project root: {project_root}")

    # ── Step 0: Install runtime extras into current env ─────
    print("\nInstalling runtime extras (data science packages)...")
    # Try uv first (used in dev), fall back to pip
    extras_cmd_pip = [sys.executable, "-m", "pip", "install", "--quiet", f"{project_root}[runtime]"]
    uv_bin = shutil.which("uv")
    if uv_bin:
        extras_cmd_uv = [uv_bin, "pip", "install", "--quiet", f"{project_root}[runtime]"]
        result = subprocess.run(extras_cmd_uv, cwd=str(project_root), capture_output=True)
    else:
        result = subprocess.CompletedProcess(args=["uv"], returncode=1)
    if result.returncode != 0:
        result = subprocess.run(extras_cmd_pip, cwd=str(project_root))
    if result.returncode != 0:
        print("Warning: failed to install runtime extras", file=sys.stderr)

    # ── Step 1: PyInstaller ──────────────────────────────────
    dist_dir = output_dir / "pyinstaller_out"
    dist_dir.mkdir(parents=True, exist_ok=True)

    entry_point = project_root / "box_agent" / "acp" / "runtime_entry.py"

    # Collect data files: config/, skills/
    datas = [
        (str(project_root / "box_agent" / "config"), "box_agent/config"),
        (str(project_root / "box_agent" / "skills"), "box_agent/skills"),
    ]
    datas_args = []
    for src, dst in datas:
        if Path(src).exists():
            datas_args.extend(["--add-data", f"{src}{os.pathsep}{dst}"])

    # Hidden imports that PyInstaller misses
    hidden_imports = [
        "box_agent",
        "box_agent.acp",
        "box_agent.acp.debug_logger",
        "box_agent.agent",
        "box_agent.cli",
        "box_agent.config",
        "box_agent.core",
        "box_agent.events",
        "box_agent.llm",
        "box_agent.llm.anthropic_client",
        "box_agent.llm.openai_client",
        "box_agent.llm.llm_wrapper",
        "box_agent.logger",
        "box_agent.retry",
        "box_agent.schema",
        "box_agent.tools",
        "box_agent.tools.bash_tool",
        "box_agent.tools.file_tools",
        "box_agent.tools.jupyter_tool",
        "box_agent.tools.mcp_loader",
        "box_agent.tools.skill_tool",
        "box_agent.utils",
        # Third-party
        "tiktoken",
        "tiktoken_ext",
        "tiktoken_ext.openai_public",
        "httpx",
        "httpcore",
        "anthropic",
        "openai",
        "pydantic",
        "yaml",
        "mcp",
        "acp",
        "jupyter_client",
        "jupyter_client.provisioning",
        "jupyter_client.provisioning.local_provisioner",
        "ipykernel",
        "ipykernel.inprocess",
        "ipykernel.inprocess.manager",
        "ipykernel_launcher",
        "jupyter_core",
        # debugpy (ipykernel dependency, has _vendored/pydevd subtree)
        "debugpy",
        "debugpy._vendored",
        # Data science (runtime extras)
        "pandas",
        "numpy",
        "matplotlib",
        "matplotlib.backends",
        "matplotlib.backends.backend_agg",
        "seaborn",
        "openpyxl",
        "xlrd",
        "sklearn",
        "sklearn.cluster",
        "sklearn.linear_model",
        # Document processing (runtime extras)
        "docx",  # python-docx imports as 'docx'
        "pypdf",
        "pdfplumber",
        "reportlab",
        "reportlab.pdfgen",
        "reportlab.lib",
        "pptx",  # python-pptx imports as 'pptx'
        "sklearn.preprocessing",
        # pip (used as library in frozen mode for runtime package installs)
        "pip",
        "pip._internal",
        "pip._internal.cli",
        "pip._internal.cli.main",
    ]
    hidden_args = []
    for imp in hidden_imports:
        hidden_args.extend(["--hidden-import", imp])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", "box-agent-acp",
        "--distpath", str(dist_dir),
        "--workpath", str(output_dir / "pyinstaller_build"),
        "--specpath", str(output_dir),
        *datas_args,
        *hidden_args,
        "--collect-all", "tiktoken",
        "--collect-all", "tiktoken_ext",
        "--collect-all", "jupyter_client",
        "--collect-all", "ipykernel",
        "--collect-all", "jupyter_core",
        "--collect-all", "debugpy",
        "--collect-all", "matplotlib",
        "--collect-submodules", "pandas",
        "--collect-submodules", "seaborn",
        "--collect-submodules", "openpyxl",
        "--collect-submodules", "sklearn",
        "--collect-submodules", "pip",
        str(entry_point),
    ]

    print(f"\nRunning PyInstaller...")
    result = subprocess.run(cmd, cwd=str(project_root))
    if result.returncode != 0:
        print("PyInstaller failed!", file=sys.stderr)
        sys.exit(1)

    pyinstaller_output = dist_dir / "box-agent-acp"
    if not pyinstaller_output.exists():
        print(f"Expected output not found: {pyinstaller_output}", file=sys.stderr)
        sys.exit(1)

    # ── Step 2: Assemble runtime directory ───────────────────
    runtime_name = f"box-agent-runtime-v{version}-{plat}-{arch}"
    runtime_dir = output_dir / "box-agent-runtime"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True)

    # bin/ directory
    bin_dir = runtime_dir / "bin"
    bin_dir.mkdir()

    # Copy PyInstaller output into bin/
    # PyInstaller --onedir produces a directory with the executable + libs
    for item in pyinstaller_output.iterdir():
        dest = bin_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Ensure entry is executable
    entry_bin = bin_dir / "box-agent-acp"
    if plat == "win32":
        entry_bin = bin_dir / "box-agent-acp.exe"
    if entry_bin.exists():
        entry_bin.chmod(0o755)

    # VERSION file
    (runtime_dir / "VERSION").write_text(version + "\n", encoding="utf-8")

    # manifest.json
    entry_path = "bin/box-agent-acp"
    if plat == "win32":
        entry_path = "bin/box-agent-acp.exe"

    manifest = {
        "name": "box-agent",
        "version": version,
        "platform": plat,
        "arch": arch,
        "entry": entry_path,
        "mode": "standalone",
    }
    (runtime_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    if plat == "darwin" and arch in {"arm64", "x64"}:
        _install_bundled_node_runtime(runtime_dir, plat=plat, arch=arch)
    elif plat == "win32" and arch == "x64":
        _install_bundled_win_runtimes(runtime_dir)
    else:
        print(f"\nSkipping bundled Node runtime for unsupported platform: {plat}-{arch}")

    print(f"\nRuntime directory assembled: {runtime_dir}")
    print(f"  manifest.json: {json.dumps(manifest)}")

    # ── Step 3: Create archive ───────────────────────────────
    archive_name = f"{runtime_name}.tar.gz"
    archive_path = output_dir / archive_name

    print(f"\nCreating archive: {archive_path}")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(runtime_dir, arcname="box-agent-runtime")

    # Archive size
    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"Archive created: {archive_path} ({size_mb:.1f} MB)")

    # ── Cleanup ──────────────────────────────────────────────
    shutil.rmtree(dist_dir, ignore_errors=True)
    shutil.rmtree(output_dir / "pyinstaller_build", ignore_errors=True)
    for f in output_dir.glob("*.spec"):
        f.unlink(missing_ok=True)

    return archive_path


def _install_bundled_node_runtime(runtime_dir: Path, *, plat: str, arch: str) -> None:
    """Install a relocatable macOS Node runtime into the runtime artifact."""
    node_root = runtime_dir / "runtimes" / "node"
    platform_id = f"{plat}-{arch}"
    print(f"\nInstalling bundled Node.js runtime {DEFAULT_NODE_VERSION} for {platform_id}...")
    manager = NodeRuntimeManager(root=node_root)
    manager.install_macos(version=DEFAULT_NODE_VERSION, platform_id=platform_id)
    shutil.rmtree(node_root / "downloads", ignore_errors=True)
    _relativize_node_manifest(node_root)
    print(f"Bundled Node runtime: {node_root}")


def _install_bundled_win_runtimes(runtime_dir: Path) -> None:
    """Bundle PortableGit (bash/coreutils) + standalone Python + Node into the Win runtime.

    box-agent on Windows can't rely on system bash/python/node — Mac users have
    them by default, Win users almost never. This drops self-contained copies
    into the runtime tar so the artifact is install-and-go.
    """
    print("\n[win] Installing bundled PortableGit + Python + Node runtimes...")
    BUILD_TOOLS_CACHE.mkdir(parents=True, exist_ok=True)

    _install_portable_git_win(runtime_dir)
    _install_portable_python_win(runtime_dir)

    node_root = runtime_dir / "runtimes" / "node"
    print(f"\n[win] Installing bundled Node.js runtime {DEFAULT_NODE_VERSION} for win-x64...")
    manager = NodeRuntimeManager(root=node_root)
    manager.install_win(version=DEFAULT_NODE_VERSION, platform_id="win-x64")
    shutil.rmtree(node_root / "downloads", ignore_errors=True)
    _relativize_node_manifest(node_root)
    print(f"[win] Bundled Node runtime: {node_root}")


def _install_portable_git_win(runtime_dir: Path) -> None:
    """Download and extract PortableGit 7-Zip SFX into ``runtime/PortableGit/``."""
    target = runtime_dir / "runtime" / "PortableGit"
    bash_exe = target / "usr" / "bin" / "bash.exe"
    if bash_exe.is_file():
        print(f"[win] PortableGit already present: {target}")
        return

    override = os.environ.get("BOX_AGENT_BUILD_PORTABLE_GIT")
    if override:
        archive = Path(override)
        if not archive.is_file():
            raise RuntimeError(f"BOX_AGENT_BUILD_PORTABLE_GIT not found: {archive}")
        print(f"[win] Using PortableGit override: {archive}")
    else:
        archive = BUILD_TOOLS_CACHE / f"PortableGit-{PORTABLE_GIT_VERSION}-64-bit.7z.exe"
        if not archive.is_file():
            print(f"[win] Downloading PortableGit -> {archive}")
            _download_to(PORTABLE_GIT_URL, archive)

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    # PortableGit-*.7z.exe is a 7-Zip self-extracting archive. The supported
    # extraction flags are: -y (assume yes), -o<dir> (output directory).
    print(f"[win] Extracting PortableGit -> {target}")
    result = subprocess.run(
        [str(archive), "-y", f"-o{target}"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"PortableGit extraction failed (exit {result.returncode}): "
            f"{result.stderr.decode(errors='replace')[:500]}"
        )

    if not bash_exe.is_file():
        raise RuntimeError(f"PortableGit extracted but bash.exe missing: {bash_exe}")
    print(f"[win] PortableGit ready: {bash_exe}")


def _install_portable_python_win(runtime_dir: Path) -> None:
    """Download and extract python-build-standalone install_only into ``runtime/python/``."""
    target = runtime_dir / "runtime" / "python"
    python_exe = target / "python.exe"
    if python_exe.is_file():
        print(f"[win] Portable Python already present: {target}")
        return

    override = os.environ.get("BOX_AGENT_BUILD_PORTABLE_PYTHON")
    if override:
        archive = Path(override)
        if not archive.is_file():
            raise RuntimeError(f"BOX_AGENT_BUILD_PORTABLE_PYTHON not found: {archive}")
        print(f"[win] Using portable Python override: {archive}")
    else:
        archive = (
            BUILD_TOOLS_CACHE
            / f"cpython-{PYTHON_STANDALONE_VERSION}-{PYTHON_STANDALONE_RELEASE}-win-x64-install_only.tar.gz"
        )
        if not archive.is_file():
            print(f"[win] Downloading python-build-standalone -> {archive}")
            _download_to(PYTHON_STANDALONE_URL, archive)

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)

    # install_only tar.gz layout: ``python/python.exe + python/Lib/...``.
    print(f"[win] Extracting portable Python -> {target}")
    extract_root = target.parent / ".python-extract"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    try:
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(extract_root)
        inner = extract_root / "python"
        if not inner.is_dir():
            raise RuntimeError(f"Portable Python archive missing 'python/' dir: {archive}")
        # Win: ``Path.rename`` (MoveFileEx) trips ``WinError 5`` when
        # Defender/Search Indexer briefly holds the freshly extracted
        # ``python.exe``. ``shutil.move`` falls back to copy+delete and is
        # more tolerant; retry once after a short pause as final safety net.
        try:
            shutil.move(str(inner), str(target))
        except PermissionError:
            import time
            time.sleep(2)
            shutil.move(str(inner), str(target))
    finally:
        if extract_root.exists():
            shutil.rmtree(extract_root, ignore_errors=True)

    if not python_exe.is_file():
        raise RuntimeError(f"Portable Python extracted but python.exe missing: {python_exe}")
    print(f"[win] Portable Python ready: {python_exe}")

    _install_sandbox_packages_win(python_exe)


# Pre-installed into the bundled Python's site-packages so that the frozen
# Win build's ``execute_code`` (InProcessKernelSession) can ``import pandas``
# etc. without spawning pip at first run. Mirrors
# ``box_agent.tools.jupyter_tool.SANDBOX_DEFAULT_PACKAGES`` + ``ipykernel``.
_SANDBOX_BUNDLED_PACKAGES = (
    "pandas",
    "numpy",
    "matplotlib",
    "openpyxl",
    "scikit-learn",
    "ipykernel",
)


def _install_sandbox_packages_win(python_exe: Path) -> None:
    """Pre-install sandbox data-science packages into the bundled portable Python."""
    print(f"\n[win] Pre-installing sandbox packages into bundled Python: {', '.join(_SANDBOX_BUNDLED_PACKAGES)}")
    print(f"[win] (this can take several minutes the first time)")
    # Strip parent-process venv markers so the bundled python doesn't try to
    # load pip/site-packages from the build venv (.venv-build / uv cpython)
    # — those copies are ABI-incompatible with python-build-standalone and
    # trip ``AttributeError: class must define a '_type_' attribute`` in
    # ctypes when imported.
    clean_env = {
        k: v for k, v in os.environ.items()
        if k not in {
            "PYTHONPATH",
            "PYTHONHOME",
            "VIRTUAL_ENV",
            "__PYVENV_LAUNCHER__",
            "PYTHONNOUSERSITE",
            "PYTHONUSERBASE",
        }
    }
    clean_env["PYTHONNOUSERSITE"] = "1"
    result = subprocess.run(
        [
            str(python_exe), "-I", "-m", "pip", "install",
            "--no-warn-script-location",
            "--disable-pip-version-check",
            *_SANDBOX_BUNDLED_PACKAGES,
        ],
        capture_output=True,
        env=clean_env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Pre-install of sandbox packages failed (exit {result.returncode}): "
            f"{result.stderr.decode(errors='replace')[:1000]}"
        )
    print("[win] Sandbox packages ready in bundled Python.")


def _download_to(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        with urllib.request.urlopen(url, timeout=300) as response, tmp.open("wb") as f:
            shutil.copyfileobj(response, f)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def _relativize_node_manifest(node_root: Path) -> None:
    """Rewrite Node manifest paths relative to node_root for relocatable archives."""
    manifest_path = node_root / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    active = data.get("active")
    if not isinstance(active, dict):
        raise RuntimeError(f"Invalid Node manifest: {manifest_path}")
    for key in ("node", "npm", "npx", "node_modules"):
        value = active.get(key)
        if not isinstance(value, str):
            continue
        path = Path(value)
        if not path.is_absolute():
            continue
        active[key] = str(path.resolve().relative_to(node_root.resolve()))
    tmp_path = manifest_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, manifest_path)


# ── CLI ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build box-agent standalone runtime")
    parser.add_argument("--version", default=None, help="Version string (default: read from package)")
    parser.add_argument("--output", default="dist/runtime", help="Output directory")
    args = parser.parse_args()

    version = args.version
    if not version:
        # Read from package
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from box_agent import __version__
        version = __version__

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    archive = build_runtime(version, output_dir)
    print(f"\nDone! Artifact: {archive}")


if __name__ == "__main__":
    main()
