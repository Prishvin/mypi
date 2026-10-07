/** Granular evidence dashboard shared by CLI monitor and conversation UI. */
import {number,duration,gib,phase,completion,testState,currentStep,thinkingView,queueGroups,taskKey,selectedTask} from './monitor-format.mjs';
const $=id=>document.getElementById(id);
const el=(tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=String(text);if(cls)node.className=cls;return node;};
const badge=value=>el('span',value,'badge '+value.toLowerCase());
const conversation=new URL(location.href).searchParams.get('conversation');
const endpoint=conversation?'/api/conversations/'+encodeURIComponent(conversation)+'/monitor':'/api/status';
let data=null,selected=decodeURIComponent(location.hash.slice(1)),queuePhase=null,pending=false;
const metric=(label,value)=>{const node=el('div',undefined,'stat');node.append(el('span',label),el('strong',value));return node;};
function nativeMetric(label,value){const node=el('div');node.append(el('strong',value),el('span',label));return node;}
function copiedText(target){
 const copy=target.cloneNode(true);copy.querySelectorAll('button').forEach(n=>n.remove());
 copy.querySelectorAll('div,p,li,pre,summary,h1,h2,h3,span,strong,code,b').forEach(n=>n.append(document.createTextNode('\n')));
 return copy.textContent.replace(/[ \t]+\n/g,'\n').replace(/\n{3,}/g,'\n\n').trim();
}
async function copyText(text){
 try{if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);return;}}catch{}
 const field=el('textarea');field.value=text;field.className='clipboard-buffer';field.setAttribute('aria-hidden','true');
 const focus=document.activeElement;document.body.append(field);field.select();
 try{if(!document.execCommand('copy'))throw Error('Copy unavailable');}finally{field.remove();focus?.focus({preventScroll:true});}
}
function copyButton(label,getText){
 const button=el('button','⧉','copy-button');button.type='button';button.title='Copy '+label;button.setAttribute('aria-label',button.title);
 button.onclick=async event=>{event.preventDefault();event.stopPropagation();try{
   await copyText(getText());button.textContent='✓';$('copy-feedback').textContent='Copied '+label;
 }catch{$('copy-feedback').textContent='Could not copy. Select the text and copy manually.';}
 setTimeout(()=>{button.textContent='⧉';},1600);};return button;
}
function renderThinking(d){
 const view=thinkingView(d),area=$('thinking-text');
 const atEnd=area.scrollHeight-area.scrollTop-area.clientHeight<40;
 $('thinking-status').textContent=view.status;$('thinking-detail').textContent=view.detail;
 $('thinking-panel').dataset.streaming=String(view.streaming);
 if(area.textContent!==view.text){const position=area.scrollTop;area.textContent=view.text;area.scrollTop=atEnd?area.scrollHeight:position;}
}
function renderNative(d){
 const area=$('native');area.replaceChildren();const n=d.native||{};
 $('model-state').textContent=n.available?(n.model||'Qwen')+' · '+number(n.context_window)+' capacity':'Native telemetry unavailable';
 if(!n.available)area.append(el('p',n.error||'Waiting for telemetry','subtle'));
 for(const r of n.requests||[]){
  area.append(el('p',phase(r.phase)+' · request '+duration(r.age_seconds)));
  const grid=el('div',undefined,'native-grid');grid.append(nativeMetric('Actual prompt',number(r.prompt_tokens)),nativeMetric('Prompt processed',number(r.prefill_done)),nativeMetric('New prompt tokens',number(r.new_prefill_tokens)),nativeMetric('Cached prompt tokens',number(r.cached_tokens)),nativeMetric('Reported prompt tok/s',number(r.prefill_tok_s)),nativeMetric('Output this request',number(r.output_tokens)),nativeMetric('Decode tok/s',number(r.decode_tok_s)));area.append(grid);
  if(r.prefill_done!=null){const rail=el('div',undefined,'native-bar'),fill=el('div');fill.style.width=completion(r.prefill_done,r.prompt_tokens)+'%';rail.append(fill);area.append(rail);}
 }
 if(n.available&&!n.requests?.length)area.append(el('p',n.other_requests?'Model busy with another request; this run may be waiting.':'No active model request for this run.'));
 const memory=el('div',undefined,'native-grid');memory.append(nativeMetric('Backend active allocation',gib(n.memory?.active_memory_bytes)),nativeMetric('Physical footprint',gib(n.memory?.phys_footprint_bytes)),nativeMetric('Sampled process RSS',gib(d.sampled_rss_bytes)),nativeMetric('Memory pressure level',number(n.memory_pressure_level)));area.append(memory);
 if(d.rss_sample_epoch)area.append(el('p','RSS sample age: '+duration(Date.now()/1000-d.rss_sample_epoch),'subtle'));
}
function section(label,child){const node=el('details');node.dataset.key=label;const heading=el('summary',label);heading.append(copyButton(label,()=>copiedText(child)));node.append(heading,child);return node;}
function renderQueue(){
 const nav=$('tasks');nav.replaceChildren();const filter=$('filter').value;
 const groups=queueGroups(data),group=groups.find(g=>g.id===queuePhase)||groups[0];queuePhase=group.id;
 const phases=$('queue-phases');phases.replaceChildren();
 for(const g of groups){const b=el('button',g.label+' ('+g.tasks.length+')');b.dataset.phase=g.id;b.setAttribute('aria-pressed',String(g.id===group.id));
  b.onclick=()=>{queuePhase=g.id;selected=g.tasks[0]?taskKey(g.tasks[0]):'';$('filter').value='All';history.replaceState(null,'','#'+encodeURIComponent(selected));renderQueue();renderTask();};phases.append(b);}
 $('count').textContent=group.tasks.length+' tasks';
 $('queue-note').textContent=group.preview?'Awaiting planning. These saved tasks may change during review; implementation has not started.':
  group.id==='planning'?'Completed steps contain saved planning results.':'Implementation status follows actual test and acceptance evidence.';
 for(const task of group.tasks.filter(t=>filter==='All'||t.status===filter)){
  const key=taskKey(task),b=el('button',undefined,'todo'+(key===selected?' selected':''));b.dataset.task=task.id;
  b.append(el('strong',task.id),el('p',task.goal),badge(task.status));
  b.onclick=()=>{selected=key;history.replaceState(null,'','#'+encodeURIComponent(selected));renderQueue();renderTask();};nav.append(b);
 }
 if(!nav.childElementCount)nav.append(el('p',group.preview&&!group.tasks.length?'The implementation draft has not been saved yet.':'No tasks with this status.','empty'));
}

