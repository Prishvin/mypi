# Second-pass task refinement

Review the selected task in the context of the original user request and whole
current plan. This is a planning review, not implementation or a new architecture
from scratch. whole_plan contains the current architecture and every task's goal,
dependencies, files, acceptance, tests and coverage. The selected task's entry
points to current_task, its full contract; read it there. Prerequisite contracts
are already present in whole_plan, including previously refined or split tasks.
Do not request a second copy of them or a superseded original draft. Python
retains the original draft and enforces preservation and unchanged-task guards.
All coverage strategy, checks, requirement links and gaps remain in coverage_plan.

Check concrete API/signature agreement with producers and consumers, missing
integration behavior, contradictory fixtures, executable nonempty tests, file
ownership, realistic patch size and context/output/thinking budgets. Keep only
the context needed for this task. Prefer 60–150 changed lines including tests;
300 is a ceiling. Consider data-heavy levels/fixtures as real output, not free
work. Do not allocate authored architecture notes to routine implementation of
an existing decision; Python maintains interfaces automatically.

Refine the selected todo's steps, test strategy, assumptions, estimates and
budgets. Add concrete missing acceptance/tests if needed. Correct a contradictory
unaccepted criterion only with its exact old/new objects and a specific reason.
Preserve user requirements. Do not edit unrelated tasks or read implementations.

If it will not fit one atomic edit, split into 2–4 coherent, independently tested
tasks. Keep the original todo ID on the FINAL child. Every child depends on the
original prerequisites and every preceding child, so consumers wait for the
whole split. Preserve the union of all original files, cases and test commands.
Put combined tests only in a child whose prerequisites create the needed files;
earlier children need their own runnable tests. Include a full V3 contract per
child, including context estimates/margin, execution policy and coverage.

For ordinary refinement, call plan_store with changed fields DIRECTLY:
steps, test_strategy, assumptions, estimated_changed_lines, context_overlay,
execution, criterion_replacements, add_files, add_tests, add_acceptance and
add_coverage. Python injects the selected ID. Do not send id, task_updates,
replace_with, status or whole task contracts. Omit unchanged fields. For example:
{"context_overlay":{"max_input_tokens":16384},"add_coverage":[{"criterion":"existing criterion ID","test":0}]}
Replace example values with your reviewed estimates and actual case IDs.
Use unchanged:true alone if the task needs no changes.

For a split, call plan_child_store ONCE PER CHILD with a full V3 task's fields
at the top level. Children use context, files, tests, acceptance and coverage.
The tool validates and stores the child, returning child_ref. It does not publish
or execute a plan. Then call plan_store with child_refs containing the 2-4
returned receipts in dependency order, plus optional architecture_replacements.
Do not combine child_refs with direct changes: put those in the child contracts.
If a child fails validation, correct and resend just that child. If final commit
fails, valid child receipts remain usable; stage corrected children and commit
the complete ordered receipt list again. Never invent receipts.

Send real JSON arrays and objects. Every top-level parameter has a direct type.
Each ordinary plan_store starts from the pinned task, not prior rejected edits:
resubmit ALL intended changes together after rejection. Python preserves every
untouched contract and assembles the complete plan without inventing task content.
Read coverage_plan: incorporate every gap assigned to this task with the exact
case, test argv and matching coverage; add fixture files to scope as needed.
Python rejects a refinement that leaves any assigned gap unaddressed. Preserve
the global testing strategy and check producer/consumer integration contracts.
Check module growth: prefer <=4096 source tokens, ceiling8192 plus300 lines/32KiB.
The complete file(s), tests and tool overhead must fit the task input with margin.
Split by responsibility when needed; architecture documents use selected sections.
Exact architecture_replacements may reconcile an affected API while preserving
unrelated decisions. Python validates and assembles the plan. Stop after a
successful plan_store, never after merely staging a child.
