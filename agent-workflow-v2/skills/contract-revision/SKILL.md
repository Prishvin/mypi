---
name: contract-revision
description: Propose an explicit correction to a contradictory unfinished generated contract.
---

This is a proposal for user review, not permission to edit code or execute it.
Review the selected todo in the architecture and whole-plan context. Preserve
the project goal, architecture interfaces, completed behavior, file scope, dependencies, exact test argv,
coverage IDs and all other todos. Do not read application implementation bodies.

Check each acceptance case's given, when and then together against the interface.
Read defaults as fallback values, not mandatory constants that discard supplied
arguments, unless the interface explicitly says otherwise. Do not invent stronger
initialization restrictions. Before saving, trace each changed example from its
stated initial values through every operation: check arithmetic, conserved counts,
units, bounds and any required preconditions. The given must describe one coherent
state; do not introduce unstated interventions to reach the expected result.
Compare the proposal with every unchanged acceptance case, not just the failing
assertion. Recheck these consistency questions independently after drafting the
correction and before plan_store.
Changing a test's starting fixture while retaining a conflicting acceptance given
does not satisfy the criterion. If a generated case is contradictory, propose the
smallest coherent correction explicitly; do not hide it in assumptions or test
instructions. Prefer preserving intended behavior over merely matching a failure.

Call plan_store with flat criterion_replacements entries containing exact old and
new cases with the SAME ID and an evidence-based reason. The native tool supplies
the selected task ID. Update steps, assumptions, test_strategy and context_overlay
as needed to implement and verify the corrected contract. Do not split tasks, add
files, change goal, architecture text or test commands, or edit other todos. Every new criterion must
remain complete and observable. Explain why the correction preserves project intent
and what tests must distinguish correct behavior from the prior contradiction.

The proposed plan remains non-executable until an explicit approval command binds
its exact digest. Python preserves the original evidence, both criterion versions,
accepted regression lineage and original size baseline. If a coherent correction
requires broader scope or changed user intent, stop and report that requirement.
