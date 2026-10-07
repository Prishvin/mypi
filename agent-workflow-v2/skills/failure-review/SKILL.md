---
name: failure-review
description: Diagnose a failed atomic task against evidence, architecture, shadow and plan.
---

Review the failed todo before prescribing a repair. Inspect the supplied failure
evidence, architecture, prototypes and original plan overview. If context selection
omitted a needed contract, retrieve only relevant architecture sections/prototypes.
Do not read or upload application implementation bodies and do not edit source
in this role. Python may supply bounded excerpts of declared failing tests as
read-only evidence. These are selected cases, not a complete project or new
requirements; omitted helpers remain unknown.

Read failed_contract as the mandatory behavior and scope. The separate
previous_attempt_strategy records an unsuccessful approach: its steps, assumptions,
test-immutability claims and read/edit restrictions are not additional frozen
requirements. Reassess them independently. If the previous strategy prohibited an
observation needed to diagnose the failure, replace that restriction with a bounded
evidence-gathering step rather than carrying it forward by default.

Distinguish observed facts from hypotheses: implementation bug, contradictory API,
missing prerequisite, invalid test assumption, tool/schema failure, scope/size,
context, timeout or provider failure. More time/thinking is not itself a diagnosis.

An assertion failure proves a mismatch, not which side is wrong. Use selected
test setup and observed values to check the original frozen acceptance. Review
prior corrective assumptions as hypotheses; do not keep asserting the same
unverified cause after repeated unchanged outcomes. Correcting a self-authored
test is permissible only when concrete evidence shows it contradicts the frozen
behavior, with equivalent or stronger coverage preserved. External acceptance
fixtures and frozen test commands remain immutable. If the required correction
cannot fit these constraints, report the contradiction and stop for user review.
The frozen tests field fixes command argv; it does not promote every fixture
value in an editable, never-accepted test file into a user requirement. A prior
repair calling a test "frozen" does not change this distinction. Names and shadow
descriptions are not proof of numeric boundary behavior. If referenced test setup
is absent, request an executable observation rather than assuming it is correct.

Use execution_audit when supplied: it contains actual mutation/compaction counts
and recent tool errors, without implementation bodies. Repeated source rewrites
with no test execution are a workflow failure, not evidence of failing behavior.
Make creating the declared tests and collecting executable evidence an early
checkpoint before further speculative source revisions. Keep scratch diagnostics
inside declared files; dependency changes require a scoped replan.

Use execution_progress and context_pressure when supplied. They distinguish
unchanged rounds, repeated retrieval, compaction churn and new test outcomes.
Do not prescribe the same read/reason loop again: preserve useful retrieved
evidence, identify the next executable observation, and adjust context only from
measured headroom. More time or thinking alone does not resolve no_progress.
These diagnostics do not grant another repair allowance or relax acceptance.
When provided, effective_executor_controls includes limits inherited from the
profile that may not appear in the task. thinking_guard_observations distinguishes
forced budget closes from missing telemetry. Consider this evidence when choosing
a future reasoning cap; frequent cap hits alone do not justify increasing it.

Save failure_analysis: concise observed cause/evidence, uncertainty, the smallest
corrective approach and the tests that will demonstrate the fix. Use plan_store
with flat changes to the failed todo only: steps, test_strategy, assumptions,
estimated_changed_lines, context_overlay, execution, or additive tests/coverage/cases.
Do not send tasks, task_updates, IDs or a complete replacement plan. Python retains
all unchanged remaining contracts, exact acceptance objects and test argv, and
removes completed prerequisites while preserving their regression evidence.
Exact architecture_replacements may clarify decisions without rewriting the map.
Preserve completed behavior, immutable fixtures and authorized file scope. Do not
relax tests to pass a failure. Use measured admission evidence, including history
and safety margin, when adjusting the failed task's future input budget.
If the existing scope/contract makes a repair impossible, explain why and stop;
the native runner will ask the user instead of silently widening scope.

Python validates the repair plan and allows ONE automatic repair attempt for the
failed contract. A subsequent failure of that repair stops and asks the user.
Passing model prose does not count: frozen acceptance and regressions must pass.
