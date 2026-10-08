/** Exercise the installed Qwen XML parser with the actual advertised tool schemas. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync,mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {homedir,tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {validateToolArguments} from '@earendil-works/pi-ai';
import {repairParameters} from './pi-plan-draft.mjs';
import {recoveryParameters} from './pi-replan-patch.mjs';
import {childParameters} from './pi-plan-contract.mjs';
import extension from './pi-extension.mjs';
import {runToolCall} from '../node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-agent-core/dist/agent-loop.js';

const home=fileURLToPath(new URL('.',import.meta.url));
const python=join(home,'.venv/bin/python');
const parser=process.env.MYPI_TEST_QWEN_PARSER||join(homedir(),'.local/share/mypi/qwen/.venv/lib/python3.12/site-packages/mlx_lm/tool_parsers/qwen3_coder.py');
function parse(name,schema,values){
  const xml='<function='+name+'>'+Object.entries(values).map(([key,value])=>
    '<parameter='+key+'>'+(typeof value==='string'?value:JSON.stringify(value))+'</parameter>').join('')+'</function>';
  const script=`import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('actual_qwen_parser',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
data=json.load(sys.stdin)
print(json.dumps(m.parse_tool_call(data['xml'],data['tools'])))`;
  const result=spawnSync(python,['-c',script,parser],{encoding:'utf8',input:JSON.stringify({xml,tools:[{type:'function',function:{name,parameters:schema}}]})});
  assert.equal(result.status,0,result.stderr);
  return JSON.parse(result.stdout);
}

test('all refinement and child top-level fields have direct Qwen parser types',()=>{
  for(const schema of [repairParameters(),repairParameters('A'),childParameters(),recoveryParameters()]){
    for(const [key,field] of Object.entries(schema.properties)){
      assert.ok(['object','array','string','integer','boolean'].includes(field.type),key);
      assert.equal(field.anyOf,undefined,key);
    }
  }
});

test('installed parser reproduces union-as-text bug and parses flat typed fields exactly',{skip:!existsSync(parser)},()=>{
  const legacy={type:'object',properties:{task_updates:{anyOf:[{type:'array'},{type:'string'}]}}};
  const edits=[{id:'A',steps:['Inspect','Test']}];
  assert.equal(typeof parse('plan_store',legacy,{task_updates:edits}).arguments.task_updates,'string');
  const schema=repairParameters('A'),values={steps:['Inspect comma, bracket ] and Unicode λ','Test'],
    assumptions:['No hidden edits'],context_overlay:{max_input_tokens:16384},
    add_acceptance:[{id:'G',given:'a,b',when:'called',then:'x'}],add_coverage:[{criterion:'G',test:0}]};
  const call=parse('plan_store',schema,values);
  assert.deepEqual(call.arguments,values);
  assert.deepEqual(validateToolArguments({name:'plan_store',parameters:schema},call),values);
  const unchanged=parse('plan_store',schema,{unchanged:true});
  assert.deepEqual(unchanged.arguments,{unchanged:true});
});

test('actual parser, Pi lifecycle and native CLI stage then commit full split without source edits',{skip:!existsSync(parser)},async()=>{
  const folder=mkdtempSync(join(tmpdir(),'qwen-plan-roundtrip-')),root=join(folder,'project'),bound=join(folder,'bound.json');
  const env={QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_SESSION:folder,QWEN_WORKFLOW_PROJECT:root,
    QWEN_WORKFLOW_PLAN:join(folder,'plan.json'),QWEN_WORKFLOW_PLAN_DRAFT:bound,
    QWEN_WORKFLOW_PLAN_COVERAGE:undefined,QWEN_WORKFLOW_PREFIXES:'["."]'};
  const previous=Object.fromEntries(Object.keys(env).map(k=>[k,process.env[k]]));
  try{
    for(const [k,v] of Object.entries(env))if(v===undefined)delete process.env[k];else process.env[k]=v;
    const setup=spawnSync(python,['-c',`import json,sys
from pathlib import Path
from test_plan_runner import todo
from plan_draft import bind
from project_map import scan
base=Path(sys.argv[1]);root=base/'project';root.mkdir()
a=todo('A');a['tests']=[['python3','-m','unittest']];a['files'].append('architecture.md')
source=base/'draft.json';source.write_text(json.dumps({'plan_version':3,'goal':'Normalize','architecture':'Pure functions','planning_review':{'required':True,'status':'draft'},'tasks':[a]}))
bind(root,source,base/'bound.json',scan(root,['.'])['snapshot'],target='A')
first=todo('A1');first['tests']=a['tests'];first['files']=a['files'];a['depends_on']=['A1']
print(json.dumps([first,a]))`,folder],{cwd:home,encoding:'utf8'});
    assert.equal(setup.status,0,setup.stderr);
    const children=JSON.parse(setup.stdout),tools={};
    const ctx={model:{provider:'local-qwen-workflow'},cwd:folder};
    extension({on:()=>{},registerCommand:()=>{},registerTool:tool=>{tools[tool.name]={...tool,execute:(...args)=>tool.execute(...args,ctx)};},
      exec:async(binary,args)=>{const result=spawnSync(binary,args,{encoding:'utf8'});return {code:result.status,stdout:result.stdout,stderr:result.stderr};}});
    const receipts=[];
    for(const child of children){
      const call=parse('plan_child_store',tools.plan_child_store.parameters,child);
      const result=await runToolCall({...call,id:child.id},{assistantMessage:{role:'assistant',content:[]},context:{messages:[],tools:Object.values(tools)}});
      assert.equal(result.isError,false,JSON.stringify(result));
      const staged=JSON.parse(result.result.content[0].text);assert.equal(staged.plan_accepted,false);
      receipts.push(staged.child_ref);assert.equal(existsSync(env.QWEN_WORKFLOW_PLAN),false);
    }
    const call=parse('plan_store',tools.plan_store.parameters,{child_refs:receipts});
    const result=await runToolCall({...call,id:'commit'},{assistantMessage:{role:'assistant',content:[]},context:{messages:[],tools:Object.values(tools)}});
    assert.equal(result.isError,false,JSON.stringify(result));
    const saved=JSON.parse(readFileSync(env.QWEN_WORKFLOW_PLAN,'utf8'));
    assert.deepEqual(saved.tasks.map(t=>t.id),['A1','A']);
    assert.equal(saved.planning_review.status,'draft');
    for(let i=0;i<children.length;i++)for(const [key,value] of Object.entries(children[i]))assert.deepEqual(saved.tasks[i][key],value);
    const unchanged=spawnSync(python,['-c',"import sys;from pathlib import Path;from project_map import scan;print(scan(Path(sys.argv[1]),['.'])['snapshot'])",root],{cwd:home,encoding:'utf8'});
    assert.equal(unchanged.stdout.trim(),JSON.parse(readFileSync(bound,'utf8')).snapshot);
  }finally{
    for(const [k,v] of Object.entries(previous))if(v===undefined)delete process.env[k];else process.env[k]=v;
    rmSync(folder,{recursive:true,force:true});
  }
});

test('installed Qwen parser through Pi tool execution saves a focused recovery without resending other tasks',{skip:!existsSync(parser)},async()=>{
 const folder=mkdtempSync(join(tmpdir(),'qwen-recovery-roundtrip-')),root=join(folder,'project');
 const env={QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_SESSION:folder,QWEN_WORKFLOW_PROJECT:root,
  QWEN_WORKFLOW_PLAN:join(folder,'repair.json'),QWEN_WORKFLOW_REPLAN_EVIDENCE:join(folder,'evidence.json'),
  QWEN_WORKFLOW_PLAN_DRAFT:undefined,QWEN_WORKFLOW_PLAN_COVERAGE:undefined,QWEN_WORKFLOW_PREFIXES:'["."]'};
 const previous=Object.fromEntries(Object.keys(env).map(key=>[key,process.env[key]]));
 try{
  for(const [k,v] of Object.entries(env))if(v===undefined)delete process.env[k];else process.env[k]=v;
  const setup=spawnSync(python,['-c',`import json,sys
from pathlib import Path
from test_coverage_plan import draft
from plans import save
from project_map import scan
base=Path(sys.argv[1]);root=base/'project';root.mkdir();path=base/'original.json'
save(root,['.'],draft(),path);plan=json.loads(path.read_text())
packet={'project':str(root.resolve()),'plan':str(path),'current_snapshot':scan(root,['.'])['snapshot'],
'failed_todo':plan['tasks'][0],'remaining':plan['tasks'],'completed':[],'acceptance_fixtures':{},'reason':'test_failed'}
(base/'evidence.json').write_text(json.dumps(packet));print(json.dumps(plan))`,folder],{cwd:home,encoding:'utf8'});
  assert.equal(setup.status,0,setup.stderr);const original=JSON.parse(setup.stdout),tools={};
  const ctx={model:{provider:'local-qwen-workflow'},cwd:folder};
  extension({on:()=>{},registerCommand:()=>{},registerTool:tool=>{tools[tool.name]={...tool,execute:(...args)=>tool.execute(...args,ctx)};},
   exec:async(binary,args)=>{const r=spawnSync(binary,args,{encoding:'utf8'});return {code:r.status,stdout:r.stdout,stderr:r.stderr};}});
  const values={failure_analysis:'Observed assertion evidence; adjust retrieval and rerun the unchanged frozen tests.',
   steps:['Read boundary evidence, including λ','Run acceptance'],context_overlay:{max_input_tokens:24576,window_tokens:65536}};
  values.strategy_review={expectation_checks:[{criterion:original.tasks[0].acceptance[0].id,status:'unknown',
   evidence:'The bounded assertion report lacks setup needed to establish the cause.'}],abandoned_assumptions:[],
   strategy_change:'Observe the declared boundary case before choosing the next edit.',first_check:values.steps[0],
   stop_condition:'Stop if the observation requires a change outside the frozen scope.'};
  const call=parse('plan_store',tools.plan_store.parameters,values);
  assert.deepEqual(call.arguments,values);
  const result=await runToolCall({...call,id:'repair'},{assistantMessage:{role:'assistant',content:[]},context:{messages:[],tools:Object.values(tools)}});
  assert.equal(result.isError,false,JSON.stringify(result));
  const saved=JSON.parse(readFileSync(env.QWEN_WORKFLOW_PLAN,'utf8'));
  assert.deepEqual(saved.tasks[1],original.tasks[1]);assert.deepEqual(saved.tasks[0].steps,values.steps);
  assert.deepEqual(saved.tasks[0].acceptance,original.tasks[0].acceptance);
  assert.deepEqual(saved.tasks[0].tests,original.tasks[0].tests);assert.equal(saved.recovery_patch.todo,'T1');
  assert.equal(saved.failure_analysis,values.failure_analysis);assert.ok(saved.replan_lineage);
 }finally{
  for(const [k,v] of Object.entries(previous))if(v===undefined)delete process.env[k];else process.env[k]=v;
  rmSync(folder,{recursive:true,force:true});
 }
});
