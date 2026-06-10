---
name: dev-code-review
description: Review software changes for correctness, regressions, missing tests, maintainability, security, and behavioral mismatches. Use when asked to review code, before merging, after implementing a major task, or when a fresh risk-focused pass is needed.
category: development
---

# Dev Code Review

Use this skill in reviewer mode. Findings come first.

## Review Priorities

1. Bugs and behavioral regressions.
2. Data loss, security, privacy, or external side effects.
3. Missing or weak tests for changed behavior.
4. Ownership or architecture violations.
5. Maintainability issues only when they create real risk.

## Workflow

1. Inspect the diff and relevant surrounding code.
2. Understand intended behavior from issue, plan, or user request.
3. Look for mismatches between intent and implementation.
4. Check platform and state edge cases named by the user.
5. Return findings ordered by severity with file and line references.

## Output Shape

```markdown
Findings:
- [P1] `path:line` issue and impact

Open questions:
- ...

Summary:
- ...
```

If no issues are found, say so and mention residual test gaps.

