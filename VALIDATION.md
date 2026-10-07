# Release verification

## Thinking panel, copy controls and source retrieval — 2026-10-07

All **388 macOS checks pass** (287 workflow Python, 22 web, 11 host, 68 JavaScript). New reasoning-stream tests cover incremental deltas, duplicate final events, request/attempt transitions, stopped state, partial UTF-8/JSON, rotation, byte/text bounds and exclusion of prompts/tool arguments/answers. Real Chrome checks passed for collapsed/open state, refresh persistence, active-task binding, safe plain-text display, reading position, desktop/mobile layout and clipboard copy through the HTTP LAN fallback.

The observed `source_query({action:"fixture",paths:["src/engine/levels.mjs"]})` failed because `query` was unnecessarily required and the caller used fixture mode for project source. Explicit bounded `file` reads now need no query; that legacy fixture request is served as a bounded project page with corrective guidance. An exact read against the actual pilot source succeeded. Tests prove external fixture pin/hash checks, path boundaries and byte limits remain enforced. The interrupted original task and rejected calls remain in its evidence history.

## Latest: local-Qwen efficiency and executable finalization — 2026-10-07

| Check | macOS Apple Silicon | Linux ARM64 Docker |
| --- | ---: | ---: |
| Workflow Python | 276 passed | 276 passed |
| Web Python | 22 passed | 22 passed |
| Host artifacts/guards | 11 passed | 11 passed |
| JavaScript | 66 passed | 66 passed |
| **Total** | **375 passed** | **375 passed** |

New coverage exercises the actual `task-finalize` skill with CPU tests: pending deliverables, preserved source/prose, current test reuse, idempotent notes, failed tests blocking publication, scope/role/insertion restrictions, bounded verbose failures and retained local logs. It also checks unchanged-contract retries, baseline/fixture/source guards, task-specific procedure loading, Node test totals and cleanup of a running skill when its parent is terminated. Python's selector can swallow an `InterruptedError`; the cleanup signal now raises a distinct exception, and the real subprocess regression passes on both platforms.

Coding rules plus default skill instructions measure 1,601 tokens versus 3,969 before (59.7% less), using the same bundled tokenizer. This excludes framework/tool schemas, task packets and history. The isolated Docker test VM was stopped after verification.

The live local-Qwen retry **accepted T1 in 107.409 seconds**, with **one model request, one `workflow_test` call and 15 passing tests**. All four source/test hashes were unchanged from its supplied packet. Qwen authored the brief missing architecture decision; Python inserted it, refreshed navigation and verified the gate (291 changed lines, zero violations), then stopped before another request. The scheduler advanced to T2. This completes existing work; it is not a fresh implementation benchmark against the original 1,200-second attempt.

Native measurements: 10,305 uncached prompt tokens, 254 output tokens, 53 provider-reported reasoning tokens, 90.47-second cold first-token delay, 114.04 tok/s prefill, 19.71 tok/s decode and 34.57 GiB active backend allocation. Settings stayed at 98,304 server capacity, 65,536 task window, 24,576 input cap, 16,384 output cap, 1,024 thinking cap and medium effort. Most retry time was cold prompt processing. Game correctness and playability remain subject to later tasks and independent browser checks.

## Original release verification

Measured on 2026-10-06. This verifies client portability and the existing Pi workflow; it is not a new model comparison.

| Check | macOS Apple Silicon | Linux ARM64 container |
| --- | ---: | ---: |
| Workflow Python tests | 159 passed | 159 passed |
| Web Python tests | 20 passed | 20 passed |
| Host artifact/guard tests | 11 passed | 11 passed |
| JavaScript tests | 46 passed | 46 passed |
| Total | **236 passed** | **236 passed** |

The Linux image installs its own Python 3.12 environment, Node 26, locked npm dependencies and Python packages. It needs `procps` for cancellation and same-host RSS sampling; the Dockerfile includes it. Cancellation treats exited zombies as stopped and waits for live owned descendants after sending signals. macOS uses a separate clean virtual environment and local npm installation. GitHub Actions repeats these CPU checks on macOS and Ubuntu; release measurements above are local runs, not a claim about completed CI.

## Genuine Linux Pi → Mac Qwen proof

A Linux Pi worker connected over HTTP to Qwen on the model Mac. It received one frozen task: repair `double(value)` while preserving the signature and satisfying numeric, keyword, sequence and invalid-input acceptance cases. The external acceptance fixture remained immutable.

| Measurement | Result |
| --- | --- |
| Atomic correctness | Passed all four acceptance tests |
| Changed source | Only `arithmetic.py` |
| Fresh shadow / final scope gate | Passed; no violations |
| Total execution time | 85.668 seconds |
| Model requests | 1 |
| Native input / output tokens | 7,473 / 373 |
| Reported reasoning tokens | 276 |
| Native prompt processing | 114.623 tokens/s |
| Native generation | 23.086 tokens/s |
| Native first-token delay | 65.585 seconds |
| Sampled model process RAM peak | 33.724 GiB |
| Native allocation high-water mark | 41.549 GiB |
| Server capacity / worker window | 98,304 / 32,768 tokens |
| Worker input / total output limits | 16,384 / 8,192 tokens |
| Reasoning / thinking cap | Medium / 512 tokens |
| Generation / KV | MTP3 / normal KV |

RAM is sampled process RSS; native allocation is a separate backend high-water metric and can include earlier work. The cold first-token delay includes processing the actual selected prompt, not preallocating the entire 96k context. This was a single smoke test, with a 2 GiB Linux VM running on the model host; it does not establish broad speed or quality rankings.

Run a fresh live proof when the Qwen server is idle:

```sh
MYPI_SERVER_URL=http://YOUR_SERVER:8000 \
  agent-workflow-v2/.venv/bin/python examples/smoke.py /new/evidence/directory
```

The script creates an isolated project, a bounded task, immutable tests, progress logs, memory samples and a measured result. It copies session evidence outside the ephemeral worker location. No production project is edited.

## Connection and UI verification

