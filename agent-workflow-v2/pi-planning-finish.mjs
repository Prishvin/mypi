/** A verified plan publication must not start an unnecessary compaction request. */
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join,resolve} from 'node:path';
import {active} from './pi-hooks.mjs';
export function planningFinished(){
 if(process.env.QWEN_WORKFLOW_ROLE!=='architect')return false;
 const plan=process.env.QWEN_WORKFLOW_PLAN,session=process.env.QWEN_WORKFLOW_SESSION;
 if(!plan||!session)return false;
 try{
  const marker=JSON.parse(readFileSync(join(session,'planning-stop.json'),'utf8'));
  return resolve(marker.plan)===resolve(plan)&&marker.sha256===createHash('sha256').update(readFileSync(plan)).digest('hex');
 }catch{return false;}
}
export function installPlanningFinish(pi){
 pi.on('session_before_compact',async(_event,ctx)=>{
  if(active(ctx.model)&&planningFinished()){ctx.abort();return {cancel:true};}
 });
}
