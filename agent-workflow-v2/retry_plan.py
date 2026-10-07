"""Explicit operator retry of unchanged behavior; no model replanning or weakened gates."""
import copy
import hashlib
import json
from pathlib import Path
from project_map import scan
from plan_runner import validate, contract_digest
from runner_process import read
from runner_resume import scope_changes
import tasks


def create(root,run_folder,output,timeout=2700):
    """Preserve all contracts and baselines while authorizing a longer operational retry."""
    root,run_folder,output=root.resolve(),run_folder.resolve(),output.resolve()
    state=read(run_folder/'state.json')
    if state.get('status')!='needs_replan':raise ValueError('Retry requires a stopped failure checkpoint')
    if state.get('reason') not in {'timeout','execution_failed','acceptance_failed'}:
        raise ValueError('This failure needs architectural replanning, not an operational retry')
    if Path(state.get('project','')).resolve()!=root:raise ValueError('Run belongs to another project')
    if output.exists() or output.is_relative_to(root):raise ValueError('Use a new plan path outside the project')
    original=read(Path(state['plan']));validate(root,original)
    if contract_digest(original)!=state['contract_digest']:raise ValueError('Original plan contract changed')
    current=scan(root,['.'])['snapshot']
    if current!=state['snapshot']:raise ValueError('Source changed after failure; replan from fresh evidence')
    failed=state['current_todo'];attempt=state['attempts'][-1]
    if attempt['todo']!=failed or not attempt.get('session'):raise ValueError('Missing failed session binding')
    session=Path(attempt['session']);frozen=read(session/'task-state.json')
    if Path(frozen['before']['root']).resolve()!=root:raise ValueError('Failed task belongs to another project')
    selected=next(t for t in original['tasks'] if t['id']==failed)
    for key in ('id','goal','files','tests','acceptance','coverage','execution','context'):
        if frozen['task'].get(key)!=selected.get(key):raise ValueError('Frozen contract changed: '+key)
    scope_changes(root,frozen,scan(root,['.']))
    for path,digest in frozen.get('readonly_tests',{}).items():
        if tasks.hash_file(Path(path))!=digest:raise ValueError('Immutable acceptance fixture changed')
    pending=[copy.deepcopy(t) for t in original['tasks'] if t['status']!='done']
    accepted=copy.deepcopy(original.get('replan_lineage',{}).get('completed',[]))+[
        copy.deepcopy(t) for t in original['tasks'] if t['status']=='done']
    accepted_ids={t['id'] for t in accepted}
    for task in pending:
        task['execution']['timeout_seconds']=timeout
        task['depends_on']=[i for i in task.get('depends_on',[]) if i not in accepted_ids]
        if task['id']==failed:task['baseline']=str(session/'task-state.json')
    plan={**copy.deepcopy(original),'tasks':pending,
          'replan_lineage':{'parent_plan':state['plan'],'reason':'Explicit operational retry: '+state['reason'],
                            'completed':accepted,'snapshot':current},
          'operational_retry':{'todo':failed,'session':str(session),'reason':state['reason'],
                               'source_run':str(run_folder),'timeout_seconds':timeout}}
    plan.pop('replan_validation',None);validate(root,plan)
    if scan(root,['.'])['snapshot']!=current:raise ValueError('Source changed while preparing retry')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:json.dump(plan,stream,indent=2)
    return {'plan':str(output),'tasks':len(pending),'timeout_seconds':timeout,
            'note':'Behavior, files, criteria, test argv and context budgets preserved; original plan untouched.'}
