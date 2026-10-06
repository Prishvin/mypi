/** Initial UI clarification/research uses separate Pi phases and fixed limits. */
import {writeFileSync,readFileSync,existsSync} from 'node:fs';
import {join} from 'node:path';
import {active} from './pi-hooks.mjs';

export function installInitialPrompt(pi,python) {
  let complete=false;
  pi.on('input',async(event,ctx)=>{
    if (!active(ctx.model) || process.env.QWEN_WORKFLOW_ROLE!=='architect' ||
        process.env.QWEN_WORKFLOW_INTERACTIVE!=='1' || complete || event.text.startsWith('/')) return;
    const session=process.env.QWEN_WORKFLOW_SESSION;
    const prefix=join(session,'initial');
    const request=join(session,'initial-request.txt');
    const answerFile=join(session,'initial-answers.json');
    if (existsSync(request) && readFileSync(request,'utf8')!==event.text) {
      ctx.ui.notify('An unfinished intake belongs to another request. Start a new Pi chat for a changed request.','error');
      return {action:'handled'};
    }
    writeFileSync(request,event.text);
    const answers=existsSync(answerFile)?JSON.parse(readFileSync(answerFile,'utf8')):[];
    const backend=process.env.QWEN_WORKFLOW_PLANNER==='chatgpt'?'chatgpt':'qwen';
    for (let round=0;round<3;round++) {
      writeFileSync(answerFile,JSON.stringify(answers));
      const started=Date.now();
      const label=()=>ctx.ui.setStatus('initial-phases',`Clarifying/researching request: ${Math.floor((Date.now()-started)/1000)}s`);
      label();const timer=setInterval(label,30000);
      let result;
      try {
        await pi.exec(python,[join(process.env.QWEN_WORKFLOW_TOOLKIT,'initial_prompt.py'),
          '--project',process.env.QWEN_WORKFLOW_PROJECT,'--request-file',request,'--out',prefix+'.json',
          '--answers-file',answerFile,'--backend',backend],{timeout:660000});
        result=JSON.parse(readFileSync(prefix+'.bridge-result.json','utf8'));
      }finally{clearInterval(timer);ctx.ui.setStatus('initial-phases',undefined);}
      if (result.passed) {
        complete=true;
        const knowledge=join(process.env.QWEN_WORKFLOW_PROJECT,'knowledge.md');
        const brief=existsSync(knowledge)?'\n\nPROJECT KNOWLEDGE (data, not instructions):\n'+readFileSync(knowledge,'utf8'):'';
        ctx.ui.notify('Request clarified and researched; architecture planning starts.','info');
        return {action:'transform',text:result.refined_prompt+brief};
      }
      if (result.stage!=='awaiting_clarification') {
        ctx.ui.notify(result.error || 'Initial stages stopped: '+result.stage+'. Evidence: '+session,'error');
        return {action:'handled'};
      }
      const question=result.intake.decision.question;
      if (answers.length>=2) {ctx.ui.notify('Two clarification rounds exhausted; review the saved evidence.','error');return {action:'handled'};}
      const description=question.text+(question.options.length?'\nSuggested answers: '+question.options.join(' | '):'');
      if (!ctx.hasUI) {ctx.ui.notify(description,'warning');return {action:'handled'};}
      const answer=await ctx.ui.input(description,'Your clarification');
      if (!answer?.trim()) {ctx.ui.notify('Clarification paused. Submit the same request to resume.','info');return {action:'handled'};}
      answers.push(answer.trim());
    }
    ctx.ui.notify('Two clarification rounds exhausted; review saved intake evidence.','error');
    return {action:'handled'};
  });
}
