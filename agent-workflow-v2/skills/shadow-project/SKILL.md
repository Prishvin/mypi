---
name: shadow-project
description: Create a local interface-only project map before development planning.
---

Prepare and run this skill when the project shadow is missing or stale. The project
comes from the orchestrator's session binding, not a free-form model path.
The fixed script generates prototypes with brief descriptions, architecture.md,
knowledge.md and a source identity manifest. It never executes implementation or
changes the source project. Use the map to select small source spans for execution.
Failed parsing remains visible; the map does not claim testability or correctness.
