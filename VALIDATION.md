# Release verification

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
