"""Console entry point for building Box-Agent standalone runtime archives."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    script_path = project_root / "scripts" / "build_runtime.py"
    if not script_path.exists():
        print(f"Error: runtime build script not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("box_agent_build_runtime_script", script_path)
    if spec is None or spec.loader is None:
        print(f"Error: failed to load runtime build script: {script_path}", file=sys.stderr)
        sys.exit(1)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


if __name__ == "__main__":
    main()
