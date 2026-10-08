/** Formatting preserves unavailable measurements instead of displaying false zeros. */
export const number=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString(undefined,{maximumFractionDigits:1}):'—';
export const gib=v=>typeof v==='number'&&Number.isFinite(v)?(v/1024**3).toFixed(2)+' GiB':'—';
export function duration(v){if(typeof v!=='number'||!Number.isFinite(v))return '—';v=Math.max(0,v);return v<60?Math.floor(v)+'s':v<3600?Math.floor(v/60)+'m '+Math.floor(v%60)+'s':Math.floor(v/3600)+'h '+Math.floor(v%3600/60)+'m';}
export function phase(value){return ({chunk:'Reading prompt',reasoning:'Thinking',tool_call:'Writing tool call',answer:'Writing response'})[value]||value||'Idle';}
export function completion(done,total){return typeof done==='number'&&total>0?Math.max(0,Math.min(100,done/total*100)):0;}
export function testState(result,fresh){if(!result)return 'Not run';if(fresh===false)return 'Stale';return result.exit_code===0?'Passed':'Failed';}

/** Keep planning acceptance separate from the future implementation contracts. */
export const taskKey=task=>task.preview||task.implementation?'implementation:'+task.id:task.planning?'planning:'+task.id:task.id;
export function queueGroups(run){
 return run.workflow_phase==='planning'?
  [{id:'planning',label:'Planning',tasks:[...(run.tasks||[]),...(run.planning_tasks||[])]},
   {id:'implementation',label:'Implementation',preview:!run.implementation_state,tasks:run.implementation_tasks||[]}]:
  [{id:'implementation',label:'Implementation',tasks:run.tasks||[]},
   ...(run.planning_tasks?.length?[{id:'planning',label:'Planning history',tasks:run.planning_tasks}]:[])];
}
export function selectedTask(run,key){
 const all=queueGroups(run).flatMap(g=>g.tasks);
 return all.find(t=>taskKey(t)===key)||
  (key?.startsWith('implementation:')?queueGroups(run).find(g=>g.id==='implementation')?.tasks.find(t=>t.id===key.slice(15)):null)||
  all.find(t=>t.id===key)||all.find(t=>t.id===run.current_todo&&!t.preview&&!t.planning)||all[0];
}

/** Follow the planning-to-execution handoff once; later history selections stay put. */
export function queueSelection(previous,run,key,filter='All'){
 const execution=run.workflow_phase!=='planning';
 const handoff=execution&&previous?.workflow_phase==='planning';
 const legacyReview=execution&&!previous&&key&&!key.includes(':')&&
  !run.tasks?.some(t=>t.id===key)&&run.planning_tasks?.some(t=>t.id===key);
 const follow=handoff||legacyReview;
 const choice=selectedTask(run,follow?(run.current_todo||run.tasks?.[0]?.id):key);
 return {selected:choice?taskKey(choice):'',
  phase:queueGroups(run).find(g=>g.tasks.includes(choice))?.id||'implementation',
  filter:follow?'All':filter,handoff:Boolean(handoff)};
}

/** Explain whether implementation is still a draft or paused with real run evidence. */
export function queueNote(run,group){
 if(group.preview)return 'Awaiting planning. These saved tasks may change during review; implementation has not started.';
 if(group.id==='planning')return run.implementation_state?
  'Reviewing an implementation failure. The Implementation tab retains all task statuses and results.':
  run.workflow_phase==='planning'?'Completed steps contain saved planning results.':
  'Planning is complete. These are saved reviews; choose Implementation for generation tasks.';
 const state=run.implementation_state;
 return state?'Implementation paused for failure review'+(state.current_todo?' · '+state.current_todo:'')+
  (state.reason?' · '+state.reason:'')+'. Task statuses and results are retained.':
  'Implementation status follows actual test and acceptance evidence.';
}

