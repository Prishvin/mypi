"""Verify acceptance and prepare bounded evidence plus interfaces for replanning."""
import json
from pathlib import Path
import subprocess
import time
from project_map import scan, outline
import tasks
import shadow
from runner_process import read, save


def acceptance(result, task, root):
    """Require a current frozen contract and fresh gate; ignore model success prose."""
    session = Path(result['session']) if result.get('session') else None
    stalled = read(session / 'progress-stop.json') if session else {}
    if (stalled.get('reason') == 'no_progress' and stalled.get('identity') ==
            {'project': str(root.resolve()), 'task': task['id']}):
        return {'passed': False, 'reason': 'no_progress',
                'violations': ['Repeated model rounds without new file contents or test outcomes'],
                'investigation': stalled.get('brief', {})}
    monitor_error = read(session / 'progress-error.json') if session else {}
    if monitor_error:
        return {'passed': False, 'reason': 'progress_monitor_failed',
                'violations': [str(monitor_error.get('error', 'Progress monitor failed'))[:500]]}
    compaction_error = read(session / 'compaction-error.json') if session else {}
    if compaction_error:
        bound = read(session / 'task-state.json')
        if (bound.get('task', {}).get('id') == task.get('id') and
                Path(bound.get('before', {}).get('root', '')).resolve() == root.resolve()):
            return {'passed': False, 'reason': 'compaction_failed',
                    'violations': [str(compaction_error.get('error', 'Compaction failed'))[:1800]],
                    'compaction': compaction_error}
    if result['exit_code'] or session is None:
        reason = 'timeout' if result['exit_code'] == 124 else 'execution_failed'
        if session:
            budget = read(session / 'request-budget-result.json')
            state = read(session / 'task-state.json')
            if budget.get('passed') is False:
                reason = 'context_budget_exceeded'
            elif reason != 'timeout' and any(row['exit_code'] for row in state.get('evidence', {}).get('results', [])):
                reason = 'acceptance_failed'
        violations=[]
        if session and (session/'task-state.json').exists():
            try:violations=tasks.check(session/'task-state.json').get('violations',[])
            except (OSError,ValueError,KeyError):pass
        return {'passed': False, 'reason': reason,'violations':violations}
    try:
        state = session / 'task-state.json'
        frozen = json.loads(state.read_text())
        if Path(frozen['before']['root']).resolve() != root.resolve():
            raise ValueError('Session belongs to a different project')
        for key in ('id', 'goal', 'files', 'tests', 'acceptance', 'coverage', 'execution'):
            if frozen['task'].get(key) != task.get(key):
                raise ValueError('Session contract differs: ' + key)
        gate = tasks.check(state)
        return {**gate, 'reason': 'accepted' if gate['passed'] else 'acceptance_failed'}
    except (OSError, ValueError, KeyError) as error:
        return {'passed': False, 'reason': 'missing_or_invalid_evidence', 'violations': [str(error)]}


def regression(root, completed, folder):
    """Re-run previously accepted commands; a later todo cannot erase correctness."""
    before = scan(root, ['.'])['snapshot']
    rows = []
    for task in completed:
        original = read(Path(task['evidence']).parent / 'task-state.json')
        for path, digest in original.get('readonly_tests', {}).items():
            if tasks.hash_file(Path(path)) != digest:
                return {'passed': False, 'reason': 'immutable_fixture_changed'}
        for index, argv in enumerate(task['tests']):
            log = folder / f"regression-{task['id']}-{index}.log"
            with log.open('w') as output:
                try:
                    process = subprocess.run(argv, cwd=root, stdout=output, stderr=subprocess.STDOUT,
                        timeout=task['execution']['test_timeout_seconds'])
                    code = process.returncode
                except subprocess.TimeoutExpired:
                    code = 124
                except OSError as error:
                    output.write(str(error)); code = 127
            from verification_counts import count
            measured=count(argv,log.read_text(errors='replace'))
            rows.append({'todo': task['id'], 'exit_code': code, 'log': str(log), 'argv': argv,'tests_collected':measured})
    unchanged = before == scan(root, ['.'])['snapshot']
    return {'passed': unchanged and all(row['exit_code'] == 0 and row.get('tests_collected')!=0 for row in rows),
            'reason': 'regressions_passed' if unchanged else 'tests_modified_source', 'tests': rows}


