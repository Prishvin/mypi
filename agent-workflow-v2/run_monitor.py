"""Read granular runner evidence for the web UI; never start a model or execute a task."""
import hashlib
import json
from pathlib import Path
import threading
import time
import urllib.request


def read(path, limit=2097152):
    """Treat half-written or missing bounded artifacts as pending rather than crashing."""
    try:
        if path.stat().st_size > limit:return {}
        data=json.loads(path.read_text())
        return data if isinstance(data,dict) else {}
    except (OSError, ValueError):return {}


def tail_json(path, limit=524288):
    """Read bounded complete JSONL records, without passing raw prompts to the viewer."""
    try:
        with path.open('rb') as stream:
            size=path.stat().st_size;stream.seek(max(0,size-limit));raw=stream.read(limit)
        lines=raw.decode(errors='replace').splitlines()
        if size>limit:lines=lines[1:]
        result=[]
        for line in lines:
            try:
                data=json.loads(line)
                if isinstance(data,dict):result.append(data)
            except ValueError:pass
        return result
    except OSError:return []


def tools(session,timing=None):
    """Expose tool names/status/timing and bounded errors, excluding arguments and source."""
    calls={}
    for event in tail_json(session/'pi.log'):
        kind=event.get('type');ident=event.get('toolCallId')
        if kind not in ('tool_execution_start','tool_execution_end'):continue
        row=calls.setdefault(ident,{'id':ident,'name':event.get('toolName'),'status':'Running'})
        if kind=='tool_execution_start':
            args=event.get('args',{});row['target']=' · '.join(str(args[k])[:180] for k in ('path','name','action') if k in args)
        if kind=='tool_execution_end':
            row['status']='Failed' if event.get('isError') else 'Completed'
            if event.get('isError'):
                content=event.get('result',{}).get('content',[])
                error=' '.join(x.get('text','') for x in content if isinstance(x,dict))
                for marker in ('Received arguments:','Closest SOURCE','\nSymbols:'):error=error.split(marker)[0]
                row['error']=error[:600]
    for event in tail_json((timing or session)/'tool-timing.jsonl'):
        row=calls.get(event.get('tool_call_id'))
        if row:
            row['started_epoch']=event.get('started_epoch')
            row['seconds']=event.get('wall_seconds')
    return list(calls.values())[-40:]


def file_status(root, paths, frozen):
    """Report actual existence/change/size without exposing implementations."""
    root=root.resolve()
    before={row['path']:row.get('sha256') for row in frozen.get('before',{}).get('files',[])}
    result=[]
    for name in paths:
        path=(root/name).resolve();row={'path':name,'state':'Not created'}
        if not path.is_relative_to(root):row['state']='Outside project'
        else:
            try:
                if path.is_file():
                    row.update(state='Present',bytes=path.stat().st_size)
                    if row['bytes']<=2097152:
                        raw=path.read_bytes();row['lines']=len(raw.splitlines())
                        if frozen:row['state']='Changed' if hashlib.sha256(raw).hexdigest()!=before.get(name) else 'Unchanged'
            except OSError:row['state']='Being updated'
        result.append(row)
    return result


def task_status(task, state, accepted):
    """Distinguish acceptance, active work, real failure and unmet dependencies."""
    if task.get('status')=='done' or task['id'] in accepted:return 'Accepted'
    if state.get('current_todo')==task['id']:
        return {'running':'Running','needs_replan':'Failed','interrupted':'Interrupted'}.get(state.get('status'),'Pending')
    if not set(task.get('depends_on',[]))<=accepted:return 'Blocked'
    return 'Pending'


def phase_rows(folder):
    """Retain planning/research failures separately from successful replacements."""
    paths=list(folder.glob('*.planning-result.json'))+list(folder.glob('plan-*/phase-result.json'))
    return [{'name':path.parent.name if path.name=='phase-result.json' else path.stem,
             'passed':data.get('passed'),'seconds':data.get('wall_seconds'),'metrics':data.get('metrics',{})}
            for path in sorted(paths) if (data:=read(path))]


