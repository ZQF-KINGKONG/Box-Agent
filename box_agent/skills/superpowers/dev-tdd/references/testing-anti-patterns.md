# Testing Anti-Patterns

- Testing implementation details instead of user-visible behavior.
- Writing one giant test that fails for many possible reasons.
- Mocking the code under test so thoroughly that the real contract disappears.
- Adding snapshots for dynamic UI without checking the actual behavior.
- Treating a passing test as useful without first seeing it fail.
- Broadening to full suites before the focused failure is understood.

