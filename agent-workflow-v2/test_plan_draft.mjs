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
  assert.ok(schema.properties.task_updates.anyOf[0].items.properties.criterion_replacements);
  assert.equal(schema.properties.task_updates.anyOf[0].items.properties.estimated_changed_lines.maximum,300);
  assert.equal(schema.properties.task_updates.anyOf[1].maxLength,1048576);
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
    assert.deepEqual(tools.plan_store.parameters.required,['task_updates']);
    assert.equal(tools.plan_store.parameters.properties.task_updates.anyOf[0].maxItems,1);
    assert.equal(tools.plan_store.parameters.properties.task_updates.anyOf[0].items.properties.id.const,'T08-enemies');
    assert.match(tools.plan_store.description,/Refine only T08-enemies/);
  }finally{
    if(old===undefined)delete process.env.QWEN_WORKFLOW_PLAN_DRAFT;else process.env.QWEN_WORKFLOW_PLAN_DRAFT=old;
    rmSync(folder,{recursive:true,force:true});
  }
});

test('actual Pi validator restricts refinement to one target and rejects full-contract patch fields',()=>{
  const tool={name:'plan_store',parameters:repairParameters('T08-enemies')};
  const validate=arguments_=>validateToolArguments(tool,{name:'plan_store',arguments:arguments_});
  for(const input of [
    {task_updates:[{id:'T08-enemies'},{id:'T08-enemies',add_coverage:[]}]},
    {task_updates:[{id:'T09-spawn'}]},
    {task_updates:[{id:'T08-enemies',context:{max_input_tokens:16384}}]},
    {task_updates:[{id:'T08-enemies',coverage:[]}]},
    {task_updates:[{id:'T08-enemies'}],goal:'Unrelated change'},
  ]){const before=structuredClone(input);assert.throws(()=>validate(input));assert.deepEqual(input,before);}
  for(const input of [
    {task_updates:[{id:'T08-enemies',context_overlay:{max_input_tokens:16384},add_coverage:[{criterion:'G',test:0}]}]},
    {task_updates:[{id:'T08-enemies'}]},
    {task_updates:[{id:'T08-enemies',replace_with:[{id:'T08a',context:{}},{id:'T08-enemies',context:{}}]}]},
  ])assert.deepEqual(validate(input),input);
  // Serialized adapter compatibility still reaches the independent Python scope guard.
  const serialized={task_updates:JSON.stringify([{id:'T08-enemies'},{id:'T08-enemies'}])};
  assert.deepEqual(validate(serialized),serialized);
  const generic={name:'plan_store',parameters:repairParameters()};
  const updates={task_updates:[{id:'A'},{id:'B'}]};
  assert.deepEqual(validateToolArguments(generic,{name:'plan_store',arguments:updates}),updates);
});
