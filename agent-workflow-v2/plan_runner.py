"""Advance validated todos with deterministic scheduling and an explicit replan exit."""
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import time
import re
from project_map import scan
import plans
from runner_process import BASE, invoke, read, save
from runner_evidence import acceptance, regression, failure
import runner_resume

REPLAN_EXIT = 20


def contract_digest(plan):
    """Detect changes to a reviewed plan while allowing evidence/status updates."""
    cleaned = copy.deepcopy(plan)
    for task in cleaned['tasks']:
        for key in ('status', 'baseline', 'evidence', 'shadow_snapshot'):
            task.pop(key, None)
    return hashlib.sha256(json.dumps(cleaned, sort_keys=True).encode()).hexdigest()


def validate(root, plan):
    """Validate an existing V3 plan without resetting its completion records."""
    from plan_contract import validate as validate_policy
    if plan.get('replan_validation', {}).get('passed') is False:
        raise ValueError('This replacement plan failed preservation checks; request a corrected plan')
    if plan.get('plan_version') != 3 or Path(plan.get('project', '')).resolve() != root.resolve():
        raise ValueError('Executor requires a V3 plan for this exact project; create a fresh plan')
    known = set()
    from tasks import hash_file
    for path, digest in plan.get('acceptance_fixtures', {}).items():
        if hash_file(Path(path)) != digest:
            raise ValueError('A planned immutable fixture changed: ' + path)
    for task in plan['tasks']:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', task['id']):
            raise ValueError('Todo id must be a safe short identifier')
        if not 1 <= len(task['files']) <= 8:
            raise ValueError('Todo requires 1-8 concrete files')
        if any(not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv)
               for argv in task['tests']):
            raise ValueError('Tests must be nonempty argv lists')
        if task['id'] in known or not set(task.get('depends_on', [])) <= known:
            raise ValueError('Invalid ids or dependency ordering')
        plans.validate_paths(root, task['files'])
        plans.validate_context(root, task)
        plans.validate_granularity(task)
        plans.validate_coverage(task)
        validate_policy(task)
        if task.get('status') not in ('todo', 'done'):
            raise ValueError('Invalid todo status')
        known.add(task['id'])


def command(root, plan_path, task, resume_prompt=None):
    """Supply only one selected todo; scheduling never asks an LLM for its next action."""
    argv = [str(BASE / 'qwen-agent'), '--profile', 'mtplx-quality', '--project', str(root),
            '--role', 'code', '--batch', '--json', '--quiet', '--plan', str(plan_path),
            '--todo', task['id'], '--stop-after-pass']
    return argv + (['--prompt-file', resume_prompt] if resume_prompt else [])


def checkpoint(folder, state, **changes):
    """Publish durable status and a chronological event ledger."""
    state.update(changes, updated_epoch=time.time())
    save(folder / 'state.json', state)
    with (folder / 'events.jsonl').open('a') as log:
        log.write(json.dumps({k: v for k, v in state.items() if k != 'attempts'}) + '\n')


def stop_for_replan(root, path, plan, task, result, gate, folder, state):
    """Stop this run; retry requires a separately reviewed replacement plan."""
    # launch.py can finish a task before aggregate regression discovers a failure.
    regressed = {row['todo'] for row in result.get('regression', {}).get('tests', []) if row['exit_code']}
    for stored in plan['tasks']:
        if stored['id'] == task['id'] or stored['id'] in regressed:
            stored['status'] = 'todo'
    save(path, plan)
    handoff = failure(root, path, copy.deepcopy(plan), copy.deepcopy(task), result, gate, folder)
    checkpoint(folder, state, status='needs_replan', reason=gate['reason'], replan_request=handoff,
               snapshot=scan(root, ['.'])['snapshot'])
    print('Stopped for replanning: ' + handoff, flush=True)
    return REPLAN_EXIT


def execute(root, path, folder, invoke_fn=invoke, *, resume=False):
    """Serialize execution for a project and retain a resumable, evidence-bound checkpoint."""
    root, path, folder = root.resolve(), path.resolve(), folder.resolve()
    if folder.is_relative_to(root):
        raise ValueError('Keep runner logs and state outside the source project')
    plan = json.loads(path.read_text())
    validate(root, plan)
    folder.mkdir(parents=True, exist_ok=True)
    lock_dir = BASE / 'runner-locks'
    lock_dir.mkdir(exist_ok=True)
    lock_path = lock_dir / (hashlib.sha256(str(root).encode()).hexdigest() + '.lock')
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another deterministic runner owns this project')
        with runner_resume.interruption_signals():
            try:
                return run_locked(root, path, plan, folder, invoke_fn, resume)
            except KeyboardInterrupt:
                state = read(folder / 'state.json')
                if not state:
                    return runner_resume.INTERRUPTED_EXIT
                state = runner_resume.interrupt(root, path, folder, state)
                checkpoint(folder, state)
                print('Interrupted; resume with pi-local resume using this same run directory.', flush=True)
                return runner_resume.INTERRUPTED_EXIT


