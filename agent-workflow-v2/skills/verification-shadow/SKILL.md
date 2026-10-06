---
name: verification-shadow
description: Keep edits independently testable and refresh shadow interfaces after every mutation.
---

Code role: keep deterministic logic separate from external adapters and inject clocks, randomness, paths and clients. Use fakes for model/network/media boundaries. Add meaningful behavior, boundary and failure tests with the change. New named functions need brief descriptions; new files <=300 lines/32 KiB and functions <=60 lines.
After every edit/write, Pi refreshes the shadow. Tests are frozen in the task contract; use workflow_test and inspect the failing assertion. Fix one cause per retry. Editing invalidates old test evidence. Completion needs current tests plus the current scope/size/shadow gate; a playable preview alone is not proof. Automatic local stop-after-pass still requires a fresh passing gate. Keep patches and evidence; do not auto-commit unrelated files. Architect role plans these checks but cannot execute them.

After every code mutation, the native refresh also inserts/updates only mypi-owned interface metadata in architecture.md and rebuilds architecture-map.md/json. The frozen scope reserves architecture.md before editing. Existing decision prose is preserved. Use architecture-navigation map search and selected section reads; never repeat the entire architecture document per todo. For changed architectural decisions, prepare/run architecture-update with a current source SHA256 to insert/append prose. Required decision updates block automatic acceptance until a fresh scoped insertion receipt and tests exist.
