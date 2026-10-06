/** Local thinking caps are real backend controls, separate from reasoning effort. */
import {join} from 'node:path';
import {active} from './pi-hooks.mjs';

export async function requireThinkingCaps(fetcher=fetch) {
  const response=await fetcher((process.env.MYPI_SERVER_URL || 'http://localhost:8000')+'/pi-workflow/capabilities',
    {signal:AbortSignal.timeout(3000),headers:process.env.MYPI_SERVER_TOKEN?{Authorization:'Bearer '+process.env.MYPI_SERVER_TOKEN}:{}});
  const value=response.ok ? await response.json() : {};
  if(value.version!==1 || value.thinking_cap!=='request-local' || value.field!=='pi_thinking_cap')
    throw new Error('The configured Qwen endpoint cannot verify request-local thinking caps. Check mypi status and the server adapter.');
}

export function registerThinkingCap(pi,python) {
  pi.registerCommand('thinkingcap',{
    description:'Local Qwen thinking-token cap: 8192, 0 (uncapped), or default. Query without arguments.',
    async handler(args,ctx) {
      if(!active(ctx.model))throw new Error('Private Pi workflow only');
      await ctx.waitForIdle();
      const value=args.trim().toLowerCase();
      if(value && value!=='default' && (!/^\d+$/.test(value) || Number(value)>30720)) {
        ctx.ui.notify('Use /thinkingcap 0..30720 or /thinkingcap default. Zero removes only the thinking cap.','error');return;
      }
      if(value && process.env.QWEN_WORKFLOW_STATE) {
        ctx.ui.notify('This worker has a frozen contract. Change reasoning_budget_tokens in a new plan before execution.','error');return;
      }
      const result=await pi.exec(python,[join(process.env.QWEN_WORKFLOW_TOOLKIT,'thinking_caps.py'),
        '--project',process.env.QWEN_WORKFLOW_PROJECT,...(value?['--value',value]:[])],{timeout:10000});
      if(result.code)throw new Error(result.stderr || result.stdout);
      const saved=JSON.parse(result.stdout).thinking_cap;
      const output=Number(process.env.QWEN_WORKFLOW_OUTPUT_BUDGET || 32768);
      const cap=Math.max(0,Math.min(saved ?? 4096,output-2048));
      if(value)process.env.QWEN_WORKFLOW_REASONING_BUDGET_TOKENS=String(cap);
      ctx.ui.notify(`Local Qwen default: ${saved===null?'profile default':saved===0?'uncapped':saved} thinking tokens. `+
        `Current output allows ${cap===0?'uncapped thinking':cap+' thinking tokens'}; total output ${output} includes thinking. `+
        'Explicit task caps win; smaller outputs keep 2048 tokens for edits. ChatGPT uses its selected reasoning effort.', 'info');
    }});
}