- Real HTTP tests verify endpoint identity/capacity, rejected changes preserving the previous setting, bearer authentication, exact forwarding of thinking/output controls, streaming completion and same-host RSS.
- A genuine Pi RPC session ran `/server IP:8000` without a generation request. Its actual model registry and active model refreshed to the LAN `/v1` base, retaining 98,304 capacity.
- The mypi web UI created a new conversation, handled `/server`, showed the saved endpoint in chat and deleted the test conversation. The original UI on 8099 remained running.
- Repeating the gateway start command reused the gateway. The existing native model PID and generation settings remained unchanged.
- The publication audit excluded private auth, endpoint preferences, sessions, user projects, model weights, logs and installed dependencies. The bundled text tokenizer has an attribution, license and SHA-256 manifest.

## Reproducible host setup

The host installer was run in a fresh private Python 3.12 environment. All pinned dependencies installed; the installed MTPLX 2.12.2 server matched the reviewed SHA-256 and the adapter import/help probe passed without loading weights. A second default-path installation passed the same gates.

All 21 existing pinned checkpoint files, 29,973,199,603 bytes total, passed their full byte checksums. The tensor index resolved 2,180 tensors and the MTP sidecar was present. Existing weights were reused rather than redownloaded. A separate pinned Hugging Face download of generation_config.json passed its Git-blob checksum. Fixture tests cover sequential resume, corrupt/partial-file repair, index/sidecar failures and path boundaries.

`mypi qwen start` and `mypi serve --start-qwen` reused the existing compatible model and LAN gateway. Its PID and 96k/MTP3/normal-KV settings stayed unchanged. The new guard’s pressure/swap thresholds and refusal to stop another launcher are tested; a second cold full-model launch was not performed while the current instance remained in use.

## Architecture maintenance and navigation — 2026-10-07

CPU verification ran against this implementation on macOS Apple Silicon and a rebuilt Linux ARM64 Docker image. No model inference was needed for these checks.

| Check | macOS | Linux ARM64 |
| --- | ---: | ---: |
| Workflow Python | 217 passed | 217 passed |
| Web Python | 21 passed | 21 passed |
| Host artifacts/guards | 11 passed | 11 passed |
| JavaScript | 55 passed | 55 passed |
| Total | **304 passed** | **304 passed** |

New coverage includes nested/duplicate/Unicode/Setext headings, fenced code, source line shifts, literal file/symbol associations, ambiguous names, compact search beyond displayed representative names, bounded long-line reads, stale document/section hashes, selective todo packets, preservation of authored prose and CRLF, atomic compare-and-swap insertions, two simultaneous native writers, failed refresh recovery, scope/root/role restrictions, change types, missing-map bootstrap, no-op maintenance, stale artifact detection, native rebuild verification, required decision receipts and the real fixed skill pipelines. Hook checks cover successful/partial failed edits, automatic tests, mutation mutexes, explicit rebuild and owned research publication. The web rebuild test verifies no classifier, model startup or inference call.

The read-only upserver size proof used 110 source files and 3060 locally indexed function/class names. Its architecture was 37820 tokens; the compact Markdown map was 11375 (69.9% smaller). The complete JSON registry stays local and is searched in bounded pages. This is a real-project size example, not a guarantee that index overhead is smaller than a tiny architecture document. Section associations use literal filenames/directories and unique symbol mentions; they do not prove architectural meaning.

Skills and hooks apply only to private mypi sessions. Existing sessions retain their pinned runtime; start a new session after upgrading to use this implementation.

### Research recovery observed in the game pilot

The first local-Qwen game research attempt stopped at its 300-second limit after two noncontiguous evidence quotations were correctly rejected. Errors now identify the offending finding/artifact and explain how to copy a short exact phrase without punctuation edits or joined fragments. Research instructions distinguish exact evidence from paraphrased claims and documentation from implementation pointers. Two new regression tests retain strict rejection and prove actionable diagnostics; 23 focused checks and the full **306-check macOS suite** passed after the change. The original 304-check Linux run predates this diagnostic improvement.

The next attempt exposed research-role confusion and excessive pre-tool reasoning. Research now receives the later development request as structured task data, explicitly separate from the current role. Local research stays at medium effort with a request-local 1024-token thinking cap; memory keeps its 512-token/low setting, and cloud/intake settings remain independent. Four additional phase tests and the full **310-check suite** pass on both macOS and a rebuilt Linux ARM64 Docker image (223 workflow Python, 21 web Python, 11 host checks, 55 JavaScript on each). The live local research retry then passed in 227 seconds with three requests and no tool/citation rejection. Architecture planning and the game pilot continue separately.

The first detailed architecture attempt timed out while steadily generating a buffered plan. Provider-completed usage omitted that interrupted 14,450-token request. Metrics now preserve native request/completion totals and cancellation flags separately, and explicitly mark unavailable process RSS. A regression fixture reproduces this partial-generation case. The full suite passes **311 checks on both macOS and a rebuilt Linux ARM64 Docker image** (224 workflow Python plus the preceding web/host/JavaScript counts on each). The game pilot retries planning with a project-local 2048-token thinking cap and a longer deadline without reducing feature scope.

### Sparse proposal recovery and architecture handoff

The live local-Qwen pilot produced a complete 15-task proposal but omitted changed-line estimates because the authoring schema incorrectly marked them optional. The schema now requires them. A sparse draft-repair mode pins unaccepted proposal/source hashes, preserves unchanged cases/files/test commands, validates splits and records explicit reasons for correcting contradictory unaccepted criteria. Executed work continues to use strict evidence-bound replanning. New-project execution publishes the accepted Qwen-authored architecture with Python-generated navigation headings; workers retrieve future module contracts before implementations exist. Existing architecture remains unchanged.

All **330 checks pass on macOS and rebuilt Linux ARM64 Docker**: 241 workflow Python, 21 web Python, 11 host checks and 57 JavaScript on each. This verifies workflow plumbing and failure boundaries; the game's source and real browser behavior are tested separately in the pilot. The isolated Docker VM is stopped after verification.

The architecture publisher now uses atomic non-replacing publication, with crash/concurrent-writer fixtures. A real MTPLX tool call joined serialized JSON parameters into one string; the compatibility decoder preserves literal JSON data, rejects duplicate/conflicting keys and verifies redundant split metadata rather than inventing estimates. All **334 checks pass on both macOS and rebuilt Linux ARM64 Docker** (245 workflow Python, 21 web Python, 11 host, 57 JavaScript on each). The original failed tool output is preserved in the pilot evidence.

