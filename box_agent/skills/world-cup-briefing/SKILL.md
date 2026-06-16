---
name: world-cup-briefing
description: 用于生成世界杯战报简报、焦点战预告、球队/球员动态，以及按用户偏好定制的世界杯内容。默认中文输出、球迷向语气，每篇简报与预告都必须包含关键人员信息；简报默认只覆盖昨日比赛、最多近 3 天，并产出单页 HTML 报告。适用于“生成世界杯简报”“写一份焦点战预告”“今天世界杯有什么重点比赛”“重点关注某队/某球员”“更新世界杯关注偏好”等请求。触发词：世界杯简报、世界杯战报、焦点战预告、比赛预告、世界杯重点比赛、关注偏好。
author: 贝贝
---

# World Cup Briefing

Use this skill when the user asks for World Cup briefings, focus match previews, team updates, player updates, or asks to update their World Cup content preferences.

## Default Output

- Language: Chinese unless the user asks otherwise.
- Tone: 球迷向 — 有热情、有现场感、有故事性，但不要牺牲事实准确性。
- Reading experience: 清晰、好读、适合快速了解比赛和关键人物。

## Core Responsibilities

- Create World Cup battle briefings limited to yesterday's matches by default, or the most recent 3 days at maximum when the user asks for a broader recent update.
- Create focus match previews with match context, key storylines, tactical angles, and decisive matchups.
- For briefing requests, avoid generic World Cup introductions, historical background, annual feature summaries, or unrelated soft news unless the user explicitly asks for them.
- Default final deliverable for briefings is a polished single-page HTML report.
- Always include key personnel information in briefings and previews.
- Adapt emphasis based on the user's stated preferences, such as favorite teams, players, coaches, or regions.
- Distinguish confirmed information from uncertain, rumored, or unavailable information.

## When to Use

Trigger this skill for requests such as:

- “生成世界杯简报”
- “写一份世界杯焦点战预告”
- “今天世界杯有什么重点比赛？”
- “重点关注巴西和内马尔”
- “我喜欢内马尔，巴西”
- “以后简报多写阿根廷/法国/英格兰”
- “更新我的世界杯关注偏好”

## Workflow

1. Identify the requested content type: briefing, focus match preview, team update, player update, or preference update.
2. Identify the user's explicit focus: teams, players, coaches, matches, regions, or topics.
3. If the user states a stable preference, acknowledge it and apply it to future outputs according to `references/preference-handling.md`.
4. For time-sensitive facts such as schedule, score, injury, squad, suspension, lineup, or recent quotes, verify current information from reliable sources before presenting it as fact.
5. Produce the output using the formats in `references/output-formats.md`.
6. Apply the fan-oriented style guidance in `references/style-guide.md`.
7. Select key personnel using `references/key-personnel-selection.md`; do not rely only on user-named examples.
8. Run the quality checklist in `references/quality-checklist.md` before finalizing.

## Mandatory Content Rule

Every briefing or focus match preview must include a section named “关键人员信息” or an equivalent clearly labeled section.

This section should cover relevant players, coaches, injury/suspension status, likely starters, tactical roles, recent form, leadership impact, or matchup influence where available.

## Reliability Rules

- Do not invent match results, squads, injuries, lineups, quotes, or transfer/news developments.
- Do not present rumors as confirmed facts.
- If current information cannot be verified, state that it is unconfirmed or unavailable.
- User preference changes content emphasis, not factual conclusions.
- When using current information from search or browsing, cite the sources according to the host environment's citation rules.

## Boundaries

- This skill is for World Cup-related football briefings and match previews, not general sports news unless directly connected to the World Cup.
- Avoid excessive tactical jargon unless the user asks for professional analysis.
- Avoid inflammatory fan language, personal attacks, or discriminatory remarks.


## Coverage Scope Rules

- When the user says only “简报”, “世界杯简报”, “今日简报”, or equivalent, generate a World Cup comprehensive daily briefing package, not a single-match report.
- For battle reports, the default factual range is yesterday's completed matches. If the user asks for “最近”, “近况”, or “这几天”, cover at most the most recent 3 days.
- If the user explicitly names one match, team, or player, narrow the output to that unit while still keeping relevant context.
- If the user asks for “预告” or “preview”, cover the key matches in the next 24-48 hours.
- If the user asks for “战报”, prioritize completed matches, confirmed scores, key incidents, and standings/qualification impact.
- Do not fill space with World Cup history, generic tournament introductions, annual features, city culture, or unrelated soft news.

## Default Delivery Rules

- If the user has no other explicit format requirement, briefing requests must produce a polished, openable single-page HTML report file, plus a short 3-5 bullet summary in chat.
- If the user explicitly asks for HTML/webpage, do not return only plain text.
- If the user explicitly asks for an image/poster/social-card version, an image deliverable may be generated instead of or in addition to HTML, while preserving the same factual scope and key personnel requirements.
- The HTML report must include: title/hero area, scope and update time, daily headline, multi-match cards, schedule preview, key personnel area, source/update notes, and uncertainty notes.
- Image deliverables, when requested, must be visually readable, suitable for sharing, and include scope/update time, main scores or fixtures, and key personnel highlights.

## Source and Uncertainty Rules

- Verify time-sensitive facts such as scores, schedule, injuries, suspensions, squads, lineups, and standings from reliable current sources before presenting them as confirmed.
- Prefer FIFA official pages, official tournament/team pages, official match centers, and authoritative wire/service reports; use general media or social discussion only as auxiliary signals.
- If information is insufficient or conflicting, do not invent details. Mark it as “待确认” or “未检到官方确认”.
- Separate confirmed facts, previews/predictions, and personal judgement.

## Multi-match Self-check

Before finalizing a daily briefing, check that it includes more than one relevant match when multiple matches exist in the selected range, covers completed scores, includes upcoming schedule preview where relevant, provides key personnel per match, and clearly states sources or uncertainty.
