/** Verify a compact handoff preserves acceptance and never invents test success. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {taskSummary} from './pi-compaction.mjs';

test('handoff retains the selected contract and current failing evidence',()=>{
  const task={goal:'Handle restart',files:['controller.js'],acceptance:[{id:'A1',then:'score resets'}],tests:[['node','--test']]};
  const summary=taskSummary(task,{passed:false,violations:['Test evidence stale'],shadow_snapshot:'now'});
  assert.ok(summary.includes('score resets'));
  assert.ok(summary.includes('Test evidence stale'));
  assert.ok(summary.includes('"passed":false'));
  assert.ok(summary.includes('Any later edit invalidates it'));
  assert.ok(summary.includes('bounded source_query'));
});

test('oversized task contracts fail instead of silently losing acceptance cases',()=>{
  assert.throws(()=>taskSummary({goal:'x'.repeat(13000)},{passed:false}),/split the task/);
});
