"""Native finalization: optional authored note, maintained navigation, fresh tests, gate."""
import hashlib
import json
import fcntl
from pathlib import Path
import tasks
from architecture_maintenance import maintain
from architecture_update import binding, update


def diagnostic(row):
    """Keep actionable failed-test observations bounded; full logs remain on disk."""
    path=Path(row['log']);text=path.read_text(errors='replace') if path.is_file() else ''
    lines=[line[:240] for line in text.splitlines() if line.lstrip().startswith(
        ('not ok','✖','×','AssertionError','Error:','TypeError:','ReferenceError:','SyntaxError:',
         'FAIL:','ERROR:','error:','actual:','expected:'))]
    return {'log':str(path),'exit_code':row['exit_code'],'failures':lines[:12], 'tail':text[-1000:]}


def publish(session, result):
    """Keep full evidence local and fit tool feedback inside the skill byte budget."""
    artifact=session/'finalization-result.json'
    artifact.write_text(json.dumps(result,indent=2))
    brief=json.loads(json.dumps(result));brief['artifact']=str(artifact)
    if len(json.dumps(brief).encode())<=6500:return brief
    brief['tests']=[{k:r[k] for k in ('exit_code','tests_collected')} for r in result.get('tests',[])]
    brief['violation_count']=len(result.get('violations',[]))
    brief['violations']=[v[:400] for v in result.get('violations',[])[:4]]
    brief['diagnostics']=[dict(log=d['log'],exit_code=d['exit_code'],
        failures=[v[:120] for v in d['failures'][:3]],tail=d['tail'][-512:])
        for d in result.get('diagnostics',[])[:2]]
    if len(json.dumps(brief).encode())>6500:
        brief={k:brief[k] for k in ('passed','tests_passed','artifact','next_action','violation_count')}
    brief['feedback_truncated']=True
    return brief


def finalize(session, inputs):
    """Bind and serialize finalization; a note is authored by Qwen, never invented here."""
    launch,state,contract,root=binding(session)
    if state.resolve().parent!=session.resolve():raise ValueError('Finalization state must belong to this session')
    with (session/'finalization.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return finish_locked(session,state,contract,root,inputs)


def finish_locked(session,state,contract,root,inputs):
    """Reuse current evidence and skip doomed tests while declared new files are absent."""
    before=contract['declared_hashes']
    missing=[name for name in contract['task']['files'] if name!='architecture.md'
             and before.get(name) is None and not (root/name).is_file()]
    maintain(root,contract['before']['prefixes'],Path(contract['shadow']),state)
    if missing and inputs.get('automatic'):
        return publish(session,{'passed':False,'tests_passed':False,'pending_files':missing,
                'next_action':'Create the remaining declared files, then tests run automatically.'})
    evidence=tasks.ensure_test_evidence(state)
    note=inputs.get('architecture_note') if evidence.get('results') and all(
        r['exit_code']==0 and r.get('tests_collected')!=0 for r in evidence['results']) else None
    if note:
        # Check scope/size before appending; preserve every existing decision byte.
        prior=tasks.check(state)
        blockers=[v for v in prior['violations'] if not v.startswith((
            'Test evidence','Declared tests','Required scoped architecture insertion'))]
        if blockers:return publish(session,{'passed':False,'tests_passed':False,'violations':blockers,'next_action':'Repair the scope/size/navigation gate first.'})
        path=root/'architecture.md';raw=path.read_bytes() if path.exists() else None
        title=inputs.get('architecture_title') or 'Task '+contract['task'].get('id','update')
        request={'action':'append_section','title':title,'text':note,
                 'expected_sha256':hashlib.sha256(raw).hexdigest() if raw is not None else ''}
        # An identical successful note is idempotent; stale receipts still require repair.
        saved=session/'finalization-note.json';identity=hashlib.sha256(json.dumps([title,note]).encode()).hexdigest()
        receipt=json.loads((session/'architecture-update.json').read_text()) if (session/'architecture-update.json').is_file() else {}
        previous=json.loads(saved.read_text()) if saved.is_file() else {}
        if previous.get('identity')!=identity or receipt.get('after_sha256')!=request['expected_sha256']:
            update(session,request);saved.write_text(json.dumps({'identity':identity}))
    if note:evidence=tasks.ensure_test_evidence(state)
    gate=tasks.check(state);rows=evidence.get('results',[])
    tests_passed=bool(rows) and all(r['exit_code']==0 and r.get('tests_collected')!=0 for r in rows)
    result={'passed':gate['passed'],'tests_passed':tests_passed,'patch_lines':gate['patch_lines'],
            'violations':gate['violations'],'shadow_snapshot':gate['shadow_snapshot'],
            'tests':[dict(argv=r['argv'],exit_code=r['exit_code'],tests_collected=r.get('tests_collected')) for r in rows]}
    failures=[diagnostic(r) for r in rows if r['exit_code']]
    if failures:result['diagnostics']=failures[:3]
    if gate['passed']:result['next_action']='Accepted; stop. No further model call is needed.'
    elif tests_passed and any('Required scoped architecture' in v for v in gate['violations']):
        result['next_action']='Code tests passed. Call workflow_test with architecture_note: one brief decision/ownership sentence and optional architecture_title. Python inserts it, refreshes maps, retests and closes the task. Do not rewrite passing source.'
    else:result['next_action']='Repair only the reported failures; current tests and gate rerun after the edit.'
    return publish(session,result)