def failed_tests(session):
    """Carry observable diagnostics without including edited implementation or patches."""
    state = read(Path(session) / 'task-state.json') if session else {}
    rows = []
    for result in state.get('evidence', {}).get('results', []):
        row = {k: result[k] for k in ('argv', 'exit_code', 'log')}
        # Raw logs stay local. Preserve decorated Node exceptions and measured
        # totals; repeated failing names must not push causes out of the packet.
        from failure_diagnostics import summarize
        text = Path(result['log']).read_text(errors='replace') if Path(result['log']).exists() else ''
        row.update(summarize(text))
        rows.append(row)
    return rows


def current_task_gate(session, root, task):
    """Keep current acceptance blockers distinct from why the process stopped."""
    try:
        state_path=Path(session)/'task-state.json'
        frozen=read(state_path)
        if Path(frozen.get('before',{}).get('root','')).resolve()!=root.resolve():
            raise ValueError('Gate session belongs to another project')
        if any(frozen.get('task',{}).get(key)!=task.get(key)
               for key in ('id','files','acceptance','tests')):
            raise ValueError('Gate session differs from failed contract')
        gate=tasks.check(state_path)
        violations=gate.get('violations',[])
        return {'available':True,'passed':gate['passed'],
                'violations':[str(value)[:300] for value in violations[:30]],
                'omitted_violations':max(0,len(violations)-30),
                'truncated_violations':sum(len(str(value))>300 for value in violations[:30]),
                'patch_lines':gate.get('patch_lines'),'shadow_snapshot':gate.get('shadow_snapshot'),
                'note':'Fresh read-only acceptance check; no tests executed and no stop reason replaced.'}
    except (OSError,ValueError,KeyError,TypeError) as error:
        return {'available':False,'passed':False,'error':str(error)[:500],
                'note':'Current gate unavailable; this is not evidence that blockers were resolved.'}


def failure(root, plan_path, plan, task, result, gate, folder):
    """Emit a stop checkpoint and a bounded packet suitable for either planner."""
    data = scan(root, ['.'])
    paths = set(task['files'] + task['context'].get('interfaces', []))
    prototypes = '\n'.join(outline(record) for record in data['files'] if record['path'] in paths)
    if len(prototypes.encode()) > 16000:
        prototypes = 'Selected shadow is too large; use project_map locate/inspect for these paths: ' + str(sorted(paths))
    handoff = {'kind': 'replan_required', 'project': str(root), 'plan': str(plan_path),
        'goal': plan['goal'], 'failed_todo': task, 'reason': gate.get('reason'),
        'violations': gate.get('violations', []), 'exit_code': result.get('exit_code'),
        'wall_seconds': result.get('wall_seconds'), 'metrics': result.get('metrics', {}),
        'completed': plan.get('replan_lineage', {}).get('completed', []) + [{'id': t['id'], 'goal': t['goal'], 'files': t['files'],
                       'tests': t['tests'], 'execution': t['execution'], 'evidence': t.get('evidence')}
                      for t in plan['tasks'] if t['status'] == 'done' and t['id'] != task['id']],
        'remaining': [t for t in plan['tasks'] if t['status'] != 'done' or t['id'] == task['id']],
        'failed_tests': failed_tests(result.get('session')), 'regression': result.get('regression'),
        'current_snapshot': data['snapshot'], 'selected_prototypes': prototypes,
        'acceptance_fixtures': plan.get('acceptance_fixtures', {}),
        'local_log': result.get('log'), 'session': result.get('session'),
        'budget_observation': read(Path(result['session']) / 'request-budget-result.json') if result.get('session') else {},
        'tool_errors':read(Path(result['session'])/'tool-errors.json') if result.get('session') else {},
        'execution_progress':read(Path(result['session'])/'execution-progress.json').get('brief', {}) if result.get('session') else {},
        'policy': 'Stop execution. Replan remaining authorized work; preserve accepted behavior, tests and scope. No application implementation bodies in planner handoff. Python may select bounded failing-test evidence for review.',
        'created_epoch': time.time()}
    if result.get('session'):
        handoff['current_task_gate']=current_task_gate(result['session'],root,task)
    # The failed baseline contains source bodies and remains only in the local session.
    if result.get('session'):
        from task_patch import measure
        frozen = read(Path(result['session']) / 'task-state.json')
        if frozen:
            handoff['patch_budget'] = measure(frozen)
    for todo in handoff['remaining'] + [handoff['failed_todo']]:
        todo.pop('baseline', None)
    save(folder / 'replan-request.json', handoff)
    brief = 'REPLAN REQUIRED\n\n' + json.dumps(handoff, indent=2)
    (folder / 'replan-request.txt').write_text(brief)
    shadow.refresh(root, ['.'], folder / 'shadow')
    return str(folder / 'replan-request.json')
