"""Web actions reuse the private planner, deterministic executor, and reviewer."""
import json
import subprocess
import time
from pathlib import Path
from config import FLOW, ROOT, PYTHON
import pi_session
import rpc
import raw_chat
import quality_service
import role_selection
import thinking_caps
from monitor import Monitor
import request_entry
import shadow_setup
import server_config


def sync_preferences(job):
    row=job.store.get(job.ident);project=Path(row['project']);cfg=row['settings']
    saved=role_selection.load(project);cfg.update({key:saved[key] for key in ('planner','reviewer')})
    cap=thinking_caps.load(project)
    cfg['thinking_cap']=cap if cap is not None else min(4096,cfg['output_tokens']-2048)
    job.store.update(job.ident,settings=cfg)


def turn(job,text,develop=False):
    with Monitor(job):
        return conversation_turn(job,text,develop)


def conversation_turn(job,text,develop=False):
    row=job.store.get(job.ident);base=job.store.folder/job.ident
    if text.split(maxsplit=1)[0] == '/server':
        values=text.split(maxsplit=1)
        if len(values)==2:
            minimum=row['settings']['input_tokens']+row['settings']['output_tokens']+8192
            connection=server_config.save(server_config.validate(values[1],minimum_context=minimum))
        else:connection=server_config.load()
        job.store.message(job.ident,'notice','Qwen endpoint: '+connection['url']+'/v1 · '+connection['model']+'. Applies to new turns and tasks; saved paused attempts retain their original endpoint.')
        job.note('Server configured');return
    job.note('Connecting to Qwen · '+server_config.load()['url'])
    quality_service.start();job.check()
    if row['settings']['mode']=='raw':
        raw_chat.run(job,base/'chat');job.note('Ready');return
    pending=row.get('pending_plan')
    if pending and text=='/resume-planning':
        prepared=pi_session.restore(Path(pending['folder']))
        rpc.run(job,prepared,pending['request']);finish_plan(job,prepared);return
    command=text.split(maxsplit=1)[0]
    if command=='/remember' and text.strip()=='/remember':
        latest=next((m['text'] for m in reversed(row['messages']) if m['role']=='assistant' and m.get('mode')=='pi' and m.get('text') and m.get('stop') not in ('error','aborted')),None)
        if latest:text='/remember '+latest
    controls={'/remember','/planner','/reviewer','/thinkingcap','/resume-planning'}
    if command not in controls:
        routed=request_entry.resolve(job,text,resume=command=='/resume-request')
        if routed is None:return
        decision,text,answers=routed
        row=job.store.get(job.ident)
        if decision['route']=='develop':
            brief=request_entry.development_brief(job,decision,text,answers)
            shadow_setup.ensure(job,Path(row['project']))
            return plan(job,brief,answers)
        role='inspect' if decision['route']=='inspect' else 'chat'
        if role=='inspect':shadow_setup.ensure(job,Path(row['project']))
        text=request_entry.local_branch_request(decision,text,answers)
    else:role='chat'
    prepared=pi_session.prepare(row,base/'chat'/role,role)
    sessions=row['sessions'];sessions['chat']=prepared['session'];job.store.update(job.ident,sessions=sessions)
    rpc.run(job,prepared,text);sync_preferences(job)
    job.note('Ready')


def plan(job,request,answers=None):
    row=job.store.get(job.ident);base=job.store.folder/job.ident
    folder=base/'planning'/str(time.time_ns())
    prepared=pi_session.prepare(row,folder,'architect')
    if answers:(Path(prepared['session'])/'initial-answers.json').write_text(json.dumps(['Clarification '+str(i+1)+' is incorporated in the supplied local intake goal.' for i in range(len(answers))]))
    job.store.update(job.ident,pending_plan={'folder':str(folder),'request':request},plan=None,run_dir=None)
    job.note('Clarifying, researching, then planning with '+row['settings']['planner'])
    rpc.run(job,prepared,request);finish_plan(job,prepared)