### Built-in granular run monitor

The dashboard is shared by `mypi monitor` and web conversation run links. All **352 checks pass on macOS and a rebuilt Linux ARM64 Docker image**: 259 workflow Python, 22 web Python, 11 host checks and 60 JavaScript. New checks cover completed/replanned lineage, interrupted/failing/blocked status, preserved atomic contracts, stale test evidence, actual file hashes, outside-root symlinks, partial/oversized/wrong-shape JSON, bounded JSONL tails, tool-error source redaction, completed tool calls versus accepted tests, RSS sample availability, telemetry request-ID filtering/cache/privacy, CLI routing without model startup, read-only HTTP/asset/host/origin boundaries and conversation integration.

Chrome exercised the actual 17-todo Qwen game run through the built-in viewer: desktop and mobile layouts, filters, task selection and reload/share hashes, acceptance coverage, exact test commands and live refresh. No JavaScript errors or mobile horizontal overflow occurred. The LAN status route was also verified. These checks prove the monitor's behavior; the displayed game remains subject to its own coding and acceptance gates. The viewer polls metrics only and does not submit inference requests. Accepted counts reflect durable runner evidence; individual planned steps are not claimed complete without evidence.

The light-theme refinement adds a sticky current-step summary and a jump-to-task control. Actual tool/model phases and native stopping reasons remain independent of the selected todo; completed actions are labeled historical and planned step numbers are not guessed. Interrupted/replanning clocks freeze at the recorded checkpoint. The updated macOS suite passes **359 checks** (260 workflow Python, 22 web Python, 11 host, 66 JavaScript); the preceding 352-check Linux run predates this refinement. Chrome verified the live stopping reason, independent selection/jump, sticky header, desktop/mobile layout, prompt/thinking/tool/queued transitions, no horizontal overflow and no JavaScript errors. Transition responses were browser fixtures, with no new generation requests or changes to the game run.

### Two-pass planning, coverage and bounded recovery — 2026-10-07

All **429 checks pass on macOS and a rebuilt Linux ARM64 Docker image**: 325 workflow Python, 23 web Python, 11 host checks and 70 JavaScript. The isolated 2-CPU/2-GiB Docker profile is stopped before restarting live Qwen work. A Linux fixture initially relied on distinct rapid filesystem mtimes; the test now assigns explicit ordered timestamps.

New tests exercise draft/coverage/task sequencing, complete acceptance and requirement references, observable gap requirements, exact gap incorporation, preservation across task splits, dependency completion, source/checkpoint drift, provider/request identity, interruption/resume without replay, atomic publication recovery, CLI/web handoff, planning progress and rejection of unreviewed drafts. Model transport is simulated in unit tests; native bindings, plan assembly, validation and filesystem checkpoints are real.

Recovery fixtures verify one automatic evidence-reviewed repair, success/final-target forwarding, interruption of that same repair, durable user escalation on a second failure and a separate allowance for a different failed todo. Context fixtures prove small-project architecture/prototypes are included without source bodies; a larger architecture is selectively retrieved for Qwen and fits the larger cloud review policy. Native file checks enforce independent line/byte/token ceilings, legacy shrink-only handling, shadow size metadata and omission of oversized whole-file prefetch. Cloud request admission preserves xhigh and rejects an oversized full payload; no new subscription benchmark was run.

The preceding UI/retrieval change passed actual Chrome checks for collapsible thinking, task/status/error copy buttons, safe rendering, retained expansion/scroll, mobile layout and both localhost clipboard and insecure-LAN fallback. The original missing-query fixture call was replayed successfully against the owned pilot source using bounded project-file retrieval. Live model output and game correctness remain separate from these workflow tests; the next pilot uses Qwen for every planning/review/execution stage.

The fresh Qwen→Qwen pilot started in an isolated project after these checks. Its actual draft session is local MTPLX Quality, 98,304 context, 57,344 input ceiling, 32,768 output ceiling, medium effort and a 2,048-token thinking cap. Native telemetry reported a 9,905-token prompt; the 96k window was not filled artificially. Chrome verified the live planning title, distinct coverage task, LAN copy control, thinking expansion and mobile width without script errors. Coverage/refinement and final game acceptance were still pending at this observation; no completion or speed/quality improvement is claimed.

### Long draft visibility — 2026-10-07

The first local draft continued generating at about 19 tokens/s while Pi awaited
complete tool arguments. The monitor now identifies draft generation, includes
the live rate in its current-step summary, and explicitly states that implementation
has not started. Active planning limits come from the recorded session launch;
execution still displays its frozen contract. Missing measurements remain unknown.
Focused verification passes 25 Python monitor/thinking checks and 11 JavaScript
monitor checks. Chrome verified increasing live tokens, actual input/output/thinking
limits, the 30-minute attempt deadline, desktop/mobile layout and no script errors.
Only the monitor was restarted; the model and planning request continued unchanged.
The initial draft still contains a complete V3 plan before coverage and per-task
refinement. Its long generation time remains a planning efficiency issue, not a
completed implementation or a measured percentage of game progress.

### Rejected plan transport and recovery — 2026-10-07

The live draft failed after 1,457.885 seconds. Its `tasks` parameter was a
59,455-byte string containing malformed JSON: one `depends_on` key lacked a
closing quote and colon. Pi's array coercion reported `tasks.0: must be object`.
It then echoed the full proposal in the error, and the following admission check
rejected 75,734 estimated tokens against the 57,344 input cap. This was a real
invalid plan followed by a feedback/context failure, not a model-load timeout.

The full-plan schema now allows a literal JSON task array to reach Python's
strict decoder. Malformed JSON gets a bounded position/excerpt diagnostic;
duplicate keys, nonfinite constants, excessive nesting, oversized encodings and
non-object tasks are rejected. Native task, scope, budget and acceptance gates
remain mandatory. Rejected proposals/errors stay on disk. Tool-result feedback
is bounded, and a context hook covers Pi schema failures that bypass result
hooks, without changing original session evidence or unrelated providers.

