"""Accept a deliberate planner stop only for its verified immutable output."""
import hashlib
import json
from pathlib import Path


def exit_code(raw, project, output, session):
    """Preserve timeouts/errors; normalize only a matching validated plan marker."""
    if raw not in (0, 1):
        return raw
    output, session = Path(output), Path(session)
    try:
        marker = json.loads((session / 'planning-stop.json').read_text())
        if Path(marker['plan']).resolve() != output.resolve():
            return raw
        payload = output.read_bytes()
        if marker['sha256'] != hashlib.sha256(payload).hexdigest():
            return raw
        from plan_runner import validate
        validate(Path(project), json.loads(payload))
    except (OSError, ValueError, KeyError, TypeError):
        return raw
    return 0
