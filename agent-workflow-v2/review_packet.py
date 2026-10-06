"""Build a bounded review handoff from prototypes and structured run evidence."""
import hashlib
import json
from pathlib import Path
from project_map import scan
from runner_process import read
from plan_runner import contract_digest, validate


def test_names(path):
    """Extract test outcomes only; raw tracebacks and source text remain local."""
    path=Path(path)
    if not path.is_file(): return []
    text=path.read_text(errors='replace')
    try:
        structured=json.loads(text)
    except ValueError:
        structured={}
    if isinstance(structured,dict) and isinstance(structured.get('checks'),list):
        return [('PASS: ' if structured.get('passed') else 'REPORTED: ')+name[:200]
                for name in structured['checks'] if isinstance(name,str)][:40]
    prefixes=('ok ','not ok ','✔ ','✖ ','# tests ','# pass ','# fail ','ℹ tests ','ℹ pass ','ℹ fail ','Ran ','OK','FAILED')
    return [line.strip()[:200] for line in text.splitlines()
            if line.strip().startswith(prefixes)][:40]


def build(root, plan_path, run_dir):
    """Require an unchanged completed run and retain only review-relevant evidence."""
    root,plan_path,run_dir=root.resolve(),plan_path.resolve(),run_dir.resolve()
    plan=read(plan_path); state=read(run_dir/'state.json'); validate(root,plan)
    data=scan(root,['.'])
    if (state.get('status')!='complete' or state.get('project')!=str(root) or state.get('plan')!=str(plan_path)
        or state.get('snapshot')!=data['snapshot'] or state.get('contract_digest')!=contract_digest(plan)):
        raise ValueError('Review requires this unchanged completed run and its exact accepted plan')
    if any(t['status']!='done' for t in plan['tasks']):
        raise ValueError('Review requires all planned todos to be accepted')
    tasks=[]
    for task in plan['tasks']:
        accepted=[a for a in state['attempts'] if a['todo']==task['id'] and a.get('gate',{}).get('passed')]
        if not accepted: raise ValueError('Missing accepted execution evidence for '+task['id'])
        attempt=accepted[-1]; frozen=read(Path(attempt['session'])/'task-state.json')
        evidence=[]
        for row in frozen.get('evidence',{}).get('results',[]):
            evidence.append({'argv':row['argv'],'exit_code':row['exit_code'],'test_outcomes':test_names(row['log'])})
        tasks.append({k:task[k] for k in ('id','goal','files','acceptance','tests','coverage')} |
                     {'evidence':evidence,'gate':attempt['gate'],'regressions_passed':attempt.get('regression',{}).get('passed'),
                      'wall_seconds':attempt['wall_seconds']})
    packet={'version':1,'project':str(root),'goal':plan['goal'],'architecture':plan['architecture'],
            'snapshot':data['snapshot'],'contract_digest':state['contract_digest'],'tasks':tasks,
            'attempt_count':len(state['attempts']),'interrupted_attempts':sum(bool(a.get('interrupted')) for a in state['attempts']),
            'evidence_ids':['run-summary']+['task:'+t['id'] for t in tasks],
            'source_paths':[f['path'] for f in data['files']],
            'completed_contracts':plan.get('replan_lineage',{}).get('completed',[])+[
                {k:t[k] for k in ('id','goal','files','tests','execution','evidence')} for t in plan['tasks']],
            'acceptance_fixtures':plan.get('acceptance_fixtures',{}), 'original_plan':str(plan_path),
            'limits':'Shadow and recorded test outcomes only; no implementation inspection or semantic coverage guarantee.'}
    raw=json.dumps(packet,sort_keys=True)
    if len(raw.encode())>48000:
        raise ValueError('Review evidence exceeds 48 KiB; split the project review into bounded groups')
    packet['packet_sha256']=hashlib.sha256(raw.encode()).hexdigest()
    return packet
