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
  const report=JSON.parse(readFileSync(join(session,'recovery-report.json'),'utf8'));
  if(process.env.QWEN_WORKFLOW_REPLAN_EVIDENCE&&report.project===process.env.QWEN_WORKFLOW_PROJECT&&
     ['needs_user','framework_fix','environment_fix'].includes(report.decision?.action)&&Number.isFinite(report.finished_epoch))return true;
 }catch{}
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
