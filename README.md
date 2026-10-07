# mypi

A Pi workflow for effective local Qwen development, with optional ChatGPT subscription planning and review. It runs on **Linux and macOS**. The client owns projects, tools, tests and execution; a separate **Apple Silicon Mac** runs Qwen through MTPLX.

The default Qwen endpoint is **http://localhost:8000**. Select another machine with **mypi server IP:PORT** or **/server IP:PORT** in chat. The tested model is MTPLX Quality: Qwen 3.8 27B, packed 8-bit weights with FP16 floating tensors, 96k capacity, MTP3 and normal KV.

## First run on another Linux machine

Install Python **3.12+**, Node **22.19+** with npm, Git, ripgrep and **ps**. On Ubuntu 24.04, the Python/system prerequisites are:

~~~sh
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv git ripgrep procps
~~~

Install a supported Node version separately if needed; check its version before running the installer. With [nvm](https://github.com/nvm-sh/nvm#install--update-script) already installed, use `nvm install 24` and `nvm use 24`. Other distributions use their own package manager. Run **./install.sh without sudo**, so it uses your selected Node and installs into your user account. Then:

~~~sh
python3 --version
node --version
git clone https://github.com/Prishvin/mypi.git
cd mypi
./install.sh
./mypi server 192.168.1.34:8000
./mypi chat ~/projects/my-project
~~~

Use your Qwen Mac's current IP. Both machines must be able to reach that address. HTTPS cloning works without importing the Mac's SSH key. SSH cloning is also available:

~~~sh
git clone git@github.com:Prishvin/mypi.git
~~~

Wait for **Installed mypi** before running **./mypi**. Its Python executable lives in **agent-workflow-v2/.venv/bin/python**, which is created locally and excluded from Git. If Python is missing or older, install Python 3.12+ and rerun; select a particular interpreter with:

~~~sh
MYPI_PYTHON=python3.12 ./install.sh
~~~

The installer creates a private virtual environment, installs locked Pi dependencies and links **~/.local/bin/mypi**. To use the short command:

~~~sh
export PATH="$HOME/.local/bin:$PATH"
mypi status
~~~

Put that PATH line in your shell's startup file if desired. Run **git pull**, then **./install.sh** to update. A virtual environment copied from another OS must be rebuilt; the installer detects a broken interpreter. Model weights and subscription credentials are not copied to clients.

## First run on macOS

Install the same client prerequisites, then use the same clone and installer commands. When Qwen is already on this Mac, the default localhost:8000 endpoint is sufficient.

To install the **model host** too, on an Apple Silicon Mac with **64 GiB+ RAM**:

~~~sh
./setup-qwen.sh
./mypi qwen start
./mypi status
~~~

The host installer requires **Python 3.12** for its pinned environment. It installs MTPLX and its dependencies into **~/.local/share/mypi/qwen/.venv**, downloads the checkpoint sequentially into **~/Models/Qwen3.8-27B-MTPLX-Optimized-Quality-FP16**, verifies hashes and tensor indexes, and checks the thinking-cap adapter without loading weights. The download is approximately **30 GB**. Rerun the script to resume; verified files are reused.

~~~sh
./setup-qwen.sh --start
./setup-qwen.sh --verify-only
./setup-qwen.sh --model-dir /path/to/model
./setup-qwen.sh --gpu-lock /path/to/shared/local-gpu.lock
./mypi qwen status
./mypi qwen stop
~~~

Use **MYPI_QWEN_ROOT** to select another host state/environment directory. **MYPI_GPU_LOCK** selects a shared image/video GPU lock. Set the same lock as other GPU jobs when integrating with an existing studio.

The recipe pins the model revision **9b53320d1e15d40add84584ccf6c5134ef1d332b**, all dependency versions and the MTPLX server-source hash. Unknown server source fails the adapter check. The installed MTPLX files are not patched.

| Host setting | Value |
| --- | --- |
| MTPLX / MLX / mlx-lm | 2.12.2 / 0.32.2 / 0.31.3 |
| Native API | 127.0.0.1:8000 |
| Model ID | mtplx-quality |
| Context capacity / maximum total output | 98,304 / 32,768 tokens |
| Generation / depth / runtime profile | MTP / 3 / turbo |
| KV quantization | Off — normal KV |
| Thinking / default effort / default cap | On / medium / 4,096 tokens |
| Thinking history | auto |
| Runtime memory limit | 48G |
| Scheduler / SSD session cache | Serial / on, 2G |
| Cooling / memory stop | 60 seconds; critical pressure or >8 GiB new swap |

The guard holds the GPU lock for the whole model lifetime, prevents sleep with caffeinate, and records logs and memory. It does not change macOS power settings or the system GPU limit. Start reuses a matching running instance; stop signals only this installer's verified guard. If another launcher owns the existing model, stop it through that launcher.

Linux runs the client; this exact MLX/Metal model-host recipe runs on macOS.

## Expose Qwen to other machines

After host setup, a single command starts/reuses Qwen and exposes its API on the Mac's LAN address:

~~~sh
mypi serve --start-qwen --listen 192.168.1.34 --port 8000 --background
~~~

The native engine keeps its loopback listener; the gateway binds the LAN address at the same port. It forwards streaming completions, models, health, thinking-cap capabilities and native telemetry. It adds same-host process RAM to health. It does not load a second model.

When an existing launcher already serves Qwen:

~~~sh
mypi serve --listen 192.168.1.34 --port 8000 --background
mypi serve --qwen-launcher /path/to/existing/pi-local --listen 192.168.1.34 --port 8000 --background
~~~

Use the current LAN address. If the engine occupies all interfaces, choose a different gateway port, for example **--listen 0.0.0.0 --port 8001**, and connect clients to that port. An incompatible occupied address is rejected. **--upstream** selects an existing native API. Repeating a compatible gateway start reuses it.

Gateway logs are in **~/.local/state/mypi/gateway/server.log**. Foreground mode omits **--background**; Ctrl+C stops the gateway. Optional **MYPI_SERVER_TOKEN** requires bearer authentication on the gateway and supplies it from clients. **MYPI_UPSTREAM_TOKEN** supplies a separate upstream bearer token. Tokens are not stored in Git.

## Use the terminal or web UI

~~~sh
mypi chat /path/to/project
# Equivalent shorthand:
mypi /path/to/project
mypi web --no-open
~~~

The web UI opens at **http://localhost:8099**. Use **--port 8120** if another app owns 8099. It supports:

- New/deleted/renamed conversations, each with its own default project folder.
- Pi or raw Qwen mode, with streamed output and reasoning.
- Local or ChatGPT planner/reviewer selection.
- Independent input, total output and thinking controls.
- Inline clarification questions, plans, progress, stop/resume and measured results.
- Conversation links that another user can open on the local network.
- A **Run monitor** link on execution plans, showing granular todo and test evidence.

To expose the **client's UI**, rather than the model API:

~~~sh
mypi web --listen 0.0.0.0 --allow-address CLIENT_MACHINE_LAN_IP
~~~

Open **http://CLIENT_MACHINE_LAN_IP:8099** from another device. The allowlist and sharing links refer to the machine hosting this UI, which can differ from the Qwen Mac. Do not confuse UI port **8099** with model API port **8000**.

The terminal starts an architectural conversation and prepares a development project. The web UI additionally classifies ordinary questions and read-only inspection before choosing a development flow. **Raw Qwen** is direct chat: saved history and token/thinking limits apply, but it has no Pi tools, research, planning or source edits.

### Built-in run dashboard

Open **Run monitor** from a web conversation's execution plan, or monitor a CLI run directly:

~~~sh
mypi monitor /path/outside/project/run --port 8137
# A parent evidence folder follows the newest run-*/state.json after a restart:
mypi monitor /path/outside/project/evidence --port 8137
# Share this viewer on the local network:
mypi monitor /path/outside/project/evidence --listen 0.0.0.0 --allow-address UI_MACHINE_LAN_IP
~~~

Open **http://localhost:8137/**, or **http://UI_MACHINE_LAN_IP:8137/**. The monitor is part of mypi, works on macOS/Linux and runs independently of the conversation UI. It reads run artifacts and polls the configured model's native metrics endpoint; it starts no model and generates no inference requests. Other compatible backends still show todos and evidence when native metrics are unavailable.

Use the **Planning** and **Implementation** queue buttons to inspect both phases.
During planning, implementation tasks are labeled **Awaiting planning**; their
steps, budgets and tests are draft contracts. Click a completed planning step to
see its **Saved planning result**: architecture and draft todos, coverage strategy
and gaps, or the refined task and recorded changes. These historical outputs
remain available after implementation starts. Planning acceptance does not count
as implemented or tested code.

The light-themed viewer refreshes every three seconds. A sticky **Current step** line shows the actual task and current tool/model activity, queue state or stopping reason, with a button to jump to that task. Browsing another todo does not change this status. The viewer shows accepted/running/blocked/failed/interrupted todos, dependencies, planned atomic steps, file changes, acceptance criteria mapped to frozen test commands, passing/failing/stale test results, recent tool calls with timings/errors, attempt history, task deadlines and context/output/thinking budgets. It retains accepted lineage after replanning. Select a todo to add its ID to the URL for sharing. Elapsed clocks stop while an interrupted run awaits replanning.

Live native telemetry shows actual prompt processing, cached/new prompt tokens, reasoning/tool/answer phase, generation speed and separate allocation/footprint/RSS measurements when available. Capacity is a limit; missing measurements appear as **—**. Process RSS requires a recorded sampler; the viewer does not inspect a remote PID. Planned steps are displayed as instructions, not invented completion checkmarks. Task acceptance reflects the runner's frozen test and scope gates, rather than a model's claim of success.

**Model thinking** is collapsed by default and shows only reasoning explicitly emitted by Pi for the current attempt. It updates without inference requests, preserves reading position and labels previous/stopped output. Long text is bounded to its recent tail. Copy icons export task details, current status, individual tool failures, thinking, project brief and model activity; copying also works on ordinary HTTP LAN connections.

## Complete Pi workflow

### 1. Bind a workspace and classify intent

A web conversation starts with a separate local classification request, without editing tools. Slash settings commands are handled directly.

| Route | Behavior |
| --- | --- |
| Discuss | Answer, explain pasted code or use bounded research skills. |
| Inspect | Read an explicitly referenced existing folder through scoped tools; no source edits or Git initialization. |
| Develop | Build/change/fix software through clarification, research, planning and atomic execution. |
| Clarify | Ask what the user wants when given only code, a folder or ambiguous instructions. |

A pasted implementation or folder path alone does not authorize development. Explicit development targeting an existing folder edits that folder directly. Otherwise the conversation's isolated project is used. Development bootstrap can create a project and Git repository when neither exists. A shadow-project skill creates or refreshes missing interfaces.

Fenced supplied code stays local. A cloud planning request receives refined requirements and prototype locations rather than copied implementation bodies. Initial user requirements and interface descriptions can still contain sensitive information; choose local planning when they must remain on the local machines.

### 2. Clarify and consolidate the request

Routing and development intake share a budget of **at most two clarification answers**. Questions appear in the main chat. The intake model combines the original request and answers into one faithful request, retaining constraints, commands and acceptance cases.

Unanswered clarification pauses. It is not permission to guess or begin edits. Routing and planning state are persisted so the same request can resume.

### 3. Research and publish essential knowledge

A research phase identifies project-specific keywords or unknown formats/APIs. It uses fixed executable skills, searches public sources, follows the first two DuckDuckGo links where reachable, removes page noise and selects question-relevant excerpts.

The model distills those excerpts into a short **knowledge.md** with source URLs. Full fetched pages are archived outside the project context; workers receive only selected briefs/topics. A blocked site or missing source is reported, not treated as verified evidence.

Built-in executable skills:

| Skill | Purpose |
| --- | --- |
| duckduckgo-search | Discover documentation and implementation links. |
| duckduckgo-research | Search, follow the first two links and extract focused content. |
| wikipedia-search | Find articles and retrieve short introductions with URLs. |
| public-page-fetch | Fetch an exact public source and return bounded relevant excerpts. |
| shadow-project | Create/refresh the architecture-linked interface shadow. |
| architecture-navigation | Parse sections, search the compact map, read selected decisions. |
| architecture-maintenance | Automatic Python after-change update of architecture metadata, shadow and map. |
| architecture-sync-check | Detect drift; rebuild after confirmation and verify consistency. |
| architecture-update | Append/insert scoped decision prose with a current document hash. |
| task-finalize | Insert an optional task decision, refresh navigation, reuse fresh frozen tests and enforce acceptance in one call. |
| browser-interaction-review | Load browser lifecycle/input/visibility checks for UI tasks; its checklist does not claim tests ran. |
| text-metrics | Example deterministic multi-step script with typed output. |

Skills have fixed input/output contracts, purposes, native scripts and pre/post-processing instructions. Coding sessions load scoped retrieval and finalization instructions; architects load granular planning, architecture navigation and research. Relevant task procedures load with the selected packet, and other skills remain available through the bounded catalog. This keeps unrelated procedures out of each Qwen request. Optional electronics/KiCad bundles remain external, selected with **MYPI_DOMAIN_SKILLS**.

### 4. Build an architecture-linked shadow

**architecture.md** records decisions, module ownership and dependency direction. Existing content is accepted as written, with no line-count or file-size limit. Model request budgets still apply to retrieved context. Generated shadow files contain interfaces, signatures, symbols and short descriptions. They live in private session folders, outside source.

The planner measures **all prototypes + generated architecture** with the matching bundled tokenizer:

- At **32,768 tokens or below**, bounded shadow navigation is available.
- **Above 32,768**, the compact architecture index is the project-wide navigation map. The planner searches/paginates it, reads selected architecture sections and supplements with a few relevant shadow files.
- Each selected read is limited to **five files / 8,192 text tokens**. Architecture page evidence must precede prototype reads or scoped searches.
- Global catalogs and unscoped searches are rejected in this larger-project mode. Prompts forbid reconstructing the whole shadow by repeated batches.

Python parses ATX/Setext headings, skips fenced code, preserves the source document and assigns hierarchical section IDs with current line ranges. It links explicit filenames/directories and unique function/class references to shadow files; ambiguous names are reported. **architecture-map.md** is a compact searchable summary with representative functions, classes and keywords. **architecture-map.json** retains the complete local symbol registry; it is searched locally, never dumped into model context. Small architecture documents can be shorter than index overhead; navigation is always paged.

Use **project_map architecture** first, then **architecture-search** with literal function/class names or task keywords, and **architecture-section** with a section ID and current document SHA256. Module `offset`, heading `section_offset` and section character `offset` are distinct. A long single-line section is also readable in bounded pages.

Each todo can pin up to five **context.architecture_sections** entries `{id, sha256}` using the returned **section_sha256**. The Python executor reloads only those decisions, counts them in the shadow estimate, and rejects changed selected sections. Unrelated edits and moved line numbers do not invalidate section content hashes. Source changes still invalidate navigation evidence. **shadow-budget.json** records counts and tokenizer identity. Selection remains a model judgment; native tools enforce access scope and read limits.

### 5. Create a granular plan and context recipe

The selected planner sees requirements, knowledge, architecture and interfaces. It creates a validated V3 plan; it does not execute source edits.

New CLI and web plans use two passes. First, generate the architectural draft. The second pass starts with a dedicated **COVERAGE** task: map request requirements to existing acceptance cases, unit/integration/e2e checks and observable pass/fail conditions; assign missing cases to their owning todos. Then a fresh model session reviews each original todo against the request, whole draft and coverage plan. It refines the task or splits it into 2–4 independently tested children. Python preserves original cases, test commands, file scope and dependency completion, and requires every coverage gap to be incorporated. The final plan becomes executable only after all reviews pass.

`--refiner qwen|chatgpt` defaults to the planner. Each stage records its own model usage, elapsed time and memory observations. This deliberately spends additional planning calls to expose missing contracts before implementation; it is not yet a measured overall speed improvement. Rerun the **same plan command/output path** to resume a checkpoint; completed reviews are retained. The monitor shows drafting, coverage and individual refinements separately from coding acceptance. A valid unexecuted draft from an interactive session can enter this pipeline with `--review-draft /outside/project/draft.json`; `--draft-plan` instead repairs an invalid proposal first.

Planning/review budgets depend on the provider. Qwen stays at 98,304 capacity with 49,152 input / 16,384 output for coverage and task reviews; a complete failure-repair plan can use 32,768 output. GPT-6.1 Sol uses a conservative **272,000 client window**, 196,608 input and 32,768 output at xhigh, based on the installed Pi catalog. OpenAI documents a **1,050,000 model context and 128,000 maximum output**; larger subscription requests have not been verified here. These are ceilings, not padding or token targets. Cloud admission uses the bundled tokenizer as a proxy plus margin, not an exact GPT token count. Local coding tasks retain their own smaller budgets. [Official GPT-6.1 Sol limits](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

Each atomic todo specifies:

- A concrete goal, exact editable files, dependencies and small implementation steps.
- Observable acceptance cases and an exact test strategy, commands and coverage links.
- Expected change size, assumptions, deadline and failure action **replan**.
- Required interfaces, named source symbols, static references, test fixtures and knowledge topics.
- Estimated framework, shadow, source, tests and history tokens, plus at least **25% margin**.
- Task window, maximum input, maximum total output, reasoning effort and thinking-token cap.

The planner must include tool/schema overhead in the estimate. A short function can still require several thousand framework tokens. **96k capacity is not a 96k prompt**: small tasks can use a 32k worker window, 16k input limit and 8k output limit while the server stays at 96k.

Source files should be comfortable to load individually: target **4,096 Qwen tokens**, ceiling **8,192 tokens**, alongside **300 lines / 32 KiB**. Shadow entries report measured source size; Python rejects new or growing files over the ceiling. Existing oversized source may shrink or remain the same size, with focused retrieval. Authored architecture documents remain exempt and are read by section. Several individually small files can still exceed a todo's input budget; planning must account for their combined context and test/tool overhead.

Review the plan and acceptance before choosing **Run plan**, or explicitly run the CLI executor.

### 6. Execute through a deterministic scheduler

The plan executor is Python, not an LLM. It selects dependency-ready todos, records checkpoints and starts one fresh Pi worker for each todo. The worker cannot schedule more todos or widen its contract.

Each worker receives only:

1. Its selected task and budget.
2. Brief architecture and selected interfaces.
3. Named implementation spans, primitive declarations and small exact editable files.
4. Relevant immutable fixtures and selected knowledge.
5. Bounded failure/resume evidence when applicable.

Scoped **source_query** tools locate symbols and read focused functions, variables or test pages instead of dumping the repository. Small files may be prefetched in full when explicitly selected. Source retrieval stays with the local Qwen worker.

The worker uses native tools to edit and run the declared tests. Test results, scope checks and a fresh shadow gate determine acceptance; a model's claim that work is complete is insufficient.

### 7. Refresh after every edit and completion

After every successful or partial failed edit/write, the Pi extension directly invokes the **architecture-maintenance** Python skill. No model call is used. It classifies added/modified/deleted files and unambiguous exact-content renames, marks interface changes, updates the owned interface block in **architecture.md**, refreshes prototypes and rebuilds a missing/stale compact map. Already-current maps are retained. Every coding contract reserves architecture.md before editing; this consumes one of its eight file slots. Existing architectural prose and line endings are preserved.

Rejected edits also receive bounded current-source evidence from Python. This works for unnamed test callbacks, arrow functions and data blocks as well as named functions. A unique exact line from the rejected `oldText` locates a current excerpt, with a SHA-256 snapshot and navigation offsets; the source text has no added line labels. Only frozen editable files can be read. Each excerpt is at most 80 lines and the combined JSON stays within 12,000 bytes. Ambiguous anchors require targeted retrieval. This is read-only evidence, never a fuzzy replacement or permission to delete the entire excerpt; Qwen still chooses and submits the correction. Failed evidence retrieval preserves the original edit error and does not masquerade as a failed shadow refresh.

Changed responsibilities/invariants still need a human-readable explanation. The worker calls **workflow_test({architecture_note, architecture_title})**, which invokes the **task-finalize** skill: Python resolves current hashes, appends the brief Qwen-authored decision, refreshes navigation, runs frozen tests and checks acceptance. Use **architecture-update** for a precise insertion into an existing section. Full-document replacement is blocked. Set **context.architecture_update_required=true** only when a todo needs a new decision; acceptance then requires the current insertion receipt as well as tests. Implementing already-planned interfaces normally needs only automatic metadata maintenance.

Preparing **architecture-update** returns `architecture_revision.expected_sha256`, the current document revision, separately from the skill's own `sha256`. Source edits may change that document revision through automatic metadata maintenance. Edit feedback reports the refreshed revision; prepare again after intervening edits. A stale insertion is rejected without overwriting newer content: reload the target section and retry with fresh preparation. This does not require regenerating the whole plan.

Finalization runs automatically after edits once declared new files exist. Tests already bound to the current snapshot are reused; a source or architecture change invalidates them. Passing tests with a missing note trigger a targeted finalization instruction, not another code rewrite. Failing tests prevent publication of a completion note. Tool feedback is bounded; full test logs and gate results remain local. Native acceptance stops the worker without another model request.

The **architecture-sync-check** skill reports stale code/architecture hashes, prototypes or map content. It asks for confirmation in the main chat before rebuilding external drift. Use **/rebuild** to execute that native skill and verify the result; in the web UI this bypasses classification and model startup entirely. A coding rebuild respects frozen scope, and all rebuilds preserve authored decision prose. Before accepting completion it checks the current source snapshot, declared file scope, size rules and fresh test evidence. Source functions should be individually testable, with small modules and pure boundaries where practical.

Frozen external fixtures protect acceptance across retries. Known completed behavior is rechecked before later or resumed work. Native guards enforce scope, hashes and size; whether an architecture is well designed or every function is suitably testable also needs reviewer judgment.

### 8. Stop with evidence, or resume interruption

A failed test, unexpected scope change, stale fixture, deadline or budget overflow stops the run with an evidence packet. The packet contains the task, changed files, bounded failure details, measurements and the reason to replan. Failure does not authorize an unbounded repair loop.

The CLI/web coordinator sends a failed todo to the selected **planner** for a fresh failure review. It supplies measured architecture/shadow, a compact original-plan overview, the failed contract and observed errors (including request-admission measurements). Complete architecture and prototypes are included when both the provider’s selection threshold and available packet space permit (32k Qwen, 128k cloud); otherwise Python selects the compact map, relevant sections and up to five interfaces. Implementation bodies remain local. The model submits **failure_analysis plus flat changes to the failed todo only**. Python assembles the complete remaining plan, preserving untouched tasks, exact acceptance/tests, authorized scope and completed regression lineage. Source and original-plan hashes must still match. A repair requiring changes to other contracts stops for user-directed replanning.

Python applies **one automatic repair attempt per failed contract**. If that repair fails, or the review cannot produce a valid plan, execution stops with an inline/CLI question and `user-question.json`. Repeating resume does not silently reset the allowance. An interrupted repair resumes the same contract. A separate later todo may receive its own one attempt. Evidence and results live under the original run directory; `execution-target.json` identifies the actual repair plan/run for final review. Explicit user-directed replanning can authorize further work.

If review generation itself failed or timed out before publishing a plan, explicitly authorize a new focused review with:

```bash
./mypi resume /path/to/project /path/to/original-plan.json \
  --run-dir /path/to/original-run --retry-review --reviewer qwen
```

This retains the failed review logs, uses a new repair artifact, checks evidence freshness, and preserves the one execution-repair allowance. It does not rerun the failed coding attempt before reviewing it. A completed generated plan or a failed corrective execution cannot use this option to bypass acceptance.

After a corrective execution has failed, explicitly authorize **one further** review and repair with:

```bash
./mypi resume /path/to/project /path/to/original-plan.json \
  --run-dir /path/to/original-run --allow-repair --reviewer qwen
```

This records the authorization, checks the current failure/source binding and keeps prior attempts and spent allowances. It reviews before starting another worker, preserves accepted tasks, and stops again if that corrective attempt fails. It cannot be combined with `--retry-review`.

Recovery includes a Python audit of actual tool outcomes: mutation counts, repeated identical writes, compactions and bounded tool errors. Source bodies and reasoning stay local. During execution, a file may be mutated twice while other declared new files are absent; further rewrites pause until those files exist. The worker can still create missing tests, inspect source, run frozen tests and insert architecture notes. Three ignored rewrite blocks stop the attempt for review. The guard's private journal survives compaction, whose native handoff now includes actual file hashes/states, missing files and whether tests are absent, stale, failed or passing. File existence alone never proves acceptance.

A separate Python watchdog detects stalled execution even after all files exist. Before each model request and deterministic compaction it compares scoped file hashes and stable test outcomes. Two unchanged model rounds produce a warning; four stop with `no_progress`. Three rounds also stop when accompanied by two compactions or three identical retrievals. Repeated tests, timing-only log changes and reverting to previously seen contents do not reset progress. Recent retrieval selectors and bounded errors survive compaction and enter failure review; implementation bodies and reasoning are excluded from that journal. The existing one-repair-then-ask allowance still applies. These thresholds measure lack of observable progress, not whether the model's unobservable reasoning is useful.

The same checkpoint records the bound attempt's remaining wall time. Near the deadline (the last third, capped at five minutes and at least one minute), it reminds the executor that prompt loading, reasoning, tools and tests share that allowance. The reminder favors a small scoped edit and verification, preserves every acceptance check, and does not extend the timeout or count clock changes as progress. The process supervisor remains responsible for enforcing the deadline.

Recovery also receives effective executor limits inherited from the selected profile, including its thinking cap, and counts of completed requests that hit the native thinking guard. Missing telemetry is marked unknown. Frequent cap hits are evidence to assess, not an automatic instruction to raise the cap.

Interrupted work keeps partial edits and original baselines. Resume verifies the source/fixtures and accepted tasks, then gives a fresh worker a short continuation brief. Accepted todos are not replayed, and old full conversations are not fed into the next task.

Use **resume** for an interruption. Use **replan** when behavior, scope or acceptance needs changing. For a stopped timeout/execution/acceptance failure with unchanged source and contracts, an explicit **retry** creates a new plan without asking an LLM to regenerate it. It preserves original baselines, completed tasks, files, criteria, tests and context budgets, and changes only task deadlines. Changed source or immutable fixtures block this retry.

Task deadlines can be **30–2,700 seconds**. Planning guidance uses shorter limits for simple tasks and reserves up to 45 minutes for setup or repairs. A longer deadline is a ceiling; native acceptance exits immediately. Individual test commands still have a maximum 300-second deadline. See [the workflow review](WORKFLOW_REVIEW.md) for measured overhead and remaining limitations.

### 9. Review the outcome

The independently selected reviewer reads shadow/architecture, accepted task outcomes, test evidence and run results. It proposes useful missing unit/e2e tests and evidenced fixes as a separate granular follow-up plan. It does not execute that plan automatically.

The web UI can adopt a valid follow-up plan for review/execution. Coding success and review success are tracked separately.

## Planner, reviewer, server and memory commands

~~~text
/server                         Show the Qwen endpoint
/server 192.168.1.34:8000        Verify and switch the endpoint
/planner local                  Qwen planning, medium reasoning
/planner chatgpt                ChatGPT 6.1 Sol, xhigh
/reviewer local                 Qwen final review
/reviewer chatgpt               ChatGPT 6.1 Sol, xhigh
/thinkingcap 8192               Project default thinking-token cap
/thinkingcap 0                  Remove the separate thinking cap
/thinkingcap default            Restore the profile default
/remember                       Fresh distillation of the last completed answer
~~~

Local planning and review are the default. For subscription planning on this client:

~~~sh
mypi login
~~~

In Pi choose **/login openai** and ChatGPT sign-in. Private OAuth credentials stay in the ignored planner configuration. Each machine signs in separately; Codex credentials/global Pi settings are not modified. Access depends on the account's subscription and model entitlement.

**/remember** runs a fresh request with the current provider to extract essential, source-grounded information from the last completed answer. It saves a bounded note to **knowledge.md** and refreshes shadow. It does not copy the whole answer or raw reasoning as a fallback.

**/server** validates the served model, real context capacity, history policy and request-local thinking-cap adapter before saving. In an idle terminal session it refreshes Pi's model registry and active connection. Frozen workers cannot change server; saved attempts retain their original endpoint.

Server preferences are in **~/.config/mypi/server.json**. **MYPI_SERVER_URL** and **MYPI_MODEL** override saved preferences. The bundled tokenizer matches Quality; another model family requires a matching **MYPI_TOKENIZER**.

## Context and thinking controls

| Control | Meaning |
| --- | --- |
| Server capacity | Physical/configured ceiling; normally 98,304 tokens. |
| Worker window | A per-task client context selection, without restarting the server. |
| Maximum input | Admission limit for serialized selected material. |
| Maximum total output | Reasoning, answer and tool-generation tokens together. |
| Thinking cap | Separate backend guard threshold inside total output. |
| Reasoning effort | Low/medium/etc. policy, independent of the thinking cap. |

Explicit frozen task caps override project/profile defaults. Positive thinking caps must leave at least **2,048 tokens** for answers/tools; zero means uncapped thinking, not thinking off. Thinking is separately enabled/disabled. A threshold can be slightly exceeded by the model's closing bridge/batched decoding; total output remains bounded.

Admission uses the matching tokenizer on serialized payload, a **25% margin** and template allowance. It is an estimate, not the server's exact rendered token count. Native usage receipts report the actual count. Pi's compaction trigger subtracts that margin and reserves space for the serialized envelope, so history compacts before the admission cap. At 32768 input tokens the history trigger is 21913 tokens; server capacity and output limits stay unchanged. Each atomic worker starts fresh. A batch inspection stopped by admission or a provider abort reports failure, even if Pi's raw process exits zero.

The active release profiles are **mtplx-quality** and **chatgpt-quality**. Historical comparison templates remain available for separately installed engines; they are not additional bundled model downloads or newly validated remote profiles.

## CLI planning, execution and recovery

~~~sh
mypi plan /path/to/project "Implement a pure parser with edge-case tests" \
  --planner qwen --out /path/outside/project/plan.json

mypi execute /path/to/project /path/outside/project/plan.json \
  --run-dir /path/outside/project/run --reviewer qwen

mypi run /path/to/project /path/outside/project/plan.json T1

mypi resume /path/to/project /path/outside/project/plan.json \
  --run-dir /path/outside/project/run

mypi replan /path/to/project /path/outside/project/run/replan-request.json \
  --planner qwen --out /path/outside/project/replacement.json

# Retry unchanged work after a timeout, preserving its original acceptance:
mypi retry /path/to/project --from-run /path/outside/project/run \
  --out /path/outside/project/retry.json --task-timeout 2700
mypi execute /path/to/project /path/outside/project/retry.json \
  --run-dir /path/outside/project/retry-run --reviewer qwen

mypi review /path/to/project /path/outside/project/plan.json \
  --run-dir /path/outside/project/run --reviewer chatgpt

mypi skills
mypi settings /path/to/project --planner local --reviewer chatgpt
~~~

Noninteractive planning can supply **--answers-file**, a JSON array of at most two answers. Unanswered clarification returns a pause. Plans/evidence must be outside the editable project. Keep the original run directory for resume.

If a model finishes an unaccepted proposal but `plan_store` rejects missing metadata, preserve its `.draft.json` and repair it without regenerating the full plan:

~~~sh
mypi plan /path/to/project --request-file /path/outside/project/corrections.md \
  --draft-plan /path/outside/project/rejected.draft.json --planner qwen \
  --out /path/outside/project/repaired.json
~~~

Draft repair skips already completed intake/research and accepts sparse model-authored corrections. Python pins the project snapshot, retains unchanged contracts, checks splits preserve files/cases/test commands and runs full V3 validation before saving. Explicit corrections to a contradictory unaccepted criterion require its exact old object, matching ID and a recorded reason. This mode cannot repair executed work: use evidence-bound **replan** after execution failures. No edit-size estimates are invented or clamped by Python.

At execution start, a new project receives the accepted planner's decisions as `architecture.md`; Python adds section headings to plain API lists for selective retrieval, including modules not created yet. Existing authored architecture stays unchanged. Atomic workers receive relevant contract sections rather than the full implementation or full todo plan.

| Exit | Meaning |
| --- | --- |
| 0 | Requested operation passed. |
| 2 | Planning awaits clarification. |
| 20 | Atomic execution stopped and requests replanning. |
| 21 | Coding finished but final review failed. |
| 130 | Interrupted execution; checkpoint retained. |

Progress reports are recorded every **30 seconds** during active workers. Metrics include execution time, native input/cache/output/reasoning usage, prompt/decode tokens/s, first-token delay, backend allocation and separately sampled model-process RSS. Token sums over repeated requests are not occupied context. RSS is available through the host gateway; native metrics retain the recent 32 requests, so long-term evidence is collected promptly and missing records remain unavailable.

## Linux container alternative

With Docker installed:

~~~sh
git clone https://github.com/Prishvin/mypi.git
cd mypi
docker build -t mypi .
docker run --rm -it \
  -e MYPI_SERVER_URL=http://192.168.1.34:8000 \
  -v "$PWD/my-project:/workspace/project" \
  -v mypi-sessions:/opt/mypi/agent-workflow-v2/sessions \
  mypi chat /workspace/project
~~~

For a container UI, run its server in the foreground, publish port 8099, bind to 0.0.0.0 and allow the address used in the browser:

~~~sh
docker run --rm -p 8099:8099 \
  --entrypoint /opt/mypi/agent-workflow-v2/.venv/bin/python \
  -e MYPI_SERVER_URL=http://192.168.1.34:8000 \
  -v mypi-web:/opt/mypi/pi-web/data \
  -v mypi-sessions:/opt/mypi/agent-workflow-v2/sessions \
  mypi /opt/mypi/pi-web/server.py --listen 0.0.0.0 --allow-address CLIENT_MACHINE_LAN_IP --port 8099
~~~

Mount **/root/.config/mypi** to retain server settings and **/opt/mypi/agent-workflow-v2/planner-config** to retain that container's private subscription login. Mount project, session and run/evidence directories at stable paths for durable resume; **--run-dir** selects the latter. Do not copy another OS's virtual environment into the image.

## Troubleshooting and verification

| Symptom | Action |
| --- | --- |
| exec .../python: not found | Run ./install.sh in the cloned repository and wait for successful completion. |
| Python missing/too old | Install Python 3.12+; set MYPI_PYTHON to its command. |
| Node missing/too old | Install Node 22.19+ and npm; rerun the installer. |
| Cannot reach Qwen | Check the Mac's current IP, shared network and mypi qwen/status/gateway logs. |
| Server validation rejects adapter | Use the pinned host setup or install the reviewed adapter on the existing compatible engine. |
| Port 8099 belongs to another app | Select a free UI port; existing unrelated UI is not replaced. |
| Raw chat reaches its input limit | Start a new chat or raise its input cap; raw history is not silently dropped. |
| Source changed after interruption | Review the evidence and replan/recover explicitly. |
| Qwen stop says another owner | Stop through the launcher that started that model. |

~~~sh
agent-workflow-v2/.venv/bin/python scripts/check.py
MYPI_SERVER_URL=http://YOUR_SERVER:8000 \
  agent-workflow-v2/.venv/bin/python examples/smoke.py /new/evidence/directory
~~~

CPU checks cover workflow, UI, host artifacts/guards and JavaScript. The live smoke uses genuine Pi tools to repair a small isolated function, run frozen acceptance, refresh shadow and record native usage/speed/RAM. GitHub Actions runs CPU checks on macOS and Ubuntu.

See **[VALIDATION.md](VALIDATION.md)** for measured results, **[run_local.md](run_local.md)** for operational commands, **[architecture.md](architecture.md)** for implementation ownership, and **[qwen-host/recipe.json](qwen-host/recipe.json)** for the complete pinned host recipe.

## Scope and privacy

These rules apply to mypi's private Pi workflow. Global Pi and Codex are unchanged. Qwen receives selected task material over the chosen connection; projects and tests run on the client. ChatGPT planning/review is optional and sends the selected requirements/interfaces/evidence to that provider.

The repository excludes weights, user projects, conversations, private auth, endpoint settings, generated sessions and logs. The text-only tokenizer and its attribution/license are included. Native scripts and tests are trusted local programs; mypi is not an OS sandbox.
