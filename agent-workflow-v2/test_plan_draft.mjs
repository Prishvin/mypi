/** The repair schema is sparse, while new full plans require explicit line estimates. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {validateToolArguments} from '@earendil-works/pi-ai';
import extension from './pi-extension.mjs';
import {repairParameters} from './pi-plan-draft.mjs';
import {coverageParameters} from './pi-coverage-plan.mjs';

test('coverage review schema exposes checks and gaps instead of task mutation',()=>{
  const schema=coverageParameters();
  assert.deepEqual(schema.required,['coverage_plan']);
  assert.deepEqual(schema.properties.coverage_plan.required,['strategy','checks','requirements','gaps']);
  assert.equal(schema.properties.tasks,undefined);
  const old=process.env.QWEN_WORKFLOW_PLAN_COVERAGE;
  try {
    process.env.QWEN_WORKFLOW_PLAN_COVERAGE='1';
    const tools={};extension({registerTool:t=>{tools[t.name]=t;},on:()=>{},registerCommand:()=>{},registerProvider:()=>{}});
    assert.deepEqual(tools.plan_store.parameters.required,['coverage_plan']);
  }finally{if(old===undefined)delete process.env.QWEN_WORKFLOW_PLAN_COVERAGE;else process.env.QWEN_WORKFLOW_PLAN_COVERAGE=old;}
});

test('repair schema omits full-plan resend and exposes explicit corrections',()=>{
  const schema=repairParameters();
  assert.deepEqual(schema.required,['task_updates']);
  assert.equal(schema.properties.tasks,undefined);
  assert.ok(schema.properties.task_updates.items.properties.criterion_replacements);
  assert.equal(schema.properties.task_updates.items.properties.estimated_changed_lines.maximum,300);
  assert.equal(schema.properties.task_updates.type,'array');
});

test('full plan schema requires estimated_changed_lines; pinned draft selects sparse schema',()=>{
  const old=process.env.QWEN_WORKFLOW_PLAN_DRAFT;
  const folder=mkdtempSync(join(tmpdir(),'bound-refinement-'));
  try{
    delete process.env.QWEN_WORKFLOW_PLAN_DRAFT;
    const tools={};const pi={registerTool:t=>{tools[t.name]=t;},on:()=>{},registerCommand:()=>{},registerProvider:()=>{}};
    extension(pi);
    assert.ok(tools.plan_store.parameters.properties.tasks.anyOf[0].items.required.includes('estimated_changed_lines'));
    process.env.QWEN_WORKFLOW_PLAN_DRAFT=join(folder,'plan-draft.json');
    writeFileSync(process.env.QWEN_WORKFLOW_PLAN_DRAFT,JSON.stringify({refine_task:'T08-enemies'}));
    extension(pi);
    assert.equal(tools.plan_store.parameters.properties.task_updates,undefined);
    assert.equal(tools.plan_store.parameters.properties.context_overlay.type,'object');
    assert.ok(tools.plan_child_store);
    assert.equal(tools.plan_child_store.parameters.properties.id.type,'string');
    assert.match(tools.plan_store.description,/Refine only T08-enemies/);
  }finally{
    if(old===undefined)delete process.env.QWEN_WORKFLOW_PLAN_DRAFT;else process.env.QWEN_WORKFLOW_PLAN_DRAFT=old;
    rmSync(folder,{recursive:true,force:true});
  }
});

test('actual Pi validator accepts typed flat fields and rejects wrappers or serialized objects',()=>{
  const tool={name:'plan_store',parameters:repairParameters('T08-enemies')};
  const validate=arguments_=>validateToolArguments(tool,{name:'plan_store',arguments:arguments_});
  for(const input of [{task_updates:[{id:'T08-enemies'}]},{id:'T09'}, {context:{}},
    {context_overlay:'{"max_input_tokens":16384}'},{steps:'["one","two"]'}, {coverage:[]},{},
    {context_overlay:{nonsense:10}},{child_refs:['../escape']}]){
    const before=structuredClone(input);assert.throws(()=>validate(input));assert.deepEqual(input,before);
  }
  for(const input of [{context_overlay:{max_input_tokens:16384},add_coverage:[{criterion:'G',test:0}]},
    {unchanged:true},{child_refs:['a'.repeat(64),'b'.repeat(64)]}])assert.deepEqual(validate(input),input);
  const generic={name:'plan_store',parameters:repairParameters()};
  const updates={task_updates:[{id:'A'},{id:'B'}]};
  assert.deepEqual(validateToolArguments(generic,{name:'plan_store',arguments:updates}),updates);
});
