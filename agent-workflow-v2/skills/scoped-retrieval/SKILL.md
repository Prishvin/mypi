---
name: scoped-retrieval
description: Retrieve only named functions, variables and references needed by one task.
---

Start from the supplied executor packet. Do not reread unchanged included code. Use project_map locate/inspect to narrow ownership, source_query symbol for named functions, variables for scopes/types, and literal search across 1-5 exact files for call sites/assignments. Batch related symbols in one file. Read actual implementation before editing; prototypes describe contracts only.

For a file's data/constants or a bounded source page, use `source_query({action:"file",paths:["src/example.mjs"],offset:0})`; no query is needed. `fixture` is for exact pinned external test paths. `symbol` and `search` require a nonempty query. Use `project_map inspect` with exact file paths; `locate` searches names and needs a query as well as selected paths. Directories are not source files.
Aim for 3-6 retrieval calls, then make the smallest justified edit. Do not request all files, recursive repository dumps, huge logs or speculative searches. Stop when evidence is sufficient. After a failure, inspect the specific failing case and implicated symbol instead of restarting broad discovery. Architect role uses only prototype tools; implementation retrieval is unavailable.
