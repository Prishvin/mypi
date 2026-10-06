"""Record task scope and bind passing test evidence to the final source snapshot."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
from difflib import SequenceMatcher, unified_diff
from project_map import scan
from policy import validate_change
import shadow
from verification_counts import count as test_count


def hash_file(path: Path) -> str | None:
    """Hash a declared file, including docs; represent deleted files explicitly."""
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def readonly_tests(root: Path, commands: list[list[str]]) -> dict:
    """Pin existing external source fixtures named directly in test argv lists."""
    from sources import EXTENSIONS
    candidates = {(root / arg).resolve() for command in commands for arg in command}
    return {str(p): hash_file(p) for p in candidates
            if p.suffix in EXTENSIONS and p.is_file() and not p.is_relative_to(root.resolve())}


def save_patch(state: Path) -> Path:
    """Preserve only the frozen task's changes without staging or committing anything."""
    data = json.loads(state.read_text())
    root = Path(data['before']['root'])
    parts = []
    for path, before in data['declared_text'].items():
        after = (root / path).read_text() if (root / path).is_file() else ''
        parts.extend(unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                  fromfile='a/' + path, tofile='b/' + path))
    output = state.parent / 'changes.patch'
    output.write_text(''.join(parts))
    return output


def validate_paths(root: Path, paths: list[str]) -> None:
    """Require concrete project-relative paths, never globs or parent escapes."""
    root = root.resolve()
    for path in paths:
        if Path(path).is_absolute() or not (root / path).resolve().is_relative_to(root):
            raise ValueError('Task path escapes project: ' + path)
        if any(c in path for c in '*?['):
            raise ValueError('Declare exact file paths: ' + path)


def begin(root: Path, prefixes: list[str], task: dict, state: Path, shadow_path: Path | None = None) -> dict:
    """Freeze acceptance criteria and allowed files before editing starts."""
    root = root.resolve()
    if state.exists():
        raise ValueError('Task state already exists; use a new state file')
    if not task.get('goal') or not task.get('acceptance') or not task.get('tests'):
        raise ValueError('A task requires goal, acceptance and test argv lists')
    import architecture_sync
    task = architecture_sync.scoped(task)
    allowed = task.get('files', [])
    validate_paths(root, allowed)
    for command in task['tests']:
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise ValueError('Tests must be nonempty argv lists; shell strings are not accepted')
    shadow_path = shadow_path or state.parent / (state.stem + '-shadow')
    shadow.refresh(root, prefixes, shadow_path)
    data = {'task': task, 'before': scan(root, prefixes), 'shadow': str(shadow_path.resolve()),
            'readonly_tests': readonly_tests(root, task['tests']),
            'declared_hashes': {p: hash_file(root / p) for p in allowed},
            'declared_text': {p: (root / p).read_text() if (root / p).is_file() else '' for p in allowed}}
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(data, indent=2))
    return data


def current_snapshot(data: dict) -> tuple[dict, dict, str]:
    """Bind indexed code and all declared files to one reproducible identity."""
    before = data['before']
    root = Path(before['root'])
    after = scan(root, before['prefixes'])
    declared = {p: hash_file(root / p) for p in data['task']['files']}
    external = {p: hash_file(Path(p)) for p in data.get('readonly_tests', {})}
    identity = after['snapshot'] + json.dumps({'declared': declared, 'readonly': external}, sort_keys=True)
    return after, declared, hashlib.sha256(identity.encode()).hexdigest()


def inherit_baseline(state: Path, baseline: Path) -> None:
    """Keep failed attempts from turning newly introduced size debt into legacy code."""
    current = json.loads(state.read_text())
    original = json.loads(baseline.read_text())
    if (current['before']['root'] != original['before']['root']
            or set(current['task']['files']) != set(original['task']['files'])):
        raise ValueError('Retry baseline must have the same project and file scope')
    for key in ('before', 'declared_hashes', 'declared_text'):
        current[key] = original[key]
    current['baseline_state'] = str(baseline)
    state.write_text(json.dumps(current, indent=2))


