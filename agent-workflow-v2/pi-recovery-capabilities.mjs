/** Advertise the exact failure-only source scope at the tool call boundary. */
import {readFileSync} from 'node:fs';

export function recoverySourceScope(){
 if(process.env.QWEN_WORKFLOW_ROLE!=='architect'||!process.env.QWEN_WORKFLOW_REPLAN_EVIDENCE)return null;
 try{
  const packet=JSON.parse(readFileSync(process.env.QWEN_WORKFLOW_REPLAN_EVIDENCE,'utf8'));
  const task=packet.failed_todo;
  if(!Array.isArray(task?.files))return null;
  const paths=[...task.files,...(task.context?.interfaces||[])];
  if(!paths.length||paths.some(p=>typeof p!=='string'))return null;
  return [...new Set(paths)].sort();
 }catch{return null;}
}
