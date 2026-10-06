"""Discover reviewed executable skills without reading a project's implementation."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from jsonschema import Draft202012Validator

BASE = Path(__file__).resolve().parent


def package(base, name):
    """Resolve one private skill pack and reject links or oversized contents."""
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name):
        raise ValueError('Use an installed skill name, not a path')
    root = base / 'skills' / name
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Skill is not installed: ' + name)
    entries = list(root.rglob('*'))
    files = sorted(p for p in entries if not p.is_dir())
    if len(files) > 50 or any(p.is_symlink() for p in entries):
        raise ValueError('Skill packs must have at most 50 regular files and no symlinks')
    if sum(p.stat().st_size for p in files) > 262144:
        raise ValueError('Keep an executable skill pack below 256 KiB')
    return root, files


def load(name, base=BASE):
    """Validate a versioned skill contract and bind scripts to a content identity."""
    root, files = package(base, name)
    data = json.loads((root / 'skill.json').read_text())
    if data.get('version') != 1 or data.get('name') != name:
        raise ValueError('Executable skills require matching name and version 1')
    for key, maximum in [('purpose', 300), ('pre_prompt', 4000), ('post_prompt', 4000)]:
        if not isinstance(data.get(key), str) or not 1 <= len(data[key]) <= maximum:
            raise ValueError('Missing or oversized skill ' + key)
    if not set(data.get('roles', [])) <= {'research', 'architect', 'code', 'chat', 'inspect', 'reviewer'} or not data.get('roles'):
        raise ValueError('A skill must declare its allowed workflow roles')
    scoped = name in {'architecture-update', 'architecture-maintenance'} and data.get('side_effects') == 'scoped-architecture' and data['roles'] == ['code']
    bound = name == 'architecture-sync-check' and data.get('side_effects') == 'bound-navigation'
    if data.get('side_effects') != 'session-artifacts' and not scoped and not bound:
        raise ValueError('Skills must declare generated files as owned session artifacts')
    Draft202012Validator.check_schema(data['input_schema'])
    binaries = data.get('binaries', {})
    if not binaries or any(not re.fullmatch(r'[a-z][a-z0-9_]*', k) for k in binaries):
        raise ValueError('Declare the installed binaries used by this skill')
    steps = data.get('steps', [])
    if not 1 <= len(steps) <= 6:
        raise ValueError('A skill needs 1-6 fixed script/binary steps')
    for step in steps:
        argv = step.get('argv', [])
        if not 1 <= len(argv) <= 24 or any(not isinstance(a, str) or len(a) > 1000 for a in argv):
            raise ValueError('Skill commands must be bounded literal argv lists')
        if argv[0] not in {'{' + key + '}' for key in binaries}:
            raise ValueError('Step executable must be a declared binary placeholder')
        if not 1 <= step.get('timeout_seconds', 0) <= 45:
            raise ValueError('Each skill step needs a 1-45 second deadline')
        if not 512 <= step.get('max_output_bytes', 0) <= 8192:
            raise ValueError('Each skill step needs a 512-8192 byte output bound')
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(root)).encode() + b'\0' + path.read_bytes())
    return {**data, 'path': str(root), 'sha256': digest.hexdigest()}


def catalog(base=BASE, role=None):
    """List purposes only; load prompts and code for one selected skill on demand."""
    rows = []
    for path in sorted((base / 'skills').glob('*/skill.json')):
        skill = load(path.parent.name, base)
        if role is None or role in skill['roles']:
            rows.append({k: skill[k] for k in ['name', 'purpose', 'roles']})
    return rows


def binaries(skill):
    """Resolve declared binaries without interpolating any model input into argv."""
    result = {}
    for alias, command in skill['binaries'].items():
        resolved = sys.executable if command == 'python' else shutil.which(command)
        if not resolved:
            raise ValueError('Required binary is unavailable: ' + command)
        result[alias] = resolved
    return result
