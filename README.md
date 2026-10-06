# mypi

A portable Pi coding workflow for macOS and Linux, using Qwen on this machine or a separate server. Projects, tools, tests, shadow maps and execution run on the client; model weights stay on the Qwen host.

The default endpoint is **`http://localhost:8000`**. The tested server is MTPLX Quality, with 96k capacity, MTP3, normal KV and the request-local thinking-cap adapter. Context capacity is a ceiling: workers send only the material selected for their atomic task.

## Install

Requires Python **3.12+**, Node **22.19+**, Git, ripgrep (`rg`) and `ps` (Linux package `procps`). macOS and Linux use the same installer:

```sh
git clone git@github.com:Prishvin/mypi.git
cd mypi
./install.sh
export PATH="$HOME/.local/bin:$PATH"
```

Set `MYPI_PYTHON=python3.12` when the default `python3` is older. The installer creates a private virtual environment, installs the locked Pi dependency and links `~/.local/bin/mypi`. It does not alter global Pi or Codex configuration.

## Connect and work

```sh
mypi server                       # show endpoint; default localhost:8000
mypi server 192.168.1.34:8000      # verify and save another Qwen instance
mypi status
mypi chat /absolute/path/to/project
```

In the Pi conversation:

```text
/server                         Show endpoint
/server 192.168.1.34:8000        Verify and switch the Qwen instance
/planner local                  Qwen planning, medium reasoning
/planner chatgpt                ChatGPT 6.1 Sol, xhigh
/reviewer local                 Select the final reviewer independently
/reviewer chatgpt
/thinkingcap 8192               Default cap; explicit atomic task caps win
/remember                       Fresh request distills the last answer into knowledge.md
```

Endpoint validation checks model identity, actual capacity, thinking-history policy and the thinking-cap adapter before saving. `/server` changes an idle main session, refreshing Pi's actual model connection. A frozen worker cannot switch endpoints. Each paused/running attempt retains its original endpoint; new turns and workers use the new choice.

Local planning/review is the default. For subscription planning, run `mypi login`, then `/login openai` and choose ChatGPT sign-in. Credentials stay in the ignored private planner configuration; each machine signs in separately.

## Qwen host

Start the existing guarded Qwen service on the model Mac. Then expose its API with the small gateway; the gateway does not load weights or change model parameters:

```sh
# Native model serves 127.0.0.1:8000; bind the gateway to this Mac's LAN IP.
mypi serve --listen 192.168.1.34 --port 8000 --background
```

To call an existing model launcher first:

```sh
mypi serve --qwen-launcher /absolute/path/to/pi-local \
  --listen 192.168.1.34 --port 8000 --background
```

The gateway forwards streaming completions, models, health, capabilities and native metrics to the default upstream `http://127.0.0.1:8000`. Native loopback and LAN gateway listeners can use the same port because they bind different addresses. An occupied incompatible address is rejected. Use the Mac's current LAN IP; `--listen 0.0.0.0 --port 8001` is an alternative when the native engine already uses all interfaces. `--upstream` selects another existing upstream. Stopping a client never stops the shared model.

Gateway logs: `~/.local/state/mypi/gateway/server.log`. Running without `--background` keeps the gateway in the foreground; Ctrl+C stops only that gateway. Optional `MYPI_SERVER_TOKEN` requires a bearer token on the gateway and supplies it on clients. `MYPI_UPSTREAM_TOKEN` is separate when the upstream itself needs authentication. Tokens are never stored in the repository.

## Web UI

```sh
mypi web
```

Open **http://localhost:8099**. Choose Pi or raw Qwen, create/delete conversations, attach a project, change planner/reviewer, and use `/server`. Development runs in the client's selected folder. A new conversation creates a separate default project. Clarifications appear in chat; busy/queued status, sharing, stop/resume, plans and final review are retained.

Use `mypi web --port 8100` if another app owns 8099. Optional LAN UI: `mypi web --listen 0.0.0.0 --allow-address YOUR_CLIENT_LAN_IP`. The UI allowlist and conversation sharing refer to the client hosting this UI, which can be a different machine from Qwen.

## Workflow

The UI first classifies discussion, inspection, ambiguity or development. At most two clarification answers refine one request. Bounded research skills find public sources, follow the first two DuckDuckGo links and distill relevant content into `knowledge.md`. Planning uses interfaces rather than whole implementations.

Above **32,768 shadow + architecture tokens**, generated `architecture.md` is the only project-wide map. The planner reads its pages, explains task-relevant selections, then reads up to five shadow files / 8,192 text tokens per read. Native tools require page evidence before prototype reads/scoped searches and reject global catalogs/unscoped searches. Selection still requires model judgment; the tools enforce scope and limits.

Granular V3 todos declare files, observable acceptance, tests, dependencies, context estimates/margins, input/output/thinking caps and deadlines. A deterministic executor starts one fresh Pi worker per todo, retrieves only selected source/fixtures, verifies edits and refreshes shadow after every edit and completion. Failure stops with an evidence packet for replanning. Accepted tasks are preserved; interrupted work resumes. The final reviewer proposes only evidenced fixes and useful missing tests.

See [run_local.md](run_local.md) for planning, execution and resume commands, and [architecture.md](architecture.md) for the implementation map.

## Linux container

```sh
docker build -t mypi .
docker run --rm -it \
  -e MYPI_SERVER_URL=http://192.168.1.34:8000 \
  -v "$PWD/my-project:/workspace/project" \
  -v mypi-sessions:/opt/mypi/agent-workflow-v2/sessions \
  mypi chat /workspace/project
```

Mount `/root/.config/mypi` to retain server preferences and `/opt/mypi/agent-workflow-v2/planner-config` to retain a container's private subscription login. For durable runs, mount a separate evidence folder and pass it with `--run-dir`.

## Verification

```sh
agent-workflow-v2/.venv/bin/python -m unittest discover -s agent-workflow-v2
agent-workflow-v2/.venv/bin/python -m unittest discover -s pi-web/tests
npm test
```

GitHub Actions runs the same CPU checks on macOS and Linux. [VALIDATION.md](VALIDATION.md) records measured release checks and live proofs; tests do not require a model or ChatGPT login.
