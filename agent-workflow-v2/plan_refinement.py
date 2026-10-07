"""Bounded per-task plan review: model decisions with native preservation guards."""
import copy
import json
from pathlib import Path
from plan_draft import decode


def guard(proposal, patch, target):
    """Refine exactly one original todo; splits must retain its final dependency gate."""
    patch,_=decode(patch)
    updates=patch.get('task_updates',[])
    if not isinstance(updates,list) or any(not isinstance(update,dict) for update in updates):
        raise ValueError('task_updates must be an array containing one object with id '+target)
    if len(updates)!=1 or updates[0].get('id')!=target:
        ids=[str(update.get('id','<missing>'))[:80] for update in updates[:5]]
        raise ValueError('Refinement must update exactly the selected todo: '+target+
                         f'. Received {len(updates)} entries with IDs {ids}. '+
                         'Combine all changes into ONE task_updates object with that id; '+
                         'do not repeat the id or edit other todos. Put split children inside replace_with.')
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
    measured,cap=count(prompt),limits(provider)['packet']
    if measured>cap:
        raise ValueError(f'Review context preparation stopped before a model request: {measured} estimated '
                         f'packet tokens exceed the {cap}-token packet budget. This is separate from the '
                         f'{limits(provider)["context"]}-token model window. Reduce review material or use smaller milestones.')
    return prompt


def packet_data(request, current, target):
    """Include each current contract once, keeping all producers, consumers and coverage."""
    selected=[t for t in current['tasks'] if t['id']==target]
    if len(selected)!=1:
        raise ValueError('Review context needs exactly one current target: '+target)
    whole=overview(current)
    whole['tasks']=[{'id':target,'contract_ref':'current_task'} if t['id']==target else t
                    for t in whole['tasks']]
    return {'original_request':request,'whole_plan':whole,'current_task':copy.deepcopy(selected[0]),
            'coverage_plan':copy.deepcopy(current.get('coverage_plan',{}))}


def packet(request, draft, current, target,provider='qwen'):
    """Review current contracts once; original-draft preservation is enforced natively."""
    return bounded_prompt('task-refinement',packet_data(request,current,target),provider)


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
    from planning_limits import arguments,limits
    from shadow_navigation import count
    save(output.with_suffix('.context-budget.json'),{
        'target':target,'provider':planner,'packet_tokens':count(prompt),'limits':limits(planner),
        'representation':'coverage_review' if target=='COVERAGE' else 'current_contracts_once',
        'includes_implementation_source':False,'context_plan':str(current_path)})
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
