"""Direct local OpenAI-compatible streaming; no Pi tools or cloud inference."""
import http.client
import json
import queue
import threading
import time
import uuid
from pathlib import Path
from config import FLOW
from token_budget import count_request
from run_metrics import rows
import quality_service
import server_config
from urllib.parse import urlsplit


def transport(timeout):
    """Build a client-side connection to the currently selected remote Qwen."""
    parts=urlsplit(server_config.load()['url'])
    factory=http.client.HTTPSConnection if parts.scheme=='https' else http.client.HTTPConnection
    return factory(parts.hostname,parts.port,timeout=timeout)


def stream_response(connection,payload,events):
    try:
        connection.request('POST','/v1/chat/completions',body=json.dumps(payload).encode(),headers={'Content-Type':'application/json',**server_config.headers()})
        response=connection.getresponse()
        if response.status!=200:raise RuntimeError(f'Qwen HTTP {response.status}: '+response.read(3000).decode(errors='replace'))
        for line in iter(response.readline,b''):
            if line.startswith(b'data: '):
                value=line[6:].strip()
                if value==b'[DONE]':break
                events.put(json.loads(value))
    except Exception as error:events.put(error)
    finally:events.put(None)


def run(job,folder):
    row=job.store.get(job.ident);cfg=row['settings']
    messages=[{'role':m['role'],'content':m['text']} for m in row['messages']
              if m['role'] in ('user','assistant') and m.get('mode')=='raw' and m['text']]
    ident='web-'+uuid.uuid4().hex
    payload={'model':server_config.load()['model'],'messages':messages,'stream':True,'stream_options':{'include_usage':True},
        'max_tokens':cfg['output_tokens'],'enable_thinking':cfg['thinking']=='on','reasoning_effort':cfg['reasoning'],
        'temperature':1 if cfg['thinking']=='on' else .7,'top_p':.95 if cfg['thinking']=='on' else .8,'top_k':20,
        'suppress_stats_footer':True,'metadata':{'client':'pi','mtplx_request_id':ident,'pi_thinking_cap':cfg['thinking_cap']},
        'chat_template_kwargs':{'enable_thinking':cfg['thinking']=='on','reasoning_effort':cfg['reasoning']}}
    folder.mkdir(parents=True,exist_ok=True);request=folder/'raw-request.json';request.write_text(json.dumps(payload))
    admission=count_request(request,cfg['input_tokens'],Path(__import__('os').environ.get('MYPI_TOKENIZER',str(FLOW/'qwen-tokenizer.json'))))
    if not admission['passed']:raise ValueError('Raw chat exceeds its input budget. Increase the input budget or create a new conversation; no history was silently discarded.')
    connection=transport(1800);events=queue.Queue();job.transport=connection
    threading.Thread(target=stream_response,args=(connection,payload,events),daemon=True).start()
    mid=job.store.message(job.ident,'assistant','',mode='raw');text='';thinking='';usage={};started=time.monotonic();saved=started;first=None
    try:
        while True:
            job.check()
            try:event=events.get(timeout=.2)
            except queue.Empty:continue
            if event is None:break
            if isinstance(event,Exception):raise event
            if event.get('error'):raise RuntimeError(str(event['error']))
            if event.get('usage'):usage=event['usage']
            for choice in event.get('choices',[]):
                delta=choice.get('delta',{});part=delta.get('content') or '';reason=delta.get('reasoning_content') or ''
                if (part or reason) and first is None:first=time.monotonic()-started
                text+=part;thinking+=reason
                if choice.get('finish_reason')=='length':job.note('Output limit reached; ask to continue or raise the cap')
            if time.monotonic()-saved>.35:
                job.store.edit_message(job.ident,mid,text=text,thinking=thinking);saved=time.monotonic()
    finally:
        connection.close();job.transport=None
        job.store.edit_message(job.ident,mid,text=text,thinking=thinking,usage=usage)
    status=quality_service.read_state();native=[r for r in rows(Path(status.get('logs','/nonexistent'))/'requests.jsonl') if str(r.get('request_id','')).endswith(ident)]
    if not native:
        from remote_metrics import native_for
        native=native_for(ident)
    metrics={'requests':1,'wall_seconds':round(time.monotonic()-started,2),'ttft_seconds':first,
             'input_tokens_sum':usage.get('prompt_tokens',0),'output_tokens_sum':usage.get('completion_tokens',0),
             'native_requests':native,'admission_estimate':admission}
    job.store.update(job.ident,metrics=metrics,metrics_phase='raw')
