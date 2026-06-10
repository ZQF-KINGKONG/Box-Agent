---
name: dev-tdd
description: Apply test-driven development to software features, bugfixes, refactors, and behavior changes. Use before writing implementation code when the behavior can be tested, especially for shared logic, regressions, parsers, state transitions, APIs, and UI behavior with existing test harnesses.
category: development
---

# Dev TDD

Use this skill when behavior should be protected by tests.

## Red Green Refactor

1. Identify the behavior contract.
2. Write the smallest failing test that proves the desired behavior.
3. Run the focused test and confirm it fails for the expected reason.
4. Implement the smallest change that makes it pass.
5. Run the focused test again.
6. Refactor only while tests stay green.
7. Broaden checks when the touched surface is shared.

## Practical Exceptions

Ask or state a test gap when:

- the change is pure copy, config, generated output, or throwaway prototype
- no local harness exists and adding one would be larger than the fix
- the only meaningful verification is manual or visual

## Guardrails

- A passing test that never failed is not proof.
- Do not add brittle tests that mirror implementation details.
- Prefer regression tests for bugs.
- Keep tests focused on observable behavior.

