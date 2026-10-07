"""Draft once, review every original todo in a fresh context, then publish atomically."""
import fcntl
import json
import os
import time
from pathlib import Path
from plan_draft import digest
from project_map import scan
from runner_process import read,save
from runner_resume import interruption_signals


def adopt(project,request,output,planner,timeout,*,source,require_refinement=True):
    """Import a validated unexecuted draft without another model-generated first pass."""
    from plan_draft import bind
    binding=output.with_suffix('.binding.json')
    bind(project,source,binding,scan(project,['.'])['snapshot'])
    plan=checked(project,source)
    plan['planning_review']={'required':True,'status':'draft'};save(output,plan)
    return {'passed':True,'plan':str(output),'adopted_draft':str(source)}


def checkpoint(folder, state, **values):
    """Publish bounded stage progress for the shared run monitor and resumable CLI."""
    state.update(values,updated_epoch=time.time());save(folder/'state.json',state)


def queue(folder, state, request, draft=None):
    """Expose review progress separately from implementation-task acceptance."""
    from planning_limits import limits
    budget=limits(state['refiner'])
    items=[{'id':'DRAFT','goal':'Generate the architectural draft','files':[],
            'status':'done' if draft else 'todo','steps':['Draft architecture, granular tasks and acceptance']}]
    items.append({'id':'COVERAGE','goal':'Plan requirement and test coverage','files':[],
        'status':'done' if state.get('coverage_passed') else 'todo','depends_on':['DRAFT'],
        'steps':['Map every requirement to observable unit, integration and e2e checks',
                 'Assign missing cases to tasks for refinement']})
    for index,task in enumerate((draft or {}).get('tasks',[]),1):
        items.append({'id':f'REVIEW-{index:02d}-{task["id"]}','goal':'Refine '+task['id']+': '+task['goal'],
            'files':[],'status':'done' if task['id'] in state.get('reviewed',[]) else 'todo',
            'depends_on':['COVERAGE'],'steps':['Review against the original request, whole draft and coverage plan',
                'Refine or split this task; validate preserved acceptance, dependencies and budgets'],
            'context':{'window_tokens':budget['context'],'max_input_tokens':budget['input'],'max_output_tokens':budget['output'],
                       'reasoning_effort':budget['reasoning'],'reasoning_budget_tokens':1024 if state['refiner']=='qwen' else None},
            'execution':{'timeout_seconds':state['timeout']}})
    save(folder/'queue.json',{'goal':request,'tasks':items})


def checked(project, path, expected=None):
    """Validate a full plan and reject changed source while reviewing it."""
    from plan_runner import validate
    plan=read(path);validate(project,plan)
    current=scan(project,['.'])['snapshot']
    if (expected and current!=expected) or plan.get('snapshot')!=current:
        raise ValueError('Project changed during planning; review from fresh evidence')
    return plan