def finish_plan(job,prepared):
    path=Path(prepared['plan'])
    sync_preferences(job)
    if path.exists():
        from plan_runner import validate
        validate(Path(job.store.get(job.ident)['project']),json.loads(path.read_text()))
        job.store.update(job.ident,plan=str(path),pending_plan=None)
        job.store.message(job.ident,'notice','Granular plan ready. Review the tasks and acceptance criteria, then choose Run plan.')
        job.note('Plan ready')
    else:job.note('Planning paused or incomplete. Resume planning to continue the same request.')


def command(job,argv,logfile):
    """Run only a server-built workflow command, preserving logs and checkpoints."""
    logfile.parent.mkdir(parents=True,exist_ok=True)
    with logfile.open('ab') as log:
        process=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        job.process=process;last=0;started=time.monotonic();tick=started
        while process.poll() is None:
            job.check()
            if time.monotonic()-last>3:
                last=time.monotonic()
                with logfile.open('rb') as reader:
                    reader.seek(max(0,logfile.stat().st_size-1600));tail=reader.read().decode(errors='replace').strip()
                job.store.update(job.ident,run_log=tail)
            if time.monotonic()-tick>=30:
                tick=time.monotonic();state_path=logfile.parent/'state.json'
                state=json.loads(state_path.read_text()) if state_path.exists() else {}
                label='Final review' if state.get('status')=='complete' else 'Task '+state['current_todo'] if state.get('current_todo') else 'Workflow'
                job.note(f'{label} working · {int(tick-started)}s since start')
            time.sleep(.2)
        job.process=None;job.check()
        return process.returncode


def execute(job):
    with Monitor(job,'execution_observation'):
        return execute_plan(job)


def execute_plan(job):
    row=job.store.get(job.ident)
    if not row.get('plan'):raise ValueError('Create a validated plan first')
    base=job.store.folder/job.ident
    run=Path(row['run_dir']) if row.get('run_dir') else base/'runs'/str(time.time_ns())
    action='resume' if row.get('run_dir') else 'execute'
    job.store.update(job.ident,run_dir=str(run));job.note('Running granular tasks; fresh context and acceptance gates for each task')
    argv=[str(ROOT/'mypi'),action,row['project'],row['plan'],'--run-dir',str(run),'--reviewer',row['settings']['reviewer']]
    code=command(job,argv,run/'web-run.log')
    review_file=run/'final-review/review.json'
    review=json.loads(review_file.read_text()) if review_file.exists() else {}
    followup=code==0 and review.get('verdict')=='followup'
    if code==0:shadow_setup.ensure(job,Path(row['project']))
    job.store.message(job.ident,'notice', ('Execution completed; the reviewer requests follow-up. '+review.get('summary','')) if followup else 'Execution and final review completed.' if code==0 else f'Workflow stopped (exit {code}). Review the evidence; failed work is not marked complete.')
    job.note('Reviewer requests follow-up' if followup else 'Completed and reviewed' if code==0 else 'Stopped with evidence · resume or replan')


def replan(job):
    row=job.store.get(job.ident)
    if not row.get('run_dir'):raise ValueError('No run evidence to replan')
    run=Path(row['run_dir']); evidence=run/'replan-request.json'
    if not evidence.exists():
        candidates=list(run.rglob('replan*.json'))
        if len(candidates)!=1:raise ValueError('No unambiguous replanning packet; inspect run evidence')
        evidence=candidates[0]
    output=job.store.folder/job.ident/'planning'/str(time.time_ns())/'plan.json'
    code=command(job,[str(ROOT/'mypi'),'replan',row['project'],str(evidence),'--out',str(output),'--planner',row['settings']['planner']],output.parent/'replan.log')
    if code or not output.exists():raise ValueError('Replanning did not produce an accepted plan; inspect the log')
    job.store.update(job.ident,plan=str(output),run_dir=None);job.note('Replacement plan ready')
