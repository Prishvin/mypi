"""Keep the implementation queue visible while its failed contract is reviewed."""
from pathlib import Path
from run_planning_results import archived


def implementation(stage, state, root, read, task_rows):
    """Bind a review to its coordinator and read only the matching execution evidence."""
    if state.get('workflow_phase') != 'planning':
        return None
    owner = stage.parent.resolve()
    recovery = read(owner / 'recovery-state.json')
    repairs = recovery.get('repairs') or []
    if not repairs or recovery.get('project') != str(root):
        return None
    destination = repairs[-1].get('plan')
    if not destination or Path(destination).with_suffix('.stages').resolve() != stage.resolve():
        return None
    if not recovery.get('current_run') or not recovery.get('current_plan'):
        return None
    run = Path(recovery['current_run']).resolve()
    if run != owner and run.parent != owner:
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
