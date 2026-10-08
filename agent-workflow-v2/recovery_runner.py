"""One automatic evidence-reviewed repair per failed contract, with durable escalation."""
import fcntl
import json
import time
from pathlib import Path
from runner_process import BASE,read,save


def ask(folder,state,reason):
    """Expose an inline/CLI question; rerunning cannot reset the spent repair allowance."""
    question={'reason':reason,'question':'The automatic repair did not resolve this todo. Should we revise its requirements/architecture, allow another repair, or stop?',
              'plan':state['current_plan'],'run_dir':state['current_run'],'repairs':state['repairs']}
    save(folder/'user-question.json',question);state.update(status='awaiting_user',reason=reason)
    save(folder/'recovery-state.json',state)
    print(question['question']+' Evidence: '+str(folder/'user-question.json'),flush=True)
    return {'code':20,'plan':Path(state['current_plan']),'run_dir':Path(state['current_run']),'question':question}


def review(root,packet_path,destination,provider,timeout):
    """Publish progress and run one isolated planner while source is locked."""
    from planning_service import create_draft
    from project_lock import exclusive
    root,destination,packet_path=root.resolve(),destination.resolve(),packet_path.resolve()
    if destination.is_relative_to(root):raise ValueError('Review output must be outside the project')
    if (destination.with_suffix('.stages')/'state.json').exists():raise ValueError('Use a new review destination')
    folder=destination.with_suffix('.stages');folder.mkdir(parents=True,exist_ok=True)
    queue=folder/'queue.json'
    save(queue,{'goal':'Review failure and plan one corrective attempt','tasks':[
        {'id':'FAILURE-REVIEW','goal':'Diagnose failure against architecture, shadow and plan',
         'status':'todo','files':[],'steps':['Read measured context and observed failures','Save a corrective plan preserving acceptance']} ]})
    state={'project':str(root),'plan':str(queue),'workflow_phase':'planning','status':'running',
           'recovery_evidence':str(packet_path),
           'current_todo':'FAILURE-REVIEW','started_epoch':time.time(),'updated_epoch':time.time(),
           'attempt_started_epoch':time.time(),'attempt_folder':str(destination.with_suffix('.planning'))}
    save(folder/'state.json',state)
    try:
        with exclusive(root,BASE):result=create_draft(root,'Diagnose and repair the failed todo.',destination,provider,timeout,packet_path)
    finally:
        state.update(status='interrupted',updated_epoch=time.time());save(folder/'state.json',state)
    state.update(status='complete' if result.get('passed') else 'needs_replan',reason=result.get('validation_error'),updated_epoch=time.time())
    if result.get('passed'):
        data=read(queue);data['tasks'][0]['status']='done';save(queue,data)
    save(folder/'state.json',state)
    return result


def execute(root,plan,folder,*,resume=False,executor=None,reviewer=None,retry_review=False,allow_repair=False):
    """Coordinate execution and bounded repairs without sending a project to the scheduler."""
    from plan_runner import execute as run
    from role_selection import load
    from runner_resume import interruption_signals
    executor=executor or run;reviewer=reviewer or review
    root,plan,folder=root.resolve(),plan.resolve(),folder.resolve()
    if retry_review and allow_repair:raise ValueError('Choose retry-review or allow-repair, not both')
    if folder.is_relative_to(root):raise ValueError('Recovery evidence must be outside the project')
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'recovery.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('An execution/recovery coordinator already owns this run') from None
        from run_owner import register
        register(folder,root,plan)
        state=read(folder/'recovery-state.json')
        if state and (state['project']!=str(root) or state['original_plan']!=str(plan)):
            raise ValueError('Recovery checkpoint belongs to a different project or plan')
        if not state:state={'project':str(root),'original_plan':str(plan),'current_plan':str(plan),
            'current_run':str(folder),'spent_ids':[],'spent_cases':[],'repairs':[],'status':'executing'}
        if allow_repair:
            from recovery_retry import authorize_repair
            authorize_repair(root,folder,state)
        elif retry_review:
            from recovery_retry import authorize
            authorize(root,folder,state)
        elif state['status']=='awaiting_user':return ask(folder,state,state['reason'])
        elif state['status']=='reviewing':return ask(folder,state,'Failure review was interrupted; review its evidence before another request')
        with interruption_signals():
            try:return advance(root,folder,state,resume,executor,reviewer,load(root)['planner'])
            except KeyboardInterrupt:
                save(folder/'recovery-state.json',state)
                return {'code':130,'plan':Path(state['current_plan']),'run_dir':Path(state['current_run'])}


def advance(root,folder,state,resume,executor,reviewer,provider):
    """Reserve each repair before invoking an LLM; only a new failing contract earns another."""
    while True:
        save(folder/'execution-target.json',{'plan':state['current_plan'],'run_dir':state['current_run']})
        retrying=state.get('status')=='retrying_review'
        code=20 if retrying else executor(root,Path(state['current_plan']),Path(state['current_run']),resume=resume)
        if code!=20:
            state['status']='complete' if code==0 else 'executing';save(folder/'recovery-state.json',state)
            return {'code':code,'plan':Path(state['current_plan']),'run_dir':Path(state['current_run'])}
        packet_path=Path(state['current_run'])/'replan-request.json';packet=read(packet_path)
        if not packet:return ask(folder,state,'Missing failure evidence')
        task=packet['failed_todo'];cases={json.dumps(c,sort_keys=True) for c in task['acceptance']}
        if not retrying and (task['id'] in state['spent_ids'] or cases & set(state['spent_cases'])):
            return ask(folder,state,'The automatic repair failed: '+task['id'])
        if not retrying:
            state['spent_ids'].append(task['id']);state['spent_cases']+=sorted(cases)
        number=len(state['repairs'])+1;destination=folder/f'repair-{number}.json'
        state['repairs'].append({'todo':task['id'],'evidence':str(packet_path),'plan':str(destination),'provider':provider})
        state['status']='reviewing';save(folder/'recovery-state.json',state)
        try:result=reviewer(root,packet_path,destination,provider,1800)
        except (OSError,ValueError) as error:return ask(folder,state,'Failure review could not produce a safe plan: '+str(error))
        state['repairs'][-1]['review_result']=result
        if not result.get('passed'):return ask(folder,state,'Failure review did not produce a validated corrective plan')
        from plan_runner import validate
        from plans import require_review
        replacement=read(destination)
        try:validate(root,replacement);require_review(replacement)
        except (OSError,ValueError,KeyError) as error:return ask(folder,state,'Invalid corrective plan: '+str(error))
        if not replacement.get('replan_lineage'):return ask(folder,state,'Repair plan lacks preserved failure lineage')
        state.update(current_plan=str(destination),current_run=str(folder/f'repair-{number}'),status='executing')
        save(folder/'recovery-state.json',state);resume=False
