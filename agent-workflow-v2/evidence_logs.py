"""Resolve only test logs recorded by the current, project-bound task state."""
import json
import os
from pathlib import Path


def recorded_log(root: Path, requested: str) -> Path | None:
    """Grant no general session access; reject escaped or differently bound evidence."""
    session_name = os.environ.get('QWEN_WORKFLOW_SESSION')
    state_name = os.environ.get('QWEN_WORKFLOW_STATE')
    if not session_name or not state_name:
        return None
    session, state = Path(session_name).resolve(), Path(state_name).resolve()
    if state != session / 'task-state.json' or not state.is_file():
        return None
    data = json.loads(state.read_text())
    target = (root / requested).resolve()
    logs = [Path(row['log']) for row in data.get('evidence', {}).get('results', [])
            if isinstance(row.get('log'), str)]
    if not any(log.is_absolute() and log.resolve() == target for log in logs):
        return None
    project = data.get('before', {}).get('root')
    if not project or Path(project).resolve() != root.resolve():
        raise ValueError('Recorded test log belongs to a different project')
    if not target.is_relative_to(session) or not target.is_file():
        raise ValueError('Recorded test log must be an existing file inside the current session')
    return target
