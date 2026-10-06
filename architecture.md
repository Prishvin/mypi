# mypi architecture

The client owns projects and execution; the Qwen server owns inference. No worker may start/stop the shared model or change a frozen task's endpoint.

| Component | Responsibility |
| --- | --- |
| `mypi`, `install.sh` | Portable entry, symlink resolution, private Python environment and locked Pi dependencies. |
| `pi_local.py` | Chat/plan/execute/resume/review and server configuration dispatch. |
| `agent-workflow-v2/server_config.py`, `pi-server.mjs` | Validate and persist endpoints; refresh idle Pi model selection; pin worker connections. |
| `quality_service.py` | Client compatibility layer that checks a server without owning model processes. |
| `server_proxy.py` | Optional host-side LAN API gateway, streaming preservation and host RSS telemetry. |
| `qwen-host/`, `setup-qwen.sh` | Optional Mac host: pinned downloads/dependencies, artifact verification, measured 96k/MTP3/normal-KV recipe and owned GPU/memory guard. |
| `agent-workflow-v2/launch.py`, `runtime.py`, `platform_paths.py` | Private per-role sessions, immutable runtime, platform-neutral executable resolution and token budgets. |
| `project_map.py`, `shadow.py`, `architecture_map.py`, `shadow_navigation.py` | Current interface shadow, architectural links, measured 32k rule and bounded selected reads. |
| `planning_service.py`, `plans.py`, `plan_runner.py`, `runner_resume.py` | V3 contracts, deterministic task scheduling, gates, evidence checkpoints and recovery. |
| `research_*`, `skills/`, `remember.py` | Bounded public research, executable skills and fresh knowledge distillation. |
| `review_*`, `role_selection.py`, `thinking_caps.py` | Independent review choice and per-project reasoning controls outside source. |
| `pi-web/` | Client-side persisted conversations, intent routing, inline clarifications, genuine Pi RPC, raw Qwen and sharing. |
| `remote_metrics.py`, `run_metrics.py`, `runner_process.py` | Native remote timings/token counts plus client-side execution evidence; no remote PID signaling. |

The internal workflow directory name preserves existing imports and test contracts. Public commands and UI are named mypi. Mutable sessions, logs, user projects and authentication are ignored by Git.

Input budgets limit actual requests. A 96k server does not imply a 96k prompt. Planning above 32k combined shadow/map tokens navigates only through generated architecture and task-relevant prototype supplements. Atomic execution gets only its selected todo, evidence and implementation spans.

Model hosting is separate: the gateway forwards a compatible server and can explicitly start the optional host owner first. MTPLX remains a Mac-side dependency, not a Linux client requirement. The request-local cap adapter is retained as a small independently testable module, without vendoring MTPLX or model weights.

## Architecture navigation and maintenance

`architecture_sections.py` parses decision headings and maps them to shadow filenames, functions/classes and keywords. The compact Markdown map shows representative vocabulary; the full local JSON registry supports native literal searches. Selected sections carry content hashes; line ranges and the whole-document hash are refreshed after edits. `prefetch.py` reloads only each todo's selected decisions.

`architecture_maintenance.py` classifies changes and coordinates `architecture_sync.py`, `shadow.py` and compact-map generation. The private after-edit hook runs the reviewed architecture-maintenance skill directly in Python, without another model call. Frozen task scope reserves architecture.md. Only the owned interface record is mechanically updated; authored prose is preserved.

`architecture_update.py` provides hash-checked, locked append/insert decisions. `architecture_consistency.py` and architecture-sync-check detect stale artifacts and implement user-approved rebuilds with final verification. `/rebuild` invokes the skill, and the web route bypasses classification/inference. Skill failures and stale selected contracts block completion.
