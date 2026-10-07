/** Keep rejected proposals on disk instead of echoing them into the next prompt. */
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';

export function planFailure(event){
  const role=process.env.QWEN_WORKFLOW_ROLE,session=process.env.QWEN_WORKFLOW_SESSION;
  if(!session||!['architect','reviewer'].includes(role)||!['plan_store','plan_child_store'].includes(event.toolName)||!event.isError)return;
  const error=(event.content||[]).filter(c=>c.type==='text').map(c=>c.text).join('\n');
  const original=JSON.stringify({arguments:event.input,error});
  const artifact=join(session,'rejected-plan-'+createHash('sha256').update(original).digest('hex').slice(0,24)+'.json');
  try{writeFileSync(artifact,original,{flag:'wx'});}catch(e){if(e.code!=='EEXIST')throw e;}
  let diagnostic=error.split('Received arguments:')[0].trim();
  if(diagnostic.includes('Traceback (most recent call last):')){
    const exceptions=[...diagnostic.matchAll(/^[\w.]*(?:Error|Exception|Interrupt|Exit):[^\n]*/gm)];
    if(exceptions.length)diagnostic=diagnostic.slice(exceptions.at(-1).index);
  }
  const bounded=diagnostic.length<=3000?diagnostic:diagnostic.slice(0,1200)+'\n…\n'+diagnostic.slice(-1800);
  const retry=process.env.QWEN_WORKFLOW_REPLAN_EVIDENCE ?
    ' Resubmit failure_analysis and the complete corrected flat changes for the failed todo only. Do not resend tasks, IDs or the whole plan. Python preserves unchanged contracts; rejected patches do not accumulate.' : process.env.QWEN_WORKFLOW_PLAN_DRAFT ?
    ' Follow the current tool schema. For selected-task review, send flat changed fields or child_refs; do not send task_updates. Correct a failed plan_child_store by resending only that full child; other receipts remain usable. For plan_store, resubmit the complete corrected change containing ALL intended edits; each save starts from the pinned draft, not the previous rejected patch. Do not resend untouched draft tasks.' :
    ' Correct the rejected call, preserve unchanged contracts, and do not repeat the whole proposal in explanations.';
  return {content:[{type:'text',text:bounded+'\n\nOriginal rejected proposal and error retained: '+artifact+
    '\nNo plan was accepted.'+retry}],
    details:{...event.details,rejectedProposal:artifact},isError:true};
}

export function planFailureContext(messages){
  /** Pi skips tool_result hooks for schema errors; bound those before provider serialization. */
  return messages.map(message=>{
    if(message.role!=='toolResult'||!['plan_store','plan_child_store'].includes(message.toolName)||!message.isError||
       !message.content?.some(c=>c.type==='text'&&c.text.includes('Received arguments:')))return message;
    const result=planFailure(message);
    return result?{...message,content:result.content,details:result.details}:message;
  });
}