def run_tests(state: Path, timeout=None) -> dict:
    """Run declared commands once and save full logs outside the target project."""
    import architecture_sync
    architecture_sync.sync(state)
    data = json.loads(state.read_text())
    timeout = timeout or data['task'].get('execution', {}).get('test_timeout_seconds', 300)
    _, _, snapshot = current_snapshot(data)
    results = []
    for index, command in enumerate(data['task']['tests']):
        log = state.parent / f'{state.stem}-test-{index}.log'
        started_epoch=time.time();started_monotonic=time.monotonic()
        with log.open('w') as output:
            try:
                process = subprocess.run(command, cwd=data['before']['root'],
                                         stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = 124
            except OSError as exc:
                output.write(str(exc))
                code = 127
        elapsed=time.monotonic()-started_monotonic
        measurement={'argv':command,'exit_code':code,'started_epoch':started_epoch,
                     'ended_epoch':time.time(),'wall_seconds':elapsed}
        with (state.parent/'test-timing.jsonl').open('a') as timing:
            timing.write(json.dumps(measurement)+'\n')
        result={'argv': command, 'exit_code': code, 'log': str(log)}
        measured=test_count(command,log.read_text(errors='replace'))
        if measured is not None:result['tests_collected']=measured
        results.append(result)
    shadow.refresh(Path(data['before']['root']), data['before']['prefixes'], Path(data['shadow']))
    _, _, finished = current_snapshot(data)
    data['evidence'] = {'snapshot': snapshot, 'finished_snapshot': finished,
                        'results': results}
    state.write_text(json.dumps(data, indent=2))
    return data['evidence']


def ensure_test_evidence(state: Path) -> dict:
    """Run the external final verifier only when current evidence is absent or stale."""
    data = json.loads(state.read_text())
    _, _, identity = current_snapshot(data)
    evidence = data.get('evidence', {})
    if (evidence.get('snapshot') == identity and evidence.get('finished_snapshot') == identity
            and len(evidence.get('results', [])) == len(data['task']['tests'])):
        return evidence
    return run_tests(state)


def check(state: Path) -> dict:
    """Check atomic scope, size and fresh test results; never commit automatically."""
    data = json.loads(state.read_text())
    after, declared, identity = current_snapshot(data)
    task = data['task']
    result = validate_change(data['before'], after, task['files'])
    if any(hash_file(Path(p)) != digest for p, digest in data.get('readonly_tests', {}).items()):
        result['violations'].append('An immutable external acceptance test changed')
    result['violations'].extend(shadow.verify(data, after))
    import architecture_sync
    result['violations'].extend(architecture_sync.verify(data, after))
    result['shadow_snapshot'] = after['snapshot']
    changed = set(result['changed']) | {p for p, h in declared.items()
                                      if h != data['declared_hashes'].get(p)}
    result['changed'] = sorted(changed)
    missing=[p for p in task['files'] if data['declared_hashes'].get(p) is None and declared.get(p) is None
             and not (p == 'architecture.md' and task.get('architecture_maintenance') and not data.get('declared_text', {}).get(p))]
    if missing:result['violations'].append('Declared new files are missing: '+', '.join(missing))
    if len(changed) > 8:
        result['violations'].append('More than 8 changed source/declaration files')
    patch_lines = 0
    root = Path(data['before']['root'])
    for p in changed & data['declared_text'].keys():
        original = data['declared_text'][p].splitlines()
        current = (root / p).read_text().splitlines() if (root / p).is_file() else []
        for tag, a, b, c, d in SequenceMatcher(a=original, b=current, autojunk=False).get_opcodes():
            if tag != 'equal':
                patch_lines += b - a + d - c
    result['patch_lines'] = patch_lines
    if patch_lines > 300:
        result['violations'].append(f'Patch has {patch_lines} changed lines; split into atomic tasks')
    evidence = data.get('evidence', {})
    if evidence.get('snapshot') != identity or evidence.get('finished_snapshot') != identity:
        result['violations'].append('Test evidence missing or stale after the latest edit')
    tests = evidence.get('results', [])
    if not tests or len(tests) != len(task['tests']) or any(t['exit_code'] for t in tests):
        result['violations'].append('Declared tests have not all passed')
    if any(t.get('tests_collected')==0 for t in tests):
        result['violations'].append('A declared unittest command ran zero tests')
    if task.get('context', {}).get('architecture_update_required'):
        receipt = state.parent / 'architecture-update.json'
        try:
            update = json.loads(receipt.read_text())
            valid = (update.get('state') == str(state.resolve()) and
                     update.get('after_sha256') == declared.get('architecture.md') and
                     update.get('before_sha256') != update.get('after_sha256'))
        except (OSError, ValueError):
            valid = False
        if not valid:
            result['violations'].append('Required scoped architecture insertion is missing or stale')
    result['passed'] = not result['violations']
    result['limits'] = 'Checks indexed source and declared files. Testability requires review; this is not an OS sandbox.'
    return result
