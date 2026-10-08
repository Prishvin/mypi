"""Keep the implementation queue visible while its failed contract is reviewed."""
from pathlib import Path
from run_planning_results import archived


def implementation(stage, state, root, read, task_rows):
    """Bind a review to its coordinator and read only the matching execution evidence."""
    if state.get('workflow_phase') != 'planning':
        return None
    owner = stage.parent.resolve()
    recovery = read(owner / 'recovery-state.json')
    evidence_path=state.get('recovery_evidence')
    if evidence_path:
        packet=read(Path(evidence_path))
        if packet.get('project')!=str(root) or not packet.get('local_log'):
            return None
        run=Path(packet['local_log']).resolve().parent.parent
        if run!=owner and not run.is_relative_to(owner):return None
        execution=read(run/'state.json')
        if (execution.get('plan')!=packet.get('plan') or
                execution.get('current_todo')!=packet.get('failed_todo',{}).get('id')):
            return None
        recovery={'project':str(root),'current_run':str(run),'current_plan':packet['plan'],
                  'repairs':[{'plan':str(stage.with_suffix('.json'))}]}
    repairs = recovery.get('repairs') or []
    if not repairs or recovery.get('project') != str(root):
        return None
    destination = repairs[-1].get('plan')
    if not destination or Path(destination).with_suffix('.stages').resolve() != stage.resolve():
        return None
    if not recovery.get('current_run') or not recovery.get('current_plan'):
        return None
    run = Path(recovery['current_run']).resolve()
    if run != owner and run.parent != owner and not (evidence_path and run.is_relative_to(owner)):
        return None
    execution = read(run / 'state.json')
    if execution.get('project') != str(root) or execution.get('workflow_phase') == 'planning':
        return None
    if execution.get('plan') != recovery['current_plan']:
        return None
    plan = read(Path(execution['plan']))
    if plan.get('project') != str(root) or not isinstance(plan.get('tasks'), list):
        return None
    rows = task_rows(run, execution, plan, root)
    for row in rows:
        row['implementation'] = True
    return {'tasks': rows, 'planning_tasks': archived(plan, root, read), 'state': {
        'run': run.name, 'status': execution.get('status'),
        'current_todo': execution.get('current_todo'), 'reason': execution.get('reason'),
        'accepted': sum(row['status'] == 'Accepted' for row in rows), 'total': len(rows)}}
