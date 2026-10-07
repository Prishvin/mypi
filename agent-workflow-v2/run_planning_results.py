"""Read saved planning outputs; never infer execution success from review receipts."""
from pathlib import Path
from plan_draft import digest

FIELDS=('id','goal','depends_on','files','steps','assumptions','test_strategy','acceptance',
        'tests','coverage','context','execution','estimated_changed_lines')


def contract(task):
    """Expose authored contracts without session prompts, source bodies or execution evidence."""
    return {k:task[k] for k in FIELDS if k in task}


def receipt(path, read, kind):
    """A missing saved artifact remains unavailable, not a fabricated successful result."""
    plan=read(path)
    if not plan or not isinstance(plan.get('tasks'),list):
        return {},{'available':False,'kind':kind,'reason':'Saved planning result is unavailable.'}
    return plan,{'available':True,'kind':kind,'artifact':Path(path).name,'sha256':digest(plan)}


def results(folder, state, read):
    """Attach draft, coverage and each historical refinement to its own completed step."""
    if state.get('workflow_phase')!='planning' or not state.get('draft_passed'):return {}
    draft,initial=receipt(folder/'draft.json',read,'draft');outputs={'DRAFT':initial}
    if not draft:return outputs
    initial.update(goal=draft.get('goal'),architecture=draft.get('architecture'),
                   tasks=[contract(t) for t in draft['tasks']])
    previous=draft
    if state.get('coverage_passed'):
        path=state.get('coverage_result',{}).get('plan')
        if path:
            covered,row=receipt(Path(path),read,'coverage');outputs['COVERAGE']=row
            if covered:
                row['coverage']=covered.get('coverage_plan',{});previous=covered
    reviews={r.get('target'):r for r in state.get('reviews',[]) if r.get('passed') and r.get('plan')}
    for index,task in enumerate(draft['tasks'],1):
        target=task['id'];entry=reviews.get(target)
        if target not in state.get('reviewed',[]) or not entry:continue
        plan,row=receipt(Path(entry['plan']),read,'refinement')
        outputs[f'REVIEW-{index:02d}-{target}']=row
        if not plan:
            previous=None;continue
        before={t['id']:contract(t) for t in (previous or {}).get('tasks',[])}
        selected=[contract(t) for t in plan['tasks'] if t['id']==target or (previous and t['id'] not in before)]
        changes=[]
        for item in selected:
            old=before.get(item['id'],{})
            changes.extend({'task':item['id'],'field':k,'before':old.get(k),'after':item.get(k)}
                           for k in FIELDS if old.get(k)!=item.get(k))
        row.update(target=target,tasks=selected,changes=changes if previous else None,
                   comparison_available=previous is not None,
                   criterion_corrections=plan.get('draft_repair',{}).get('criterion_corrections',[]))
        if previous and plan.get('architecture')!=previous.get('architecture'):
            row['architecture_change']={'before':previous.get('architecture'),'after':plan.get('architecture')}
        previous=plan
    return outputs


def archived(plan, root, read):
    """Keep completed planning visible after the monitor follows implementation."""
    review=plan.get('planning_review',{});source=review.get('coverage_receipt')
    if not source:return []
    folder=Path(source).parent;state=read(folder/'state.json')
    if state.get('status')!='complete' or state.get('project')!=str(root):return []
    if not review.get('draft_sha256') or review['draft_sha256']!=state.get('draft_sha256'):return []
    queue=read(folder/'queue.json');outputs=results(folder,state,read);rows=[]
    for task in queue.get('tasks',[]):
        row=contract(task)
        row.update(planning=True,status='Accepted' if task.get('status')=='done' else 'Pending',
                   files=[],tools=[],attempts=[],test_results=[])
        if task['id'] in outputs:row['planning_result']=outputs[task['id']]
        rows.append(row)
    return rows
