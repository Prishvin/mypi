---
name: architecture-sync-check
description: Detect stale architecture, map or shadow and request a rebuild before relying on it.
---
Check current source hashes, architecture hash, section links and saved prototypes/map. A coding contract also checks maintained interface records. The check action is read-only. The rebuild action regenerates the bound shadow and map; it also repairs the owned architecture interface metadata while preserving authored prose. Coding sessions use their frozen scope. If rebuild_required is true, quote the reasons in the main chat and ask for confirmation in the main chat. After confirmation, run this skill with action=rebuild; /rebuild invokes it directly. Keep stale evidence out of planning. Rebuild includes a final consistency check and fails unless current evidence matches. New sessions initialize a fresh shadow; each mypi edit maintains it automatically.
This checks structural freshness. It cannot prove that authored architectural prose correctly describes behavior; the reviewer evaluates that.
