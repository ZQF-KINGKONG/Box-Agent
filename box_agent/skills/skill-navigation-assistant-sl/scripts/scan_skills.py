#!/usr/bin/env python3
"""Scan local Office Raccoon skill directories and output normalized metadata."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

DEFAULT_SKILL_DIRS = [
    Path.home() / ".box-agent" / "skills",
    Path("/Applications/office-raccoon.app/Contents/Resources/box-agent-runtime/bin/_internal/box_agent/skills"),
]

CATEGORY_RULES = [
    ("技能创建", ["skill-creator", "skillhub", "skill maker", "创建技能", "技能包"]),
    ("地图出行", ["map", "地图", "路线", "天气", "poi", "腾讯位置"]),
    ("飞书协作", ["lark", "飞书"]),
    ("专家顾问", ["expert", "team", "专家", "顾问", "思维"]),
    ("记忆管理", ["memory", "记忆"]),
    ("技能导航", ["skill-map", "navigation", "技能地图", "技能导航"]),
    ("通用办公", ["office", "文档", "写作", "分析", "报告"]),
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def parse_front_matter(text: str) -> tuple[Dict[str, Any], Optional[str]]:
    if not text.startswith("---"):
        return {}, "missing_front_matter"
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not match:
        return {}, "invalid_front_matter_block"
    if yaml is None:
        return {}, "pyyaml_not_available"
    try:
        data = yaml.safe_load(match.group(1)) or {}
        if not isinstance(data, dict):
            return {}, "front_matter_not_mapping"
        return data, None
    except Exception as exc:
        return {}, f"yaml_parse_error: {exc}"


def first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def chinese_name(name: str, heading: str, description: str) -> str:
    for candidate in [heading, description]:
        zh = re.findall(r"[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9·：:（）()\- ]{1,24}", candidate or "")
        if zh:
            return zh[0].strip(" ：:")
    mapping = {
        "skill": "技能",
        "map": "地图",
        "navigation": "导航",
        "assistant": "助手",
        "creator": "创建器",
        "optimized": "优化版",
        "architect": "架构师",
        "memory": "记忆",
        "lark": "飞书",
    }
    parts = re.split(r"[-_]+", name)
    translated = "".join(mapping.get(p.lower(), p.title()) for p in parts if p)
    return translated or "待识别"


def categorize(name: str, description: str) -> str:
    haystack = f"{name} {description}".lower()
    for category, keywords in CATEGORY_RULES:
        if any(k.lower() in haystack for k in keywords):
            return category
    return "未分类"


def scan_skill_dir(root: Path) -> List[Dict[str, Any]]:
    results = []
    if not root.exists():
        return results
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        skill_md = child / "SKILL.md"
        text = read_text(skill_md) if skill_md.exists() else ""
        fm, err = parse_front_matter(text) if text else ({}, "missing_skill_md")
        name = str(fm.get("name") or child.name)
        title = str(fm.get("title") or fm.get("display_name") or first_heading(text) or "")
        description = str(fm.get("description") or "").strip()
        if not description:
            lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("---") and not l.startswith("#")]
            description = lines[0][:160] if lines else ""
        health = "normal" if skill_md.exists() and not err and name and description else "warning"
        if err and err not in {"missing_front_matter"}:
            health = "error"
        results.append({
            "english_name": name,
            "slug": child.name,
            "chinese_name": chinese_name(name, title, description),
            "description_zh": description or "该技能缺少清晰说明，需要补充 description。",
            "version": str(fm.get("version") or "unknown"),
            "category": categorize(name, description),
            "invoke": f"/{name}",
            "path": str(child),
            "source": str(root),
            "has_skill_md": skill_md.exists(),
            "front_matter_status": "ok" if not err else err,
            "health": health,
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan local skills")
    parser.add_argument("--dirs", nargs="*", help="Skill roots to scan")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()
    roots = [Path(p).expanduser() for p in args.dirs] if args.dirs else DEFAULT_SKILL_DIRS
    skills: List[Dict[str, Any]] = []
    for root in roots:
        skills.extend(scan_skill_dir(root))
    if args.json:
        print(json.dumps(skills, ensure_ascii=False, indent=2))
    else:
        print(f"扫描到 {len(skills)} 个技能")
        for item in skills:
            print(f"- {item['english_name']} / {item['chinese_name']} | {item['category']} | {item['invoke']} | {item['health']}")


if __name__ == "__main__":
    main()
