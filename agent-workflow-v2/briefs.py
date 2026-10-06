"""Attach reviewed external contracts only to the exact source they describe."""
import json
import os
from pathlib import Path


def annotate(files: list[dict], path: str | None = None) -> list[str]:
    """Ignore stale briefs so edited implementations cannot inherit old guarantees."""
    path = path or os.environ.get('QWEN_WORKFLOW_BRIEFS')
    if not path:
        return []
    entries = json.loads(Path(path).read_text()).get('files', {})
    stale = []
    for record in files:
        entry = entries.get(record['path'])
        if not entry:
            continue
        if entry.get('sha256') != record['sha256']:
            stale.append(record['path'])
            continue
        record['brief_origin'] = 'Reviewed external brief, bound to source SHA256'
        if entry.get('description'):
            record['description'] = entry['description']
        for symbol in record['symbols']:
            if symbol['name'] in entry.get('symbols', {}):
                symbol['description'] = entry['symbols'][symbol['name']]
    return stale
