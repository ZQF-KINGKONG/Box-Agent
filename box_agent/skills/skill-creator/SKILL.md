---
name: skill-creator
description: Create and refine Codex skill files after the skill architecture is clear. Use when writing or editing SKILL.md, references, scripts, templates, trigger wording, or validating that an existing skill package is concise, discoverable, and portable across macOS, Windows, and Linux. For deciding single skill vs skill suite vs expert/team architecture first, use skill-architect.
keywords: [skill, codex skill, 创建skill, 技能开发, 写skill]
---

# Skill Creator

Create skills that are easy to trigger, easy to maintain, and small enough to stay useful.

## Goals

- Capture one repeatable task or workflow per skill.
- Keep triggering text explicit and concrete.
- Keep the body short; move detail into `references/` or `scripts/`.
- Prefer reusable patterns over one-off prose.
- Keep the skill usable in products with different host runtimes and OSes.

## Workflow

### 1. Clarify the target

- Identify the user-facing task the skill should solve.
- List the concrete prompts that should trigger it.
- Note constraints, file types, APIs, or product surfaces involved.

### 2. Design the structure

Choose the lightest structure that fits:

- **Workflow-based**: when the task has clear steps.
- **Task-based**: when the skill offers several operations.
- **Reference-based**: when the skill encodes rules, standards, or schemas.
- **Capability-based**: when the skill combines related behaviors.

### 3. Keep `SKILL.md` lean

- Put trigger conditions in the frontmatter `description`.
- Use imperative language in the body.
- Keep only the core procedure and decision points.
- Move long examples, schemas, and variants into reference files.

### 4. Add resources only when they reduce repetition

- Put deterministic logic in `scripts/`.
- Put reusable domain knowledge in `references/`.
- Put templates or assets in `assets/`.
- Do not assume a local Node install.
- If a script is needed, make the runtime explicit or configurable.
- Prefer host-provided executable paths or environment overrides over hardcoded tool paths.

### 5. Keep runtime assumptions portable

- Write paths in a cross-platform way.
- Avoid shell syntax that only works on one OS unless a wrapper handles it.
- Treat host-supplied `node`, `python`, or similar paths as optional overrides, not guarantees.
- Fail gracefully when a bundled helper is unavailable on the user machine.

### 6. Validate the skill

- Check that the name is short, lowercase, and hyphenated.
- Check that the description states both what it does and when to use it.
- Check that the body has no placeholder text.
- Check that any bundled resources are actually needed.
- Check that no instruction depends on a single desktop OS or a fixed interpreter path.

## Writing rules

- Do not add background process notes.
- Do not explain the entire skill-creation philosophy in the final skill.
- Prefer concrete examples over generic advice.
- Prefer deletion over extra layers.
- Prefer host-agnostic wording over product-specific assumptions.

## Output shape

When drafting a new skill, produce:

1. skill folder name
2. trigger description
3. `SKILL.md`
4. any required references or scripts
5. validation notes

## Relationship to skill-architect

Use `skill-architect` before this skill when the user is still deciding whether the capability
should be a single skill, a skill suite, an expert, an expert team, or a hybrid pipeline.

Use this skill after that decision to write, edit, or validate the actual skill package files. If
the user provides an Office Raccoon `skill-blueprint`, preserve the chosen architecture and focus on
making the files concise, portable, and valid.
