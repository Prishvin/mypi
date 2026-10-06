"""Publish a new project's model-authored contracts without an extra model call."""
import hashlib
from pathlib import Path
import re
import os


def sectioned(text):
    """Add navigation headings to plain proposals, preserving every original text line."""
    if re.search(r'^#{1,6}\s', text, re.M):
        return text
    lines = ['# Planned architecture', '']
    for line in text.splitlines():
        module = re.match(r'^- (src/[^:]+):', line)
        label = re.match(r'^([A-Z][A-Z ()/&-]{2,50}):', line)
        if module:
            lines.extend(['', '## ' + module[1], ''])
        elif label:
            lines.extend(['', '## ' + label[1].title(), ''])
        lines.append(line)
    return '\n'.join(lines) + '\n'


def bootstrap(root, plan):
    """Exclusively create missing architecture at execution start; never overwrite prose."""
    destination = root / 'architecture.md'
    if destination.is_symlink():
        raise ValueError('architecture.md must be a regular project file')
    if destination.exists():
        if not destination.is_file():
            raise ValueError('architecture.md must be a regular project file')
        return {'created': False}
    if 'architecture.md' not in plan['tasks'][0]['files']:
        return {'created': False}
    content = sectioned(plan['architecture']).encode()
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return {'created': False}
    with os.fdopen(descriptor, 'wb') as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    return {'created': True, 'sha256': hashlib.sha256(content).hexdigest(),
            'origin': 'Accepted planner architecture; Python navigation headings only'}
