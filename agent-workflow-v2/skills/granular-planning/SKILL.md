---
name: granular-planning
description: Plan atomic behavior changes with precise test coverage and per-task budgets.
---

Architect role: inspect prototypes only and state missing contracts. Initial drafts save plan_version=3; pinned reviews use only the current sparse repair or coverage tool schema, never resend the full plan. Full task contracts below describe the resulting plan and split children, not sparse patch arguments. Each todo addresses one observable behavior or independently testable seam with 2-6 steps, exact files, assumptions, patch estimate <=300 changed lines and a test_strategy. Prefer 1-3 files/30-150 lines. Include verification in the same todo.
Specify given/when/then success, boundary and failure cases. Map every acceptance id to a real test argv command index; with one command use 0 throughout. Never invent fixture paths or pretend unrun tests pass. Order dependencies explicitly. Select small (16k input/8k output/2k thinking), standard (24k/16k/4k), or large (40k/32k/8k) as needed. Small/standard fit 64k; large needs 96k. Small fits32k with8192 tokens of template headroom. These are independent ceilings, not token targets or a whole-project retrieval allowance. Count the complete request as input. Thinking is inside total output, not additional capacity. Local thinking caps do not apply to ChatGPT.
Code role: execute only the selected frozen todo. If a prerequisite is missing, identify it rather than expanding scope. Do not replan the entire project in the executor.