All **332 workflow Python tests and 74 JavaScript tests pass on macOS**. New
checks include the actual installed Pi validator and tool-call lifecycle,
native persistence, untouched input, missing JSON punctuation, rejected
contracts, evidence retention and repeated context preparation. These changes
have not received a new Linux Docker run.

A fresh private Pi/Qwen request repaired only the missing quote and colon:
3,173 input tokens, 230 output tokens, 39.788 seconds including startup/prefill.
All 20 model-authored tasks were preserved and passed native plan validation.
The original failure, correction and metrics are retained in the pilot report.
The same plan checkpoint resumed with the validated draft; coverage and all
20 task refinements are still required before implementation can start.

### Coverage progress visibility — 2026-10-07

The resumed coverage request continued generating (5,229 to 8,350 output tokens,
about 20 tokens/s); no coverage validation result had arrived. It reviewed
100 existing acceptance cases across 20 tasks in one buffered tool response.
The monitor now names coverage/refinement generation explicitly and explains
that partial arguments are unavailable until delivery. Native tool/answer/prompt
phases override a stale Pi thinking-stream flag; the original thinking text stays
available. Thirteen monitor unit checks and a live Chrome check passed, including
increasing token counts, the corrected thinking label and mobile width. No model
request was restarted. This is a display correction, not a coverage acceptance
or a reduction in the large response's generation time.

### Implementation preview and saved planning results — 2026-10-07

The monitor now offers separate Planning and Implementation queues. During
planning, the implementation preview follows the latest hash-bound saved plan,
including task splits, and always remains Awaiting planning. Preview rows never
increase execution acceptance or claim tests have run. Completed planning rows
show their own saved draft, coverage matrix/gaps, or refinement contracts and
before/after changes. Once execution starts, the completed planning pipeline is
retained only when its project and draft hash match the execution plan.

Focused checks pass: **31 Python monitor/results/thinking tests and 14 JavaScript
monitor tests** on macOS. Chrome exercised the actual 20-task draft, completed
draft/coverage/refinement results, expanded-section persistence, implementation
share-link reload, current-step navigation and mobile width, with no script
errors. A browser response fixture verified the transition to implementation
while retaining completed planning results. No model work was restarted, and no
game implementation acceptance is implied by these UI checks.

### Sparse plan save diagnostics — 2026-10-07

Weapons refinement rejected two plan_store calls because full-task `context` and
`coverage` fields were used in a sparse patch. Qwen corrected them and the third
save passed; planning advanced to enemies. The original rejected artifacts remain
unchanged. Native errors now name unknown fields and explain `context_overlay`
and additive alternatives. Tool schema descriptions clarify these fields. The
monitor shows the final Python exception before traceback frames, retaining
bounded output and argument/source redaction; complete logs remain available.

Verification: **45 Python tests and 7 Pi integration tests pass**. Replaying both
rejected payloads through the pure patch function produces specific corrections
without modifying the saved plan. Reading the retained tool log confirms two
historical failures followed by the successful save; the live monitor reports
weapons review Accepted and enemies review Running. Only the monitor was restarted.

### Bound task refinement schema — 2026-10-07

Enemy review submitted two entries for the same selected task, then an unsupported
`context` patch field, then coverage referencing nonexistent acceptance ID `G`.
The native gates rejected these calls. Qwen corrected them; its fourth save was
accepted and the pipeline advanced to spawn review without a restart.

New sessions derive the tool schema's literal todo ID and one-entry limit from
the pinned draft binding. Unknown patch properties are rejected by Pi, while
serialized adapter input still passes through the independent Python guards.
Native scope errors list received IDs and explain how to combine changes. The
refinement skill distinguishes full task contracts from sparse patches and split
children. Coverage schema text requires exact existing or newly added IDs.

Verification: **37 Python and 8 JavaScript tests pass**, covering duplicate IDs,
wrong targets, typed and serialized patches, unknown properties without silent
dropping, unchanged-task acknowledgements, split children, generic multi-task
repair, native validation, checkpoint resume and immutable session runtimes.
Spawn review already had the preceding field-diagnostic fix; the tighter schema
will take effect in the next newly created session. Existing runtimes and model
work were not modified or restarted.

### Planning prompt mode separation — 2026-10-07

Inspection found that pinned task/coverage reviews also received both the initial
create-plan request template and system instructions to save a full plan. These
conflicted with their sparse or coverage-only tool schemas. New pinned sessions
use dedicated architect review rules and a mode-specific request wrapper. The
granular planning skill explicitly distinguishes full resulting contracts from
sparse patch arguments. New draft generation retains its full-plan instructions.

Verification: **47 Python and 9 JavaScript tests pass**. Actual launch preparation
for draft, generic repair, selected-task refinement and coverage selects compatible
prompts. Pi system prompt hooks are checked for local and cloud planners, and the
new review rules are copied and hashed into immutable session runtimes. No game
contract, acceptance test or implementation was authored or changed by Codex.

An additional system-prompt check found coding-only rules were prepended to all
architect sessions. Architects now receive only their planning mode's rules;
executors keep their coding rules, test-gate instructions and tools. The actual
Pi hook regression covers both planner providers and unchanged executor rules.

The rejected pickup review was interrupted through the planning CLI and resumed
through mypi at the same checkpoint. Nine accepted reviews, the saved plan hash
and source snapshot were preserved. Rerun `review-10-attempt-11` passed in 434.13
seconds after Qwen corrected one context-margin rejection; ten task reviews were
then accepted. The next live request was verified to contain review rules with
neither full-plan creation directives nor coding-only rules. Review instructions
and sparse context schema now state the exact 25% margin formula used by native
validation. No model-authored values were filled in or adjusted by Codex.
Supervision decisions and periodic metrics are retained in the pilot's
`supervision.jsonl` alongside the original attempt evidence.

### Sparse split JSON diagnostics — 2026-10-07

