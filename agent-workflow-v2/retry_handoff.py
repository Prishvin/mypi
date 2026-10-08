"""Apply an operational retry only to its unfinished task, preserving old receipts."""
from pathlib import Path
from runner_resume import write_brief


def target(plan):
    """Reject unknown retry targets; completed ancestors have no launch instruction."""
    retry = plan.get('operational_retry')
    if not retry:
        return
    if not isinstance(retry, dict) or not isinstance(retry.get('todo'), str):
        raise ValueError('Invalid operational retry target')
    lineage = plan.get('replan_lineage', {})
    selected = next((t for t in plan['tasks'] if t['id'] == retry['todo']), None)
    accepted = {t['id'] for t in lineage.get('completed', [])}
    accepted.update(t['id'] for t in plan['tasks'] if t.get('status') == 'done')
    if retry['todo'] in accepted:
        return
    if selected is None:
        raise ValueError('Operational retry target is neither pending nor accepted: ' + retry['todo'])
    if not isinstance(retry.get('session'), str) or not retry['session']:
        raise ValueError('Operational retry is missing its source session')
    return selected


def prepare(plan, folder, state, snapshot):
    """Tolerate historical inherited metadata only when its target is accepted."""
    retry = plan.get('operational_retry')
    if not retry:return
    selected = target(plan)
    if selected is None:
        state['historical_retry_ignored'] = {'todo': retry['todo'],
            'reason': 'Target already accepted; historical receipt is preserved on the plan.'}
        return
    if snapshot != plan.get('replan_lineage', {}).get('snapshot'):
        raise ValueError('Retry source changed; replan from fresh evidence')
    accepted = [t['id'] for t in plan['replan_lineage']['completed']]
    write_brief(folder, selected, Path(retry['session']), selected['files'], accepted)
    state.update(resume_prompt=str(folder/'resume-brief.txt'), resume_todo=selected['id'])
