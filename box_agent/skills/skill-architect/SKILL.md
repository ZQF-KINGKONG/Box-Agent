---
name: skill-architect
description: Design skill architecture before creation. Use when the user wants to discuss whether an ability should become a single skill, a skill suite, an expert, an expert team, or a hybrid pipeline; produce a structured architecture plan and, when appropriate, an Office Raccoon skill-blueprint handoff for the Skills page.
keywords:
  [
    skill architecture,
    skill blueprint,
    skill design,
    创建skill,
    技能架构,
    架构方案,
    专家团,
  ]
---

# Skill Architect

Help users turn fuzzy repeatable work into the right product structure before any files are created.

## Responsibilities

- Decide whether the request belongs in a single skill, multiple skills, an expert, an expert team, or a hybrid pipeline.
- Separate architecture decisions from implementation details.
- Keep user-facing discussion readable, with a compact diagram or structured plan when it helps.
- Emit a `skill-blueprint` JSON block only when there is a concrete skill package worth creating in the Skills page.
- Hand implementation details to `skill-creator` after the architecture is accepted.

## Architecture Decision Rules

Choose the lightest structure that preserves quality:

- **Single skill**: one repeatable task, one trigger boundary, no substantial shared references or scripts.
- **Skill suite**: several narrow capabilities that should trigger independently but share a domain.
- **Expert**: persona, methodology, and default skills matter more than file resources.
- **Expert team**: multi-role collaboration, staged review, or member-specific outputs are core to quality.
- **Hybrid pipeline**: one orchestrating entry plus several narrow skills, references, scripts, or expert/team metadata.

Prefer expert or expert team when the main value is judgment, role discipline, review, or output depth. Prefer skill packages when the main value is reusable procedure, reference material, deterministic scripts, templates, or triggerable capabilities.

## Discussion Flow

1. Restate the user's target capability in one sentence.
2. Identify inputs, outputs, repeated steps, decision points, required references, scripts, and quality gates.
3. Compare the viable architectures briefly.
4. Recommend one architecture with the reason it is safer or easier to maintain.
5. If the user wants to create it, include a `skill-blueprint` block for the concrete skill package.

Ask a short clarifying question only when the trigger boundary or final deliverable is genuinely ambiguous.

## Output Shape

For ordinary planning, output:

1. Recommended architecture.
2. Component list.
3. Workflow or routing diagram in concise text.
4. Why not the other options.
5. Creation handoff, if applicable.

For Office Raccoon creation handoff, include one fenced JSON block:

```skill-blueprint
{
  "name": "short-english-slug",
  "description": "Use this skill when ...",
  "architecture": "single_skill | skill_suite | expert | expert_team | hybrid",
  "summary": "One sentence explaining the recommended structure.",
  "rationale": ["Why this split is maintainable", "What stays out of SKILL.md"],
  "files": [
    {
      "path": "SKILL.md",
      "content": "---\nname: short-english-slug\ndescription: Use this skill when ...\n---\n\n# Short English Slug\n\n..."
    },
    {
      "path": "references/checklist.md",
      "content": "# Checklist\n\n..."
    }
  ],
  "validation": ["Check that SKILL.md frontmatter name matches the folder name."],
  "nextSteps": ["Review the files in the Skills page before creating."]
}
```

## Handoff Rules

- Always include root `SKILL.md` in the blueprint.
- Keep `name` lowercase, English, and hyphenated.
- Keep `description` trigger-focused and 10-160 characters.
- Keep `SKILL.md` lean; put long methods, rubrics, schemas, and examples into `references/`.
- Use scripts only for deterministic checks or repeated logic.
- Use only relative paths such as `references/foo.md`, `scripts/check.js`, or `templates/prompt.md`.
- Do not include absolute paths, `..`, hidden files, secrets, user-local config, caches, or generated output.
- If the right answer is only an expert or expert team, do not force a skill blueprint; explain the expert/team structure instead.
