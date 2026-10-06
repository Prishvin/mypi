/** The repair schema is sparse, while new full plans require explicit line estimates. */
import assert from 'node:assert/strict';
import test from 'node:test';
import extension from './pi-extension.mjs';
import {repairParameters} from './pi-plan-draft.mjs';

test('repair schema omits full-plan resend and exposes explicit corrections',()=>{
  const schema=repairParameters();
  assert.deepEqual(schema.required,['task_updates']);
  assert.equal(schema.properties.tasks,undefined);
  assert.ok(schema.properties.task_updates.items.properties.criterion_replacements);
  assert.equal(schema.properties.task_updates.items.properties.estimated_changed_lines.maximum,300);
});

test('full plan schema requires estimated_changed_lines; pinned draft selects sparse schema',()=>{
  const old=process.env.QWEN_WORKFLOW_PLAN_DRAFT;
  try{
    delete process.env.QWEN_WORKFLOW_PLAN_DRAFT;
    const tools={};const pi={registerTool:t=>{tools[t.name]=t;},on:()=>{},registerCommand:()=>{},registerProvider:()=>{}};
    extension(pi);
    assert.ok(tools.plan_store.parameters.properties.tasks.items.required.includes('estimated_changed_lines'));
    process.env.QWEN_WORKFLOW_PLAN_DRAFT='/private/session/plan-draft.json';
    extension(pi);
    assert.deepEqual(tools.plan_store.parameters.required,['task_updates']);
  }finally{
    if(old===undefined)delete process.env.QWEN_WORKFLOW_PLAN_DRAFT;else process.env.QWEN_WORKFLOW_PLAN_DRAFT=old;
  }
});
