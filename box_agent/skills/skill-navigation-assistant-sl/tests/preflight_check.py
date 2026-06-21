#!/usr/bin/env python3
"""Preflight release checks for Skill Navigation Assistant SL."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from zipfile import ZipFile

import yaml

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT.parent / "skill-navigation-assistant-sl.zip"
REQUIRED_ROOT_FILES = {"SKILL.md", "README.md"}
REQUIRED_METADATA = {"name", "display_name", "description", "version"}
FORBIDDEN = (".DS_Store", ".uploading.cfg", "__pycache__", ".pytest_cache")


def fail(msg: str, failures: list[str]) -> None:
    failures.append(msg)


def parse_skill_md(failures: list[str]) -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        fail("SKILL.md 缺少 YAML front matter", failures)
        return
    try:
        data = yaml.safe_load(m.group(1))
    except Exception as exc:
        fail(f"YAML 不可解析：{exc}", failures)
        return
    if not isinstance(data, dict):
        fail("YAML front matter 不是 mapping", failures)
        return
    missing = REQUIRED_METADATA - set(k for k, v in data.items() if v)
    if missing:
        fail(f"YAML 缺少字段：{sorted(missing)}", failures)
    if data.get("name") != "skill-navigation-assistant-sl":
        fail("name 不等于 skill-navigation-assistant-sl", failures)


def check_python_syntax(failures: list[str]) -> None:
    for path in sorted((ROOT / "scripts").glob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            fail(f"Python 语法错误 {path.relative_to(ROOT)}: {exc}", failures)


def check_zip(failures: list[str]) -> None:
    if not ZIP.exists():
        fail("缺少发布 ZIP", failures)
        return
    with ZipFile(ZIP) as zf:
        names = zf.namelist()
    for required in REQUIRED_ROOT_FILES:
        if required not in names:
            fail(f"ZIP 根层缺少 {required}", failures)
    bad = [n for n in names if any(token in n for token in FORBIDDEN)]
    if bad:
        fail(f"ZIP 包含临时/缓存文件：{bad}", failures)
    nested_skill = [n for n in names if n.count("/") == 1 and n.endswith("SKILL.md")]
    if nested_skill and "SKILL.md" not in names:
        fail("ZIP 疑似套了一层目录，根层没有 SKILL.md", failures)


def main() -> None:
    failures: list[str] = []
    parse_skill_md(failures)
    check_python_syntax(failures)
    check_zip(failures)
    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
        sys.exit(1)
    print("PASS: release preflight checks passed")


if __name__ == "__main__":
    main()
