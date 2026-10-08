/** Incomplete addresses yield usable current references, never an unverified read. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {commandFor} from './pi-extension.mjs';
import {navigationReply,sectionLookup} from './pi-map-navigation.mjs';
const home=dirname(fileURLToPath(import.meta.url));

test('missing hashes produce labelled lookup results, multiple choices and independent search paging',()=>{
 const params={action:'architecture-section',query:'src/rules.py',offset:8000};
 const response=JSON.stringify({source_sha256:'hash',matches:[{kind:'file',path:'src/rules.py'},
  {kind:'section',id:'core'},{kind:'section',id:'core/rules'}],more:true,next_offset:10});
 const result=JSON.parse(navigationReply(params,response));
 assert.equal(result.section_read,false);assert.equal(result.action,'architecture-search');
 assert.equal(result.next_calls.length,2);assert.equal(result.next_calls[0].sha256,'hash');
 assert.equal(result.next_calls[0].offset,0);assert.equal(result.next_search.offset,10);
 assert.deepEqual(commandFor(params.action,[],params.query,null,params.offset),['architecture-search','src/rules.py','--offset','0']);
 assert.equal(navigationReply({...params,sha256:'stale'},response),response);
 assert.equal(sectionLookup(params.action,params.query,'stale'),false);
});

test('zero matches remain an honest unresolved lookup without guessed IDs',()=>{
 const result=JSON.parse(navigationReply({action:'architecture-section',query:'missing'},
  JSON.stringify({matches:[],more:false,source_sha256:'hash'})));
 assert.deepEqual(result.next_calls,[]);assert.equal(result.section_read,false);
 assert.equal(result.next_search,undefined);assert.match(result.note,/shorter filename/);
 assert.equal(navigationReply({action:'architecture'},'plain index'),'plain index');
});

test('real filename lookup supplies a usable section call; changed architecture rejects its stale hash',t=>{
 const root=mkdtempSync(join(tmpdir(),'mypi-map-'));t.after(()=>rmSync(root,{recursive:true,force:true}));
 writeFileSync(join(root,'rules.py'),'def move():\n    """Advance one position."""\n    return "PRIVATE_IMPLEMENTATION_SENTINEL"\n');
 const doc=join(root,'architecture.md');writeFileSync(doc,'# Rules\nrules.py owns movement.\n');
 const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>!key.startsWith('QWEN_WORKFLOW_')));
 const invoke=params=>spawnSync(join(home,'.venv/bin/python'),[join(home,'workflow.py'),'--root',root,
  ...commandFor(params.action,[],params.query,null,params.offset||0,0,params.sha256)],{cwd:home,env,encoding:'utf8'});
 const params={action:'architecture-section',query:'rules.py'},lookup=invoke(params);
 assert.equal(lookup.status,0,lookup.stderr);const result=JSON.parse(navigationReply(params,lookup.stdout));
 assert.equal(result.section_read,false);assert.equal(result.next_calls.length,1);
 assert.doesNotMatch(JSON.stringify(result),/PRIVATE_IMPLEMENTATION_SENTINEL/);
 const selected=invoke(result.next_calls[0]);assert.equal(selected.status,0,selected.stderr);
 assert.match(JSON.parse(selected.stdout).text,/owns movement/);
 writeFileSync(doc,readFileSync(doc,'utf8')+'Decision changed.\n');
 const stale=invoke(result.next_calls[0]);assert.notEqual(stale.status,0);assert.match(stale.stderr,/changed/);
});