def run_locked(root, path, plan, folder, invoke_fn, resume=False):
    """Resume only unchanged work; failed checkpoints never automatically run again."""
    digest = contract_digest(plan)
    state = read(folder / 'state.json')
    architecture_seed = None
    if not state:
        from plan_architecture import bootstrap
        architecture_seed = bootstrap(root, plan)
    snapshot = scan(root, ['.'])['snapshot']
    if state:
        if state['plan'] != str(path) or state['contract_digest'] != digest:
            raise ValueError('Run folder belongs to a different or changed plan')
        if state['status'] == 'needs_replan':
            print('This run is stopped; create a replacement plan from ' + str(folder / 'replan-request.json'))
            return REPLAN_EXIT
        if state['status'] in ('running', 'interrupted'):
            if not resume:
                print('Run interrupted; use pi-local resume with the original run directory.')
                return runner_resume.INTERRUPTED_EXIT
            accepted = {row['todo'] for row in state['attempts'] if row.get('gate', {}).get('passed')}
            completed = [t for t in plan['tasks'] if t['status'] == 'done' and t['id'] in accepted]
            completed += plan.get('replan_lineage', {}).get('completed', [])
            if not regression(root, completed, folder)['passed']:
                raise ValueError('Accepted behavior changed before resume; replan explicitly')
            state = runner_resume.prepare(root, path, folder, plan, state)
            plan = read(path)
            snapshot = scan(root, ['.'])['snapshot']
        if state['status'] == 'complete' and state['snapshot'] == snapshot:
            return 0
        if state.get('snapshot') != snapshot:
            task = next((t for t in plan['tasks'] if t['status'] != 'done'), plan['tasks'][-1])
            return stop_for_replan(root, path, plan, task, {},
                {'passed': False, 'reason': 'interrupted_or_source_drift'}, folder, state)
    else:
        if any(t['status'] == 'done' for t in plan['tasks']) and not plan.get('replan_lineage'):
            raise ValueError('Use the original run directory for an existing execution')
        state = {'plan': str(path), 'project': str(root), 'contract_digest': digest,
                 'attempts': [], 'started_epoch': time.time(), 'snapshot': snapshot}
        state['architecture_seed'] = architecture_seed
    checkpoint(folder, state, status='ready')
    return advance(root, path, plan, folder, state, invoke_fn)


def advance(root, path, plan, folder, state, invoke_fn):
    """Execute in dependency order, verifying each todo and earlier behavior before advancing."""
    for task in plan['tasks']:
        if task['status'] == 'done':
            continue
        plans.select(path, task['id'])
        attempt_folder = folder / f"{len(state['attempts'])+1:02d}-{task['id']}"
        checkpoint(folder, state, status='running', current_todo=task['id'],
                   attempt_folder=str(attempt_folder), attempt_started_epoch=time.time())
        try:
            brief = state.get('resume_prompt') if state.get('resume_todo') == task['id'] else None
            result = invoke_fn(command(root, path, task, brief), attempt_folder, task['execution']['timeout_seconds'])
        except OSError as error:
            result = {'exit_code': 127,
                      'error': str(error), 'session': read(attempt_folder / 'session.json').get('session')}
        gate = acceptance(result, task, root)
        from run_metrics import collect
        result['metrics'] = collect(result, attempt_folder)
        if gate['passed']:
            completed = plan.get('replan_lineage', {}).get('completed', []) + [t for t in plan['tasks'] if t['status'] == 'done']
            result['regression'] = regression(root, completed, attempt_folder)
            if not result['regression']['passed']:
                gate = {'passed': False, 'reason': 'previous_acceptance_regressed'}
        state['attempts'].append({'todo': task['id'], **result, 'gate': gate})
        if not gate['passed']:
            return stop_for_replan(root, path, json.loads(path.read_text()), task, result, gate, folder, state)
        latest = json.loads(path.read_text())
        if contract_digest(latest) != state['contract_digest']:
            return stop_for_replan(root, path, latest, task, result,
                {'passed': False, 'reason': 'plan_contract_changed'}, folder, state)
        if next(t for t in latest['tasks'] if t['id'] == task['id'])['status'] != 'done':
            plans.complete(path, task['id'], gate, Path(result['session']))
        plan = json.loads(path.read_text())
        checkpoint(folder, state, status='ready', snapshot=scan(root, ['.'])['snapshot'])
        print('Accepted ' + task['id'] + '; frozen tests, scope and shadow passed.', flush=True)
    checkpoint(folder, state, status='complete', current_todo=None, ended_epoch=time.time(),
               snapshot=scan(root, ['.'])['snapshot'])
    return 0
