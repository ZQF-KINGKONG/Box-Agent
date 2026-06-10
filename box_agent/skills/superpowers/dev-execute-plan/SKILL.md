---
name: dev-execute-plan
description: Execute an existing software implementation plan task-by-task. Use when a written plan, checklist, issue breakdown, or approved spec should be implemented with incremental progress, local verification, and careful handling of blockers.
category: development
---

# Dev Execute Plan

Use this skill to implement a plan without drifting from it.

## Workflow

1. Read the plan fully before editing.
2. Check the current git status and identify unrelated user changes.
3. Review the first task for ambiguity or unsafe operations.
4. Execute one coherent step at a time.
5. After each meaningful step, run the smallest relevant check.
6. If the plan becomes wrong because repo evidence contradicts it, pause implementation and update the plan rationale.
7. Finish with a concise change summary and verification record.

## Stop Conditions

Stop and ask only when:

- the plan requires destructive or irreversible work
- credentials or external side effects are needed
- two valid paths have materially different product outcomes
- repeated verification failures indicate the plan is wrong

## Guardrails

- Do not use implementation shortcuts that violate the plan's acceptance criteria.
- Do not modify unrelated files just because they are nearby.
- Do not claim completion without fresh verification.

