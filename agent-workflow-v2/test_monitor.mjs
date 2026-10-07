import test from 'node:test';
import assert from 'node:assert/strict';
import {number,gib,duration,phase,completion,testState,currentStep,thinkingView,queueGroups,taskKey,selectedTask} from '../pi-web/static/monitor-format.mjs';
test('Unavailable measurements remain unavailable, zero stays zero',()=>{for(const x of [undefined,null,NaN,'3']){assert.equal(number(x),'—');assert.equal(gib(x),'—');assert.equal(duration(x),'—');}assert.equal(number(0),'0');assert.equal(gib(1024**3),'1.00 GiB');});
test('Thinking labels distinguish live, previous and stopped output without manufacturing text',()=>{
 const r={status:'running',thinking:{text:'Recorded thought',streaming:true,todo:'T2',truncated:true}};
 assert.equal(thinkingView(r).status,'Streaming');assert.match(thinkingView(r).detail,/T2.*Earlier text omitted/);
 r.status='needs_replan';assert.match(thinkingView(r).status,/Run stopped/);assert.equal(thinkingView(r).streaming,false);
 r.status='complete';assert.match(thinkingView(r).status,/Run complete/);
 r.status='running';r.thinking.streaming=false;r.thinking.previous=true;assert.equal(thinkingView(r).status,'Previous response');
 assert.match(thinkingView({}).text,/No thinking text/);
});
test('Native tool-call phase ends the visible thinking stream even if Pi has not emitted thinking_end',()=>{
 const r={status:'running',thinking:{text:'Last thought',streaming:true},native:{available:true,requests:[{phase:'tool_call'}]}};
 let view=thinkingView(r);assert.equal(view.streaming,false);assert.match(view.status,/Writing tool call/);
 assert.match(view.detail,/buffered until the call is complete/);assert.equal(view.text,'Last thought');
 r.native.requests[0].phase='reasoning';assert.equal(thinkingView(r).streaming,true);
 for(const p of ['answer','chunk']){r.native.requests[0].phase=p;assert.equal(thinkingView(r).streaming,false);}
 r.native.requests=[];assert.equal(thinkingView(r).streaming,false);
 r.native={available:false};assert.equal(thinkingView(r).streaming,true);
 r.thinking.previous=true;assert.equal(thinkingView(r).streaming,false);
 r.status='needs_replan';assert.match(thinkingView(r).status,/Run stopped/);
});
test('Elapsed durations and completion limits do not fabricate progress',()=>{assert.equal(duration(61),'1m 1s');assert.equal(duration(3661),'1h 1m');assert.equal(duration(-1),'0s');assert.equal(completion(5,10),50);assert.equal(completion(99,10),100);assert.equal(completion(0,0),0);});
test('Test success becomes stale after source changes',()=>{assert.equal(testState(undefined),'Not run');assert.equal(testState({exit_code:0},false),'Stale');assert.equal(testState({exit_code:1},true),'Failed');assert.equal(testState({exit_code:0},true),'Passed');assert.equal(phase('reasoning'),'Thinking');});

