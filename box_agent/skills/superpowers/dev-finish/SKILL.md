---
name: dev-finish
description: Finish a software-development branch or completed coding task. Use after implementation and verification to summarize changes, inspect git status, prepare commit or PR notes, choose merge/push/keep options, and avoid accidentally staging unrelated user changes.
category: development
---

# Dev Finish

Use this skill when implementation is complete and verified.

## Workflow

1. Run or confirm final verification.
2. Inspect `git status --short`.
3. Separate intended changes from unrelated user changes.
4. Summarize:
   - changed files
   - behavior changed
   - checks run
   - skipped checks or residual risks
5. If asked to commit:
   - stage only intended files
   - write a concise conventional commit
6. If asked to open a PR:
   - include functional impact
   - include tests
   - call out env/schema/platform notes

## Guardrails

- Do not commit unless explicitly asked.
- Do not stage unrelated files.
- Do not merge, push, or discard branches without explicit instruction.
- Do not claim a clean tree if unrelated changes remain.

