/** Keep rejected proposals on disk instead of echoing them into the next prompt. */
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';

export function planFailure(event){
  const role=process.env.QWEN_WORKFLOW_ROLE,session=process.env.QWEN_WORKFLOW_SESSION;
  if(!session||!['architect','reviewer'].includes(role)||event.toolName!=='plan_store'||!event.isError)return;
  const error=(event.content||[]).filter(c=>c.type==='text').map(c=>c.text).join('\n');
  const original=JSON.stringify({arguments:event.input,error});
  const artifact=join(session,'rejected-plan-'+createHash('sha256').update(original).digest('hex').slice(0,24)+'.json');
  try{writeFileSync(artifact,original,{flag:'wx'});}catch(e){if(e.code!=='EEXIST')throw e;}
  const diagnostic=error.split('Received arguments:')[0].trim();
  const bounded=diagnostic.length<=3000?diagnostic:diagnostic.slice(0,1200)+'\n…\n'+diagnostic.slice(-1800);
  return {content:[{type:'text',text:bounded+'\n\nOriginal rejected proposal and error retained: '+artifact+
    '\nNo plan was accepted. Do not repeat the whole proposal in explanations; preserve unchanged contracts for a focused repair.'}],
    details:{...event.details,rejectedProposal:artifact},isError:true};
}

export function planFailureContext(messages){
  /** Pi skips tool_result hooks for schema errors; bound those before provider serialization. */
  return messages.map(message=>{
    if(message.role!=='toolResult'||message.toolName!=='plan_store'||!message.isError||
       !message.content?.some(c=>c.type==='text'&&c.text.includes('Received arguments:')))return message;
    const result=planFailure(message);
    return result?{...message,content:result.content,details:result.details}:message;
  });
}