class RunMonitor:
    """Bind one run or an evidence folder that follows subsequent replanned runs."""
    def __init__(self,folder,backend=None):
        self.folder=folder.resolve();self.backend=backend;self.lock=threading.Lock();self.native={};self.native_at=0
        if not self.folder.is_dir():raise ValueError('Choose an existing run or evidence folder')

    def selected(self):
        """Follow the most recently updated child run after repair/restart."""
        if (self.folder/'state.json').is_file():return self.folder
        candidates=[p.parent for p in self.folder.glob('run-*/state.json')]
        return max(candidates,key=lambda p:(p/'state.json').stat().st_mtime,default=self.folder)

    def telemetry(self,prefixes):
        """Poll metrics only, with cache/timeout and no model generation requests."""
        with self.lock:
            if time.monotonic()-self.native_at<3:return self.native
            try:
                if self.backend is None:
                    import server_config
                    endpoint=server_config.load()['url'].removesuffix('/v1')
                    headers=server_config.headers()
                else:endpoint=self.backend.removesuffix('/v1');headers={}
                request=urllib.request.Request(endpoint+'/v1/mtplx/metrics/stream',headers=headers)
                with urllib.request.urlopen(request,timeout=2) as response:
                    for _ in range(10):
                        line=response.readline(2097152)
                        if line.startswith(b'data:'):data=json.loads(line[5:]);break
                    else:raise ValueError('No native metrics snapshot')
                rows=[]
                for item in data.get('in_flight',[]):
                    if not any(item.get('request_id','').startswith(p) for p in prefixes):continue
                    progress=item.get('last_progress') or {};prefill=item.get('prefill_state') or {}
                    rows.append({'request_id':item['request_id'],'age_seconds':item.get('age_s'),
                        'prompt_tokens':item.get('prompt_tokens'),'prefill_done':prefill.get('tokens_done'),
                        'cached_tokens':prefill.get('cached_tokens'),'new_prefill_tokens':prefill.get('new_prefill_tokens'),
                        'prefill_tok_s':prefill.get('prefill_tok_s'),'phase':progress.get('decode_phase') or prefill.get('phase'),
                        'output_tokens':progress.get('completion_tokens'),'decode_tok_s':progress.get('decode_tok_s')})
                self.native={'available':True,'model':data.get('model_id'),'context_window':data.get('context_window'),
                    'requests':rows,'other_requests':max(0,data.get('active_requests',0)-len(rows)),
                    'memory':{key:value for key,value in data.get('mem',{}).items() if key.endswith('_bytes')},
                    'memory_pressure_level':data.get('memory_pressure_level')}
            except (OSError,ValueError,KeyError) as error:self.native={'available':False,'error':str(error)[:200]}
            self.native_at=time.monotonic();return self.native

    def snapshot(self):
        """Combine frozen todo contracts, actual tool/test evidence and native progress."""
        run=self.selected();state=read(run/'state.json');plan=read(Path(state['plan'])) if state.get('plan') else {}
        completed=plan.get('replan_lineage',{}).get('completed',[])
        accepted={t['id'] for t in plan.get('tasks',[]) if t.get('status')=='done'}
        accepted.update(t['id'] for t in completed)
        root=Path(state.get('project',plan.get('project',str(self.folder)))).resolve()
        current=Path(state.get('attempt_folder',str(run)))
        metadata=read(current/'session.json');session=Path(metadata['session']) if metadata.get('session') else current
        frozen=read(session/'task-state.json');current_tools=tools(current,session)
        fresh=None
        if frozen.get('evidence'):
            try:
                from tasks import current_snapshot
                identity=current_snapshot(frozen)[2];e=frozen['evidence']
                fresh=e.get('snapshot')==identity and e.get('finished_snapshot')==identity
            except (OSError,ValueError,KeyError):fresh=False
        tasks=[]
        current_ids={t['id'] for t in plan.get('tasks',[])}
        for task in [t for t in completed if t['id'] not in current_ids]+plan.get('tasks',[]):
            active=task['id']==state.get('current_todo');attempts=[a for a in state.get('attempts',[]) if a['todo']==task['id']]
            row={key:task.get(key) for key in ('id','goal','depends_on','steps','acceptance','coverage','tests','context','execution','estimated_changed_lines')}
            row.update(status=task_status(task,state,accepted),files=file_status(root,task['files'],frozen if active else {}),
                attempts=[{k:a.get(k) for k in ('wall_seconds','exit_code','gate','metrics','interrupted')} for a in attempts])
            if attempts and attempts[-1].get('session'):
                prior=read(Path(attempts[-1]['session'])/'task-state.json')
                row['test_results']=prior.get('evidence',{}).get('results',[])
                row['tools']=tools(Path(attempts[-1].get('log',str(run/'pi.log'))).parent,Path(attempts[-1]['session']))
            if active:row.update(tools=current_tools,test_results=frozen.get('evidence',{}).get('results',[]),tests_fresh=fresh,
                elapsed_seconds=max(0,time.time()-state.get('attempt_started_epoch',time.time())))
            tasks.append(row)
        prefixes=[]
        for path in self.folder.rglob('session.json'):
            data=read(path)
            if data.get('session'):prefixes.append('chatcmpl-'+Path(data['session']).name+'-')
        if metadata.get('session'):prefixes.append('chatcmpl-'+session.name+'-')
        observations=tail_json(self.folder/'observations.jsonl',65536)+tail_json(current/'memory.jsonl',65536)
        observations.sort(key=lambda row:row.get('epoch',0))
        sample=next((row for row in reversed(observations) if row.get('server_rss_bytes') is not None),{})
        rss=sample.get('server_rss_bytes')
        return {'updated_epoch':time.time(),'name':self.folder.name,'run':run.name,'goal':plan.get('goal'),
            'status':state.get('status','planning'),'current_todo':state.get('current_todo'),
            'accepted':len([t for t in tasks if t['status']=='Accepted']),'total':len(tasks),'tasks':tasks,
            'reason':state.get('reason'),'started_epoch':state.get('started_epoch'),'ended_epoch':state.get('ended_epoch'),
            'phases':phase_rows(self.folder),'native':self.telemetry(prefixes),'sampled_rss_bytes':rss,
            'rss_sample_epoch':sample.get('epoch'),
            'note':'Task acceptance proves frozen tests and gates passed; step completion is not inferred from model prose.'}
