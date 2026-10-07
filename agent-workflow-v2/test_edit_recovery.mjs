import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync,existsSync,statSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {failedEditEvidence} from './pi-edit-recovery.mjs';
import {installRefreshHooks} from './pi-hooks.mjs';
import {createEditToolDefinition} from '../node_modules/@earendil-works/pi-coding-agent/dist/core/tools/edit.js';

const home=dirname(fileURLToPath(import.meta.url));
const python=join(home,'.venv/bin/python');
const cli=join(home,'workflow.py');
const source='test("ordinary callback", () => {\n  const sample = 42;\n  assert.equal(sample, 42);\n});\n';

function fixture(t) {
  const root=mkdtempSync(join(tmpdir(),'mypi-edit-test-')),previous={...process.env};
  Object.assign(process.env,{QWEN_WORKFLOW_STATE:join(root,'state.json'),QWEN_WORKFLOW_PROJECT:root,
    QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_SHADOW:join(root,'shadow'),QWEN_WORKFLOW_STOP_AFTER_PASS:'0'});
  writeFileSync(process.env.QWEN_WORKFLOW_STATE,JSON.stringify({before:{root},task:{files:['checks.mjs']}}));
  writeFileSync(join(root,'checks.mjs'),source);
  t.after(()=>{for(const key of Object.keys(process.env))if(!(key in previous))delete process.env[key];
    Object.assign(process.env,previous);rmSync(root,{recursive:true,force:true});});
  return {root,ctx:{cwd:root,model:{provider:'local-qwen-workflow'}},
    event:{isError:true,toolName:'edit',input:{path:'checks.mjs',edits:[{oldText:source.replace('= 42','= 41'),newText:''}]}}};
}

function nativeExec(_python,args) {
  const result=spawnSync(python,args,{encoding:'utf8',timeout:30000});
  if(result.error)throw result.error;
  return {code:result.status,stdout:result.stdout,stderr:result.stderr};
}

test('failed callback gets exact text through Python; source payload stays off argv and temp file is removed',async t=>{
  const {root,ctx,event}=fixture(t);let input;
  const pi={exec:async(bin,args)=>{
    input=args.at(-1);
    assert.equal(statSync(input).mode&0o777,0o600);
    assert.equal(args.includes(event.input.edits[0].oldText),false);
    assert.deepEqual(Object.keys(JSON.parse(readFileSync(input))),['path','old_texts']);
    return nativeExec(bin,args);
  }};
  const text=await failedEditEvidence(pi,event,ctx,python,cli);
  assert.match(text,/CURRENT SOURCE EVIDENCE/);assert.match(text,/not approved edit boundaries/);
  assert.ok(text.includes(JSON.stringify(source)));
  assert.equal(readFileSync(join(root,'checks.mjs'),'utf8'),source);
  assert.equal(existsSync(dirname(input)),false);
});

test('legacy top-level oldText also receives evidence',async t=>{
  const {ctx,event}=fixture(t);
  event.input={path:'checks.mjs',...event.input.edits[0]};
  assert.match(await failedEditEvidence({exec:nativeExec},event,ctx,python,cli),/CURRENT SOURCE EVIDENCE/);
});

test('unscoped failed edit cannot disclose source even when tool execution was blocked',async t=>{
  const {root,ctx,event}=fixture(t);
  writeFileSync(join(root,'private.mjs'),'private marker\n'+source);
  event.input.path='private.mjs';
  const text=await failedEditEvidence({exec:nativeExec},event,ctx,python,cli);
  assert.match(text,/within the frozen scope/);assert.doesNotMatch(text,/private marker|sample = 42/);
});

test('success, other tools and malformed input do not launch evidence reads',async t=>{
  const {ctx,event}=fixture(t);let calls=0;
  const pi={exec:()=>{calls++;throw Error('unexpected');}};
  assert.equal(await failedEditEvidence(pi,{...event,isError:false},ctx,python,cli),'');
  assert.equal(await failedEditEvidence(pi,{...event,toolName:'write'},ctx,python,cli),'');
  for(const edits of [[],[{}],null,'wrong',Array(9).fill({oldText:'x'}),[{oldText:'x'.repeat(65537)}]]) {
    await failedEditEvidence(pi,{...event,input:{path:'checks.mjs',edits}},ctx,python,cli);
  }
  delete process.env.QWEN_WORKFLOW_STATE;
  await failedEditEvidence(pi,event,ctx,python,cli);
  assert.equal(calls,0);
});

test('subprocess and malformed output failures preserve original error and clean temporary data',async t=>{
  const {ctx,event}=fixture(t);
  for(const output of ['{','x'.repeat(12002),'{}',null]) {
    let input;
    const text=await failedEditEvidence({exec:async(_bin,args)=>{
      input=args.at(-1);if(output===null)throw Error('subprocess failure');
      return {code:0,stdout:output};
    }},event,ctx,python,cli);
    assert.match(text,/original edit error is unchanged/);
    assert.equal(existsSync(dirname(input)),false);
  }
});

test('real Pi edit rejects a guessed callback; refresh attaches evidence and exact fixture retry succeeds',async t=>{
  const {root,ctx,event}=fixture(t),tool=createEditToolDefinition(root);
  await assert.rejects(tool.execute('initial',event.input,undefined,undefined,ctx),/Could not find/);
  assert.equal(readFileSync(join(root,'checks.mjs'),'utf8'),source);
  const handlers={},mutations=new Map([[join(root,'checks.mjs'),'initial']]);let refreshes=0;
  const pi={on:(name,fn)=>{handlers[name]=fn;},exec:async(bin,args)=>{
    if(args[0]===cli){refreshes++;return {code:0,stdout:'{"snapshot":"fixture","architecture_sha256":"revision"}'};}
    return nativeExec(bin,args);
  }};
  installRefreshHooks(pi,python,cli,()=>[],mutations);
  const result=await handlers.tool_result({...event,toolCallId:'initial',content:[{type:'text',text:'Exact edit rejected'}]},ctx);
  assert.equal(result.content[0].text,'Exact edit rejected');
  assert.match(result.content[1].text,/CURRENT SOURCE EVIDENCE/);
  assert.match(result.content[1].text,/expected_sha256="revision"/);
  assert.equal(refreshes,1);assert.equal(mutations.size,0);
  const jsonLine=result.content[1].text.split('\n').find(line=>line.startsWith('{"path":'));
  const evidence=JSON.parse(jsonLine);
  await tool.execute('retry',{path:'checks.mjs',edits:[{oldText:evidence.excerpts[0].source,
    newText:source.replace('42','43')}]},undefined,undefined,ctx);
  assert.equal(readFileSync(join(root,'checks.mjs'),'utf8'),source.replace('42','43'));
});

test('diagnostic subprocess failure is not mislabeled as a shadow refresh failure',async t=>{
  const {ctx,event}=fixture(t),handlers={};
  const pi={on:(name,fn)=>{handlers[name]=fn;},exec:async(_bin,args)=>{
    if(args[0]===cli)return {code:0,stdout:'{"snapshot":"fresh"}'};
    throw Error('diagnostic crashed');
  }};
  installRefreshHooks(pi,python,cli,()=>[]);
  const result=await handlers.tool_result({...event,content:[{type:'text',text:'Original mismatch'}]},ctx);
  assert.match(result.content[1].text,/Shadow refreshed: fresh/);
  assert.doesNotMatch(result.content[1].text,/Shadow refresh failed/);
});
