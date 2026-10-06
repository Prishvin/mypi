---
name: architecture-maintenance
description: Automatically maintain architecture metadata, shadow and compact map after each code mutation.
---
The Pi edit hook invokes this Python skill directly; it costs zero model requests. Native code classifies added, modified, deleted and unambiguous same-content renamed files, and flags interface changes. It updates only the owned architecture interface record, preserves authored prose, refreshes shadow prototypes and builds a compact map if missing or stale. If all artifacts already match, map regeneration is skipped.
The bound coding task reserves architecture.md before edits. Failed/partial mutations still trigger maintenance. Errors block acceptance and retain recovery evidence. Architectural reasoning uses architecture-update insert/append; existing prose is never automatically rewritten. External drift uses architecture-sync-check check, asks for confirmation, then rebuild.
