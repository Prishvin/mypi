"""Load the private workflow's default skills without discovering global instructions."""
import json
from pathlib import Path


def instructions(base: Path, role='code') -> str:
    """Load reviewed, small default skills from the session's pinned runtime."""
    manifest = base/'skills.json'
    if not manifest.exists():
        return ''
    chunks = []
    names = json.loads(manifest.read_text())['default_skills']
    if role in ('intake','memory','chat','inspect'):
        return ''
    if role == 'research':
        names = ['web-research']
    if role == 'reviewer':
        names = ['granular-planning']
    for name in names:
        path = base/'skills'/name/'SKILL.md'
        if path.parent.parent != base/'skills':
            raise ValueError('Invalid private skill path')
        text = path.read_text()
        if text.startswith('---\n'):
            text = text.split('---',2)[2].strip()
        chunks.append('ACTIVE PRIVATE PI SKILL: '+name+'\n'+text)
    from skill_registry import catalog
    chunks.append('EXECUTABLE PRIVATE SKILLS (prepare to read prompts/schema, then run):\n' + json.dumps(catalog(base, role)))
    result = '\n\n'.join(chunks)
    if len(result.encode())>14000:
        raise ValueError('Default skill instructions exceed 14 KiB; shorten the private skills')
    return result
