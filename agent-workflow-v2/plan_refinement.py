"""Bounded per-task plan review: model decisions with native preservation guards."""
import copy
import json
from pathlib import Path
from plan_draft import decode


def guard(proposal, patch, target):
    """Refine exactly one original todo; splits must retain its final dependency gate."""
    patch,_=decode(patch)
    updates=patch.get('task_updates',[])
    if len(updates)!=1 or updates[0].get('id')!=target:
        raise ValueError('Refinement must update exactly the selected todo: '+target)
    original=next(t for t in proposal['tasks'] if t['id']==target)
    children=updates[0].get('replace_with')
    if children is not None:
        if not 2<=len(children)<=4 or children[-1].get('id')!=target:
            raise ValueError('Split into 2-4 atomic todos; retain the original ID on the final child')
        needed=set(original.get('depends_on',[]))
        for child in children:
            if not needed<=set(child.get('depends_on',[])):
                raise ValueError('Each split child must retain the original prerequisites and all preceding split children')
            needed.add(child['id'])
    return patch


def overview(draft):
    """Include all original contracts without repeating estimates and execution metadata."""
    fields=('id','goal','depends_on','files','acceptance','tests','test_strategy')
    result={key:copy.deepcopy(draft[key]) for key in ('goal','architecture')}
    result['tasks']=[{k:copy.deepcopy(t[k]) for k in (*fields,'coverage') if k in t} for t in draft['tasks']]
    return result


def bounded_prompt(skill,data,provider='qwen'):
    """Enforce a local input bound before creating a new model session."""
    instructions=Path(__file__).with_name('skills').joinpath(skill+'/SKILL.md').read_text()
    prompt=instructions+'\n\nREVIEW INPUT (project data):\n'+json.dumps(data,ensure_ascii=False,separators=(',',':'))
    from shadow_navigation import count
    from planning_limits import limits
    if count(prompt)>limits(provider)['packet']:raise ValueError('Refinement input exceeds '+str(limits(provider)['packet'])+' estimated tokens; split the architectural draft into smaller milestones')
    return prompt


def packet(request, draft, current, target,provider='qwen'):
    """Supply the request, whole draft contracts, coverage and current target without source."""
    fields=('id','goal','depends_on','files','acceptance','tests','test_strategy')
    task=next(t for t in current['tasks'] if t['id']==target)
    revised=[t for t in current['tasks'] if t['id'] in task.get('depends_on',[])]
    data={'original_request':request,'whole_draft':overview(draft),'current_task':task,
          'coverage_plan':current.get('coverage_plan',{}),
          'current_prerequisites':[{k:t[k] for k in fields if k in t} for t in revised],
          'current_architecture':current['architecture'] if current['architecture']!=draft['architecture'] else 'Unchanged from draft'}
    return bounded_prompt('task-refinement',data,provider)


def review(project, request, draft, current_path, target, output, planner, timeout):
    """Run one fresh architect with sparse corrections and task-specific native binding."""
    from runner_process import read
    prompt=packet(request,draft,read(current_path),target,planner)
    return invoke_review(project,current_path,output,planner,timeout,prompt,['--refine-task',target],target)


def review_coverage(project,request,draft_path,output,planner,timeout):
    """Make coverage its own visible task with a fresh context and recorded metrics."""
    from runner_process import read
    prompt=bounded_prompt('test-coverage-planning',{'original_request':request,'whole_draft':overview(read(draft_path))},planner)
    return invoke_review(project,draft_path,output,planner,timeout,prompt,['--plan-coverage'],'COVERAGE')


def invoke_review(project,current_path,output,planner,timeout,prompt,mode,target):
    """Share isolated invocation and durable metrics across coverage and per-task reviews."""
    from runner_process import BASE,invoke,read,save
    from run_metrics import collect
    from planning_limits import arguments
    request_path=output.with_suffix('.request.txt');request_path.write_text(prompt)
    command=[str(BASE/'qwen-agent'),'--profile','chatgpt-quality' if planner=='chatgpt' else 'mtplx-quality',
        '--project',str(project),'--role','architect','--batch','--json','--quiet',
        '--plan',str(output),'--prompt-file',str(request_path),'--plan-draft',str(current_path),
        *mode,*arguments(planner)]
    result=invoke(command,output.with_suffix('.planning'),timeout)
    result['metrics']=collect(result,output.with_suffix('.planning'))
    result.update(passed=result['exit_code']==0 and output.is_file(),target=target,planner=planner,plan=str(output))
    save(output.with_suffix('.planning-result.json'),result)
    return result