/** Label actual external-model reasoning, retaining clear empty and stopped states. */
export function thinkingCounter(run){
 const t=run.thinking||{},n=run.native?.requests?.[0],context=run.tasks?.find(x=>x.id===run.current_todo)?.context||{};
 const valid=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
 const parts=[];
 if(valid(t.reported_reasoning_tokens))parts.push((t.previous?'Previous response thinking: ':'Response thinking: ')+number(t.reported_reasoning_tokens)+' tokens');
 else if(!t.previous&&n?.phase==='reasoning'&&valid(n.reasoning_phase_tokens))parts.push('Current thinking phase: '+number(n.reasoning_phase_tokens)+' tokens');
 if(t.text&&valid(t.visible_tokens_estimate))parts.push('Shown'+(t.truncated?' tail':' text')+': ≈'+number(t.visible_tokens_estimate)+' tokens');
 if(!parts.length)parts.push(t.text?'Thinking tokens unavailable':'Thinking: waiting');
 if(context.thinking==='off')parts.push('thinking disabled');
 else if(context.reasoning_budget_tokens===0)parts.push('cap uncapped');
 else if(valid(context.reasoning_budget_tokens))parts.push('cap '+number(context.reasoning_budget_tokens));
 if(n&&valid(n.output_tokens))parts.push('Current response: '+number(n.output_tokens)+' total output tokens');
 return {text:parts.join(' · '),title:'Thinking is part of total output. Shown-text counts use the bundled tokenizer and are estimates, especially for cloud models. A shown tail is not the full response. Backend phase and completed usage counts are reported separately.'};
}

export function thinkingView(run){
 const t=run.thinking||{},text=typeof t.text==='string'?t.text:'';
 const native=run.native?.requests?.[0],movedOn=native?.phase&&native.phase!=='reasoning';
 const idle=run.native?.available===true&&!native;
 const streaming=run.status==='running'&&t.streaming===true&&!t.previous&&!movedOn&&!idle;
 const status=streaming?'Streaming':text?(run.status==='running'?(t.previous?'Previous response':movedOn?phase(native.phase)+' · last recorded thinking':'Latest recorded thinking'):(run.status==='complete'?'Run complete':'Run stopped')+' · last recorded thinking'):'No thinking text yet';
 const note=run.status==='running'&&native?.phase==='tool_call'?
  'Thinking text has ended; the backend is writing tool arguments, which may be buffered until the call is complete.':'Recorded Pi reasoning; updates every 3 seconds.';
 const detail=[t.todo||run.current_todo,t.attempt,note,t.truncated?'Earlier text omitted; showing the recent tail.':''].filter(Boolean).join(' · ');
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
  const planning=run.workflow_phase==='planning',drafting=planning&&id==='DRAFT',repair=Boolean(run.implementation_state);
  const planningTitle=id==='DRAFT'?'Generating draft plan':id==='COVERAGE'?'Generating coverage plan':
   id?.startsWith('REVIEW-')?'Refining task plan':repair?'Reviewing implementation failure':'Generating planning response';
  const title=planning&&!reading?planningTitle:phase(native.phase);
  const note=planning?(repair?'Implementation is paused for a corrective plan. ':drafting?'Implementation has not started. ':'This planning step is not yet validated. ')+
   (native.phase==='tool_call'?'Waiting for complete tool arguments before validation; partial arguments are not shown.':
    repair?'The remaining implementation tasks are available in the Implementation tab.':
    'Implementation waits for all required planning reviews to pass.'):'';
  return {title:title+suffix,detail:[goal,progress,rate,note].filter(Boolean).join(' — '),state:'running',todo:id};
 }
 if(run.native?.other_requests)return {title:'Waiting for the model'+suffix,detail:'The model is serving another request. '+goal,state:'waiting',todo:id};
 const last=task?.tools?.at(-1);
 return {title:(id?'Executing task':'Preparing run')+suffix,
  detail:[goal,last?'Last recorded action: '+last.name+(last.target?' · '+last.target:'')+' ('+last.status.toLowerCase()+')':''].filter(Boolean).join(' — '),
  state:'waiting',todo:id};
}
