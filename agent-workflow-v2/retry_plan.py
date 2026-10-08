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


def create(root,run_folder,output,timeout=2700,*,input_tokens=None,reason=None):
    """Preserve all contracts and baselines while authorizing a longer operational retry."""
    root,run_folder,output=root.resolve(),run_folder.resolve(),output.resolve()
    state=read(run_folder/'state.json')
    if state.get('status')!='needs_replan':raise ValueError('Retry requires a stopped failure checkpoint')
    if state.get('reason') not in {'timeout','execution_failed','acceptance_failed','no_progress','compaction_failed'}:
        raise ValueError('This failure needs architectural replanning, not an operational retry')
    if input_tokens is not None:
        if type(input_tokens) is not int or input_tokens<512:
            raise ValueError('Input override must be an integer of at least 512 tokens')
        if not isinstance(reason,str) or not reason.strip() or len(reason)>1000:
            raise ValueError('An input override requires a bounded explicit operator reason')
    if state.get('reason')=='no_progress' and input_tokens is None:
        raise ValueError('No-progress retry requires explicit increased input headroom and an operator reason')
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
    if state.get('reason')=='no_progress':
        stop=read(session/'progress-stop.json')
        if (stop.get('reason')!='no_progress' or stop.get('identity')!={'project':str(root),'task':failed}):
            raise ValueError('Missing bound no-progress evidence')
        if input_tokens<=selected['context']['max_input_tokens']:
            raise ValueError('No-progress operational retry must increase input headroom')
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
        task['depends_on']=[i for i in task.get('depends_on',[]) if i not in accepted_ids]
        if task['id']==failed:
            task['execution']['timeout_seconds']=timeout
            task['baseline']=str(session/'task-state.json')
            if input_tokens is not None:task['context']['max_input_tokens']=input_tokens
    plan={**copy.deepcopy(original),'tasks':pending,
          'replan_lineage':{'parent_plan':state['plan'],'reason':'Explicit operational retry: '+state['reason'],
                            'completed':accepted,'snapshot':current},
          'operational_retry':{'todo':failed,'session':str(session),'reason':state['reason'],
                               'source_run':str(run_folder),'timeout_seconds':timeout}}
    plan.pop('replan_validation',None);validate(root,plan)
    if input_tokens is not None:
        plan['operational_retry'].update(input_tokens_before=selected['context']['max_input_tokens'],
            input_tokens_after=input_tokens,operator_reason=reason.strip(),
            output_thinking_window_unchanged=True)
    if scan(root,['.'])['snapshot']!=current:raise ValueError('Source changed while preparing retry')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:json.dump(plan,stream,indent=2)
    return {'plan':str(output),'tasks':len(pending),'timeout_seconds':timeout,
            'note':'Behavior, files, criteria, test argv and original baselines preserved; original plan untouched. '
                'Only the failed task deadline and any explicitly recorded input override change.'}
