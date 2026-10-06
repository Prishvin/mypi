/** Return exact bounded current functions after an edit used stale or guessed text. */
export async function failedEditEvidence(pi,event,ctx,python,cli,scopeArgs) {
  if(!event.isError||event.toolName!=='edit'||!event.input?.path)return '';
  const names=[];
  for(const edit of event.input.edits||[]) {
    for(const match of (edit.oldText||'').matchAll(/\bfunction\s+([A-Za-z_$][\w$]*)\s*\(/g)) {
      if(!names.includes(match[1])&&names.length<8)names.push(match[1]);
    }
  }
  if(!names.length)return '\nEdit text did not match. Retrieve the exact current affected symbol; never reconstruct oldText from memory or include source line labels.';
  const result=await pi.exec(python,[cli,...scopeArgs(process.env.QWEN_WORKFLOW_PROJECT||ctx.cwd),
    'read-symbols',event.input.path,...names],{timeout:30000});
  if(result.code)return '\nRetrieve the exact current symbol before retrying the edit. '+result.stderr.slice(-500);
  return '\nCURRENT SOURCE FOR FAILED EDIT (line labels are not edit text):\n'+result.stdout.slice(0,12000);
}
