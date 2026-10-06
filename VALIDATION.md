# Release verification

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
