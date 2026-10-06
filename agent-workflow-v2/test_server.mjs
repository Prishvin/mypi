/** Prove live /server selection refreshes Pi and refuses frozen-worker changes. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, writeFileSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {registerServer} from './pi-server.mjs';

test('/server updates the actual model after validation and keeps scopes private', async () => {
  const old={...process.env}; const folder=mkdtempSync(join(tmpdir(),'mypi-server-'));
  try {
    Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'architect',PI_CODING_AGENT_DIR:folder,QWEN_WORKFLOW_TOOLKIT:'/client/tools',QWEN_WORKFLOW_INPUT_BUDGET:'24576',QWEN_WORKFLOW_OUTPUT_BUDGET:'8192'});
    delete process.env.QWEN_WORKFLOW_STATE;
    writeFileSync(join(folder,'models.json'),JSON.stringify({providers:{'local-qwen-workflow':{baseUrl:'http://localhost:8000/v1',models:[{id:'mtplx-quality',contextWindow:98304}]}}}));
    let command, refreshed=0, switched;const calls=[];
    registerServer({registerCommand:(name,value)=>{assert.equal(name,'server');command=value;},
      exec:async(bin,args)=>{calls.push(args);return {code:0,stdout:JSON.stringify({url:'http://192.168.1.34:8000',model:'mtplx-quality',context_window:98304})};},
      setModel:async(model)=>{switched=model;return true;}},'python');
    const ctx={model:{provider:'local-qwen-workflow'},waitForIdle:async()=>{},ui:{notify:()=>{}},modelRegistry:{refresh:async()=>{refreshed++;},find:(provider,id)=>({provider,id,baseUrl:'http://192.168.1.34:8000/v1'})}};
    await command.handler('192.168.1.34:8000',ctx);
    assert.equal(refreshed,1);assert.equal(switched.baseUrl,'http://192.168.1.34:8000/v1');
    assert.equal(process.env.MYPI_SERVER_URL,'http://192.168.1.34:8000');
    assert.deepEqual(calls[0],['/client/tools/server_config.py','192.168.1.34:8000','--minimum-context','40960']);
    const provider=JSON.parse(readFileSync(join(folder,'models.json'))).providers['local-qwen-workflow'];
    assert.equal(provider.baseUrl,switched.baseUrl);
    process.env.QWEN_WORKFLOW_STATE='/client/frozen.json';
    await command.handler('other:8000',ctx);assert.equal(calls.length,1);
    await assert.rejects(command.handler('other:8000',{...ctx,model:{provider:'unrelated'}}),/mypi workflow/);
  } finally {
    for(const key of Object.keys(process.env))if(!(key in old))delete process.env[key];Object.assign(process.env,old);
    rmSync(folder,{recursive:true,force:true});
  }
});