def create(project,request,output,planner,timeout,draft_fn,options,refiner=None):
    """Resume only matching requests; no partial review is published as executable."""
    project,output=project.resolve(),output.resolve();refiner=refiner or planner
    if output.is_relative_to(project):raise ValueError('Choose a new plan path outside the project')
    if planner not in ('qwen','chatgpt') or refiner not in ('qwen','chatgpt'):raise ValueError('Invalid planner/refiner')
    folder=output.with_suffix('.stages');folder.mkdir(parents=True,exist_ok=True)
    with (folder/'planning.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('This two-stage planning run is already active') from None
        identity={'project':str(project),'request_sha256':digest(request),'planner':planner,'refiner':refiner}
        state=read(folder/'state.json')
        if state and any(state.get(k)!=v for k,v in identity.items()):raise ValueError('Planning checkpoint belongs to a different request or provider')
        if output.exists():
            if not state.get('published_sha256') or digest(read(output))!=state['published_sha256']:
                raise ValueError('Plan already exists; choose a new output path')
            checked(project,output,state['source_snapshot'])
            checkpoint(folder,state,status='complete',reason=None,current_todo=None)
            return read(output.with_suffix('.planning-result.json'))
        if not state:
            state={**identity,'workflow_phase':'planning','plan':str(folder/'queue.json'),
                   'started_epoch':time.time(),'reviewed':[],'reviews':[],'attempts':[]}
        state['timeout']=timeout
        with interruption_signals():
            try:return drive(project,request,output,folder,state,draft_fn,options)
            except KeyboardInterrupt:
                checkpoint(folder,state,status='interrupted',reason='Planning interrupted; rerun the same plan command to resume')
                return {'passed':False,'stage':'interrupted','checkpoint':str(folder/'state.json')}
            except (OSError,ValueError) as error:
                checkpoint(folder,state,status='needs_replan',reason=str(error))
                return {'passed':False,'stage':'refinement_failed','validation_error':str(error),'checkpoint':str(folder/'state.json')}


def drive(project,request,output,folder,state,draft_fn,options):
    """Keep a fixed original review order; split children are validated within their review."""
    draft_path=folder/'draft.json'
    if not state.get('draft_passed'):
        number=state.get('draft_attempts',0)+(0 if state.get('reason')=='awaiting_clarification' else 1)
        candidate=folder/f'draft-attempt-{max(1,number)}.json'
        queue(folder,state,request)
        checkpoint(folder,state,status='running',reason=None,current_todo='DRAFT',
                   draft_attempts=max(1,number),attempt_folder=str(candidate.with_suffix('.planning')),attempt_started_epoch=time.time())
        result=draft_fn(project,request,candidate,state['planner'],state['timeout'],require_refinement=True,**options)
        state['draft_result']=result
        if not result.get('passed'):
            checkpoint(folder,state,status='needs_replan',reason=result.get('stage','draft_failed'))
            return {**result,'checkpoint':str(folder/'state.json')}
        draft=checked(project,candidate)
        draft['planning_review']={'required':True,'status':'draft'};save(draft_path,draft)
        checkpoint(folder,state,draft_passed=True,source_snapshot=draft['snapshot'],
                   draft_sha256=digest(draft),current_plan=str(draft_path),current_plan_sha256=digest(draft),
                   refined_request=result.get('pipeline',{}).get('refined_prompt',request))
    draft=checked(project,draft_path,state['source_snapshot'])
    if digest(draft)!=state['draft_sha256']:raise ValueError('Original draft checkpoint changed')
    current=checked(project,Path(state['current_plan']),state['source_snapshot'])
    if digest(current)!=state['current_plan_sha256']:raise ValueError('Reviewed plan checkpoint changed')
    queue(folder,state,request,draft)
    review_request=request+'\n\nClarified request:\n'+state['refined_request'] if state.get('refined_request',request)!=request else request
    from plan_refinement import review,review_coverage
    if not state.get('coverage_passed'):
        attempt=state.get('coverage_attempts',0)+1;destination=folder/f'coverage-attempt-{attempt}.json'
        checkpoint(folder,state,status='running',reason=None,current_todo='COVERAGE',coverage_attempts=attempt,
                   attempt_folder=str(destination.with_suffix('.planning')),attempt_started_epoch=time.time())
        result=review_coverage(project,review_request,draft_path,destination,state['refiner'],state['timeout'])
        state['coverage_result']=result
        if not result.get('passed'):
            checkpoint(folder,state,status='needs_replan',reason='coverage_failed')
            return {'passed':False,'stage':'coverage_failed','checkpoint':str(folder/'state.json')}
        current=checked(project,destination,state['source_snapshot'])
        from coverage_plan import validate as validate_coverage
        validate_coverage(draft,current.get('coverage_plan'))
        checkpoint(folder,state,coverage_passed=True,current_plan=str(destination),current_plan_sha256=digest(current))
        queue(folder,state,request,draft)
    for index,task in enumerate(draft['tasks'],1):
        if task['id'] in state['reviewed']:continue
        attempt=state.get('review_attempts',0)+1;destination=folder/f'review-{index:02d}-attempt-{attempt}.json'
        checkpoint(folder,state,status='running',reason=None,current_todo=f'REVIEW-{index:02d}-{task["id"]}',
                   review_attempts=attempt,attempt_folder=str(destination.with_suffix('.planning')),attempt_started_epoch=time.time())
        result=review(project,review_request,draft,Path(state['current_plan']),task['id'],destination,state['refiner'],state['timeout'])
        state['reviews'].append(result)
        if not result.get('passed'):
            checkpoint(folder,state,status='needs_replan',reason='refinement_failed: '+task['id'])
            return {'passed':False,'stage':'refinement_failed','task':task['id'],'checkpoint':str(folder/'state.json')}
        current=checked(project,destination,state['source_snapshot'])
        state['reviewed'].append(task['id'])
        checkpoint(folder,state,current_plan=str(destination),current_plan_sha256=digest(current))
        queue(folder,state,request,draft)
    from plans import save as publish
    from coverage_plan import require_gaps
    require_gaps(current['tasks'],current['coverage_plan']['gaps'])
    if state['reviewed']!=[t['id'] for t in draft['tasks']]:raise ValueError('Review coverage does not match the original draft')
    current['planning_review']={'required':True,'status':'passed','draft_sha256':digest(draft),
        'reviewed_original_tasks':state['reviewed'],'refiner':state['refiner'],
        'coverage_receipt':state['coverage_result']['plan'],
        'receipts':[r['plan'] for r in state['reviews'] if r.get('passed')]}
    candidate=folder/'validated-final.json'
    if candidate.exists():candidate.unlink() # Only our unpublished final candidate; every review is retained.
    publish(project,['.'],current,candidate)
    checked(project,candidate,state['source_snapshot'])
    result={'passed':True,'plan':str(output),'stage':'reviewed','planner':state['planner'],'refiner':state['refiner'],
            'draft_result':state['draft_result'],'coverage_result':state['coverage_result'],
            'task_reviews':state['reviews'],'checkpoint':str(folder/'state.json')}
    save(output.with_suffix('.planning-result.json'),result)
    checkpoint(folder,state,published_sha256=digest(read(candidate)))
    os.link(candidate,output) # Atomic publication that cannot overwrite another writer.
    checkpoint(folder,state,status='complete',reason=None,ended_epoch=time.time(),current_todo=None)
    return result
