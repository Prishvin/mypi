/** Deterministic failure-review handoff; never spend a model call summarizing it. */
import {writeFileSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {active,recoverySourceEnabled} from './pi-hooks.mjs';
import {planningFinished} from './pi-planning-finish.mjs';
import {recallSource,attachSourceMemory} from './pi-source-memory.mjs';

export function installRecoveryCompaction(pi,python,cli){
  pi.on('session_before_compact',async(event,ctx)=>{
    if(!active(ctx.model)||!recoverySourceEnabled())return;
    if(planningFinished()){ctx.abort();return {cancel:true};}
    const session=process.env.QWEN_WORKFLOW_SESSION,runtime=dirname(cli);
    try{
      const built=await pi.exec(python,[join(runtime,'recovery_handoff.py'),'--session',session],
        {signal:event.signal,timeout:30000});
      if(built.code)throw new Error((built.stdout+built.stderr).slice(-1800));
      const draft=JSON.parse(built.stdout);
      const memory=recallSource(session,process.env.QWEN_WORKFLOW_PROJECT,16000);
      const handoff=attachSourceMemory(draft.summary,memory,1000000);
      const candidate=join(session,'compaction-candidate.json');
      writeFileSync(candidate,JSON.stringify(handoff));
      const fitted=await pi.exec(python,[join(runtime,'compaction_budget.py'),'--session',session,
        '--candidate',candidate,'--limit',process.env.QWEN_WORKFLOW_INPUT_BUDGET],
        {signal:event.signal,timeout:30000});
      if(fitted.code)throw new Error((fitted.stdout+fitted.stderr).slice(-1800));
      const result=JSON.parse(fitted.stdout);
      if(result.budget?.passed!==true||typeof result.summary!=='string')throw new Error('Invalid recovery handoff budget');
      const compaction={summary:result.summary,tokensBefore:event.preparation.tokensBefore,
        details:{method:'Bound recovery contract and verified source observations',modelCall:false,
          fullContractPreserved:true,retainedConversationEntries:0,
          sourceMemory:{...result.stats,byteLimit:16000},tokenBudget:result.budget,
          historyPolicy:'Native evidence replaces duplicate history; original journal and allowances preserved.'}};
      writeFileSync(join(session,'compaction-latest.json'),JSON.stringify(compaction,null,2));
      return {compaction};
    }catch(error){
      try{writeFileSync(join(session,'compaction-error.json'),JSON.stringify({error:String(error),
        modelFallbackAllowed:false,role:'failure-recovery',
        action:'Review the preserved context failure before retrying; no task or allowance was changed.'},null,2));}catch{}
      ctx.abort();return {cancel:true};
    }
  });
}
