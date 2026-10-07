/** Read a recorded diagnostic through the real Pi tool and Python boundary. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import extension from './pi-extension.mjs';

test('source_query file reads only this task recorded test log outside the project',async()=>{
  const root=mkdtempSync(join(tmpdir(),'mypi-log-project-'));
  const session=mkdtempSync(join(tmpdir(),'mypi-log-session-'));
  const keys=['QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_PROJECT','QWEN_WORKFLOW_SESSION','QWEN_WORKFLOW_STATE'];
  const old=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  try {
    const state=join(session,'task-state.json'),log=join(session,'task-state-test-0.log');
    writeFileSync(log,'DIAGNOSTIC result=7\n'+Array(145).fill('test output').join('\n'));
    writeFileSync(state,JSON.stringify({before:{root},evidence:{results:[{log}]}}));
    writeFileSync(join(session,'private.txt'),'UNRELATED_PRIVATE');
    Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_PROJECT:root,
      QWEN_WORKFLOW_SESSION:session,QWEN_WORKFLOW_STATE:state});
    const registered={};extension({on:()=>{},registerCommand:()=>{},registerTool:t=>{registered[t.name]=t;},
      exec:async(binary,args)=>{const p=spawnSync(binary,args,{encoding:'utf8'});
        return {code:p.status,stdout:p.stdout,stderr:p.stderr};}});
    const ctx={model:{provider:'local-qwen-workflow'},cwd:root};
    const call=(path,offset=0)=>registered.source_query.execute('',{action:'file',paths:[path],offset},null,null,ctx);
    const page=JSON.parse((await call(log)).content[0].text);
    assert.equal(page.mode,'test-log');assert.equal(page.readonly,true);
    assert.match(page.source,/DIAGNOSTIC result=7/);assert.equal(page.more,true);
    assert.equal(JSON.parse((await call(log,page.next_offset)).content[0].text).more,false);
    await assert.rejects(call(join(session,'private.txt')),error=>
      /Not a project file/.test(error.message)&&!error.message.includes('UNRELATED_PRIVATE'));
  }finally{
    for(const k of keys)if(old[k]===undefined)delete process.env[k];else process.env[k]=old[k];
    rmSync(root,{recursive:true,force:true});rmSync(session,{recursive:true,force:true});
  }
});
