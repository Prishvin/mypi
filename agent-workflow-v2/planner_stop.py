"""Accept a deliberate planner stop only for its verified immutable output."""
import hashlib
import json
from pathlib import Path


def verified(project, output, session, current_source=False):
    """Verify a saved artifact independently of the planner process outcome."""
    output, session = Path(output), Path(session)
    try:
        marker = json.loads((session / 'planning-stop.json').read_text())
        if Path(marker['plan']).resolve() != output.resolve():
            return False
        payload = output.read_bytes()
        if marker['sha256'] != hashlib.sha256(payload).hexdigest():
            return False
        from plan_runner import validate
        validate(Path(project), json.loads(payload))
        if current_source:
            from project_map import scan
            if json.loads(payload).get('snapshot') != scan(Path(project), ['.'])['snapshot']:
                return False
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return True


def exit_code(raw, project, output, session):
    """Preserve timeouts/errors; normalize only a matching validated plan marker."""
    if raw not in (0, 1):return raw
    return 0 if verified(project, output, session) else raw
