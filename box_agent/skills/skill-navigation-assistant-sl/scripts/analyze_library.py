#!/usr/bin/env python3
"""Analyze a local skill library: usage recommendations, workflows, and capability gaps."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

CORE_CATEGORIES = [
    "技能导航",
    "技能创建",
    "通用办公",
    "数据分析",
    "写作内容",
    "地图出行",
    "知识管理",
    "协作沟通",
    "专家顾问",
    "系统运维",
]

TASK_STAGE_RULES = [
    ("需求澄清", ["需求", "目标", "任务", "规划", "方案"]),
    ("资料收集", ["调研", "研究", "资料", "知识库", "网页", "research"]),
    ("分析判断", ["分析", "数据", "对比", "诊断", "洞察", "评估"]),
    ("内容生产", ["写", "写作", "文章", "报告", "文档", "公众号", "邮件", "总结"]),
    ("交付打包", ["技能", "skill", "SkillHub", "打包", "安装", "发布", "上传"]),
]

CATEGORY_KEYWORDS = {
    "技能导航": ["navigation", "skill-map", "技能导航", "技能地图"],
    "技能创建": ["skill-creator", "skillhub", "创建技能", "技能包", "打包"],
    "通用办公": ["office", "办公", "文档", "word", "excel", "ppt"],
    "数据分析": ["data", "analysis", "excel", "数据", "分析", "可视化"],
    "写作内容": ["writer", "write", "写作", "文章", "公众号", "标题"],
    "地图出行": ["map", "地图", "出行", "路线", "天气", "poi"],
    "知识管理": ["ima", "memory", "知识库", "笔记", "记忆"],
    "协作沟通": ["lark", "飞书", "wecom", "企微", "会议", "协作"],
    "专家顾问": ["expert", "team", "专家", "顾问", "咨询"],
    "系统运维": ["system", "health", "deploy", "运维", "部署", "检查"],
}


def load_json(path: str | None, default: Any) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def infer_category(skill: Dict[str, Any]) -> str:
    existing = str(skill.get("category") or "")
    if existing and existing != "未分类":
        return existing
    haystack = " ".join(str(skill.get(k, "")) for k in ["english_name", "slug", "chinese_name", "description_zh"]).lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k.lower() in haystack for k in keywords):
            return category
    return "未分类"


def health_score(skill: Dict[str, Any]) -> Tuple[int, List[str], List[str]]:
    score = 100
    issues: List[str] = []
    fixes: List[str] = []
    if not skill.get("has_skill_md", True):
        score -= 35
        issues.append("缺少 SKILL.md")
        fixes.append("补齐根目录 SKILL.md")
    fm = str(skill.get("front_matter_status") or "")
    if fm and fm != "ok":
        penalty = 25 if "parse" in fm or "invalid" in fm else 15
        score -= penalty
        issues.append(f"YAML 状态异常：{fm}")
        fixes.append("修复 YAML front matter，确保可解析")
    if not skill.get("description_zh") or "缺少" in str(skill.get("description_zh")):
        score -= 15
        issues.append("缺少清晰中文用途说明")
        fixes.append("补充 description 或中文用途说明")
    if not skill.get("version") or str(skill.get("version")) == "unknown":
        score -= 8
        issues.append("缺少版本号")
        fixes.append("在 YAML 中补充 version")
    if infer_category(skill) == "未分类":
        score -= 7
        issues.append("无法自动分类")
        fixes.append("补充更明确的触发词和适用场景")
    if not skill.get("invoke"):
        score -= 10
        issues.append("缺少唤起方式")
        fixes.append("补充调用方式或触发说明")
    score = max(0, min(100, score))
    if not issues:
        issues.append("结构和说明基本完整")
        fixes.append("保持版本说明和触发词更新")
    return score, issues, fixes


def enrich_skills(skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched = []
    for skill in skills:
        item = dict(skill)
        item["category"] = infer_category(item)
        score, issues, fixes = health_score(item)
        item["health_score"] = score
        item["health_issues"] = issues
        item["fix_suggestions"] = fixes
        enriched.append(item)
    return enriched


def usage_insights(skills: List[Dict[str, Any]], usage: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_name = {s.get("english_name") or s.get("slug"): s for s in skills}
    counter: Counter[str] = Counter()
    recent: List[Tuple[str, str]] = []
    for record in usage:
        name = str(record.get("skill") or record.get("name") or "")
        if not name:
            continue
        counter[name] += int(record.get("count") or 1)
        ts = str(record.get("last_used") or record.get("time") or "")
        recent.append((ts, name))
    recent_sorted = [name for _, name in sorted(recent, reverse=True)[:5]]
    if counter:
        frequent = [name for name, _ in counter.most_common(5)]
        pinned = frequent[:3]
        mode = "usage_data"
    else:
        sorted_skills = sorted(skills, key=lambda s: (s.get("health_score", 0), s.get("english_name", "")), reverse=True)
        frequent = [s.get("english_name") for s in sorted_skills[:5]]
        pinned = frequent[:3]
        mode = "fallback_health_based"
    return {
        "mode": mode,
        "recent_skills": recent_sorted,
        "frequent_skills": frequent,
        "suggested_pins": pinned,
        "note": "无使用日志时，基于健康分和名称稳定性降级推荐。" if mode.startswith("fallback") else "基于使用记录统计。",
    }


def pick_skill(skills: List[Dict[str, Any]], keywords: List[str], used: set[str]) -> Dict[str, Any] | None:
    candidates = []
    for skill in skills:
        if skill.get("english_name") in used:
            continue
        category_text = str(skill.get("category", "")).lower()
        description_text = str(skill.get("description_zh", "")).lower()
        name_text = " ".join(str(skill.get(k, "")) for k in ["english_name", "chinese_name"]).lower()
        category_hit = sum(1 for kw in keywords if kw.lower() in category_text)
        description_hit = sum(1 for kw in keywords if kw.lower() in description_text)
        name_hit = sum(1 for kw in keywords if kw.lower() in name_text)
        hit = category_hit * 3 + description_hit * 2 + name_hit
        if hit:
            candidates.append((hit, category_hit, description_hit, skill.get("health_score", 0), skill))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1], x[2], x[3]), reverse=True)
    return candidates[0][4]


def workflow_for_task(task: str, skills: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    stages = []
    used: set[str] = set()
    for stage, triggers in TASK_STAGE_RULES:
        if any(t.lower() in task.lower() for t in triggers):
            skill = pick_skill(skills, triggers, used)
            if skill:
                name = str(skill.get("english_name"))
                used.add(name)
                stages.append({
                    "stage": stage,
                    "skill": name,
                    "invoke": str(skill.get("invoke") or f"/{name}"),
                    "reason": f"任务包含“{stage}”相关意图，该技能在名称、类别或说明中命中相关关键词。",
                })
    if not stages and skills:
        best = sorted(skills, key=lambda s: s.get("health_score", 0), reverse=True)[0]
        name = str(best.get("english_name"))
        stages.append({
            "stage": "主执行",
            "skill": name,
            "invoke": str(best.get("invoke") or f"/{name}"),
            "reason": "未识别明显多阶段意图，建议先使用健康度最高且最通用的技能。",
        })
    return stages


def gap_analysis(skills: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter(infer_category(s) for s in skills)
    strong = [cat for cat, count in counts.most_common() if count >= 2 and cat != "未分类"]
    covered = {cat for cat in counts if cat != "未分类"}
    gaps = [cat for cat in CORE_CATEGORIES if cat not in covered]
    risk_items = [s.get("english_name") for s in skills if s.get("health_score", 0) < 70]
    keywords = [f"{cat} 技能" for cat in gaps[:6]]
    return {
        "category_counts": dict(counts),
        "strong_categories": strong[:6],
        "gap_categories": gaps,
        "risk_skills": risk_items[:10],
        "skillhub_keywords": keywords,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("# 技能库分析报告")
    lines.append("")
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append(f"技能总数：{report['total_skills']}")
    lines.append("")
    lines.append("## 高频/置顶建议")
    ui = report["usage_insights"]
    lines.append(f"模式：{ui['mode']}。{ui['note']}")
    lines.append("建议置顶：" + "、".join([str(x) for x in ui["suggested_pins"] if x]))
    lines.append("")
    lines.append("## 技能组合方案")
    for i, stage in enumerate(report["workflow"], 1):
        lines.append(f"{i}. {stage['stage']}：{stage['skill']}（{stage['invoke']}）")
        lines.append(f"   - 理由：{stage['reason']}")
    lines.append("")
    lines.append("## 缺口分析")
    gap = report["gap_analysis"]
    lines.append("强项类别：" + ("、".join(gap["strong_categories"]) or "暂无明显强项"))
    lines.append("缺口类别：" + ("、".join(gap["gap_categories"]) or "暂无明显缺口"))
    lines.append("SkillHub 搜索建议：" + ("、".join(gap["skillhub_keywords"]) or "暂无"))
    lines.append("")
    lines.append("## 健康风险")
    lines.append("需关注技能：" + ("、".join([str(x) for x in gap["risk_skills"]]) or "暂无"))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze skill library")
    parser.add_argument("--skills-json", required=True)
    parser.add_argument("--task", default="")
    parser.add_argument("--usage-json", default=None)
    parser.add_argument("--markdown-out", default=None)
    args = parser.parse_args()

    skills = enrich_skills(load_json(args.skills_json, []))
    usage = load_json(args.usage_json, [])
    report = {
        "total_skills": len(skills),
        "skills": skills,
        "usage_insights": usage_insights(skills, usage),
        "workflow": workflow_for_task(args.task, skills),
        "gap_analysis": gap_analysis(skills),
    }
    if args.markdown_out:
        Path(args.markdown_out).write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
