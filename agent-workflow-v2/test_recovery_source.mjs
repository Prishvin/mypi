/** A bound recovery may observe selected source; ordinary architects cannot. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import extension from './pi-extension.mjs';

test('real source tool is active only for bound recovery and Python enforces its scope',async t=>{
  const base=realpathSync(mkdtempSync(join(tmpdir(),'mypi-recovery-source-')));
  const root=join(base,'project'),session=join(base,'session');mkdirSync(root);mkdirSync(session);
  writeFileSync(join(root,'fixture.py'),'def sample():\n    return 42\n');
  writeFileSync(join(root,'unrelated.py'),'SECRET = 99\n');
  const keys=['QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_SESSION','QWEN_WORKFLOW_PROJECT','QWEN_WORKFLOW_REPLAN_EVIDENCE'];
  const old=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  t.after(()=>{for(const k of keys)if(old[k]===undefined)delete process.env[k];else process.env[k]=old[k];rmSync(base,{recursive:true,force:true});});
  const evidence=join(session,'replan-evidence.json');
  Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_PROJECT:root,QWEN_WORKFLOW_SESSION:session});
  delete process.env.QWEN_WORKFLOW_REPLAN_EVIDENCE;
  const handlers={},tools={};let active=[];
  extension({on:(n,h)=>{(handlers[n]??=[]).push(h);},registerTool:tool=>{tools[tool.name]=tool;},registerCommand(){},
    setActiveTools:names=>{active=names;},exec:async(binary,args)=>{
      const result=spawnSync(binary,args,{encoding:'utf8'});return {code:result.status,stdout:result.stdout,stderr:result.stderr};
    }});
  const ctx={model:{provider:'local-qwen-workflow'},cwd:root,abort(){}};
  const start=async()=>{for(const h of handlers.session_start)await h({},ctx);};
  const guarded=async event=>{for(const h of handlers.tool_call){const result=await h(event,ctx);if(result?.block)return result;}};
  const call=path=>tools.source_query.execute('',{action:'symbol',paths:[path],query:'sample'},null,null,ctx);
  await start();assert.ok(!active.includes('source_query'));
  assert.equal((await guarded({toolName:'source_query',input:{}})).block,true);
  await assert.rejects(call('fixture.py'),/bound failure recovery/);
  const workflow=fileURLToPath(new URL('.',import.meta.url));
  const snapshot=spawnSync(join(workflow,'.venv/bin/python'),['-c','from project_map import scan; import sys; print(scan(__import__("pathlib").Path(sys.argv[1]),["."])["snapshot"])',root],{encoding:'utf8',cwd:workflow});
  assert.equal(snapshot.status,0,snapshot.error?.message||snapshot.stderr||'Snapshot command did not exit successfully');
  writeFileSync(evidence,JSON.stringify({project:root,current_snapshot:snapshot.stdout.trim(),failed_todo:{files:['fixture.py'],context:{interfaces:[]}}}));
  writeFileSync(join(session,'launch.json'),JSON.stringify({project:root,session,role:'architect',replan_evidence:evidence}));
  process.env.QWEN_WORKFLOW_REPLAN_EVIDENCE=evidence;
  await start();assert.ok(active.includes('source_query'));assert.ok(!active.includes('edit'));
  assert.equal(await guarded({toolName:'source_query',input:{action:'symbol',paths:['fixture.py'],query:'sample'}}),undefined);
  for(const toolName of ['edit','write','bash','workflow_test'])assert.equal((await guarded({toolName,input:{path:'fixture.py'}})).block,true);
  const result=JSON.parse((await call('fixture.py')).content[0].text);
  assert.equal(result.readonly,true);assert.match(result.source,/return 42/);
  await assert.rejects(call('unrelated.py'),/declared task/);
  assert.equal(readFileSync(join(root,'fixture.py'),'utf8'),'def sample():\n    return 42\n');
  assert.equal(JSON.parse(readFileSync(join(session,'recovery-source-reads.json'),'utf8')).calls.length,1);
});
