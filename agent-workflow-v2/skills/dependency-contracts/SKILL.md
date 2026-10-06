---
name: dependency-contracts
description: Check API versions and dependency contracts before integrating a library.
---

When a task depends on an unfamiliar API, identify the installed/pinned version from a bounded local contract. Use web_research to fetch the matching official docs, changelog or source; community answers must match the relevant version before adoption. Save a brief with exact signatures, compatibility constraints, recommended minimal integration and unresolved questions.
Keep third-party code behind a narrow adapter and test it with fakes. Do not install packages, migrate frameworks or change server/system configuration as an incidental code fix. If a required dependency or test command is absent, record that prerequisite explicitly in the plan. Research should settle a concrete decision, not become open-ended browsing.
