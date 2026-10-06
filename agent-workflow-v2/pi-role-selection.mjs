/** User slash commands choose planner and reviewer independently; workers stay local. */
import {join} from 'node:path';
import {existsSync,readFileSync} from 'node:fs';
import {active} from './pi-hooks.mjs';

export function registerRoleSelection(pi,python) {
  for(const role of ['planner','reviewer']) pi.registerCommand(role,{
    description:`Select ${role}: chatgpt (GPT-6.1 Sol xhigh) or local (MTPLX Quality medium)`,
    async handler(args,ctx) {
      if(!active(ctx.model)) throw new Error('Private Pi workflow only');
      await ctx.waitForIdle();
      let value=args.trim().toLowerCase();
      if(!value) {
        if(!ctx.hasUI) {ctx.ui.notify(`Use /${role} chatgpt or /${role} local`,'info');return;}
        const choice=await ctx.ui.select(`Choose ${role}`,['ChatGPT — GPT-6.1 Sol / xhigh','Local — MTPLX Quality / medium']);
        if(!choice)return;value=choice.startsWith('ChatGPT')?'chatgpt':'local';
      }
      if(!['chatgpt','local','qwen'].includes(value)) {ctx.ui.notify('Choose chatgpt or local','error');return;}
      const selected=value==='chatgpt'?'chatgpt':'qwen';
      if(role==='planner' && process.env.QWEN_WORKFLOW_ROLE==='architect') {
        const state=join(process.env.QWEN_WORKFLOW_SESSION,'initial.intake/state.json');
        if(existsSync(state)) {
          const intake=JSON.parse(readFileSync(state,'utf8'));
          if(intake.status!=='ready' && intake.backend!==selected) {
            ctx.ui.notify('Finish the pending clarification or open a new chat before changing its planner.','error');return;
          }
        }
        if(selected==='qwen') {
          const started=await pi.exec(join(process.env.QWEN_WORKFLOW_TOOLKIT,'../mypi'),['start'],{timeout:200000});
          if(started.code)throw new Error(started.stderr || started.stdout);
        }
        const provider=selected==='chatgpt'?'openai':'local-qwen-workflow';
        const model=ctx.modelRegistry.find(provider,selected==='chatgpt'?'gpt-6.1-sol':(process.env.MYPI_MODEL || 'mtplx-quality'));
        if(!model || !await pi.setModel(model))throw new Error('Selected model unavailable. Restart pi-local chat to refresh its private catalogue/login.');
        process.env.QWEN_WORKFLOW_PLANNER=selected==='chatgpt'?'chatgpt':'local';
        process.env.QWEN_WORKFLOW_REASONING=selected==='chatgpt'?'xhigh':'medium';
        process.env.QWEN_WORKFLOW_THINKING='on';
        pi.setThinkingLevel(process.env.QWEN_WORKFLOW_REASONING);
      }
      const result=await pi.exec(python,[join(process.env.QWEN_WORKFLOW_TOOLKIT,'role_selection.py'),
        '--project',process.env.QWEN_WORKFLOW_PROJECT,'--role',role,'--value',selected],{timeout:10000});
      if(result.code)throw new Error(result.stderr || result.stdout);
      ctx.ui.notify(`${role}: ${selected==='chatgpt'?'GPT-6.1 Sol / xhigh':'MTPLX Quality / medium'}. Saved for this project.`,'info');
    }});
}
