/** Attach exact current evidence to rejected edits; never apply a guessed patch. */
import {mkdtempSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join} from 'node:path';

const advice='\nRetrieve exact current source before retrying. Never reconstruct oldText from memory or include source line labels.';

export async function failedEditEvidence(pi,event,ctx,python,cli) {
  if(!event.isError||event.toolName!=='edit'||!event.input?.path)return '';
  const state=process.env.QWEN_WORKFLOW_STATE;
  if(!state)return advice;
  const edits=event.input.edits??[event.input];
  if(!Array.isArray(edits)||!edits.length||edits.length>8)return advice;
  const oldTexts=edits.map(edit=>edit?.oldText);
  if(oldTexts.some(old=>typeof old!=='string'||!old))return advice;
  const request=JSON.stringify({path:event.input.path,old_texts:oldTexts});
  if(Buffer.byteLength(request)>65536)return advice;
  let temporary;
  try {
    temporary=mkdtempSync(join(tmpdir(),'mypi-edit-evidence-'));
    const input=join(temporary,'request.json');
    writeFileSync(input,request,{mode:0o600});
    const result=await pi.exec(python,[join(dirname(cli),'edit_recovery.py'),
      '--root',process.env.QWEN_WORKFLOW_PROJECT||ctx.cwd,'--state',state,'--input',input],{timeout:30000});
    if(result.code)return advice+'\nCurrent-source evidence unavailable; use source_query within the frozen scope.';
    if(Buffer.byteLength(result.stdout)>12001)throw Error('Evidence exceeded its output limit');
    const evidence=JSON.parse(result.stdout);
    if(evidence.readonly!==true||!Array.isArray(evidence.excerpts))throw Error('Invalid evidence response');
    return '\nCURRENT SOURCE EVIDENCE FOR FAILED EDIT (read-only, no replacement applied):\n'+result.stdout+
      '\nThe source fields contain exact current text without line labels. Unique anchors or parsed declaration names identify context, not approved edit boundaries. '+
      'Inspect the excerpt and choose the smallest uniquely matching exact replacement; do not delete unrelated surrounding lines. '+
      'sha256 identifies this snapshot; retrieve again after intervening edits. No fuzzy repair was applied.';
  } catch {
    return advice+'\nCurrent-source evidence unavailable; the original edit error is unchanged.';
  } finally {
    if(temporary)rmSync(temporary,{recursive:true,force:true});
  }
}
