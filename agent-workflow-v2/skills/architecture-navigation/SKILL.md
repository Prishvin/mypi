---
name: architecture-navigation
description: Search a compact architecture-to-shadow map before reading selected decisions.
---
Active workflow: read architecture, parse headings, read shadow filenames/interfaces, then build architecture-map.md/json. Map rows link section IDs to files; the interface vocabulary lists functions, classes and keywords without implementation bodies. Use literal search in the map; retrieve only matching architecture sections and a few associated prototypes. Current line ranges are disposable; stable IDs plus the source SHA256 protect later reads.
Prepare/run this native skill for index, search or section actions. The regular project_map architecture/architecture-search/architecture-section tools use the same native implementation. The skill's generated artifacts remain outside source and inspection never edits architecture.md. Index offset pages headings; section offset counts characters. Reload the index after edits. For coding, every edit refreshes owned architecture interface metadata, shadow and map; architectural explanations use architecture-update insert/append.
