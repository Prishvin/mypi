/** Record mechanical evidence; Python owns stagnation decisions and durable state. */
import {appendFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {active} from './pi-hooks.mjs';

function enabled(ctx) {
  return active(ctx.model) && process.env.QWEN_WORKFLOW_ROLE==='code' &&
    process.env.QWEN_WORKFLOW_STATE && process.env.QWEN_WORKFLOW_SESSION;
}

export async function executionProgress(pi,python,runtime,ctx,compaction=false) {
  if(!enabled(ctx))return null;
  const session=process.env.QWEN_WORKFLOW_SESSION;
  try {
    const result=await pi.exec(python,[join(runtime,'progress_observer.py'),session,
      ...(compaction?['--compaction']:[])],{timeout:10000});
    if(result.code)throw new Error(result.stderr || result.stdout);
    const brief=JSON.parse(result.stdout);
    if(!['continue','warning','stop'].includes(brief.status))throw new Error('Invalid progress response');
    if(brief.status==='stop')ctx.abort();
    return brief;
  } catch(error) {
    writeFileSync(join(session,'progress-error.json'),JSON.stringify({error:String(error).slice(0,500)}));
    ctx.abort();
    throw error;
  }
}

export function installExecutionProgressHooks(pi,python,runtime) {
  const pending=new Map();
  const save=row=>appendFileSync(join(process.env.QWEN_WORKFLOW_SESSION,'execution-events.jsonl'),JSON.stringify(row)+'\n');
  pi.on('message_end',(event,ctx)=>{
    if(enabled(ctx) && event.message?.role==='assistant')save({kind:'round'});
  });
  pi.on('tool_execution_start',(event,ctx)=>{
    if(!enabled(ctx))return;
    const args=event.args || {},selector={};
    for(const key of ['action','path','paths','query','offset','name'])
      if(args[key]!==undefined)selector[key]=String(args[key]).slice(0,160);
    pending.set(event.toolCallId,selector);
  });
  pi.on('tool_execution_end',(event,ctx)=>{
    if(!enabled(ctx))return;
    const selector=pending.get(event.toolCallId)||{};pending.delete(event.toolCallId);
    let error;
    if(event.isError) {
      const text=(event.result?.content||[]).filter(b=>b.type==='text').map(b=>b.text).join('\n').split('Received arguments:')[0];
      const lines=text.split('\n'),causes=lines.filter(line=>/^\s*(?:[\w.]*Error|Exception):/.test(line));
      const fields=lines.filter(line=>/^\s*-\s+[\w.]+:\s/.test(line)).slice(0,3);
      error=(causes.at(-1)||[lines[0]||'Tool failed',...fields].join('\n')).slice(0,240);
    }
    save({kind:'tool',tool:event.toolName,selector,...(error?{error}:{})});
  });
  pi.on('context',async(event,ctx)=>{
    const brief=await executionProgress(pi,python,runtime,ctx);
    if(!brief)return;
    if(brief.status==='stop')throw new Error('Stopped for evidence-based replanning: no_progress');
    if(brief.status==='warning'||brief.deadline?.near_deadline)return {messages:[...event.messages,{role:'user',timestamp:Date.now(),
      content:[{type:'text',text:'Native progress checkpoint (observed tool evidence):\n'+JSON.stringify(brief)+
        (brief.deadline?.near_deadline ? '\nATTEMPT DEADLINE: '+brief.deadline.remaining_seconds+
          ' seconds remain, including prompt loading, reasoning, tools and verification. Prefer a small scoped edit and fresh tests; '+
          'avoid redundant reads, long rewrites or explanations. Preserve all acceptance checks. '+
          'If completion is infeasible, preserve partial work and report the concrete blocker. The timeout is unchanged.' : '')}]}]};
  });
}
