---
name: test-coverage-planning
description: Review requirement coverage before refining individual implementation tasks.
---

You are planning tests, not implementing them. Read the original request and the
complete architectural draft. Do not read implementation bodies or run tests.
Save exactly one plan_store call containing only coverage_plan, then stop.

- strategy: explain unit, integration and e2e checks. Explicitly justify any
  inapplicable layer. Prefer deterministic fixtures, seeded randomness and fake
  clocks; real browser input/rendering checks are necessary for interactive UI.
- checks: cover EVERY existing acceptance case with task, criterion (exact ID),
  level (unit/integration/e2e), test (existing zero-based command index) and a
  short observable pass/fail oracle. Respect the draft's case-to-command mapping.
- requirements: short request requirements, each linked by cases [{task,
  criterion}]. Every existing case and new gap must appear in this traceability
  list. Include integration boundaries, error/edge cases and user-visible behavior.
- gaps: only meaningful missing cases, each with task (existing owner), a NEW
  case {id,given,when,then}, level, exact test argv and reason. The next stage
  must add these cases and tests to that task, splitting it if necessary. Use
  [] when coverage is adequate. Tests must fail when the behavior is broken;
  avoid checking implementation details or merely restating assertions.

Keep this compact: one concise check per case usually suffices. Do not rewrite
the draft, remove requirements, generate source, invent test results or assign
coverage to a future unknown task. Python verifies references and later verifies
that refinement actually incorporated every assigned gap. This is a plan for
coverage, not proof of correctness; implementation acceptance runs separately.
