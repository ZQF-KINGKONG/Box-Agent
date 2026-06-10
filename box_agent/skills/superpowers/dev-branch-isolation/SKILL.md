---
name: dev-branch-isolation
description: Prepare isolated git branches or worktrees for software-development tasks. Use before larger coding work when a clean branch, worktree, baseline verification, or separation from existing user changes is needed.
category: development
---

# Dev Branch Isolation

Use this skill when larger work should be isolated from the current tree.

## Workflow

1. Inspect current branch and `git status --short`.
2. Identify unrelated user changes and leave them untouched.
3. Prefer an ordinary branch for small or medium tasks.
4. Use a worktree only when parallel work, long-running experiments, or risky changes justify it.
5. Verify project setup in the isolated branch/worktree before coding.
6. Record the base branch and worktree path if created.

## Guardrails

- Do not run destructive git commands.
- Do not move user changes into a new branch unless asked.
- Do not create worktrees inside ignored build output.
- Do not delete a worktree or branch without explicit instruction.

