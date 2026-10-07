# Browser interaction review

Load for browser adapters, application bootstrap and real interaction checks.
Use the fixed `skill.json` procedure/checklist; it does not execute a browser test.

Check startup, injectable DOM/time, consumed mouse deltas, keyboard rates,
focus/pause, pointer-lock rejection and fresh-gesture resume, live references
after restart, and computed overlay visibility. Test adapter behavior with fakes,
then observe actual browser input/rendering. Record the test evidence explicitly.
