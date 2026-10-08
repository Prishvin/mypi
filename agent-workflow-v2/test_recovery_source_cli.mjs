/** Verify the real launcher exposes and executes recovery reads at the provider boundary. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';

const home=dirname(fileURLToPath(import.meta.url));
for(const compact of [false,true])test(`prepared recovery retrieves source${compact?' and compacts without a summary request':''}`, {timeout:30000},async t=>{
  const base=realpathSync(mkdtempSync(join(tmpdir(),'mypi-recovery-cli-'))),project=join(base,'project');mkdirSync(project);
  t.after(()=>rmSync(base,{recursive:true,force:true}));
  writeFileSync(join(project,'fixture.py'),'def sample():\n    """Synthetic source evidence."""\n    return 42\n');
  const env={...process.env};for(const key of Object.keys(env))if(key.startsWith('QWEN_WORKFLOW_'))delete env[key];
  const helper=`from pathlib import Path
import sys,json
from unittest.mock import patch
from test_profiles import options
from test_plan_runner import todo
import launch
from project_map import scan
base=Path(sys.argv[1]);root=base/'project'
task=todo(filename='fixture.py')
plan=base/'original.json';plan.write_text(json.dumps({'project':str(root),'tasks':[task]}))
packet=base/'failure.json';packet.write_text(json.dumps({'project':str(root),'plan':str(plan),
 'current_snapshot':scan(root,['.'])['snapshot'],'failed_todo':task,'remaining':[task],
 'completed':[],'metrics':{},'reason':'acceptance_failed','failed_tests':[]}))
p=launch.prepare(options(profile='local-27b',project=root,role='architect',replan_evidence=packet,
 prompt='Synthetic recovery observation only.',batch=True,thinking='off',output_tokens=8192,input_tokens=57344))
with patch('launch.check_server'):
 e=launch.environment(p)
e={k:v for k,v in e.items() if k.startswith('QWEN_WORKFLOW_') or k=='PI_CODING_AGENT_DIR'}
(base/'prepared.json').write_text(json.dumps({'prepared':p,'env':e}))
`;
  execFileSync(join(home,'.venv/bin/python'),['-c',helper,base],{cwd:home,env});
  const {prepared,env:controls}=JSON.parse(readFileSync(join(base,'prepared.json')));
  t.after(()=>rmSync(prepared.session,{recursive:true,force:true}));
  const requests=[];
  const server=createServer(async(req,res)=>{
    let body='';for await(const chunk of req)body+=chunk;
    requests.push(JSON.parse(body));const first=requests.length===1;
    res.writeHead(200,{'Content-Type':'text/event-stream'});
    const emit=(choices,usage)=>res.write('data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',created:1,model:'fixture',choices,...(usage?{usage}:{})})+'\n\n');
    emit([{index:0,delta:first?{role:'assistant',tool_calls:[{index:0,id:'read1',type:'function',function:{name:'source_query',arguments:JSON.stringify({action:'symbol',paths:['fixture.py'],query:'sample'})}}]}:{role:'assistant',content:'Observation collected.'},finish_reason:null}]);
    emit([{index:0,delta:{},finish_reason:first?'tool_calls':'stop'}]);
    const promptTokens=compact&&first?48000:1000;
    emit([],{prompt_tokens:promptTokens,completion_tokens:50,total_tokens:promptTokens+50});res.end('data: [DONE]\n\n');
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');t.after(()=>server.close());
  const config=join(prepared.session,'pi-config/models.json'),models=JSON.parse(readFileSync(config));
  models.providers['local-qwen-workflow'].baseUrl=`http://127.0.0.1:${server.address().port}/v1`;
  writeFileSync(config,JSON.stringify(models));
  const child=spawn(prepared.command[0],prepared.command.slice(1),{cwd:project,env:{...env,...controls},stdio:['ignore','pipe','pipe']});
  t.after(()=>{if(child.exitCode===null)child.kill('SIGTERM');});
  let output='',errors='';child.stdout.on('data',x=>output+=x);child.stderr.on('data',x=>errors+=x);
  const [code]=await once(child,'exit');assert.equal(code,0,errors+'\n'+output.slice(-3000));
  assert.equal(requests.length,2,errors+'\n'+output.slice(-3000));
  const names=requests[0].tools.map(x=>x.function.name);
  assert.ok(names.includes('source_query'),JSON.stringify(names));
  const sourceSchema=requests[0].tools.find(x=>x.function.name==='source_query').function.parameters;
  assert.ok(sourceSchema.properties.paths.items.enum.includes('fixture.py'));
  assert.ok(!sourceSchema.properties.paths.items.enum.includes('unrelated.py'));
  assert.ok(!JSON.stringify(sourceSchema.properties.action).includes('fixture'));
  for(const name of ['edit','write','bash','workflow_test'])assert.ok(!names.includes(name));
  const text=JSON.stringify(requests[1].messages);
  assert.match(text,/return 42/);
  if(compact){
    assert.match(text,/FAILURE RECOVERY HANDOFF/);
    assert.match(text,/Immutable|slugify/);
    const receipt=JSON.parse(readFileSync(join(prepared.session,'compaction-latest.json')));
    assert.equal(receipt.details.modelCall,false);
    assert.equal(receipt.details.fullContractPreserved,true);
    assert.equal(receipt.details.sourceMemory.retained,1);
    assert.equal(receipt.details.tokenBudget.passed,true);
    assert.ok(!requests[1].messages.some(m=>m.role==='tool'));
  }else assert.match(text,/readonly/);
  const audit=JSON.parse(readFileSync(join(prepared.session,'recovery-source-reads.json')));
  assert.equal(audit.calls.length,1);assert.deepEqual(audit.calls[0].paths,['fixture.py']);
  const memory=JSON.parse(readFileSync(join(prepared.session,'retrieved-source-memory.json')));
  assert.equal(memory.length,1);assert.match(memory[0].source,/return 42/);
  const settings=JSON.parse(readFileSync(join(prepared.session,'pi-config/settings.json')));
  assert.equal(settings.compaction.keepRecentTokens,0);
  assert.equal(readFileSync(join(project,'fixture.py'),'utf8'),'def sample():\n    """Synthetic source evidence."""\n    return 42\n');
});
