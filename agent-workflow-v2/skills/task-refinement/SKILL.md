# Second-pass task refinement

Review the selected task in the context of the original user request and whole
draft. This is a planning review, not implementation or a new architecture from
scratch. The packet contains every draft task's goal, dependencies, files,
acceptance and tests; the selected task has its full current contract.

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

Save ONE sparse plan_store call: task_updates contains exactly ONE object with
the selected ID. Combine all its changes into that object, never two objects with
the same ID. The current_task is a full contract to read, not the patch format.
Use context_overlay for changed context fields (never context), and add_coverage,
add_tests, add_files and add_acceptance to append entries (never coverage, tests,
files or acceptance). Omit unchanged values. For example:
{"task_updates":[{"id":"selected ID","context_overlay":{"max_input_tokens":16384},"add_coverage":[{"criterion":"existing criterion ID","test":0}]}]}
Replace the example IDs and values with this task's actual requirements; do not
copy example budgets. Split children go in replace_with inside that one object;
each child is a full V3 contract and therefore uses context, not context_overlay.
Read coverage_plan: incorporate every gap assigned to this task with the exact
case, test argv and matching coverage; add fixture files to scope as needed.
Python rejects a refinement that leaves any assigned gap unaddressed. Preserve
the global testing strategy and check producer/consumer integration contracts.
Check module growth: prefer <=4096 source tokens, ceiling8192 plus300 lines/32KiB.
The complete file(s), tests and tool overhead must fit the task input with margin.
Split by responsibility when needed; architecture documents use selected sections.
Use replace_with for a split; otherwise supply only changed fields. An unchanged
task is acknowledged with {"id":"selected ID"}; do not manufacture changes.
Add acceptance with add_acceptance and matching add_coverage/add_tests. Exact
architecture_replacements may reconcile an affected API, preserving unrelated
decisions. Python validates and assembles the plan. Stop after a successful save.
