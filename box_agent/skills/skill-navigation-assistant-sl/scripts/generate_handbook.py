#!/usr/bin/env python3
"""Generate a user-facing Markdown handbook for the local skill library."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

try:
    from analyze_library import enrich_skills, gap_analysis, usage_insights, workflow_for_task
except ImportError:  # pragma: no cover
    import sys
    sys.path.append(str(Path(__file__).resolve().parent))
    from analyze_library import enrich_skills, gap_analysis, usage_insights, workflow_for_task


def load_json(path: str | None, default: Any) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def render_handbook(skills: List[Dict[str, Any]], task: str, usage: List[Dict[str, Any]]) -> str:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for skill in skills:
        grouped[str(skill.get("category") or "未分类")].append(skill)
    ui = usage_insights(skills, usage)
    workflow = workflow_for_task(task, skills)
    gaps = gap_analysis(skills)
    normal = sum(1 for s in skills if s.get("health_score", 0) >= 85)
    warning = sum(1 for s in skills if 70 <= s.get("health_score", 0) < 85)
    risk = sum(1 for s in skills if s.get("health_score", 0) < 70)

    lines: List[str] = []
    lines.append("# 我的技能说明书")
    lines.append("")
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"技能总数：{len(skills)}")
    lines.append(f"健康概览：正常 {normal} 个，需完善 {warning} 个，风险 {risk} 个")
    lines.append("")
    lines.append("## 1. 我现在有哪些技能")
    for category in sorted(grouped):
        lines.append(f"\n### {category}")
        for skill in sorted(grouped[category], key=lambda s: str(s.get("english_name"))):
            lines.append(f"- **{skill.get('english_name')} / {skill.get('chinese_name', '待识别')}**")
            lines.append(f"  - 用途：{skill.get('description_zh', '暂无说明')}")
            lines.append(f"  - 唤起方式：{skill.get('invoke', '/' + str(skill.get('english_name', '')))}")
            lines.append(f"  - 健康分：{skill.get('health_score', 'N/A')}；建议：{'; '.join(skill.get('fix_suggestions', [])[:2])}")
    lines.append("")
    lines.append("## 2. 推荐置顶与高频入口")
    lines.append(f"统计模式：{ui['mode']}。{ui['note']}")
    lines.append("建议置顶：" + ("、".join([str(x) for x in ui["suggested_pins"] if x]) or "暂无"))
    lines.append("最近使用：" + ("、".join([str(x) for x in ui["recent_skills"] if x]) or "暂无使用记录"))
    lines.append("")
    lines.append("## 3. 当前任务推荐工作流")
    if task:
        lines.append(f"任务：{task}")
    else:
        lines.append("任务：未指定。以下为通用推荐。")
    for i, stage in enumerate(workflow, 1):
        lines.append(f"{i}. **{stage['stage']}**：{stage['skill']}（{stage['invoke']}）")
        lines.append(f"   - {stage['reason']}")
    lines.append("")
    lines.append("## 4. 技能库强项与缺口")
    lines.append("强项类别：" + ("、".join(gaps["strong_categories"]) or "暂无明显强项"))
    lines.append("缺口类别：" + ("、".join(gaps["gap_categories"]) or "暂无明显缺口"))
    lines.append("建议去 SkillHub 搜索：" + ("、".join(gaps["skillhub_keywords"]) or "暂无"))
    lines.append("")
    lines.append("## 5. 需要维护的技能")
    risky = [s for s in skills if s.get("health_score", 0) < 85]
    if not risky:
        lines.append("当前没有明显需要维护的技能。")
    for skill in sorted(risky, key=lambda s: s.get("health_score", 0))[:12]:
        lines.append(f"- **{skill.get('english_name')}**：健康分 {skill.get('health_score')}")
        lines.append(f"  - 问题：{'; '.join(skill.get('health_issues', []))}")
        lines.append(f"  - 建议：{'; '.join(skill.get('fix_suggestions', []))}")
    lines.append("")
    lines.append("## 6. 下一步建议")
    lines.append("1. 优先修复健康分低于 70 的技能。")
    lines.append("2. 将高频技能置顶或记入常用入口。")
    lines.append("3. 对缺口类别优先去 SkillHub 查找 Prompt 安装或 ZIP 包安装入口。")
    lines.append("4. 如果某类任务经常出现但没有合适技能，建议沉淀为新的 SkillHub 技能。")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate skill handbook")
    parser.add_argument("--skills-json", required=True)
    parser.add_argument("--task", default="")
    parser.add_argument("--usage-json", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    skills = enrich_skills(load_json(args.skills_json, []))
    usage = load_json(args.usage_json, [])
    Path(args.out).write_text(render_handbook(skills, args.task, usage), encoding="utf-8")
    print(f"PASS: handbook generated -> {args.out}")


if __name__ == "__main__":
    main()
