/** Preserve the full frozen contract without falling through to model summaries. */
import {readFileSync, writeFileSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {active} from './pi-hooks.mjs';
import {executionProgress} from './pi-execution-progress.mjs';

export function failingNames(text) {
  return [...new Set(text.split('\n').filter(line => line.startsWith('✖ ') && line !== '✖ failing tests:')
    .map(line => line.slice(2).trim().replace(/\s+\([^)]*ms\)\s*$/, '')))];
}

export function compactSummary(task, gate, failures = [], investigation = null) {
  const data = {task, current_gate:{passed:gate.passed === true, shadow_snapshot:gate.shadow_snapshot,
    violations:(gate.violations || []).slice(0,6).map(value => String(value).slice(0,160)),
    omitted_violations:Math.max(0,(gate.violations || []).length-6),
    truncated_violation_texts:(gate.violations || []).slice(0,6).filter(value => String(value).length>160).length},
    failures:failures.map(row => ({exit_code:row.exit_code,log:row.log,
      failed_names:row.failed_names.slice(0,8).map(name => name.slice(0,160)),
      truncated_failed_names:row.failed_names.slice(0,8).filter(name => name.length>160).length,
      omitted_failed_names:Math.max(0,row.failed_names.length-8)})),
    ...(gate.progress ? {progress:gate.progress} : {}),
    ...(investigation ? {investigation} : {}),
    next_action:gate.passed ? 'Review current evidence and finish.' : gate.progress?.next_action ||
      'Repair one named mechanism within scope; run workflow_test and project_map gate.',
    evidence_rule:'Every acceptance case and declared test below is preserved. Any later edit invalidates this gate. Truncated diagnostics are marked; project_map gate retrieves current violations.',
    retrieval_rule:'Use current shadow and bounded source_query, including pinned acceptance fixture pages. Discard old implementation assumptions.'};
  let summary='FROZEN ATOMIC TASK HANDOFF\n'+JSON.stringify(data);
  if (summary.length>12000) {
    if(data.investigation) data.investigation={...data.investigation,recent_tools:[],
      omitted_recent_tools:data.investigation.recent_tools?.length || 0,
      local_evidence:'execution-progress.json retains all bounded investigation metadata'};
    data.failures=failures.map(row => ({exit_code:row.exit_code,log:row.log,
      omitted_failed_names:row.failed_names.length}));
    summary='FROZEN ATOMIC TASK HANDOFF\n'+JSON.stringify(data);
  }
  if (summary.length>12000) throw new Error('Frozen contract itself needs a smaller task; deterministic compaction cancelled.');
  return summary;
}

export function installFixedCompactionHooks(pi, python, cli) {
  pi.on('session_before_compact', async (event, ctx) => {
    if (!active(ctx.model) || process.env.QWEN_WORKFLOW_ROLE !== 'code' || !process.env.QWEN_WORKFLOW_STATE) return;
    const session=process.env.QWEN_WORKFLOW_SESSION;
    try {
      const investigation=await executionProgress(pi,python,dirname(cli),ctx,true);
      if(investigation?.status==='stop')return {cancel:true};
      const state=JSON.parse(readFileSync(process.env.QWEN_WORKFLOW_STATE,'utf8'));
      const checked=await pi.exec(python,[cli,'check','--state',process.env.QWEN_WORKFLOW_STATE],
        {signal:event.signal,timeout:30000});
      const gate=JSON.parse(checked.stdout);
      const failures=(state.evidence?.results || []).filter(row => row.exit_code).slice(0,2)
        .map(row => ({exit_code:row.exit_code,log:row.log,
          failed_names:failingNames(readFileSync(row.log,'utf8'))}));
      const compaction={summary:compactSummary(state.task,gate,failures,investigation),
        firstKeptEntryId:event.preparation.firstKeptEntryId,tokensBefore:event.preparation.tokensBefore,
        details:{method:'complete frozen task plus bounded fresh diagnostics',modelCall:false,
          shadow:gate.shadow_snapshot,fullContractPreserved:true}};
      writeFileSync(join(session,'compaction-latest.json'),JSON.stringify(compaction,null,2));
      return {compaction};
    } catch (error) {
      try {
        writeFileSync(join(session,'compaction-error.json'),JSON.stringify({error:String(error),
          modelFallbackAllowed:false,action:'Split task or resolve current evidence before resuming.'},null,2));
      } catch {}
      ctx.abort();
      return {cancel:true};
    }
  });
}
