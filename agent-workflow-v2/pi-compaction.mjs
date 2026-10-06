/** Rebuild a bounded task handoff from verified artifacts rather than another model call. */
import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {active} from './pi-hooks.mjs';

export function taskSummary(task, gate, failures = []) {
  const data = {task, current_gate:gate, failure_tails:failures,
    next_action:gate.passed ? 'Review the evidence and finish this task.' :
      'Inspect the named current symbols needed to address these violations; edit within scope, then workflow_test and gate.',
    evidence_rule:'The gate is current at compaction time. Any later edit invalidates it. Do not infer passing tests from old conversation.',
    retrieval_rule:'Use the current shadow and bounded source_query. Discard old implementation assumptions.'};
  const summary = 'FROZEN ATOMIC TASK HANDOFF\n' + JSON.stringify(data);
  if(summary.length > 12000)throw new Error('Task handoff exceeds compaction budget; split the task.');
  return summary;
}

export function installCompactionHooks(pi, python, cli) {
  pi.on('session_before_compact', async (event,ctx) => {
    if(!active(ctx.model) || process.env.QWEN_WORKFLOW_ROLE !== 'code' || !process.env.QWEN_WORKFLOW_STATE)return;
    const state = process.env.QWEN_WORKFLOW_STATE;
    const data = JSON.parse(readFileSync(state,'utf8'));
    const checked = await pi.exec(python,[cli,'check','--state',state],{signal:event.signal,timeout:30000});
    const gate = JSON.parse(checked.stdout);
    const failures = (data.evidence?.results || []).filter(row=>row.exit_code)
      .slice(0,2).map(row=>({argv:row.argv,exit_code:row.exit_code,tail:readFileSync(row.log,'utf8').slice(-1500)}));
    const compaction = {summary:taskSummary(data.task,gate,failures),
      firstKeptEntryId:event.preparation.firstKeptEntryId,tokensBefore:event.preparation.tokensBefore,
      details:{method:'frozen task plus fresh gate',modelCall:false,shadow:gate.shadow_snapshot}};
    writeFileSync(join(process.env.QWEN_WORKFLOW_SESSION,'compaction-latest.json'),JSON.stringify(compaction,null,2));
    return {compaction};
  });
}
