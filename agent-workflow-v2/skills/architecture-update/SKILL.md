---
name: architecture-update
description: Insert architectural decisions without replacing the existing project document.
---
Prepare this skill before running it. First read the current section index and required section. Preparation returns `architecture_revision.expected_sha256`: the current whole-document byte hash (empty string only when architecture.md does not exist). Copy it to `expected_sha256`; the top-level `sha256` identifies the skill version and cannot be used as a document hash.

Source edits automatically refresh the document's owned interface metadata, even when authored prose stays the same. Prepare again after intervening edits. If the revision is stale, reload the index/target section and retry the intended insertion using fresh preparation. Do not restart planning solely for a stale revision; actual scope/contract changes require a replan. Native compare-and-swap still rejects stale writes.

`insert` appends prose to the selected section's direct body before children; `append_section` appends a titled section. No deletion, replacement or full-document rewrite. Link concrete source paths so the index associates shadow prototypes.

The coding task must declare architecture.md. If it does not, request a scoped replan. A refresh error blocks completion; reload current evidence. The native script preserves existing bytes, refreshes shadow/index and records a receipt. Concurrent skill calls use a project lock; direct external editor writes do not use that lock.
