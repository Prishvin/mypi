"""Persist a small Python execution watchdog at Pi request/compaction boundaries."""
import argparse
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import time
from execution_progress import advance
from execution_audit import error_brief
from runner_process import save


def read(path, default=None):
    """Missing optional evidence is empty; malformed journals fail visibly."""
    return json.loads(path.read_text()) if path.exists() else (default if default is not None else {})


def evidence(contract, session):
    """Hash scoped contents; retain only bounded, stable test diagnostics, never bodies."""
    root = Path(contract['before']['root']).resolve()
    files = {}
    for name in contract['task']['files']:
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Progress file escapes the project')
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    tests = []
    for row in contract.get('evidence', {}).get('results', []):
        observations = []
        log = Path(row.get('log', '')).resolve()
        if log.is_relative_to(session.resolve()) and log.is_file():
            for line in log.read_text(errors='replace').splitlines():
                if line.strip().startswith(('not ok ', '✖ ', 'AssertionError', 'TypeError:', 'ReferenceError:',
                                             'SyntaxError:', 'FAILED ', 'FAIL:', 'ERROR:', 'error:')):
                    observations.append(re.sub(r'\s+\([^)]*ms\)\s*$', '', line.strip())[:160])
        tests.append({key: row.get(key) for key in ('argv', 'exit_code', 'tests_collected')}
                     | {'observations': list(dict.fromkeys(observations))[:4]})
    return {'files': files, 'tests': tests}


def clean(event):
    """Bound metadata before it enters a model handoff, ignoring arbitrary extra fields."""
    kind = event.get('kind')
    if kind in {'round', 'compaction'}:
        return {'kind': kind}
    if kind != 'tool':
        return {}
    selector = event.get('selector', {})
    row = {'kind': kind, 'tool': str(event.get('tool', ''))[:60],
           'selector': {k: str(selector[k])[:160] for k in ('action', 'path', 'paths', 'query', 'offset', 'name')
                        if k in selector}}
    if event.get('error'):
        row['error'] = error_brief(str(event['error']))
    return row


def deadline(session, identity, now=None):
    """Expose the bound process clock without extending or enforcing its deadline."""
    launch = read(session / 'launch.json')
    process = read(session / 'process.json')
    if not launch or not process or launch.get('timeout_seconds') is None:
        return None
    if (launch.get('role') != 'code'
            or Path(launch.get('project', '')).resolve() != Path(identity['project']).resolve()
            or Path(launch.get('state', '')).resolve() != (session / 'task-state.json').resolve()):
        raise ValueError('Deadline launch differs from the frozen task')
    timeout, started = launch['timeout_seconds'], process.get('started_epoch')
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) or value <= 0 for value in (timeout, started)):
        raise ValueError('Invalid bound attempt timing')
    clock = time.time() if now is None else now
    elapsed = max(0, clock - started)
    remaining = max(0, math.ceil(timeout - elapsed))
    return {'elapsed_seconds': math.floor(elapsed), 'remaining_seconds': remaining,
            'timeout_seconds': timeout, 'near_deadline': remaining <= min(300, timeout),
            'rule': 'Includes prompt loading, reasoning, tools and tests. This notice never extends the deadline.'}


def check(session, *, compaction=False):
    """Consume events once under a lock; preserve counters across Pi compactions/reloads."""
    session = session.resolve()
    with (session / 'execution-progress.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        contract = read(session / 'task-state.json')
        identity = {'project': str(Path(contract['before']['root']).resolve()), 'task': contract['task']['id']}
        saved = read(session / 'execution-progress.json')
        if saved and saved['identity'] != identity:
            raise ValueError('Progress journal belongs to another task')
        events_path = session / 'execution-events.jsonl'
        events, cursor = [], saved.get('cursor', 0)
        if events_path.exists():
            with events_path.open('rb') as stream:
                if stream.seek(0, 2) < cursor:
                    raise ValueError('Progress event journal was truncated')
                stream.seek(cursor)
                while line := stream.readline():
                    if not line.endswith(b'\n'):
                        break
                    events.append(clean(json.loads(line)))
                    cursor = stream.tell()
        if compaction:
            events.append({'kind': 'compaction'})
        result = advance(saved, evidence(contract, session), events)
        result.update(identity=identity, cursor=cursor)
        # A stop cannot be cleared by a repeated callback or externally changed file.
        prior_stop = read(session / 'progress-stop.json')
        if prior_stop:
            result['brief'] = prior_stop['brief']
        timing = deadline(session, identity)
        if timing:
            result['brief'] = {**result['brief'], 'deadline': timing}
        save(session / 'execution-progress.json', result)
        brief = result['brief']
        if brief['status'] == 'stop' and not prior_stop:
            save(session / 'progress-stop.json', {'reason': 'no_progress', 'identity': identity, 'brief': brief})
        return brief


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    parser.add_argument('--compaction', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check(args.session, compaction=args.compaction)))