const run=()=>({status:'running',current_todo:'T1',tasks:[{id:'T1',goal:'Implement number extraction',steps:['Implement','Test'],tools:[]},{id:'T2',goal:'Unrelated task'}]});
test('Planning and implementation groups keep selection, acceptance and shared links distinct',()=>{
 const r={workflow_phase:'planning',current_todo:'DRAFT',accepted:1,total:2,
  tasks:[{id:'DRAFT',status:'Accepted'}],implementation_tasks:[{id:'DRAFT',preview:true,status:'Awaiting planning'},{id:'T1',preview:true}]};
 assert.equal(queueGroups(r).length,2);assert.equal(selectedTask(r,'DRAFT').preview,undefined);
 assert.equal(selectedTask(r,'implementation:DRAFT').preview,true);assert.equal(taskKey(r.implementation_tasks[1]),'implementation:T1');
 assert.equal(r.accepted,1);assert.equal(r.total,2);
 const execution={workflow_phase:'execution',tasks:[{id:'T1',status:'Pending'}]};
 assert.equal(queueGroups(execution).length,1);assert.equal(selectedTask(execution,'implementation:T1').id,'T1');
 execution.planning_tasks=[{id:'DRAFT',planning:true,planning_result:{available:true}}];
 assert.equal(queueGroups(execution).length,2);assert.equal(selectedTask(execution,'DRAFT').planning,true);
 assert.equal(taskKey(selectedTask(execution,'DRAFT')),'planning:DRAFT');
 assert.equal(selectedTask(execution,'planning:DRAFT').planning_result.available,true);
 assert.equal(selectedTask(r,'missing').id,'DRAFT');assert.equal(selectedTask({},''),undefined);
});
test('Current activity uses recorded model phase and actual tokens, never guesses planned step numbers',()=>{
 const r=run();r.native={requests:[{phase:'chunk',prefill_done:100,prompt_tokens:200}]};
 const activity=currentStep(r);assert.equal(activity.todo,'T1');assert.match(activity.title,/Reading prompt/);
 assert.match(activity.detail,/100 \/ 200 prompt tokens/);assert.doesNotMatch(activity.detail,/Unrelated|step 1|step 2/i);
});
test('Long draft generation exposes live rate and validation boundary without claiming implementation progress',()=>{
 const r={...run(),workflow_phase:'planning',current_todo:'DRAFT',tasks:[{id:'DRAFT',goal:'Create draft'}],
  native:{requests:[{phase:'tool_call',output_tokens:18064,decode_tok_s:18.9}]}};
 const activity=currentStep(r);assert.equal(activity.title,'Generating draft plan · DRAFT');
 assert.match(activity.detail,/18.9 tok\/s/);assert.match(activity.detail,/Implementation has not started/);
 assert.match(activity.detail,/complete tool arguments before validation/);assert.doesNotMatch(activity.detail,/%|remaining|complete plan/);
 r.native.requests[0].decode_tok_s=null;assert.doesNotMatch(currentStep(r).detail,/tok\/s/);
 r.native.requests[0].phase='chunk';assert.match(currentStep(r).title,/Reading prompt/);
 r.workflow_phase='execution';assert.doesNotMatch(currentStep(r).detail,/Implementation has not started/);
});
test('Coverage and refinement explain buffered generation without inventing verified checks',()=>{
 for(const [id,title] of [['COVERAGE','Generating coverage plan'],['REVIEW-01-T1','Refining task plan']]){
  const r={...run(),workflow_phase:'planning',current_todo:id,tasks:[{id,goal:'Review'}],
   native:{requests:[{phase:'tool_call',output_tokens:5229,decode_tok_s:20.6}]}};
  const view=currentStep(r);assert.equal(view.title,title+' · '+id);
  assert.match(view.detail,/20.6 tok\/s/);assert.match(view.detail,/not yet validated/);
  assert.match(view.detail,/partial arguments are not shown/);assert.doesNotMatch(view.detail,/%|checks completed/);
  r.native.requests[0].phase='chunk';assert.match(currentStep(r).title,/Reading prompt/);
  r.tasks[0].tools=[{name:'plan_store',status:'Running'}];assert.match(currentStep(r).title,/Running plan_store/);
  r.status='needs_replan';assert.equal(currentStep(r).state,'stopped');
 }
});
test('A running tool identifies its real file instead of replaying a completed action',()=>{
 const r=run();r.tasks[0].tools=[{name:'write',target:'old.py',status:'Completed'},{name:'edit',target:'active.py',status:'Running'}];
 const activity=currentStep(r);assert.match(activity.title,/Editing file/);assert.match(activity.detail,/active.py/);assert.doesNotMatch(activity.detail,/old.py/);
});
test('Stopped runs take precedence over lingering model telemetry and include native gate evidence',()=>{
 const r=run();r.status='needs_replan';r.reason='timeout';r.native={requests:[{phase:'answer'}]};
 r.tasks[0].attempts=[{gate:{violations:['Required architecture insertion missing']}}];
 const activity=currentStep(r);assert.equal(activity.state,'stopped');assert.match(activity.title,/Needs replanning/);
 assert.match(activity.detail,/timeout.*architecture insertion missing/);assert.doesNotMatch(activity.title,/Writing response/);
});
test('An interrupted run reports interruption without claiming tool execution is live',()=>{
 const r=run();r.status='interrupted';r.tasks[0].tools=[{name:'write',status:'Running'}];
 const activity=currentStep(r);assert.match(activity.title,/Interrupted/);assert.equal(activity.detail,r.tasks[0].goal);
});
test('A model serving another request explains waiting; prior actions remain clearly historical',()=>{
 const r=run();r.native={other_requests:1};assert.match(currentStep(r).title,/Waiting for the model/);
 r.native={};r.tasks[0].tools=[{name:'workflow_test',status:'Completed'}];
 const activity=currentStep(r);assert.match(activity.detail,/Last recorded action.*completed/);assert.doesNotMatch(activity.title,/Running tests/);
});
test('Complete and unplanned runs have useful summaries without stale todo links',()=>{
 assert.deepEqual(currentStep({status:'complete',accepted:3}),{title:'Run complete',detail:'3 tasks accepted.',state:'complete'});
 const activity=currentStep({status:'planning'});assert.equal(activity.todo,undefined);assert.match(activity.detail,/Waiting for an execution plan/);
});