T12 review submitted three malformed serialized task_updates calls. Sparse
decoding incorrectly tried its legacy joined-parameter wrapper after every JSON
error, shifting reported offsets by the wrapper length and emitting two Python
tracebacks. The decoder now tries joining only after a complete value followed by
extra data. Errors name the field, original character/line/column and a bounded
excerpt, with a lexical hint for mismatched brackets or parentheses. It rejects
duplicates, nonfinite constants, excessive nesting and invalid array shapes.
It never repairs values or guesses plan content.

Pi retains the full rejected arguments and error locally, while returning the
final diagnostic to the model. Retry guidance explicitly requires all intended
sparse edits because unsuccessful calls do not modify the pinned base. The
refinement skill clarifies nested array/object syntax. **46 Python tests and
10 JavaScript tests pass**, including native save rejection without publication
and unchanged preserved proposal data. All three actual rejected payloads were
replayed read-only and now report their original error positions. Eleven accepted
reviews and the source snapshot were preserved when stopping the failed T12 loop.

The fresh mypi/Qwen T12 review (`review-12-attempt-14`, session `b4e36ae7a8b3`)
passed its first plan_store call with no rejected calls in **329.292 seconds**.
Native telemetry recorded 26,162 prompt tokens (2,048 cached), 1,709 generated
tokens, 107.49 prompt tokens/s and 16.62 generation tokens/s. The pipeline moved
to T13 with 12 original reviews accepted. The prior 11 reviews and source snapshot
were verified unchanged. The model authored the successful proposal; Codex only
changed mypi tooling. Replay and rerun evidence are retained in the pilot report
as `t12-transport-replay.json` and `t12-transport-rerun-result.json`.

### Typed task review and staged split children — 2026-10-07

T15 failed again while submitting a 10,694-character nested patch. The installed
Qwen XML parser uses only a parameter's direct `type`; the advertised
array-or-string `anyOf` for task_updates had no direct type, so it arrived as text.
Previous diagnostic changes exposed the error but did not eliminate this fragile
model-facing format.

Selected-task reviews now submit flat typed fields. Python supplies the pinned
task ID and assembles the existing sparse representation. Splits use one
`plan_child_store` call per full child, followed by `plan_store` with ordered
immutable receipts. Each receipt binds the exact child to its session, draft and
source snapshot. Staging never publishes or executes a plan. Final commit keeps
all original preservation, dependency, coverage-gap and V3 budget gates. A
rejected child can be replaced without regenerating valid siblings. Generic
native patch artifacts remain readable; no malformed JSON or task values are
repaired. Initial whole-plan generation is unchanged.

**89 Python tests and 31 JavaScript tests passed.** These include reproducing the
old union-as-text behavior through the actual installed Qwen parser and an
end-to-end XML → Pi tool lifecycle → native staging → final save test. Tests cover
flat edits, no-op review, split receipts, exact value retention, source/draft
staleness, tampering, session replay, unknown fields, invalid budgets, incomplete
coverage, preservation failures and corrected-child retries. Child staging does
not trigger Pi's accepted-plan stop hook. Launch tests verify that only selected
task reviews receive the child tool and matching instructions.

Restarted T15 through mypi after checking the canonical saved-plan digest, all 14
accepted review IDs and the source snapshot against pre-interruption evidence.
No game contract, game source or game acceptance tests were authored by Codex.
Live rerun evidence is recorded under `t15-typed-*` in the pilot report directory.

During the live typed retry, Qwen made an unrelated architecture-section lookup
with pasted plan prose and no source hash. The adapter returned an irrelevant
locate/inspect/gate hint. Its diagnostic now names the required section ID and
source_sha256 and distinguishes supplied draft architecture from indexed source
sections. Ten architecture/navigation JavaScript tests passed. The active review
was allowed to recover by itself; no game-specific guidance was injected.

Live result: T15 `review-15-attempt-18`, session `56e3bf172cdf`, passed its first
plan_store call with **zero rejected plan calls**, in **514.011 seconds**. It made
one failed architecture lookup before recovering without intervention. Native
requests generated 3,669 total tokens at 17.23 and 16.11 tokens/s. Cold input was
30,589 tokens with 287.88 seconds to first token; the follow-up reused 31,758 of
31,786 prompt tokens and reached first token in 0.635 seconds. Native active
allocation was 35.66/38.32 GB; shared backend peak allocation was 46.98 GB (not a
per-request RSS measurement). The prior 14 accepted reviews and project snapshot
were unchanged. Mypi advanced to T16 with 15 of 20 original task reviews accepted.
The live retry used flat updates; staged split behavior was verified by the real
parser/Pi/native integration test, not by this particular model response.
Details: `t15-typed-validation.json`, `t15-typed-rerun-result.json`, and
`t15-typed-summary.json` in the pilot report directory.

### T20 context preflight recovery — 2026-10-07

Nineteen original task reviews passed, but T20 stopped before any model request:
its 29,083-token packet exceeded the old 28,000-token packet budget. This was a
client preparation limit, not model context exhaustion or a game-test failure.
The packet repeated the original whole-plan contracts, 19 current prerequisite
contracts, and old/new architecture text.

Task review now includes the current whole-plan contracts exactly once, points
the selected entry to its full current_task contract, and retains the complete
coverage plan and request. It removes superseded copies without truncating
acceptance cases, tests, producers, consumers or split children. Native original
contract preservation and all final-plan gates remain unchanged. T20's packet
is now **21,343 tokens**. Every invoked review writes a context-budget sidecar.
Errors report both measured packet size and the separate model window.

At the user's request, local planning packet/input limits increased to
**32,768 / 57,344 tokens**. The physical model window stays **98,304**, ordinary
review output stays **16,384**, and medium effort with a **1,024-token thinking
cap** remains unchanged. Recovery can still reserve 32,768 output tokens plus
8,192 additional tokens inside the same window. The actual serialized-request
admission check (including tools, 25% margin and template reserve) remains active.

**66 Python tests passed**, including current-contract retention, split and
consumer visibility, non-mutation, both provider boundaries, real-tokenizer
packet reduction, context sidecars, failure before a model invocation, and
resume of only the unreviewed task after a context-preparation failure. The
saved T19 plan digest and source snapshot were checked before resuming T20
through mypi. No game contract or implementation was authored by Codex.

