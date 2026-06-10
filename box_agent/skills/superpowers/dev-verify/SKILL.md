---
name: dev-verify
description: Verify software work before claiming it is complete. Use before saying a fix works, tests pass, a build is clean, a bug is resolved, a PR is ready, or a task is done; requires fresh command output, manual checks, or explicit skipped-verification notes.
category: development
---

# Dev Verify

Use this skill before making completion claims.

## Workflow

1. Identify the claim you want to make.
2. Pick the smallest check that proves it.
3. Run the check fresh.
4. Read the full output and exit code.
5. If it passes, state the exact command and result.
6. If it fails, continue fixing when local and safe.
7. If a check cannot run, state why and the residual risk.

## Claim Map

| Claim | Evidence |
| --- | --- |
| tests pass | test command output with zero failures |
| type safe | typecheck output |
| lint clean | lint output |
| bug fixed | original symptom no longer reproduces |
| UI works | browser/manual screenshot or explicit manual check |
| no whitespace issues | `git diff --check` |

## Guardrails

- Do not say "should be fixed" as completion.
- Do not rely on previous runs after edits.
- Do not hide failing checks.

