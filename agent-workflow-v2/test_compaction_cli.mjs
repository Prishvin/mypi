/** Exercise automatic compaction in the bundled CLI with a loopback fake provider. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {prepareCompaction,estimateProjectedContextTokens} from '../node_modules/@earendil-works/pi-coding-agent/dist/core/compaction/compaction.js';
import {SessionManager} from '../node_modules/@earendil-works/pi-coding-agent/dist/core/session-manager.js';

const home=dirname(fileURLToPath(import.meta.url));
const python=process.env.PYTHON || join(home,'.venv/bin/python');

test('a short first tool turn previously prevented the coding handoff',()=>{
  const manager=SessionManager.inMemory(home);
  manager.appendMessage({role:'user',content:'task '.repeat(4000),timestamp:1});
  manager.appendMessage({role:'assistant',content:[{type:'toolCall',id:'call1',name:'probe',arguments:{}}],
    api:'openai-completions',provider:'local-qwen-workflow',model:'fixture',stopReason:'toolUse',timestamp:2,
    usage:{input:12999,output:1704,cacheRead:0,cacheWrite:0,totalTokens:14703,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}});
  manager.appendMessage({role:'toolResult',toolCallId:'call1',toolName:'probe',content:[{type:'text',text:'x'.repeat(4000)}],isError:false,timestamp:3});
  const entries=manager.getBranch(),projection=manager.buildSessionProjection();
  assert.ok(estimateProjectedContextTokens(projection,entries).tokens>11878);
  const settings={enabled:true,reserveTokens:20890,keepRecentTokens:4000};
  assert.equal(prepareCompaction(entries,settings),undefined);
  assert.ok(prepareCompaction(entries,{...settings,keepRecentTokens:0}));
});

test('bundled CLI compacts consecutive tool turns without summary calls or extra turns', {timeout:30000},async t=>{
  const root=mkdtempSync(join(tmpdir(),'mypi-cli-compaction-'));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  const config=join(root,'config'),project=join(root,'project');mkdirSync(project);
  execFileSync(python,['-c','from pathlib import Path;import sys;from launch import configure,tune_context;p=Path(sys.argv[1]);configure(p,"27b",32768);tune_context(p,16384,8192,complete_handoff=True)',config],{cwd:home});
  const requests=[];
  const server=createServer(async(req,res)=>{
    let body='';for await(const chunk of req)body+=chunk;
    requests.push(JSON.parse(body));
    const first=requests.length<=2;
    res.writeHead(200,{'Content-Type':'text/event-stream'});
    const emit=(choices,usage)=>res.write('data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',created:1,model:'fixture',choices,...(usage?{usage}:{})})+'\n\n');
    emit([{index:0,delta:first?{role:'assistant',tool_calls:[{index:0,id:'probe1',type:'function',function:{name:'probe',arguments:'{}'}}]}:{role:'assistant',content:'Finished synthetic check.'},finish_reason:null}]);
    emit([{index:0,delta:{},finish_reason:first?'tool_calls':'stop'}]);
    emit([],{prompt_tokens:first?12999:100,completion_tokens:first?1704:10,total_tokens:first?14703:110});
    res.end('data: [DONE]\n\n');
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  t.after(()=>server.close());
  const models=JSON.parse(readFileSync(join(config,'models.json')));
  models.providers['local-qwen-workflow'].baseUrl=`http://127.0.0.1:${server.address().port}/v1`;
  models.providers['local-qwen-workflow'].models[0].reasoning=false;
  writeFileSync(join(config,'models.json'),JSON.stringify(models));
  const extension=join(root,'probe.mjs');
  writeFileSync(extension,`import {installCompactionBoundary} from ${JSON.stringify(join(home,'pi-compaction-fixed.mjs'))};
  export default function(pi){
    installCompactionBoundary(pi);
    pi.registerTool({name:'probe',label:'Probe',description:'Synthetic result',parameters:{type:'object',properties:{}},
      async execute(){return {content:[{type:'text',text:'OLD_TOOL_RESULT '+ 'x'.repeat(4000)}],details:{}};}});
    pi.on('session_before_compact',async(e)=>({compaction:{summary:'COMPLETE_SYNTHETIC_HANDOFF',tokensBefore:e.preparation.tokensBefore,details:{modelCall:false,fullContractPreserved:true,retainedConversationEntries:0}}}));
  }`);
  const env={...process.env,PI_CODING_AGENT_DIR:config};
  for(const key of Object.keys(env))if(key.startsWith('QWEN_WORKFLOW_'))delete env[key];
  env.QWEN_WORKFLOW_ROLE='code';
  const child=spawn(process.execPath,[join(home,'../node_modules/.bin/pi'),'--provider','local-qwen-workflow','--model','qwen27b-q8','--thinking','off','--tools','probe','--no-extensions','--no-skills','--no-prompt-templates','--extension',extension,'--session-dir',join(root,'sessions'),'--offline','--mode','json','-p','SYNTHETIC_INITIAL_TASK '.repeat(900)],{cwd:project,env,stdio:['ignore','pipe','pipe']});
  t.after(()=>{if(child.exitCode===null)child.kill('SIGTERM');});
  let output='',errors='';child.stdout.on('data',x=>output+=x);child.stderr.on('data',x=>errors+=x);
  const [code]=await once(child,'exit');
  assert.equal(code,0,errors+'\n'+output.slice(-3000));
  assert.equal(requests.length,3,'Compaction must not request an LLM summary or an extra turn: '+errors);
  assert.match(JSON.stringify(requests[0].messages),/SYNTHETIC_INITIAL_TASK/);
  assert.match(JSON.stringify(requests[1].messages),/COMPLETE_SYNTHETIC_HANDOFF/);
  assert.doesNotMatch(JSON.stringify(requests[1].messages),/SYNTHETIC_INITIAL_TASK|OLD_TOOL_RESULT/);
  assert.match(JSON.stringify(requests[2].messages),/COMPLETE_SYNTHETIC_HANDOFF/);
  assert.doesNotMatch(JSON.stringify(requests[2].messages),/SYNTHETIC_INITIAL_TASK|OLD_TOOL_RESULT/);
  const events=output.split('\n').filter(x=>x.startsWith('{')).map(JSON.parse);
  assert.equal(events.filter(e=>e.type==='compaction_end' && e.result).length,2);
});
