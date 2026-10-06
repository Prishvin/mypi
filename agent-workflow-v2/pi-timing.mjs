/** Attribute real streamed text/reasoning/tools and partial provider outcomes. */
import {appendFileSync} from 'node:fs';
import {join} from 'node:path';
import {active} from './pi-hooks.mjs';

export function installTimingHooks(pi){
  let started=0, seen=new Set(), requestId=null;
  const tools=new Map();
  const save=row=>appendFileSync(join(process.env.QWEN_WORKFLOW_SESSION,'provider-timing.jsonl'),JSON.stringify(row)+'\n');
  pi.on('tool_call',(event,ctx)=>{
    if(!active(ctx.model)||!process.env.QWEN_WORKFLOW_SESSION)return;
    tools.set(event.toolCallId,{tool:event.toolName,started_epoch:Date.now()/1000});
  });
  pi.on('tool_result',(event,ctx)=>{
    if(!active(ctx.model)||!tools.has(event.toolCallId))return;
    const call=tools.get(event.toolCallId);tools.delete(event.toolCallId);
    const ended=Date.now()/1000;
    appendFileSync(join(process.env.QWEN_WORKFLOW_SESSION,'tool-timing.jsonl'),JSON.stringify({
      type:'tool_end',tool_call_id:event.toolCallId,...call,ended_epoch:ended,
      wall_seconds:ended-call.started_epoch,is_error:!!event.isError,
      nested_validation_included:true})+'\n');
  });
  pi.on('before_provider_request',(event,ctx)=>{
    if(!active(ctx.model)||!process.env.QWEN_WORKFLOW_SESSION)return;
    started=Date.now();seen=new Set();
    requestId=event.payload?.metadata?.mtplx_request_id || process.env.QWEN_WORKFLOW_CURRENT_REQUEST_ID || null;
    save({type:'request_start',request_id:requestId,epoch:started/1000,provider:ctx.model.provider,model:ctx.model.id});
  });
  pi.on('message_update',(event,ctx)=>{
    if(!active(ctx.model)||!started)return;
    const item=event.assistantMessageEvent;
    const kind=item?.type;
    if(!['thinking_delta','text_delta','toolcall_delta'].includes(kind) || item.delta==='')return;
    for(const type of ['first_token', ...(kind==='text_delta'?['first_visible_text']:[]), ...(kind==='toolcall_delta'?['first_tool_call']:[])]){
      if(seen.has(type))continue;
      seen.add(type);
      save({type,request_id:requestId,epoch:Date.now()/1000,latency_seconds:(Date.now()-started)/1000,kind});
    }
  });
  pi.on('message_end',(event,ctx)=>{
    if(!active(ctx.model)||!started||event.message?.role!=='assistant')return;
    const stop=event.message.stopReason;
    save({type:'request_end',request_id:requestId,epoch:Date.now()/1000,wall_seconds:(Date.now()-started)/1000,
      usage:event.message.usage,stop_reason:stop,partial:['aborted','error'].includes(stop),error:event.message.errorMessage || null});
    started=0;
  });
}
