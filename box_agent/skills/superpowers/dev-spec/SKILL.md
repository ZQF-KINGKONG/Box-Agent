---
name: dev-spec
description: Turn rough software-development requests into clear, reviewable specifications before implementation. Use for new features, behavior changes, ambiguous bugfix scope, product requirements, technical designs, acceptance criteria, or when a coding task needs agreement on intent, constraints, and non-goals before code changes.
category: development
---

# Dev Spec

Use this skill to convert an idea into a compact implementation-ready spec.
Do not use it for tiny, already-specified edits.

## Workflow

1. Inspect local project context before asking questions.
2. Identify the actual user goal, impacted users, constraints, non-goals, and risks.
3. Ask one concise question at a time only when repo evidence cannot answer it.
4. Propose 1-3 implementation approaches with tradeoffs when choices matter.
5. Write a spec that includes:
   - problem statement
   - desired behavior
   - non-goals
   - affected surfaces
   - acceptance criteria
   - risks and open questions
6. Keep visible prompts natural. Do not expose internal skill names as user-facing instructions.

## Output Shape

For chat-only planning, return the spec inline.
When the user wants an artifact, save it under `docs/specs/` or the repo's established planning location.

## Guardrails

- Prefer repo-local evidence over generic guesses.
- Keep the spec small enough to review.
- Do not start implementation while the user is still deciding scope.
- If the user explicitly asks to implement directly, move to implementation and keep only the minimum needed spec in your head.

