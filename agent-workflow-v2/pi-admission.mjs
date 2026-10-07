/** Count full serialized requests; cloud counts are a conservative tokenizer proxy. */
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
export async function admit(pi,home,runtime,payload,ctx) {
  if(!process.env.QWEN_WORKFLOW_INPUT_BUDGET)return;
  const session=process.env.QWEN_WORKFLOW_SESSION,request=join(session,'request-budget.json');
  writeFileSync(request,JSON.stringify(payload));
  const result=await pi.exec(join(home,'.venv/bin/python'),[join(runtime,'token_budget.py'),request,
    '--limit',process.env.QWEN_WORKFLOW_INPUT_BUDGET],{timeout:10000});
  writeFileSync(join(session,'request-budget-result.json'),result.stdout);
  if(result.code){ctx.abort();throw new Error('Context budget exceeded; split the task or compact: '+result.stdout+result.stderr);}
}
