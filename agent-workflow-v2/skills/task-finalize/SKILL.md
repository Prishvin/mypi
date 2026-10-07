# Task finalization

`workflow_test` is the direct shortcut to this native Python skill. Automatic
post-edit hooks use the same implementation. Full logs stay in session artifacts;
Qwen receives only current gates and bounded failure diagnostics.

Create all declared deliverables. Tests run automatically once they exist. If code
passes and the gate requests an architecture decision, call `workflow_test` with
one brief `architecture_note` and the plan's optional `architecture_title`.
Python handles scope, current hashes, insertion, shadow/map refresh, fresh frozen
tests and the final gate. A missing note is a finalization step, not a code defect.
Never invent design decisions or erase existing prose. For precise section placement,
use `architecture-update`. A false native gate means the task is still unfinished.
