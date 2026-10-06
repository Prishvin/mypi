---
name: architecture-update
description: Insert architectural decisions without replacing the existing project document.
---
Prepare this skill before running it. First read the current section index and required section. Supply its exact source SHA256 (empty string only when architecture.md does not exist). `insert` appends prose to the selected section's direct body before children; `append_section` appends a titled section. No deletion, replacement or full-document rewrite. Link concrete source paths so the index associates shadow prototypes.
The coding task must declare architecture.md. If it does not, request a scoped replan. A stale hash or refresh error blocks completion; reload current evidence. The native script preserves existing bytes, refreshes shadow/index and records a receipt. Concurrent skill calls use a project lock; direct external editor writes do not use that lock.
