"""Bounded JSONL transport for Pi RPC, including clarification dialogs and streaming."""
import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from config import FLOW
from processes import terminate
import launch
from run_metrics import collect


def records(stream,output):
    try:
        for line in iter(stream.readline,b''):
            try: output.put(json.loads(line))
            except ValueError: continue
    finally:output.put(None)


def run(job,prepared,prompt):
    """One resumed Pi turn; only server-created commands cross the RPC boundary."""
    env=launch.environment(prepared); folder=Path(prepared['session'])
    with (folder/'rpc-stderr.log').open('ab') as errors:
        process=subprocess.Popen(prepared['command'],cwd=prepared['cwd'],env=env,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,start_new_session=True)
        job.process=process; events=queue.Queue()
        threading.Thread(target=records,args=(process.stdout,events),daemon=True).start()
        def send(value):
            process.stdin.write(json.dumps(value,ensure_ascii=False).encode()+b'\n');process.stdin.flush()
        send({'type':'prompt','id':'turn','message':prompt})
        started=time.monotonic(); tick=started; saved=0; current=None; text=''; thinking=''; failure=None;accepted_stop=False
        with (folder/'rpc-events.jsonl').open('ab') as log:
            try:
                while True:
                    job.check()
                    if time.monotonic()-started>1800:raise TimeoutError('Pi turn exceeded 30 minutes; history and evidence saved')
                    if time.monotonic()-tick>30:
                        job.note(f'Pi working · {int(time.monotonic()-started)}s');tick=time.monotonic()
                    try:event=events.get(timeout=.2)
                    except queue.Empty:continue
                    if event is None:
                        job.check()
                        raise RuntimeError('Pi exited unexpectedly (code '+str(process.poll())+'): '+(folder/'rpc-stderr.log').read_text()[-1500:])
                    record=event
                    if event.get('type')=='message_update':
                        delta=event.get('assistantMessageEvent',{})
                        record={'type':'message_update','assistantMessageEvent':{k:delta[k] for k in ('type','delta') if k in delta}}
                    log.write(json.dumps(record,ensure_ascii=False).encode()+b'\n');log.flush()
                    kind=event.get('type')
                    if kind=='response' and event.get('id')=='turn':
                        if not event.get('success'):raise RuntimeError(event.get('error','Pi rejected the request'))
                        if event.get('data',{}).get('disposition')=='handled':break
                    if kind=='extension_ui_request':
                        method=event['method']
                        if method in ('input','select','confirm','editor'):
                            value=job.dialog(event)
                            answer={'type':'extension_ui_response','id':event['id']}
                            if value is None:answer['cancelled']=True
                            elif method=='confirm':answer['confirmed']=bool(value)
                            else:answer['value']=str(value)
                            send(answer)
                        elif method=='notify':
                            job.note(event.get('message',''))
                            job.store.message(job.ident,'notice',event.get('message',''))
                        elif method=='setStatus' and event.get('statusText'):job.note(event['statusText'])
                    if kind=='message_start' and event.get('message',{}).get('role')=='assistant':
                        current=job.store.message(job.ident,'assistant','',mode='pi',phase=prepared['role'])
                        text='';thinking='';failure=None
                    if kind=='message_update':
                        delta=event.get('assistantMessageEvent',{})
                        if delta.get('type')=='text_delta':text+=delta.get('delta','')
                        if delta.get('type')=='thinking_delta':thinking+=delta.get('delta','')
                        if current and time.monotonic()-saved>.35:
                            job.store.edit_message(job.ident,current,text=text,thinking=thinking);saved=time.monotonic()
                    if kind=='message_end' and event.get('message',{}).get('role')=='assistant':
                        message=event['message'];text=''.join(x.get('text','') for x in message.get('content',[]) if x.get('type')=='text')
                        if current:job.store.edit_message(job.ident,current,text=text,thinking=thinking,usage=message.get('usage',{}),stop=message.get('stopReason'))
                        if message.get('stopReason')=='error':failure=message.get('errorMessage','Model request failed')
                    if kind=='tool_execution_start':job.note('Running '+event.get('toolName','tool'))
                    if kind=='tool_execution_end':
                        job.note(event.get('toolName','Tool')+(' failed' if event.get('isError') else ' finished'))
                        detail=event.get('result',{}).get('details',{})
                        if not event.get('isError') and (detail.get('developmentHandoff') or detail.get('acceptedPlanningStop')):
                            accepted_stop=True
                    if kind=='auto_compaction_start':job.note('Compacting conversation to its input budget')
                    if kind=='agent_settled':break
                if failure and not (accepted_stop and 'abort' in failure.lower()):raise RuntimeError(failure)
            finally:
                if current:job.store.edit_message(job.ident,current,text=text,thinking=thinking)
                process.stdin.close()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:terminate(process)
                job.process=None
    metrics=collect({'session':str(folder)},folder)
    metrics['wall_seconds']=round(time.monotonic()-started,2)
    phase=prepared['role']
    if prompt.split(maxsplit=1)[0]=='/remember':
        remembered=folder/'remember-result.json'
        if remembered.exists():
            result=json.loads(remembered.read_text()).get('phase',{})
            metrics={**result.get('metrics',{}),'wall_seconds':result.get('wall_seconds',metrics['wall_seconds'])}
            phase='memory distillation'
    job.store.update(job.ident,metrics=metrics,metrics_phase=phase)
    return metrics