function renderPlanningResult(result){
 const area=el('section',undefined,'planning-output');area.append(el('h3','Saved planning result'));
 if(!result.available){area.append(el('p',result.reason||'Saved result unavailable.'));return area;}
 area.append(el('p','Validated planning artifact · '+result.artifact+' · implementation and tests have not been performed by this review.','subtle'));
 if(result.architecture)area.append(section('Architecture decisions',el('pre',result.architecture)));
 if(result.changes)area.append(section('Changes made in this review',el('pre',JSON.stringify(result.changes,null,2))));
 if(result.architecture_change)area.append(section('Architecture changes',el('pre',JSON.stringify(result.architecture_change,null,2))));
 if(result.criterion_corrections?.length)area.append(section('Acceptance corrections and reasons',el('pre',JSON.stringify(result.criterion_corrections,null,2))));
 if(result.coverage){
  const c=result.coverage;area.append(el('p',(c.checks?.length||0)+' planned checks · '+(c.requirements?.length||0)+' requirement links · '+(c.gaps?.length||0)+' gaps'));
  const strategy=el('div');for(const [name,text] of Object.entries(c.strategy||{})){strategy.append(el('h4',name),el('p',text));}area.append(section('Test strategy',strategy));
  for(const [label,items] of [['Planned checks',c.checks],['Requirement coverage',c.requirements],['Gaps to add during refinement',c.gaps]]){
   const content=el('div');for(const item of items||[])content.append(el('pre',JSON.stringify(item,null,2)));
   if(!items?.length)content.append(el('p','None recorded.'));area.append(section(label,content));
  }
 }
 for(const task of result.tasks||[]){
  const content=el('div');content.append(el('p',task.goal),el('p','Files: '+(task.files||[]).join(', '),'subtle'));
  const steps=el('ol',undefined,'step-list');for(const step of task.steps||[])steps.append(el('li',step));content.append(steps);
  if(task.test_strategy)content.append(el('h4','Test strategy'),el('p',task.test_strategy));
  content.append(renderCases(task),renderTests(task),section('Full saved task contract · '+task.id,el('pre',JSON.stringify(task,null,2))));
  area.append(section(task.id+' · '+task.goal,content));
 }
 area.querySelector('details')?.setAttribute('open','');
 return area;
}
function renderTests(task){
 const area=el('div');if(task.tests_fresh===false)area.append(el('p','Last tests are stale: source changed after they ran.','failure'));
 (task.tests||[]).forEach((argv,i)=>{const result=task.test_results?.[i],row=el('div',undefined,'command');row.append(el('strong','Command '+(i+1)+' '),badge(testState(result,task.tests_fresh)),el('pre',argv.join(' ')));if(result)row.append(el('p','Exit '+result.exit_code+' · tests collected: '+number(result.tests_collected),'subtle'));area.append(row);});return area;
}
function renderCases(task){
 const area=el('div');for(const c of task.acceptance||[]){const row=el('div',undefined,'case');row.append(el('strong',c.id));for(const k of ['given','when','then']){const p=el('p');p.append(el('b',k.toUpperCase()+' '),document.createTextNode(c[k]));row.append(p);}const commands=(task.coverage||[]).filter(x=>x.criterion===c.id).map(x=>x.test+1);row.append(el('p','Covered by frozen command '+commands.join(', '),'subtle'));area.append(row);}return area;
}
function renderFiles(task){
 const area=el('div');for(const file of task.files||[]){const row=el('div',undefined,'file-row');row.append(el('code',file.path),el('span',file.state+(file.lines!=null?' · '+file.lines+' lines':'')+(file.bytes!=null?' · '+number(file.bytes)+' B':'')));area.append(row);}return area;
}
function renderTools(task){
 const area=el('div');for(const call of [...(task.tools||[])].reverse()){const row=el('div',undefined,'tool'+(call.error?' error':'')),left=el('div');left.append(el('strong',call.name),el('span',call.target||'','target'));row.append(left,badge(call.status),copyButton('tool '+call.name,()=>copiedText(row)));if(call.seconds!=null)row.append(el('span',duration(call.seconds)));if(call.error)row.append(el('pre',call.error));area.append(row);}if(!area.childElementCount)area.append(el('p','No recorded tool calls for this task yet.','subtle'));return area;
}
function renderTask(){
 const area=$('detail'),prior=area.dataset.taskKey,open=new Set([...area.querySelectorAll('details[open]')].map(n=>n.dataset.key));area.replaceChildren();
 const task=queuePhase==='implementation'&&data.workflow_phase==='planning'&&!data.implementation_tasks?.length?null:selectedTask(data,selected);
 if(!task){area.append(el('h2','Waiting for an execution plan'),el('p','Saved planning/research attempts are listed below.','empty'));return;}
 selected=taskKey(task);const head=el('div',undefined,'task-head');head.append(el('h2',task.id),badge(task.status),copyButton('task details',()=>copiedText(area)));area.append(head,el('p',task.goal),el('p','Dependencies: '+((task.depends_on||[]).join(', ')||'none'),'subtle'));
 area.dataset.taskKey=selected;
 if(task.preview)area.append(el('p','Implementation draft — awaiting completion of planning. Steps, budgets and tests below are planned, not execution results.','subtle'));
 if(task.planning_result)area.append(renderPlanningResult(task.planning_result));
 if(task.elapsed_seconds!=null)area.append(el('p',(task.status==='Running'?'Current attempt: ':'Attempt duration: ')+duration(task.elapsed_seconds)+' / '+duration(task.execution?.timeout_seconds)));
 const limits=el('div',undefined,'limits');for(const [label,value] of [['Input cap',number(task.context?.max_input_tokens)],['Output cap',number(task.context?.max_output_tokens)],['Thinking cap',task.context?.thinking==='off'?'Disabled':task.context?.reasoning_budget_tokens===0?'Uncapped':number(task.context?.reasoning_budget_tokens)],['Client window',number(task.context?.window_tokens)],['Effort',task.context?.reasoning_effort||'—'],['Patch estimate',number(task.estimated_changed_lines)+' lines']]){const n=el('div');n.append(el('span',label),el('strong',value));limits.append(n);}area.append(limits);
 area.append(el('h3','Planned atomic steps'),el('p','Steps are the plan. Actual activity and test evidence below show what has happened.','subtle'));const steps=el('ol',undefined,'step-list');for(const step of task.steps||[])steps.append(el('li',step));area.append(steps);
 area.append(el('h3','Recent tool activity'),el('p','Completed means the tool call returned. Test results and task acceptance are tracked separately.','subtle'),renderTools(task),section('Files and actual change state',renderFiles(task)),section('Acceptance criteria and coverage',renderCases(task)),section('Frozen test commands and results',renderTests(task)));
 if(task.attempts?.length)area.append(section('Attempt history and metrics',el('pre',JSON.stringify(task.attempts,null,2))));
 area.append(section('Context recipe and stopping policy',el('pre',JSON.stringify({context:task.context,execution:task.execution},null,2))));
 if(prior===selected)for(const node of area.querySelectorAll('details'))node.open=open.has(node.dataset.key);
}
function render(d){
 data=d;$('goal').textContent=d.goal||'Planning is in progress';$('run-name').textContent=d.name+' / '+d.run;
 const choice=selectedTask(d,selected);if(choice){selected=taskKey(choice);queuePhase=choice.preview||(d.workflow_phase!=='planning'&&!choice.planning)?'implementation':'planning';}
 $('overview-title').textContent=d.workflow_phase==='planning'?'Planning review':'Run overview';$('completion-label').textContent=d.workflow_phase==='planning'?'planning steps verified':'tasks accepted';
 const step=currentStep(d);$('current-title').textContent=step.title;$('current-detail').textContent=step.detail;
 $('current-step').dataset.state=step.state;$('current-jump').hidden=!step.todo;
 $('completion').textContent=d.accepted+' / '+d.total;$('completion-bar').style.width=completion(d.accepted,d.total)+'%';
 $('run-status').textContent=d.status.replaceAll('_',' ')+' · '+(d.current_todo||'no active todo');$('count').textContent=d.total+' tasks';
 const active=d.native?.requests?.[0],elapsed=d.started_epoch?(d.elapsed_until_epoch||d.ended_epoch||Date.now()/1000)-d.started_epoch:null;
 $('stats').replaceChildren(metric('Accepted',d.accepted+' / '+d.total),metric('Elapsed',duration(elapsed)),metric('Current task',d.current_todo||'—'),metric('Live decode tok/s',number(active?.decode_tok_s)),metric('Live prompt tokens',number(active?.prompt_tokens)));
 $('failure').hidden=!d.reason;$('failure').textContent=d.reason?'Stopped for evidence-based replanning: '+d.reason:'';
 renderThinking(d);renderNative(d);renderQueue();renderTask();const history=$('phases');history.replaceChildren();for(const p of d.phases||[]){const row=el('div',undefined,'phase-row');row.append(el('span',p.name),badge(p.passed?'Passed':'Failed'),el('span',duration(p.seconds)));history.append(row);}
 $('updated').textContent='Evidence refreshed '+new Date(d.updated_epoch*1000).toLocaleTimeString();
}
async function refresh(){if(pending)return;pending=true;try{const r=await fetch(endpoint,{cache:'no-store'}),d=await r.json();if(!r.ok)throw Error(d.error||'Snapshot unavailable');if(!d.total&&data?.total){$('connection').textContent='Evidence being updated · retaining last snapshot';return;}render(d);$('connection').textContent='● Live · refresh every 3s';}catch(e){$('connection').textContent='Disconnected · '+e.message;}finally{pending=false;}}
$('current-jump').onclick=()=>{if(!data?.current_todo)return;selected=data.current_todo;queuePhase=data.workflow_phase==='planning'?'planning':'implementation';$('filter').value='All';history.replaceState(null,'','#'+encodeURIComponent(selected));renderQueue();renderTask();$('detail').scrollIntoView({behavior:'smooth',block:'start'});};
for(const [target,label,heading] of [[$('current-step'),'current status',$('current-step')],[$('thinking-text'),'model thinking',$('thinking-panel').querySelector('summary')],[$('goal'),'project brief',document.querySelector('.brief summary')],[$('native'),'model activity',document.querySelector('.live .section-title')]]){
 heading.append(copyButton(label,()=>copiedText(target)));
}
$('refresh').onclick=refresh;$('filter').onchange=()=>{if(data)renderQueue();};await refresh();setInterval(refresh,3000);
