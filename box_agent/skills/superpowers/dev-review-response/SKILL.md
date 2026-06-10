---
name: dev-review-response
description: Handle code review feedback carefully. Use when review comments, requested changes, PR feedback, CI review output, or human reviewer notes need to be understood, verified against the codebase, implemented, or pushed back on with technical reasoning.
category: development
---

# Dev Review Response

Use this skill when responding to review feedback.

## Workflow

1. Read all feedback before editing.
2. Group comments by required behavior, not by comment order.
3. Verify each claim against the current codebase.
4. Decide for each item:
   - fix now
   - ask clarification
   - explain why the suggestion is not applicable
   - defer with a concrete reason
5. Implement one logical group at a time.
6. Run focused verification after each group.
7. Summarize exactly which comments were addressed.

## Guardrails

- Do not performatively agree before checking.
- Do not implement unclear feedback.
- Do not silently broaden scope.
- Preserve unrelated changes.