### Reviewer versus future executor budget scope — 2026-10-07

The T20 review reasoning treated the live review's 16,384 output / 1,024 thinking
limits as mandatory settings for a future implementation todo with a valid larger
budget. The system prompt contributed directly: every role received the heading
"Effective task caps" and an instruction to follow the selected frozen contract.
Architects are still authoring/reviewing future contracts, so that wording mixed
two different scopes.

System controls now identify the current role and say "this model call only".
Architects/reviewers explicitly choose future task input, output, effort and
thinking budgets independently from the review session and the executor's own
supported limits. They must not copy or clamp task settings merely to match their
current caps. Coding sessions retain frozen-task/explicit-override semantics;
other conversation phases do not receive execution-contract instructions.
Refinement rules and the skill reinforce the same distinction. Backend controls,
validation bounds and model-authored task values were not changed.

**58 Python and 22 JavaScript tests passed.** Actual local/cloud prompt hooks cover
initial planning, refinement, final review and coding roles. Native plan saving
and worker profile resolution preserve both larger (32k output / 8k thinking /
xhigh) and smaller task budgets under a 16k-output / 1k-thinking / medium reviewer.
Invalid future budgets still fail the existing native gates. The affected T20
session was interrupted before a plan save; all 19 prior accepted reviews, their
current-plan digest and the source snapshot were preserved before resuming the
same mypi pipeline. No game implementation, contract or acceptance criterion was
authored by Codex.

### Monitor handoff and recovery queues — 2026-10-07

After all 20 task reviews passed, execution started but the browser retained its
last planning selection. The monitor now switches to the active implementation
todo at a planning-to-execution handoff and clears stale status filters. Normal
polls preserve explicit history selections; old unscoped review bookmarks open
execution, while explicit planning-history links still work.

Failure review previously replaced the visible queue with one review task and
no implementation preview. It now retains the coordinator's actual execution
queue, including acceptance, failures, blocked dependencies, test results, attempt
metrics and stopped clocks. The association is checked against project, stage,
plan and run location. Saved planning artifacts remain accessible. Recovery is
labeled as paused implementation, not as implementation that never started.

Validation: **32 Python and 20 JavaScript tests passed**, including handoffs,
bookmark behavior, filters, recovery evidence, completed lineage, historical
planning results and rejected mismatched recovery references. Static syntax and
diff checks passed. The live HTTP snapshot exposed all 20 implementation tasks
and 22 saved planning steps during Qwen's automatic T01 failure review. Browser
automation was unavailable, so visual rendering was not verified. Only the
monitor was restarted; model execution and game artifacts were not changed.

### Focused failure recovery — 2026-10-07

The original automatic T01 review exhausted its 1,800-second deadline while
serializing a complete remaining plan. Native telemetry recorded 28,031 output
tokens, but Pi received no complete tool call and published no repair plan.
That output was not accepted as a successful repair. The original 20-task plan,
failed task baseline and all generated source remained intact.

Recovery now exposes a typed flat patch for the failed todo plus failure_analysis.
Python preserves untouched contracts and assembles the remaining V3 plan. The
model may refine steps, retrieval, estimates, budgets and deadlines, or add tests
and coverage within frozen scope. It cannot replace criteria, expand files or
edit another todo. Source freshness, pinned original-plan hash, frozen fixtures,
V3 validation and regression lineage still gate publication. Existing complete
native recovery artifacts remain subject to the original full-plan gates.

The review prompt contains the failed contract, observed errors, admission
measurements, architecture/prototypes and one compact whole-plan overview.
Separate recovery system rules remove contradictory whole-plan generation
instructions. The private runtime pins those rules and schema with each session.

An explicit --retry-review retries a stopped review generation without rerunning
failed coding first or resetting the one corrective-execution allowance. It keeps
old artifacts and records the user authorization; completed plans and stale
source cannot use this path. A failed corrective execution still asks the user.

**72 Python and 13 JavaScript tests passed.** Checks include immutable-contract
preservation, completed lineage, original baseline handling, stale source/plan
rejection, context validation, bounded additive coverage, actual CLI publication,
private runtime rules, explicit retry accounting and the installed Qwen XML
parser through the real Pi tool lifecycle into native validation.

The live retry uses session 2bc8486181b9. Its evidence packet fell from **30,464 to
7,149 estimated tokens**, and the backend prompt fell from **39,064 to 12,612
actual tokens**. The request schema was inspected to confirm it advertises flat
recovery fields and no tasks array. Live publication/execution evidence follows.

Live result: Qwen's focused repair **passed and was published** as
`run-3/repair-2.json` in **506.724 seconds**. It corrected two rejected metadata
proposals (instruction/tool estimate below the 6,144-token floor, then task
input/output/reserve larger than its selected window) without changing source.
The schema now exposes the same estimate floor as the native validator, and
window errors report exact merged values and the required total.

Only T01's steps, assumptions, test strategy and context changed. All **19 other
contracts** and every task's frozen cases, test commands, files and coverage were
compared and preserved. The accepted T01 recipe uses a **24,576 input / 8,192
output / 65,536 window / 2,048 thinking** budget at medium effort. The shared
server remains at 98,304 capacity. The coordinator started Qwen implementation
from this plan; plan acceptance does not claim implementation tests have passed.

The review used three requests, **8,358 output tokens** total, at **19.84, 21.45
and 24.11 tokens/s**. First-token delay was 111.45 seconds for the initial
12,612-token prompt, then 1.71 and 1.46 seconds for cached correction turns.
Backend active allocation was 37.38–40.98 GB; shared peak was 46.98 GB, which is
not per-request process RSS. Measurements, unchanged-contract comparison and
both old/new review outcomes are retained in `focused-recovery-result.json` and
`supervision.jsonl` in the pilot evidence directory. The additional window-error
and retry-state regressions passed. No game implementation or task-specific
repair content was authored by Codex.

### Architecture revision feedback — 2026-10-07

In pilot session `e316369a202b`, Qwen read the architecture index, changed source,
then submitted an insertion using the old document hash. Automatic maintenance
had already refreshed the owned interface metadata. The stale-write check
correctly rejected the insertion. Qwen reloaded the index, retried successfully,
and T01 passed all six tests and its acceptance gate. T02 subsequently passed;
T03 is running. No accepted task was replayed for this fix.

