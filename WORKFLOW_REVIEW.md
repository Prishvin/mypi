# Review: efficient local Qwen execution

The design remains a deterministic scheduler around small, fresh Pi workers. Qwen decides what to build and how to repair it; Python owns navigation, context admission, task scheduling, evidence, acceptance and recovery. Reusable procedures belong in skills and load only for their role or task. These rules apply to private mypi sessions, not Codex.

## Responsibilities

| Stage | Model judgment | Native work / skill |
| --- | --- | --- |
| Intake | Classify intent; ask at most two clarifications; consolidate requirements | Persist answers, route settings directly, bind workspace |
| Research | Identify unknowns; distill relevant facts and exact source evidence | Search, fetch, extract bounded content, retain artifacts |
| Navigation | Select relevant decisions/interfaces | Parse architecture, build compact map/shadow, literal keyword/symbol search, verify hashes |
| Planning | Define architecture, atomic tasks, acceptance, dependencies and budgets | Validate contracts, estimates, scope, fixtures and context caps |
| Execution | Implement one frozen behavior and interpret failures | Fresh worker, selected packet, scoped retrieval, maintained navigation |
| Finalization | Supply a brief new decision only when required | `task-finalize`: frozen tests, current receipts, scope/size checks, bounded feedback, stop on acceptance |
| Recovery | Replan when requirements/contracts are inadequate | Resume interruption or explicitly retry unchanged work with preserved baselines |
| Review | Identify missing behavior/tests and propose a follow-up plan | Present actual results; do not execute follow-up work automatically |

## Issues found and changes

1. **Tests passed but finalization stalled.** The first game task had 15 passing tests, but no required architecture insertion receipt. Qwen had to discover a separate multi-call procedure. `workflow_test` now accepts the decision text and invokes a fixed native skill in one call. Passing source should remain untouched.
2. **Unrelated instructions increased every prompt.** Browser/game guidance moved into a task procedure. Coding and architect skill selections are now separate. Core instructions retain scope, context and acceptance boundaries; other procedures stay available through the catalog.
3. **Premature/noisy test feedback grew history.** Automatic tests wait for declared new files. Current evidence is reused. Full logs stay local, with a bounded actionable summary in tool feedback.
4. **Ordinary recovery required full replanning.** An explicit operational retry preserves all behavior contracts and original task baselines. It refuses changed source, altered immutable fixtures and failures that require architectural replanning.
5. **Deadlines were rigid and cleanup incomplete.** The task ceiling is now 45 minutes, with shorter planning defaults for small work. Interrupting a fixed skill cleans up its owned child process group. The outer task deadline still limits the whole attempt.
6. **Node test totals were unobserved.** Native accounting recognizes Node TAP/spec totals, including ANSI output and zero-test results. Passing process exit alone cannot hide observed zero-test discovery.

## Context and task policy

- Keep the server at 98,304 tokens. Treat that as capacity, not a request target.
- Give each todo a fresh session, selected architecture sections, interfaces, exact relevant source and bounded failure evidence. Do not replay an earlier full chat.
- Above the 32,768-token architecture/shadow threshold, navigate through the compact map and selected sections. The full symbol registry remains local.
- Budget input, total output and thinking separately, with at least 25% admission margin. Output includes reasoning and tool arguments.
- Prefer 60–150 changed lines per atomic todo where that preserves coherent behavior. The existing 300-line patch gate remains an upper bound, not a target.
- Do not require an authored architecture note for routine implementation of a decision already in the accepted plan. Automatic interface metadata still updates after every edit.
- Skills contain procedures and bounded scripts. Hard scope, fixture, context and acceptance enforcement remains in Python; moving it into model instructions would weaken reliability.

## Measurement

Using the same bundled tokenizer, **coding rules plus default skill instructions decreased from 3,969 to 1,601 tokens (59.7%)**. This excludes Pi's base prompt, tool schemas, the selected task packet and conversation history. It is a measured reduction in fixed instruction material, not a claim of 60% faster end-to-end execution.

The stopped pilot spent 1,200.892 seconds on its first math/RNG task. It ended with 15 passing tests and one missing architecture receipt. That establishes a finalization failure; it does not establish that the model was incapable of the coding task. Real retry observations and current platform check totals are recorded in [VALIDATION.md](VALIDATION.md).

## Remaining limits and next decisions

Native gates verify declared evidence, not whether the plan captures every user expectation. An independent reviewer and real browser checks remain necessary for the game. A procedure checklist is not proof of a completed test.

Long plans can still consume substantial output and prefill time. Sparse repair already avoids regenerating rejected proposals; further optimization should be based on measured planner/worker request totals and time to acceptance. Do not increase thinking caps, add models or load more context simply because capacity remains.

The next pilot uses two-pass planning: architectural draft, a dedicated coverage review, then one fresh review per original task. Coverage decisions and task splitting are model work; reference validation, preservation, gap enforcement, checkpointing and publication are Python. Failed coding tasks now receive a separate measured architecture/shadow/evidence review and one automatic corrective attempt; a second failure asks the user. The Qwen→Qwen pilot runs first. These changes require live evidence before claiming better game completion or overall speed.

The skill runtime bounds processes, output and declared inputs but is not an OS sandbox. Session artifacts are local and immutable task fixtures remain protected by the workflow. General semantic architecture changes still require a model-authored decision; native maintenance must not invent one.
