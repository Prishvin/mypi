/** /remember is an explicit user command, not an autonomous model write tool. */
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {active} from './pi-hooks.mjs';

export function latestOutput(branch) {
  for (const entry of [...branch].reverse()) {
    const message=entry.type==='message'?entry.message:null;
    if (message?.role!=='assistant' || ['error','aborted'].includes(message.stopReason)) continue;
    const text=(message.content || []).filter(x=>x.type==='text').map(x=>x.text).join('\n').trim();
    if (text) return text;
  }
  throw new Error('No completed assistant text to remember in the current branch');
}

export function registerRemember(pi, python, runtime) {
  pi.registerCommand('remember',{description:'Distill the latest response in a fresh request and save essentials to knowledge.md; optional selected note',
    async handler(args,ctx) {
      if (!active(ctx.model)) throw new Error('Private Pi workflow only');
      await ctx.waitForIdle();
      const text=args.trim() || latestOutput(ctx.sessionManager.getBranch());
      const session=process.env.QWEN_WORKFLOW_SESSION;
      const input=join(session,'remember-input.txt');
      writeFileSync(input,text);
      const backend=ctx.model.provider==='openai'?'chatgpt':'qwen';
      const started=Date.now();
      const status=()=>ctx.ui.setStatus?.('remember',`Distilling project memory (${backend}): ${Math.floor((Date.now()-started)/1000)}s`);
      status();const timer=setInterval(status,30000);
      let result;
      try {result=await pi.exec(python,[join(process.env.QWEN_WORKFLOW_TOOLKIT,'remember.py'),'--project',process.env.QWEN_WORKFLOW_PROJECT,
        '--input',input,'--session',session,'--shadow',process.env.QWEN_WORKFLOW_SHADOW,
        '--base',process.env.QWEN_WORKFLOW_TOOLKIT,'--backend',backend],{timeout:540000});
      } finally {clearInterval(timer);ctx.ui.setStatus?.('remember',undefined);}
      const lines=result.stdout.trim().split('\n');
      const saved=JSON.parse(lines.at(-1));
      if (result.code) {ctx.ui.notify(saved.error || result.stderr,'error');return;}
      ctx.ui.notify(saved.skipped?'Nothing new to remember: '+saved.reason:saved.duplicate?'Already remembered.':
        'Distilled essentials saved; shadow updated.\n'+saved.summary,'info');
    }});
}
