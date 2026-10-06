"""Require a completed batch answer rather than Pi's raw process exit alone."""
import json
from pathlib import Path


def completion(raw, session):
    """Return the preserved process failure or a diagnosed incomplete inspection."""
    if raw:
        return raw, ''
    session = Path(session)
    budget = session / 'request-budget-result.json'
    if budget.exists():
        evidence = json.loads(budget.read_text())
        if evidence.get('passed') is False:
            return 24, (f"Inspection stopped: request admission estimate {evidence.get('admission_tokens')} "
                        f"exceeds input budget {evidence.get('limit')}. Evidence: {budget}")
    timing = session / 'provider-timing.jsonl'
    final = None
    if timing.exists():
        for line in timing.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get('type') == 'request_end':
                final = row
    if final and final.get('stop_reason') != 'stop':
        return 1, ('Inspection did not produce a completed answer: ' +
                   str(final.get('error') or final.get('stop_reason')) + '. Evidence: ' + str(timing))
    return 0, ''
