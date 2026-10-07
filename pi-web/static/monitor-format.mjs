/** Formatting preserves unavailable measurements instead of displaying false zeros. */
export const number=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString(undefined,{maximumFractionDigits:1}):'—';
export const gib=v=>typeof v==='number'&&Number.isFinite(v)?(v/1024**3).toFixed(2)+' GiB':'—';
export function duration(v){if(typeof v!=='number'||!Number.isFinite(v))return '—';v=Math.max(0,v);return v<60?Math.floor(v)+'s':v<3600?Math.floor(v/60)+'m '+Math.floor(v%60)+'s':Math.floor(v/3600)+'h '+Math.floor(v%3600/60)+'m';}
export function phase(value){return ({chunk:'Reading prompt',reasoning:'Thinking',tool_call:'Writing tool call',answer:'Writing response'})[value]||value||'Idle';}
export function completion(done,total){return typeof done==='number'&&total>0?Math.max(0,Math.min(100,done/total*100)):0;}
export function testState(result,fresh){if(!result)return 'Not run';if(fresh===false)return 'Stale';return result.exit_code===0?'Passed':'Failed';}

/** Label actual external-model reasoning, retaining clear empty and stopped states. */
export function thinkingView(run){
 const t=run.thinking||{},text=typeof t.text==='string'?t.text:'',streaming=run.status==='running'&&t.streaming===true;
 const status=streaming?'Streaming':text?(run.status==='running'?(t.previous?'Previous response':'Latest recorded thinking'):(run.status==='complete'?'Run complete':'Run stopped')+' · last recorded thinking'):'No thinking text yet';
 const detail=[t.todo||run.current_todo,t.attempt,'Recorded Pi reasoning; updates every 3 seconds.',t.truncated?'Earlier text omitted; showing the recent tail.':''].filter(Boolean).join(' · ');
 return {status,detail,streaming,text:text||(streaming?'Waiting for the first thinking text…':'No thinking text is available in the recorded output for this attempt.')};
}

/** Describe recorded activity without guessing a numbered step from planned prose. */
export function currentStep(run){
 const task=run.tasks?.find(t=>t.id===run.current_todo),id=run.current_todo;
 const suffix=id?' · '+id:'',goal=task?.goal||run.goal||'Waiting for an execution plan.';
 if(run.status==='complete')return {title:'Run complete',detail:run.accepted+' tasks accepted.',state:'complete'};
 if(['needs_replan','interrupted'].includes(run.status)){
  const last=task?.attempts?.at(-1),reasons=[run.reason,...(last?.gate?.violations||[])].filter(Boolean);
  return {title:(run.status==='interrupted'?'Interrupted':'Needs replanning')+suffix,
   detail:reasons.length?reasons.join(' · '):goal,state:'stopped',todo:id};
 }
 const call=task?.tools?.findLast(c=>c.status==='Running');
 if(call){
  const label={write:'Writing file',edit:'Editing file',source_query:'Reading code',workflow_test:'Running tests',web_research:'Researching',skill_use:'Running skill'}[call.name]||'Running '+call.name;
  return {title:label+suffix,detail:[call.target,goal].filter(Boolean).join(' — '),state:'running',todo:id};
 }
 const native=run.native?.requests?.[0];
 if(native){
  const reading=native.phase==='chunk',tokens=reading?native.prefill_done:native.output_tokens;
  const progress=tokens!=null?(reading?number(tokens)+' / '+number(native.prompt_tokens)+' prompt tokens':number(tokens)+' output tokens'):'';
  const speed=reading?native.prefill_tok_s:native.decode_tok_s;
  const rate=typeof speed==='number'&&Number.isFinite(speed)?number(speed)+' tok/s':'';
  const drafting=run.workflow_phase==='planning'&&id==='DRAFT';
  const title=drafting&&!reading?'Generating draft plan':phase(native.phase);
  const note=drafting?'Implementation has not started. '+(native.phase==='tool_call'?
   'Waiting for complete tool arguments before validation.':'The draft must pass validation and task review first.'):'';
  return {title:title+suffix,detail:[goal,progress,rate,note].filter(Boolean).join(' — '),state:'running',todo:id};
 }
 if(run.native?.other_requests)return {title:'Waiting for the model'+suffix,detail:'The model is serving another request. '+goal,state:'waiting',todo:id};
 const last=task?.tools?.at(-1);
 return {title:(id?'Executing task':'Preparing run')+suffix,
  detail:[goal,last?'Last recorded action: '+last.name+(last.target?' · '+last.target:'')+' ('+last.status.toLowerCase()+')':''].filter(Boolean).join(' — '),
  state:'waiting',todo:id};
}
