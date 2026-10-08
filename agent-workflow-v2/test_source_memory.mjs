/** Source retention is bounded, scoped, current and independent of game contents. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,symlinkSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {rememberSource,recallSource,attachSourceMemory,sourceHandoffLimit} from './pi-source-memory.mjs';
import {compactSummary,installFixedCompactionHooks} from './pi-compaction-fixed.mjs';

function setup(t) {
  const base=mkdtempSync(join(tmpdir(),'pi-source-memory-'));
  const project=join(base,'project'),session=join(base,'session');mkdirSync(project);mkdirSync(session);
  t.after(()=>rmSync(base,{recursive:true,force:true}));
  const source='export function fixture() { return {sample:()=>42}; }\n';
  writeFileSync(join(project,'fixture.mjs'),source);
  const row={path:'fixture.mjs',sha256:createHash('sha256').update(source).digest('hex'),
    symbol:'fixture',next_offset:1,more:false,source:'1: '+source.trim()};
  return {base,project,session,row};
}

test('single and batch observations survive with labels and exact current hashes',t=>{
  const x=setup(t);rememberSource(x.session,x.project,JSON.stringify(x.row));
  rememberSource(x.session,x.project,JSON.stringify({symbols:[x.row],errors:[]}));
  assert.deepEqual(recallSource(x.session,x.project),{entries:[x.row],invalidated:0,omitted:0});
  rememberSource(x.session,x.project,JSON.stringify({...x.row,path:join(x.project,'fixture.mjs')}));
  assert.equal(recallSource(x.session,x.project).entries.length,1);
});

test('subsequent source edits invalidate observations without replaying stale text',t=>{
  const x=setup(t);rememberSource(x.session,x.project,JSON.stringify(x.row));
  writeFileSync(join(x.project,'fixture.mjs'),'changed source');
  assert.deepEqual(recallSource(x.session,x.project),{entries:[],invalidated:1,omitted:0});
});

test('outside files, symlink escapes and arbitrary tool text never enter memory',t=>{
  const x=setup(t);writeFileSync(join(x.base,'outside.mjs'),readFileSync(join(x.project,'fixture.mjs')));
  symlinkSync(join(x.base,'outside.mjs'),join(x.project,'link.mjs'));
  for(const path of ['../outside.mjs',join(x.base,'outside.mjs'),'link.mjs'])
    rememberSource(x.session,x.project,JSON.stringify({...x.row,path}));
  rememberSource(x.session,x.project,'not JSON');
  rememberSource(x.session,x.project,JSON.stringify({content:'PRIVATE_TOOL_TEXT'}));
  assert.deepEqual(recallSource(x.session,x.project).entries,[]);
});

test('recall drops complete over-budget excerpts and keeps smaller recent ones',t=>{
  const x=setup(t);const large={...x.row,symbol:'large',source:'x'.repeat(7000)};
  rememberSource(x.session,x.project,JSON.stringify({symbols:[x.row,large]}));
  const memory=recallSource(x.session,x.project,1000);
  assert.deepEqual(memory.entries,[x.row]);assert.equal(memory.omitted,1);
});

test('journal storage is bounded and repeated observations do not multiply',t=>{
  const x=setup(t);
  for(let i=0;i<20;i++)rememberSource(x.session,x.project,JSON.stringify({...x.row,symbol:'f'+i,source:'x'.repeat(5000)}));
  const text=readFileSync(join(x.session,'retrieved-source-memory.json'),'utf8');
  assert.ok(Buffer.byteLength(text)<=24576);assert.ok(JSON.parse(text).length<=8);
  rememberSource('/missing/source-memory',x.project,JSON.stringify(x.row));
  assert.deepEqual(recallSource('/missing/source-memory',x.project).entries,[]);
});

test('handoff retains the complete frozen contract and fits its original cap',t=>{
  const x=setup(t),task={goal:'Synthetic task',acceptance:[{id:'A',then:'preserve contract'}]};
  const original=compactSummary(task,{passed:false,violations:[]});
  const memory={entries:[x.row],omitted:2,invalidated:1};
  const kept=attachSourceMemory(original,memory);
  const data=JSON.parse(kept.summary.split('\n').slice(1).join('\n'));
  assert.deepEqual(data.task,task);assert.deepEqual(data.retrieved_sources.entries,[x.row]);
  assert.deepEqual(kept.stats,{retained:1,omitted:2,invalidated:1});
  const small=attachSourceMemory(original,memory,original.length+10);
  assert.equal(small.summary,original);assert.equal(small.stats.retained,0);
  const crowded=attachSourceMemory(original,{entries:Array(8).fill({...x.row,source:'x'.repeat(2000)}),omitted:0,invalidated:0});
  assert.ok(crowded.summary.length<=12000);assert.ok(crowded.stats.omitted>0);
  assert.deepEqual(JSON.parse(crowded.summary.split('\n').slice(1).join('\n')).task,task);
});

test('actual compaction hook preserves retrieved interfaces without old conversation turns',async t=>{
  const x=setup(t),old={...process.env},handlers={};
  t.after(()=>{for(const key of Object.keys(process.env))if(!(key in old))delete process.env[key];Object.assign(process.env,old);});
  const state=join(x.session,'state.json');writeFileSync(state,JSON.stringify({before:{root:x.project},task:{id:'T1',goal:'Synthetic task',context:{max_input_tokens:24576}}}));
  Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_SESSION:x.session,QWEN_WORKFLOW_STATE:state});
  rememberSource(x.session,x.project,JSON.stringify(x.row));
  installFixedCompactionHooks({on:(event,fn)=>handlers[event]=fn,
    exec:async(_command,args)=>({code:0,stdout:JSON.stringify(args[0].endsWith('progress_observer.py')?
      {status:'continue'}:{passed:false,violations:[]})})},'python','workflow.py');
  const result=await handlers.session_before_compact({preparation:{tokensBefore:19000}},
    {model:{provider:'local-qwen-workflow'},abort:()=>assert.fail('Unexpected abort')});
  assert.match(result.compaction.summary,/sample/);
  assert.equal(result.compaction.details.sourceMemory.retained,1);
  assert.equal(result.compaction.details.sourceMemory.handoffCharacterLimit,18000);
  assert.equal(result.compaction.details.sourceMemory.byteLimit,6000);
  assert.equal(result.compaction.details.retainedConversationEntries,0);
});

test('verbose contracts retain a bounded whole source excerpt with sufficient input headroom',t=>{
  const x=setup(t),task={goal:'Synthetic task',steps:['instruction '.repeat(730)],
    context:{max_input_tokens:24576},acceptance:[{id:'A',then:'preserve contract'}]};
  const summary=compactSummary(task,{passed:false,violations:[]});
  const row={...x.row,source:'source observation '.repeat(270)};
  const memory={entries:[row],omitted:0,invalidated:0};
  assert.equal(attachSourceMemory(summary,memory).stats.retained,0);
  const extended=attachSourceMemory(summary,memory,sourceHandoffLimit(task));
  assert.equal(extended.stats.retained,1);
  assert.ok(extended.summary.length<=18000);
  const data=JSON.parse(extended.summary.slice(extended.summary.indexOf('\n')+1));
  assert.deepEqual(data.task,task);assert.deepEqual(data.retrieved_sources.entries,[row]);
  for(const cap of [undefined,null,8192,16384,24575,'24576',NaN])
    assert.equal(sourceHandoffLimit({context:{max_input_tokens:cap}}),12000);
  for(const cap of [24576,32768,57344])
    assert.equal(sourceHandoffLimit({context:{max_input_tokens:cap}}),18000);
});
