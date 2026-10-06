# Running mypi

Install with `./install.sh`, then put `~/.local/bin` on PATH. Python 3.12+, Node 22.19+, Git, ripgrep and ps (Linux procps) are required on macOS or Linux.

## Optional Qwen host setup

On a 64 GiB+ Apple Silicon Mac, run `./setup-qwen.sh` with Python 3.12. It installs the tested isolated engine, downloads/reuses the pinned Quality checkpoint, verifies every hash/index and checks the adapter. `--verify-only` checks existing artifacts; `--start` starts/reuses the guarded model. `mypi qwen start|status|stop` manages only this installer’s host owner.

`mypi serve --start-qwen --listen SERVER_LAN_IP --port 8000 --background` starts/reuses that host and exposes its API. Linux clients only need the client installer and `mypi server SERVER_LAN_IP:8000`. The full algorithm and first-time Linux setup are in [README.md](README.md).

## Endpoint

The default is `localhost:8000`. Save another instance with `mypi server IP:PORT`, or type `/server IP:PORT` in Pi or its web chat. `MYPI_SERVER_URL` overrides saved configuration. Bare hostnames default to port 8000; explicit HTTP(S) URLs retain their standard scheme port unless supplied.

`mypi status` reads actual health. `mypi start` verifies the server but never loads weights. `mypi stop` refuses to stop a shared model: use its owner on the host. Server preferences live in `~/.config/mypi/server.json`; `MYPI_SERVER_CONFIG` can select another file. The bundled tokenizer matches the tested Quality model. Set `MYPI_TOKENIZER` to another matching tokenizer before selecting a different model family.

`mypi serve --listen SERVER_LAN_IP --port 8000 --background` exposes a native loopback Qwen API. `--qwen-launcher /path/to/pi-local` starts the host's existing guard first. The Mac already has this model and launcher; no weights are included in this repository. The gateway adds same-host RSS to health and forwards native token/timing metrics. A client never probes remote PIDs locally.

## Interactive entry

```sh
mypi chat /path/to/project
# Equivalent shorthand:
mypi /path/to/project
mypi web
```

The CLI starts an architectural conversation; the web UI also has a separate intent classifier for ordinary discussion and read-only inspection. Existing folders are used directly. Missing folders can be initialized without a pre-existing plan or Git repository; development bootstrap creates Git. Inspection/shadow scanning itself remains read-only and does not initialize Git.

Local Qwen planning and review are the default. Change either with `/planner local|chatgpt` and `/reviewer local|chatgpt`. Run `mypi login` on this client for subscription planning; in Pi choose `/login openai` and ChatGPT sign-in. Do not copy credentials from another machine. `/thinkingcap 0` means uncapped reasoning, with total output still bounded; it does not disable thinking.

## Plan and execute

```sh
mypi plan /path/to/project "Implement a small pure function with edge-case tests" \
  --planner qwen --out /path/outside/project/plan.json
mypi execute /path/to/project /path/outside/project/plan.json \
  --run-dir /path/outside/project/run --reviewer qwen
```

Review granular todos and acceptance before execution. For one todo:

```sh
mypi run /path/to/project /path/outside/project/plan.json T1
```

At most two clarification answers are shared by request routing and intake. Unanswered questions pause rather than guessing. Noninteractive planning can supply `--answers-file`, a JSON array of up to two answers. Research uses `knowledge.md` and selected briefs, not whole fetched pages.

Generated shadow is outside source. Existing project `architecture.md` is accepted as written without a line-count or file-size limit, and generated architecture links it to current module prototypes. Model request budgets still apply to retrieved context. Above 32768 combined prototype/map tokens, architecture-only navigation and selected prototype supplements are enforced. Session `shadow-budget.json` records counts and tokenizer hash. Architecture-page evidence is invalidated by source changes.

Each V3 task has concrete steps, exact allowed files, observable acceptance, test argv, coverage links, dependencies, changed-line estimates and `on_failure=replan`. Its context recipe selects interfaces, functions, fixtures and knowledge topics; estimates plus at least 25% margin fit the input budget. Input, total output and thinking are separate caps. The verified model has 98304 capacity; 96k is not padded into each request. Keep at least 2048 output tokens beyond a positive thinking cap.

## Interrupted or failed work

```sh
mypi resume /path/to/project /path/outside/project/plan.json \
  --run-dir /path/outside/project/run
mypi replan /path/to/project /path/outside/project/run/replan-request.json \
  --planner qwen --out /path/outside/project/replacement.json
```

Resume uses the original run directory and immutable task scope/acceptance. Completed tasks are not repeated. Failure exit 20 requests a replan; exit 21 means coding finished but final review failed. Changed baselines or fixtures require explicit recovery. A reviewer follow-up plan is saved separately and does not execute automatically.

Progress is recorded/reported every 30 seconds. Metrics distinguish native token speed, first-token delay, token usage, model memory and sampled host RSS. Native metrics retain only the server's recent 32 requests; unavailable remote records are reported as unavailable. An SSH tunnel can be used in place of direct LAN serving, provided it forwards health/capabilities/metrics as well as completions.

## Remember and skills

`/remember` makes a fresh model request that distills essential information from the last completed assistant response into bounded `knowledge.md`, then refreshes shadow. It never copies the full answer as a fallback. `mypi skills` lists built-in executable skills and fixed input/output contracts. Web research includes DuckDuckGo, Wikipedia and focused public-page extraction. Optional domain skill bundles can be installed outside this repository and selected with `MYPI_DOMAIN_SKILLS`.

## Architecture navigation and rebuild

The default skills parse architecture sections and shadow interfaces in Python. `project_map architecture` returns a compact index; `architecture-search` searches literal keywords/function/class names, and `architecture-section` reads selected IDs. No model request is needed to build/search/check/rebuild the map. The complete symbol registry stays local.

After each coding edit, the automatic maintenance skill updates the owned architecture interface record, shadow and compact map. The map is built when absent or stale. Existing decision prose is preserved; architectural explanations use the append/insert skill. Todos pin section content hashes, so unrelated edits do not require loading the full architecture again.

If the sync-check skill reports drift, confirm with `/rebuild` in terminal Pi or the web chat. It rebuilds navigation using the native skill and verifies consistency. Start a new Pi session after upgrading mypi because existing sessions retain their pinned runtime.

To run the focused CPU tests:

```sh
agent-workflow-v2/.venv/bin/python -m unittest discover -s agent-workflow-v2 -p 'test_architecture*.py'
node --test agent-workflow-v2/test_architecture_hooks.mjs
```

## Privacy and scope

Projects and tests run on the client. Qwen receives selected request material; a ChatGPT planner receives refined requirements and interfaces, so prototype signatures/descriptions can leave the client when that planner is chosen. Implementation retrieval stays with the local worker. Executable skills/tests are trusted local programs; mypi is not an OS sandbox. Global Pi, Codex, conversations, model weights, private source projects and OAuth credentials are not included in the published repository.
