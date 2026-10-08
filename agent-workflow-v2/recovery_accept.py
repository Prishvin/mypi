"""Recover a published review after a process failure without hiding that failure."""
import copy
import time
from pathlib import Path
from runner_process import read, save


def accept(root,folder,state):
    """Adopt only this stopped review's unchanged, source-bound validated artifact."""
    repairs=state.get('repairs',[])
    if state.get('status')!='awaiting_user' or not repairs:
        raise ValueError('Accept-review requires a stopped review with a saved artifact')
    last=repairs[-1];result=last.get('review_result',{})
    if result.get('passed') or not result.get('session'):
        raise ValueError('No failed review session to recover')
    plan_path=Path(last['plan']);session=Path(result['session'])
    launch=read(session/'launch.json')
    if (launch.get('role')!='architect' or launch.get('project')!=str(root.resolve())
            or launch.get('plan')!=str(plan_path.resolve())):
        raise ValueError('Saved review belongs to a different project or output')
    from planner_stop import verified
    if not verified(root,plan_path,session,current_source=True):
        raise ValueError('Saved review is missing, changed, stale or invalid; cannot accept')
    packet=read(Path(last['evidence']));bound=read(session/'replan-evidence.json')
    if (packet.get('plan')!=state['current_plan'] or bound.get('plan')!=packet.get('plan')
            or bound.get('current_snapshot')!=packet.get('current_snapshot')
            or bound.get('failed_todo')!=packet.get('failed_todo')):
        raise ValueError('Saved review differs from the stopped failure contract')
    from plan_draft import digest
    if bound.get('recovery_plan_sha256') and digest(read(Path(bound['plan'])))!=bound['recovery_plan_sha256']:
        raise ValueError('Original plan changed since the saved review was bound')
    from planning_service import attach_lineage
    from plans import require_review
    plan=read(plan_path);checked=copy.deepcopy(plan)
    attach_lineage(checked,bound);require_review(checked)
    if checked!=plan:raise ValueError('Saved review lineage differs from its bound evidence')
    receipt={'epoch':time.time(),'plan':str(plan_path),'session':str(session),
             'process_exit_code':result.get('exit_code'),
             'reason':'Explicit acceptance of verified published review; process failure retained'}
    last['review_result_original']=copy.deepcopy(result)
    last['review_result']={**result,'passed':True,'saved_artifact_recovery':receipt}
    state.update(current_plan=str(plan_path),current_run=str(plan_path.with_suffix('')),status='executing')
    state.pop('reason',None)
    save(folder/'accepted-saved-review.json',receipt);save(folder/'recovery-state.json',state)
