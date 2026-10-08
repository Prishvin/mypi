/** Exercise the real tokenizer subprocess at Pi's deterministic compaction hook. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {compactSummary,installFixedCompactionHooks} from './pi-compaction-fixed.mjs';
import {rememberSource,recallSource} from './pi-source-memory.mjs';

test('long valid handoff uses actual request envelope without model summaries or contract loss',async t=>{
  const folder=mkdtempSync(join(tmpdir(),'mypi-budget-handoff-')),old={...process.env};
  t.after(()=>{rmSync(folder,{recursive:true,force:true});for(const k of Object.keys(process.env))if(!(k in old))delete process.env[k];Object.assign(process.env,old);});
  const task={id:'T1',goal:'A synthetic bounded task',steps:Array.from({length:1500},(_,i)=>'instruction '+i),
    acceptance:[{id:'A',then:'Preserve all criteria'}],tests:[['node','--test']],context:{max_input_tokens:40960}};
  const gate={passed:false,violations:['Tests pending']};
  assert.throws(()=>compactSummary(task,gate),/smaller task/);
  writeFileSync(join(folder,'state.json'),JSON.stringify({task,before:{root:folder}}));
  writeFileSync(join(folder,'request-budget.json'),JSON.stringify({messages:[{role:'system',content:'Required instructions'},
    {role:'user',content:'Discarded previous conversation'}],tools:[{name:'fixture'}]}));
  for(let i=0;i<3;i++){
    const source='// '+('current observation '+i+' ').repeat(180),path='fixture'+i+'.mjs';
    writeFileSync(join(folder,path),source);
    rememberSource(folder,folder,JSON.stringify({path,source,
      sha256:createHash('sha256').update(source).digest('hex')}));
  }
  assert.equal(recallSource(folder,folder).entries.length,1);
  Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_SESSION:folder,
    QWEN_WORKFLOW_STATE:join(folder,'state.json'),QWEN_WORKFLOW_INPUT_BUDGET:'40960'});
  const handlers={},calls=[];
  const python=fileURLToPath(new URL('./.venv/bin/python',import.meta.url));
  const cli=fileURLToPath(new URL('./workflow.py',import.meta.url));
  installFixedCompactionHooks({on:(name,fn)=>handlers[name]=fn,exec:async(binary,args)=>{
    calls.push(args[0]);
    if(args[0].endsWith('progress_observer.py'))return {code:0,stdout:'{"status":"continue"}'};
    if(args[0].endsWith('workflow.py'))return {code:1,stdout:JSON.stringify(gate)};
    const result=spawnSync(binary,args,{encoding:'utf8',timeout:30000});
    return {code:result.status,stdout:result.stdout,stderr:result.stderr};
  }},python,cli);
  const result=await handlers.session_before_compact({preparation:{tokensBefore:34000}},
    {model:{provider:'local-qwen-workflow'},abort:()=>assert.fail('Unexpected abort')});
  assert.ok(result.compaction.summary.length>12000);
  assert.deepEqual(JSON.parse(result.compaction.summary.split('\n').slice(1).join('\n')).task,task);
  assert.equal(result.compaction.details.tokenBudget.passed,true);
  assert.equal(result.compaction.details.modelCall,false);
  assert.equal(result.compaction.details.retainedConversationEntries,0);
  assert.equal(result.compaction.details.sourceMemory.retained,3);
  assert.equal(result.compaction.details.sourceMemory.omitted,0);
  assert.equal(result.compaction.details.sourceMemory.byteLimit,16000);
  assert.equal(calls.filter(name=>name.endsWith('compaction_budget.py')).length,1);
  assert.equal(JSON.parse(readFileSync(join(folder,'compaction-budget-result.json'),'utf8')).input_limit,40960);
});
