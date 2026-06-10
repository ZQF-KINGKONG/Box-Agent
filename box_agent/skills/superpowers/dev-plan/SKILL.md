---
name: dev-plan
description: Create concrete implementation plans for software-development tasks after requirements are known. Use when a feature, bugfix, refactor, migration, or integration needs file-level steps, sequencing, test strategy, risk notes, and verification before coding.
category: development
---

# Dev Plan

Use this skill when the task is clear enough to plan but not yet safe to code.

## Workflow

1. Read the spec, issue, or user request.
2. Inspect the real code paths, tests, configuration, and nearby patterns.
3. List affected files and ownership boundaries.
4. Break work into reviewable steps:
   - smallest useful code change
   - focused tests or checks
   - expected observable result
5. Include verification commands that match the repo's toolchain.
6. Call out risks, assumptions, and rollback paths.

## Plan Format

```markdown
# <Task> Implementation Plan

Goal:
Scope:
Non-goals:

Affected files:
- `path`: why it changes

Steps:
1. ...
2. ...

Verification:
- command/result expected

Risks:
- ...
```

## Guardrails

- Do not invent architecture when an existing pattern fits.
- Do not create a huge plan for a small change.
- Do not bury important uncertainty; mark it as an open question.
- Keep user-owned unrelated changes out of scope.

