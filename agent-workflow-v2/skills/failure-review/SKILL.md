---
name: failure-review
description: Diagnose a failed atomic task against evidence, architecture, shadow and plan.
---

Review the failed todo before prescribing a repair. Inspect the supplied failure
evidence, architecture, prototypes and original plan overview. If context selection
omitted a needed contract, retrieve only relevant architecture sections/prototypes.
Do not read or upload implementation bodies and do not edit source in this role.

Distinguish observed facts from hypotheses: implementation bug, contradictory API,
missing prerequisite, invalid test assumption, tool/schema failure, scope/size,
context, timeout or provider failure. More time/thinking is not itself a diagnosis.

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
