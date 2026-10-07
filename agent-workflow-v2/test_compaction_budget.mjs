/** Validate mypi thresholds against the installed Pi estimator, not an assumed formula. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {estimateContextTokens,shouldCompact} from '../node_modules/@earendil-works/pi-coding-agent/dist/core/compaction/compaction.js';

const home=dirname(fileURLToPath(import.meta.url));
const python=process.env.PYTHON||join(home,'.venv/bin/python');

function settings(t,cap=24576) {
  const root=mkdtempSync(join(tmpdir(),'mypi-native-usage-'));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  execFileSync(python,['-c','from pathlib import Path;import sys;from launch import configure,tune_context; p=Path(sys.argv[1]);configure(p,"27b",65536);tune_context(p,int(sys.argv[2]),16384)',root,String(cap)],{cwd:home});
  return JSON.parse(readFileSync(join(root,'settings.json'))).compaction;
}

function reply(input,output,cacheRead=0) {
  return {role:'assistant',content:[{type:'text',text:'small visible answer'}],stopReason:'toolUse',
    usage:{input,output,cacheRead,cacheWrite:0,totalTokens:input+output+cacheRead}};
}

test('provider usage includes the envelope even when visible messages are tiny',t=>{
  const config=settings(t);
  const estimate=estimateContextTokens([reply(13000,3379)]);
  assert.equal(estimate.usageTokens,16379);
  assert.equal(estimate.tokens,16379);
  assert.equal(estimate.trailingTokens,0);
  // Recorded pilot compaction size: an extra envelope reserve forced this compaction.
  assert.equal(shouldCompact(estimate.tokens,65536,{...config,reserveTokens:50176}),true);
  assert.equal(shouldCompact(estimate.tokens,65536,config),false);
});

test('cached input and trailing tool results still count toward compaction',t=>{
  const config=settings(t);
  const estimate=estimateContextTokens([reply(3000,1000,15000),
    {role:'toolResult',toolCallId:'x',toolName:'source_query',content:[{type:'text',text:'x'.repeat(4000)}],isError:false,timestamp:1}]);
  assert.equal(estimate.usageTokens,19000);
  assert.ok(estimate.trailingTokens>456);
  assert.equal(shouldCompact(estimate.tokens,65536,config),true);
});

test('the recorded oversized Linux payload still crosses the corrected trigger',t=>{
  const config=settings(t,32768);
  assert.equal(shouldCompact(estimateContextTokens([reply(26513,0)]).tokens,65536,config),true);
});

test('recorded short tool burst compacts before the full-payload guard',t=>{
  const config=settings(t);
  // Pilot: native usage 18522, SDK trailing estimate 644; final serialized
  // payload was 19917 after tokenization and request-local progress feedback.
  const estimate=estimateContextTokens([reply(596,45,17881),
    {role:'toolResult',toolCallId:'x',toolName:'source_query',content:[{type:'text',text:'x'.repeat(2576)}],isError:false,timestamp:1}]);
  assert.equal(estimate.tokens,19166);
  assert.equal(shouldCompact(estimate.tokens,65536,{...config,reserveTokens:46080}),false);
  assert.equal(shouldCompact(estimate.tokens,65536,config),true);
  // The earlier excessive 16k compaction remains avoided.
  assert.equal(shouldCompact(16379,65536,config),false);
});

test('the full serialized admission check still rejects oversized requests',()=>{
  const script='from unittest.mock import Mock,patch;from pathlib import Path;import tempfile,json;from token_budget import count_request;'+
    '\nwith tempfile.TemporaryDirectory() as tmp:\n p=Path(tmp)/"payload.json";p.write_text("{}")\n tok=Mock();tok.encode.return_value.ids=list(range(21000))\n with patch("token_budget.Tokenizer.from_file",return_value=tok): print(json.dumps(count_request(p,24576,Path("unused"))))';
  const result=JSON.parse(execFileSync(python,['-c',script],{cwd:home,encoding:'utf8'}));
  assert.equal(result.passed,false);assert.equal(result.admission_tokens,26506);
});
