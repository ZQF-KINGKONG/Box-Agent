#!/usr/bin/env python3
"""Validate Skill Navigation Assistant SL package structure and metadata."""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except Exception as exc:  # pragma: no cover
    print(f"FAIL: PyYAML unavailable: {exc}")
    sys.exit(1)

REQUIRED = [
    "SKILL.md",
    "README.md",
    "references/usage-guide.md",
    "references/matching-rules.md",
    "references/skillhub-policy.md",
    "references/health-check.md",
    "references/advanced-capabilities.md",
    "scripts/scan_skills.py",
    "scripts/match_skills.py",
    "scripts/analyze_library.py",
    "scripts/generate_handbook.py",
    "scripts/health_check.py",
    "templates/skill-list.md",
    "templates/recommendation.md",
    "templates/skillhub-result.md",
    "templates/skillhub-install-options.md",
    "templates/workflow.md",
    "templates/gap-analysis.md",
    "templates/handbook.md",
]


def parse_fm(text: str):
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not match:
        raise ValueError("SKILL.md 缺少合法 YAML front matter")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("YAML front matter 不是 mapping")
    return data


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    failures = []
    for rel in REQUIRED:
        if not (root / rel).exists():
            failures.append(f"缺少文件：{rel}")
    skill_md = root / "SKILL.md"
    if skill_md.exists():
        try:
            data = parse_fm(skill_md.read_text(encoding="utf-8"))
            for key in ["name", "display_name", "description", "version"]:
                if not data.get(key):
                    failures.append(f"YAML 缺少字段：{key}")
            if data.get("name") != "skill-navigation-assistant-sl":
                failures.append("YAML name 必须是 skill-navigation-assistant-sl")
        except Exception as exc:
            failures.append(str(exc))
    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
        sys.exit(1)
    print("PASS: package structure and YAML front matter are valid")


if __name__ == "__main__":
    main()
