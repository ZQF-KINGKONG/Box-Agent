---
name: dev-debug
description: Systematically debug software failures before proposing fixes. Use for test failures, runtime errors, build failures, flaky behavior, performance regressions, integration failures, logs, screenshots, or any unexpected technical behavior where root cause must be established from evidence.
category: development
---

# Dev Debug

Use this skill when something technical is failing or behaving unexpectedly.

## Workflow

1. Read the exact error, log, screenshot, or failing output.
2. Reproduce or identify why reproduction is unavailable.
3. Trace the failing path through real code and configuration.
4. Compare expected vs actual data at each boundary.
5. Identify the smallest root cause that explains all observed symptoms.
6. Fix the owner layer, not the visible symptom, when safe to do so.
7. Add a regression test or explicit verification for the original symptom.

## Evidence Ladder

Prefer evidence in this order:

1. failing command output or runtime logs
2. code path and config that directly own the behavior
3. focused reproduction
4. related tests
5. historical memory or external docs

## Guardrails

- Do not patch before root cause unless containment is explicitly requested.
- Do not blame UI, runtime, cache, or model behavior without tracing boundaries.
- If multiple explanations remain, rank them and state what evidence would decide.

