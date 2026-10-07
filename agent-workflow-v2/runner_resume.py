"""Resume explicitly interrupted todos without replaying accepted work or history."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from project_map import scan
from runner_process import read, save
import tasks

INTERRUPTED_EXIT = 130
CONTRACT_FIELDS = ('id', 'goal', 'files', 'tests', 'acceptance', 'coverage', 'execution')


@contextmanager
def interruption_signals():
    """Allow a CLI SIGTERM to save a checkpoint and clean up its owned worker."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.getsignal(signal.SIGTERM)
    def interrupt(*_):
        """Use the same cleanup path as an ordinary keyboard interruption."""
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def attempt_session(folder, state):
    """Locate the captured session of this run's current owned attempt."""
    attempt = Path(state.get('attempt_folder', folder / 'missing-attempt')).resolve()
    if not attempt.is_relative_to(folder.resolve()):
        raise ValueError('Interrupted attempt folder escapes the run directory')
    return attempt, read(attempt / 'session.json').get('session')


def stop_orphan(session):
    """Stop only a detached Pi group whose live command matches this session."""
    process = read(session / 'process.json')
    pid = process.get('pid')
    if type(pid) is not int or pid <= 1 or process.get('process_group') != pid:
        return
    command = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'command='],
                             capture_output=True, text=True).stdout
    if str(session / 'pi-sessions') not in command:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
        for _ in range(20):
            time.sleep(.1)
            if subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'command='],
                              capture_output=True, text=True).returncode:
                return
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def scope_changes(root, frozen, after):
    """Reject source edits outside the interrupted task's original file scope."""
    before = frozen['before']
    old = {f['path']: f['sha256'] for f in before['files']}
    new = {f['path']: f['sha256'] for f in after['files']}
    changed = {p for p in old.keys() | new.keys() if old.get(p) != new.get(p)}
    changed |= {p for p, digest in frozen.get('declared_hashes', {}).items()
                if tasks.hash_file(root / p) != digest}
    for key in ['architecture', 'knowledge']:
        if before.get(key, {}) != after.get(key, {}):
            changed.add(key + '.md')
    if not changed <= set(frozen['task']['files']):
        raise ValueError('Interrupted source changed outside task scope: ' + str(sorted(changed)))
    return sorted(changed)


def interrupt(root, path, folder, state):
    """Preserve partial files, the original baseline and a resumable stop marker."""
    plan = read(path)
    current = state.get('current_todo') if state.get('status') == 'running' else None
    attempt, name = attempt_session(folder, state)
    attempt.mkdir(parents=True, exist_ok=True)
    result = {'exit_code': 130, 'session': name, 'interrupted': True, 'timed_out': False}
    result.update(wall_seconds=round(time.time() - state.get('attempt_started_epoch', time.time()), 3),
                  log=str(attempt / 'pi.log'))
    from run_metrics import collect
    result['metrics'] = collect(result, attempt)
    if current:
        task = next(t for t in plan['tasks'] if t['id'] == current)
        task['status'] = 'todo'
        if name and (Path(name) / 'task-state.json').is_file():
            task.setdefault('baseline', str(Path(name) / 'task-state.json'))
            tasks.save_patch(Path(name) / 'task-state.json')
        save(path, plan)
        state['attempts'].append({'todo': current, **result,
                                 'gate': {'passed': False, 'reason': 'interrupted'}})
        save(attempt / 'result.json', result)
    state.update(status='interrupted', interrupted_epoch=time.time(),
                 snapshot=scan(root, ['.'])['snapshot'], interrupted_todo=current)
    return state


def prepare(root, path, folder, plan, state):
    """Bind a fresh worker to verified accepted work and bounded partial evidence."""
    attempt, name = attempt_session(folder, state)
    session = Path(name) if name else None
    if session:
        stop_orphan(session)
    after = scan(root, ['.'])
    if state['status'] == 'interrupted' and state['snapshot'] != after['snapshot']:
        raise ValueError('Source changed after interruption; replan from current evidence')
    accepted = {row['todo'] for row in state['attempts'] if row.get('gate', {}).get('passed')}
    current = state.get('interrupted_todo') or state.get('current_todo')
    if current in accepted:
        current = None
    task = next((t for t in plan['tasks'] if t['id'] == current), None)
    frozen = read(session / 'task-state.json') if session else {}
    changed = []
    if task and frozen:
        if Path(frozen['before']['root']).resolve() != root:
            raise ValueError('Interrupted session belongs to another project')
        if any(frozen['task'].get(k) != task.get(k) for k in CONTRACT_FIELDS):
            raise ValueError('Interrupted task contract changed; replan explicitly')
        changed = scope_changes(root, frozen, after)
        for filename, digest in frozen.get('readonly_tests', {}).items():
            if tasks.hash_file(Path(filename)) != digest:
                raise ValueError('Interrupted acceptance fixture changed')
        task['status'] = 'todo'
        task.setdefault('baseline', str(session / 'task-state.json'))
    elif state['status'] == 'running' and state['snapshot'] != after['snapshot']:
        raise ValueError('Crashed task has source changes but no frozen session evidence')
    if task:
        write_brief(folder, task, session, changed, sorted(accepted))
        state.update(resume_prompt=str(folder / 'resume-brief.txt'), resume_todo=task['id'])
    save(path, plan)
    state.update(status='ready', snapshot=after['snapshot'],
                 resume_count=state.get('resume_count', 0) + 1, resumed_epoch=time.time())
    return state


def write_brief(folder, task, session, changed, accepted):
    """Carry progress and failures into a fresh task session without old messages."""
    from runner_evidence import failed_tests
    activity = read(session / 'last-activity.json') if session else {}
    packet = {'mode': 'resume_interrupted_todo', 'todo': task['id'],
              'accepted_todos_do_not_repeat': accepted, 'partial_changed_files': changed,
              'last_activity': str(activity.get('activity', ''))[:300],
              'previous_test_observations': failed_tests(str(session))[:4] if session else [],
              'instructions': 'Continue this same frozen task from its current files. Preserve partial work and accepted behavior. The supplied packet has fresh architecture/interfaces/source. Retrieve missing spans only. Run frozen acceptance; never widen scope or replay completed todos.'}
    if session and (session/'task-state.json').is_file():
        packet['remaining_gate_violations']=tasks.check(session/'task-state.json').get('violations',[])
        packet['finalization']='If tests already pass and only the architecture note is missing, call workflow_test with architecture_note and architecture_title immediately; preserve passing code.'
    text = 'RESUMING INTERRUPTED ATOMIC TASK\n' + json.dumps(packet, indent=2)
    if len(text.encode()) > 8000:
        packet['previous_test_observations'] = []
        text = 'RESUMING INTERRUPTED ATOMIC TASK\n' + json.dumps(packet, indent=2)
    (folder / 'resume-brief.txt').write_text(text)