The avoidable feedback gap was in preparation: it returned the skill version
hash but no current document revision. Preparation now reads the scoped bound
document and returns `architecture_revision.expected_sha256`, without prose or
source bodies. Edit feedback exposes the native maintenance revision, including
automatic-finalization and pending-batch paths. Instructions distinguish skill
and document hashes and require fresh preparation after intervening edits.
Stale errors direct a focused reload/retry, not whole-plan regeneration.

**55 Python and 11 JavaScript tests passed.** These cover the real native skill
pipeline after source maintenance, nonmutating stale rejection, fresh insertion,
empty versus missing documents, original CRLF bytes, scope/role/root binding,
symlinks and directories, concurrent writers, direct-editor races, read-only
preparation, shadow consistency, finalization and model-visible hook feedback.
The live worker retains its immutable runtime; later task sessions capture the
updated tooling. No model restart or game implementation edits were needed.

### Missing-file rewrite loop and explicit continuation — 2026-10-07

T03 exhausted its initial 900-second attempt and a 1,800-second corrective
attempt. The latter performed seven successful writes to one source file, the
last identical to its predecessor, with six compactions. Its declared test file
was still absent and tests never ran. An attempted dependency edit was correctly
blocked by scope. The old recovery packet lacked these tool-history counts.

Python now distills the execution log into bounded mutation/compaction/error
evidence for the reviewer. The native gate exposes exact declared-file states
and hashes, missing files and test freshness; the compaction handoff retains
these facts and prioritizes collecting runnable evidence. Pi pauses repeated
rewrites after two successful mutations while declared new files remain absent;
creating those files unlocks edits. Three ignored blocks stop for review. The
private journal survives compaction, and rejected tool calls do not count as
successful mutations. Scope errors identify the allowed files and test workflow.

`resume --allow-repair` records one explicit authorization after an executed
repair failed. It verifies fresh failure/source/plan binding, preserves spent
allowances and old artifacts, reviews before execution, and escalates again on
another failure. It is separate from retrying an unpublished review generation.

**58 Python and 38 JavaScript tests passed.** Coverage includes progress freshness,
zero-test evidence, bounded audit extraction without source/reasoning, the actual
Pi hook lifecycle, rejected edits, persisted rewrite counts, missing-file
creation, compaction contract preservation, stale/mismatched continuation,
one-attempt limits, CLI exclusivity, finalization, resume and task scheduling.
The real failed T03 contract plus fresh progress fits an 8,162-byte handoff.
Qwen review session `a246673f8db7` received the recorded audit and published a
validated repair in **327.205 seconds**, after correcting one rejected reasoning
effort value. It used 4,651 output tokens; the two decode rates were 19.85 and
42.76 tokens/s. All 17 other pending contracts and all frozen acceptance cases,
test commands and file scopes were compared and preserved. The next worker
created the missing test file and collected eight tests; implementation is still
under repair. Codex did not edit game source, tests or task-specific repair prose.

### Unambiguous symbol lookup — 2026-10-07

The active worker requested a short function name with exactly one qualified
match, which formerly produced a traceback and forced another model request.
`retrieval.read_symbol` now resolves that unique short name in the requested file
and returns its qualified identity plus the original query. Exact locators retain
precedence; ambiguous names, nonexistent scopes and path escapes remain rejected.
Pagination, byte hashes and source span boundaries are unchanged.

**14 Python and 20 JavaScript tests passed**, including unique nested JavaScript
retrieval, exact Python-name precedence, ambiguity, wrong qualification, batch
partial success, pinned fixtures, source limits and the Pi tool adapter. The
current worker's immutable runtime was retained; future sessions receive the fix.

### Repair-4 outcome and timeout evidence — 2026-10-07

Worker `15a035ea4eb9` stopped at its 2,700.892-second attempt timer (launch epoch
elapsed 3,046.208 seconds). It created the missing tests, ran them four times and
ended with seven of eight passing. T03's exit-reachability assertion and required
architecture note remain unresolved. T01/T02 remain accepted; no further worker
was started after the explicitly authorized repair failed.

There were 13 completed requests and one deadline cancellation, 27,743 output
tokens including 23,906 reasoning tokens, nine compactions, two source mutations
and two test-file mutations. Ten completed requests engaged the 2,048-token
thinking guard. The median completed-request decode rate was 18.88 tokens/s,
range 5.51–22.28; completed-request backend allocation was 35.40–38.63 GB. A late
snapshot measured 47.85 GB physical process footprint, distinct from allocation
or RSS. The late slowdown's cause is unconfirmed. Measurements and raw events
remain in the pilot's results.md, supervision.jsonl and repair-4 evidence.

The runner previously marked `timed_out=false` when the child enforced its own
deadline and returned 124, and test failure evidence could overwrite the timeout
stop reason. Both paths now preserve the deadline classification while retaining
failed assertions. **32 Python tests passed**, including a real short-lived
child returning 124 and a deadline alongside failing acceptance. Original pilot
receipts were retained; corrected interpretation is recorded separately.

The execution audit also now retains the terminal exception instead of truncating
the start of a traceback. **Three audit tests passed**, including a long private
traceback whose bounded summary retains the cause without implementation frames.

### Progress-aware execution recovery — 2026-10-07

The prior T03 corrective worker kept reading and compacting after creating its
tests, so the missing-file rewrite guard did not stop that pattern. Python now
compares actual scoped content hashes and stable test outcomes at each request
and compaction boundary. It warns after two unchanged completed model rounds and
stops after four, or after three with repeated retrieval/two compactions. A
session journal survives compaction and records bounded selectors/errors without
source bodies or reasoning. Duplicate tests, timing changes and previously seen
content do not reset progress. These are heuristic lack-of-progress thresholds;
they do not prove that every stopped investigation was unproductive.

Native recovery receives `no_progress` even if Pi exits zero. The existing repair
allowance, source/plan binding and frozen acceptance remain enforced. Compaction
retains bounded investigation history; review receives it and measured task input
and compaction limits. Observer corruption fails visibly as `progress_monitor_failed`.

