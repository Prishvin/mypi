/** Bound unverified rewrites while declared files are still absent; survive compaction. */
import {existsSync,readFileSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';

function state(contract) {
  const session=process.env.QWEN_WORKFLOW_SESSION;
  if (!session || !contract.declared_hashes) return null;
  const pending=contract.task.files.filter(path=>path!=='architecture.md' &&
    contract.declared_hashes[path]==null && !existsSync(resolve(contract.before.root,path)));
  const path=join(session,'mutation-progress.json');
  let saved={};
  if(existsSync(path))saved=JSON.parse(readFileSync(path,'utf8'));
  if(JSON.stringify(saved.pending_files)!==JSON.stringify(pending))saved={pending_files:pending,counts:{},blocked:{}};
  return {path,saved};
}

export function mutationProgress(contract, target, completed=false) {
  const journal=state(contract);
  if(!journal)return null;
  const {path,saved}=journal;
  const name=contract.task.files.find(p=>resolve(contract.before.root,p)===target);
  if(!name || name==='architecture.md' || !saved.pending_files.length || saved.pending_files.includes(name))return null;
  if(completed) {
    saved.counts[name]=(saved.counts[name]||0)+1;
    writeFileSync(path,JSON.stringify(saved));
    return null;
  }
  if((saved.counts[name]||0)<2)return null;
  saved.blocked[name]=(saved.blocked[name]||0)+1;
  writeFileSync(path,JSON.stringify(saved));
  return {block:true,stop:saved.blocked[name]>=3,
    reason:'Repeated unverified rewrite paused for '+name+'. Missing declared files: '+saved.pending_files.join(', ')+
      '. Create those files, including the frozen tests, then measure behavior with workflow_test. '+
      'Existing source can be repaired after the required files exist. Do not create scratch files outside scope.'};
}
