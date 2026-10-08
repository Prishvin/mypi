# Private Pi workflow architecture

- Planning sees brief decisions and generated prototypes; implementation stays local.
- Intake consolidates the request and at most two clarification answers before research.
- Research uses executable skills and publishes bounded, source-backed knowledge.md.
- User /remember notes retain external artifacts and refresh the knowledge shadow.
- Planner and reviewer independently select subscription Sol61 xhigh or local Quality.
- Plan contracts live outside the project so workers receive one atomic todo at a time.
- Deterministic scheduling owns dependency order, verification and durable progress.
- Every coding todo gets a fresh session and explicit input and output ceilings.
- Project architecture.md records brief decisions, ownership and dependency direction.
- Generated shadow/architecture.md links those decisions to current prototype files.
- Shadow regeneration follows every edit, test and completion; hashes detect staleness.
- An explicit resume preserves partial edits and original size baselines without replaying accepted todos.
- Actual test, scope or budget failures require replanning rather than automatic resume.
- Immutable external acceptance and regression checks protect behavior across retries.
- Final review reads prototypes/outcomes and saves a separate granular follow-up.
- Per-session runtime copies keep changes to tooling out of already-running workers.
- These private tools and profiles leave Codex and global agent settings unchanged.

## Responsibilities

| Component | Ownership |
| --- | --- |
| project_map.py and architecture_map.py | Source identity, prototypes and architecture navigation |
| shadow.py | Regeneration and freshness verification |
| plans.py and plan_contract.py | Granularity, retrieval recipes and reviewed budgets |
| planning_service.py | Planner selection and preserved replacement contracts |
| staged_planning.py and plan_refinement.py | Resumable draft, coverage and fresh per-todo review; atomic final publication |
| coverage_plan.py and pi-coverage-plan.mjs | Typed coverage matrix, requirement references and mandatory gap incorporation |
| planning_limits.py | Separate cloud planning ceilings and bounded local review packets |
| failure_context.py and recovery_runner.py | Measured failure review, preserved corrective plans, one repair then user escalation |
| strategy_review.py | Typed comparison of expectations with evidence, changed repair steps and a falsifiable first check; frozen acceptance remains unchanged |
| intake_service.py and request_pipeline.py | Durable questions, consolidated prompt and phase ordering |
| skill_registry.py and skill_runner.py | Typed purpose/pre/post contracts and fixed native pipelines |
| research_service.py and knowledge.py | Source-backed brief, merging, caching and publication |
| remember.py and pi-remember.mjs | Explicit output archive, bounded note and shadow refresh |
| role_selection.py and pi-role-selection.mjs | Independent private project model choices |
| review_packet.py, review_store.py and review_service.py | Final review and protected follow-up contracts |
| plan_runner.py and runner_resume.py | Task order, interruption checkpoints and explicit resume |
| launch.py and prefetch.py | One-task sessions and bounded initial context |
| pi-extension.mjs, pi-map-navigation.mjs and pi-hooks.mjs | Scoped tools, bounded section-address lookup, request admission and edit lifecycle |
| tasks.py and runner_evidence.py | Frozen acceptance, atomic gates and regressions |
| runner_process.py and run_metrics.py | Owned processes, memory, tokens and timing |

The reusable workflow depends on Pi and local MTPLX through explicit adapters.
Projects depend on their own interfaces, never on the model's conversation history.

Thinking controls: `thinking_caps.py` stores private project defaults; `pi-thinking-cap.mjs` validates slash commands and backend capability. Explicit frozen task caps win. The opt-in `../mtplx-pi-adapter` wraps native guard resolution with request-local state and pins server source; installed MTPLX files remain unchanged.

Memory distillation: `/remember` runs an isolated `memory` phase with only `memory_store`, using the current chat provider at low effort. `memory_draft.py` validates bounded source-grounded bullets; `remember.py` publishes only essentials and refreshes shadow under the project lock. No raw-copy fallback; generation failure leaves knowledge unchanged.

## Architecture navigation and maintenance

`architecture_sections.py` parses decision headings and maps them to shadow filenames, functions/classes and keywords. The compact Markdown map shows representative vocabulary; the full local JSON registry supports native literal searches. Selected sections carry content hashes; line ranges and the whole-document hash are refreshed after edits. `prefetch.py` reloads only each todo's selected decisions.

`architecture_maintenance.py` classifies changes and coordinates `architecture_sync.py`, `shadow.py` and compact-map generation. The private after-edit hook runs the reviewed architecture-maintenance skill directly in Python, without another model call. Frozen task scope reserves architecture.md. Only the owned interface record is mechanically updated; authored prose is preserved.

`architecture_update.py` provides hash-checked, locked append/insert decisions. `architecture_consistency.py` and architecture-sync-check detect stale artifacts and implement user-approved rebuilds with final verification. `/rebuild` invokes the skill, and the web route bypasses classification/inference. Skill failures and stale selected contracts block completion.

Planner completion: `planner_stop.py`, `pi-planning-finish.mjs` and `progress.py` verify publication and end the owned planner before redundant compaction. `recovery_accept.py` validates an already published stopped review for explicit continuation while retaining its raw failure evidence. Thinking telemetry separates completed provider usage, live reasoning-phase tokens and cached tokenizer estimates of the visible bounded tail.