**61 Python and 47 JavaScript tests passed on macOS.** They include real Python
watchdog execution through Pi hook fixtures, exact request/compaction thresholds,
durable event cursors, partial journal writes, timing-independent test evidence,
source/path privacy, stop classification, preserved acceptance, one-review-then-
escalate behavior, role isolation and immutable runtime capture. No new Linux run
or claim of successful game completion is included in this validation.

An offline replay of the previous worker's round/mutation/compaction events
triggers the guard; it changes no project files and is not a model benchmark.
The separately authorized live Qwen review/rerun is recorded in the pilot's
`stall-recovery-*` logs and results, preserving earlier failed attempts.

The live retry exposed an omitted `edit.path`. Native schema validation correctly
rejected it, but the compact diagnostic kept only the generic validation header.
Audit/watchdog summaries now retain up to three field-error lines and still omit
received arguments and traceback source. **17 Python and 5 JavaScript targeted
tests passed** (overlapping the suite above). Already-running sessions retain
their pinned runtime; this reporting change applies to later sessions/reviews.

Recovery context now includes effective profile-inherited input/output/thinking
limits and native thinking-guard counts for completed requests. It excludes
cancelled requests from that comparison and distinguishes missing telemetry from
an uncapped setting. **22 Python tests passed** (overlapping prior recovery/runtime
tests), including a real review-packet assembly with private launcher content
omitted. The running worker's settings were not modified.

Live Qwen retry `4b6a437b5988` exercised the watchdog: warnings were emitted,
new scoped edits/test outcomes reset counters, and four unchanged rounds ended
the worker with `no_progress` at **2,262.321 seconds** rather than its 2,700-second
deadline. Pi's raw exit was zero, the workflow exit was one, and native recovery
retained the distinct stop reason. All **eight original checks passed** by then;
one additional temporary diagnostic test and the required architecture note
still blocked acceptance. The last cleanup edit failed an exact-text match.
The coordinator correctly stopped under the one-repair-then-ask rule.

The worker made 19 completed requests, 26,137 output tokens (22,845 reasoning),
four compactions and seven verified mutations. Median decode was **19.08 tokens/s**;
maximum completed-request active allocation was **40.13 GB**, while maximum
sampled physical process footprint was **51.88 GB**. These differ from RSS.
The Qwen review had increased task input from 24,576 to 32,768 tokens and its
client window to 98,304, preserving every acceptance object/test command and
17 unrelated pending contracts. This was not an isolated watchdog benchmark.
No game source, tests or corrective plan were authored by Codex.

## Rejected edit evidence (2026-10-07)

The final cleanup failure in `4b6a437b5988` submitted 36 lines of `oldText`
containing one incorrect line. The preceding source retrieval matched the
current file, so this was a copying error rather than a stale retrieval or tool
schema rejection. The previous recovery helper recognized only named function
declarations and supplied generic advice for this unnamed test callback.

The replacement helper performs read-only Python retrieval using unique exact
line anchors. It supports callbacks/data and both batched and legacy edit input,
preserves CRLF/Unicode, bounds serialized evidence, and verifies frozen editable
scope before reading. It never repairs strings or mutates source automatically.
Private temporary payloads are deleted after success or subprocess failure.

**31 Python and 15 JavaScript tests passed on macOS**, including the installed
Pi edit implementation rejecting a guessed callback and accepting an exact
fixture-only retry through the refresh hook. Checks cover ambiguous anchors,
scope/symlink escapes, changed snapshots, serialized limits, malformed input,
temporary-file cleanup and preservation of original errors. Existing retrieval,
immutable-runtime and no-progress guard tests are included in these totals.

A read-only replay against the recorded pilot failure returns the exact current
36-line region (1,256 bytes), preserving file bytes and modification time. No
Qwen request or game mutation was made for this replay. The stopped pilot retains
its consumed repair allowance; this change has not yet demonstrated a successful
live Qwen retry. No additional Linux run is claimed.

The subsequent authorized live retry (`641617e24cfe`) demonstrated recovery:
its first callback edit failed, the helper returned exact current source, and
Qwen's next successful edit used old text copied exactly from that evidence.
All eight T03 checks, the required architecture insertion and T01/T02 regressions
passed. The runner accepted T03 and advanced automatically to T04, preserving
the two previously accepted tasks. No supervisor-authored game edits were used.

The corrective execution took **334.472 seconds**, five completed requests,
2,662 output tokens (1,064 reasoning), with median native decode **21.84 tokens/s**.
Maximum completed-request active allocation was **37.89 GB** and maximum sampled
physical footprint was **48.49 GB** (six supervision samples; not RSS). The
preceding Qwen review took 318.831 seconds and preserved all frozen acceptance
and unrelated pending tasks. This resumed existing partial work, so these figures
are not a clean-start benchmark or an isolated comparison of thinking caps.

## Remaining-time feedback (2026-10-08 local time)

T06 reached its 900-second limit with eight of ten tests passing. Native recovery
correctly classified the timeout and started Qwen review. Its final request had
started with little time left, but the executor had no remaining-time feedback.
The workflow now records bound elapsed/remaining wall time at request and
compaction checkpoints, and injects a short notice near the deadline. This is
advice to scope the next action, not an extension or an early-abort mechanism.

**43 Python and 20 JavaScript tests passed on macOS**, including real Python
clock feedback through Pi's context hook, threshold/expiry handling, launch and
process binding, source/prompt privacy, unchanged stagnation policy and recovery
allowances, compaction and exact-edit recovery regressions. These overlap earlier
suites. No Linux run or claim that the notice eliminates timeouts is included.
Already-running sessions keep their immutable runtime; subsequent launches
capture the tested notice implementation.

The T06 reviewer called `project_map locate` with known file paths but no query.
The rejection was correct, but the schema description did not clearly distinguish
searching from prototype inspection. Tool/field descriptions and action-specific
feedback now require a nonempty search query and point file-only requests to
`inspect`. Whitespace-only queries are rejected. **29 JavaScript routing, scope,
architecture-maintenance and provider-isolation checks passed**; this does not
change the running review's pinned tools or silently reinterpret its request.
