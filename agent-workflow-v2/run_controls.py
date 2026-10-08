"""Explicit browser actions restart one bound todo through native mypi resume."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid
from runner_process import read, save
from task_instructions import coordinator, current
from run_owner import identity

BASE=Path(__file__).resolve().parent.parent


def selected(monitor):
    """Bind edits to the displayed atomic attempt, never whichever task runs later."""
    run=monitor.selected();state=read(run/'state.json')
    if state.get('workflow_phase')=='planning':
        raise ValueError('Task controls are available during implementation; planning is still in progress')
    plan=read(Path(state.get('plan','/nonexistent')))
    task=next((t for t in plan.get('tasks',[]) if t['id']==state.get('current_todo') and t.get('status')!='done'),None)
    if not task:raise ValueError('There is no unfinished current task to restart')
    owner=coordinator(run);recovery=read(owner/'recovery-state.json')
    if recovery and recovery.get('project')!=state.get('project'):raise ValueError('Coordinator project mismatch')
    payload={'run':str(run),'todo':task['id'],'attempt':state.get('attempt_folder'),'plan':state.get('plan'),
             'contract':{k:v for k,v in task.items() if k not in ('status','baseline','evidence','shadow_snapshot')}}
    revision=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    return run,state,task,owner,revision


class Controls:
    """Serialize restart requests and persist their outcomes for refresh/reconnect."""
    def __init__(self,monitor):self.monitor=monitor

    def view(self):
        try:
            run,state,task,owner,revision=selected(self.monitor)
            request=read(owner/'ui-control.json')
            if request.get('status')=='starting':
                if revision!=request['revision']:
                    request.update(status='restarted',finished_epoch=time.time())
                elif not identity(request.get('pid')):
                    log=owner/('ui-restart-'+request['id']+'.log')
                    request.update(status='failed',error='Restart stopped before a new attempt. '+(
                        log.read_text(errors='replace')[-1000:] if log.exists() else 'Inspect the native run evidence.'))
                save(owner/'ui-control.json',request)
            return {'available':True,'run':run.name,'todo':task['id'],'revision':revision,
                    'prompt':current(run,task),'request':request}
        except (OSError,ValueError,KeyError) as error:return {'available':False,'reason':str(error)}

    def restart(self,data):
        if not isinstance(data,dict) or set(data)-{'revision','mode','prompt'}:
            raise ValueError('Invalid task restart fields')
        run,state,task,owner,revision=selected(self.monitor)
        if data.get('revision')!=revision:raise ValueError('The active task changed. Reload its prompt before restarting.')
        if read(owner/'ui-control.json').get('status') in ('stopping','starting'):
            raise ValueError('A task restart is already in progress')
        mode=data.get('mode');text=data.get('prompt','')
        if mode not in ('append','replace') or not isinstance(text,str) or not text.strip() or len(text.encode())>16000:
            raise ValueError('Supply 1–16000 bytes of task instructions')
        prompt=current(run,task)+'\n\nAdditional user instruction:\n'+text.strip() if mode=='append' else text.strip()
        if len(prompt.encode())>24000:raise ValueError('Combined instructions exceed 24000 bytes; edit the task prompt instead')
        lock=(owner/'ui-control.lock').open('a')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:lock.close();raise ValueError('A task restart is already in progress') from None
        row={'id':uuid.uuid4().hex,'status':'stopping','epoch':time.time(),'todo':task['id'],
             'revision':revision,'mode':mode,'prompt':prompt}
        save(owner/'ui-control.json',row)
        threading.Thread(target=self._restart,args=(run,state,task,owner,row,lock),daemon=True).start()
        return {'accepted':True,'request_id':row['id'],'status':'stopping'}

    def _restart(self,run,state,task,owner,row,lock):
        try:
            process=read(owner/'coordinator-process.json');pid=process.get('pid')
            if state.get('status')=='running':
                if process.get('project')!=state.get('project') or not process.get('identity') or identity(pid)!=process['identity']:
                    raise ValueError('Cannot verify this running coordinator; restart it with the updated mypi first')
                os.kill(pid,signal.SIGINT)
                deadline=time.monotonic()+45
                while identity(pid)==process['identity']:
                    if time.monotonic()>deadline:raise ValueError('Coordinator has not stopped; no replacement was launched')
                    time.sleep(.1)
            stopped=read(run/'state.json')
            if stopped.get('current_todo')!=task['id']:
                raise ValueError('Task changed during interruption; instructions were not applied')
            if stopped.get('status') not in ('interrupted','needs_replan'):
                raise ValueError('Task did not reach a resumable checkpoint')
            folder=owner/'task-instructions';folder.mkdir(exist_ok=True)
            save(folder/(task['id']+'.json'),row)
            save(folder/(task['id']+'-'+row['id']+'.json'),row)
            recovery=read(owner/'recovery-state.json')
            plan=recovery.get('original_plan',state['plan'])
            command=[str(BASE/'mypi'),'resume',state['project'],plan,'--run-dir',str(owner)]
            if recovery.get('status')=='awaiting_user':
                command.append('--retry-review' if 'review' in str(recovery.get('reason','')).lower() else '--allow-repair')
            child=self.launch(command,owner/('ui-restart-'+row['id']+'.log'))
            row.update(status='starting',pid=child.pid,command=command,finished_epoch=time.time())
        except Exception as error:row.update(status='failed',error=str(error),finished_epoch=time.time())
        finally:
            save(owner/'ui-control.json',row);lock.close()

    def launch(self,command,logfile):
        """Start only a server-built native command, keeping its output for review."""
        with logfile.open('w') as log:
            return subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
