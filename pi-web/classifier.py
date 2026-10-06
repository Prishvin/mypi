"""One short, tool-free local LLM call before the Pi conversation branches."""
import http.client
import json
import queue
import threading
import time
import uuid
from pathlib import Path
from config import ROOT, FLOW
from request_routing import PROMPT,without_code,parse
from raw_chat import stream_response,transport
from token_budget import count_request
from run_metrics import rows
import quality_service
import server_config


def classify(job,text,answers,folder):
    """Save raw evidence locally; send only intent and snippet markers to the router."""
    row=job.store.get(job.ident)
    history=[without_code(m['text'])[:1200] for m in row['messages'] if m['role']=='user' and m.get('kind')!='clarification-answer' and not m['text'].startswith('/')] [-4:]
    packet={'request':without_code(text),'answers':answers,'answered_rounds':len(answers),'recent_user_requests':history}
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'user-request.txt').write_text(text)
    (folder/'packet.json').write_text(json.dumps(packet))
    ident='route-'+uuid.uuid4().hex
    payload={'model':server_config.load()['model'],'messages':[{'role':'system','content':PROMPT},{'role':'user','content':json.dumps(packet)}],
        'stream':True,'stream_options':{'include_usage':True},'max_tokens':768,
        'enable_thinking':False,'chat_template_kwargs':{'enable_thinking':False},
        'temperature':0,'top_p':1,'suppress_stats_footer':True,
        'metadata':{'client':'pi','mtplx_request_id':ident}}
    request=folder/'request.json';request.write_text(json.dumps(payload))
    limit=min(job.store.get(job.ident)['settings']['input_tokens'],16384)
    admission=count_request(request,limit,Path(__import__('os').environ.get('MYPI_TOKENIZER',str(FLOW/'qwen-tokenizer.json'))))
    if not admission['passed']:raise ValueError('Classification input exceeds its budget. Put code in fenced blocks and state the requested action separately.')
    connection=transport(180);job.transport=connection;events=queue.Queue()
    threading.Thread(target=stream_response,args=(connection,payload,events),daemon=True).start()
    started=time.monotonic();tick=started;output='';usage={}
    try:
        while True:
            job.check()
            if time.monotonic()-started>180:raise TimeoutError('Request classification exceeded three minutes; no branch started')
            if time.monotonic()-tick>=30:job.note('Classifying request · '+str(int(time.monotonic()-started))+'s');tick=time.monotonic()
            try:event=events.get(timeout=.2)
            except queue.Empty:continue
            if event is None:break
            if isinstance(event,Exception):raise event
            if event.get('error'):raise ValueError(str(event['error']))
            usage=event.get('usage') or usage
            for choice in event.get('choices',[]):
                output+=choice.get('delta',{}).get('content') or ''
                if choice.get('finish_reason')=='length':raise ValueError('Classifier output truncated; no branch started')
    finally:connection.close();job.transport=None;(folder/'response.txt').write_text(output)
    decision=parse(output,packet);(folder/'decision.json').write_text(json.dumps(decision,indent=2))
    logs=Path(quality_service.read_state().get('logs','/nonexistent'))
    native=[r for r in rows(logs/'requests.jsonl') if str(r.get('request_id','')).endswith(ident)]
    if not native:
        from remote_metrics import native_for
        native=native_for(ident)
    metrics={'requests':1,'wall_seconds':round(time.monotonic()-started,2),'input_tokens_sum':usage.get('prompt_tokens',0),
             'output_tokens_sum':usage.get('completion_tokens',0),'native_requests':native,'admission_estimate':admission}
    (folder/'metrics.json').write_text(json.dumps(metrics,indent=2))
    row=job.store.get(job.ident);previous=row.get('classification_metrics',{})
    total={key:previous.get(key,0)+metrics.get(key,0) for key in ('requests','wall_seconds','input_tokens_sum','output_tokens_sum')}
    total['native_requests']=previous.get('native_requests',[])+native
    job.store.update(job.ident,classification=decision,classification_metrics=total)
    return decision
