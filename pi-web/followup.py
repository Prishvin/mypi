"""Adopt a verified reviewer follow-up without overwriting the accepted run."""
import hashlib
import json
from pathlib import Path


def adopt(store,ident):
    row=store.get(ident)
    if not row.get('run_dir'):raise ValueError('No completed review exists')
    folder=Path(row['run_dir'])/'final-review'
    result=json.loads((folder/'result.json').read_text());review=json.loads((folder/'review.json').read_text())
    if not result.get('passed') or review.get('verdict')!='followup':raise ValueError('No validated reviewer follow-up is ready')
    path=Path(review['followup_plan'])
    if not path.resolve().is_relative_to(folder.resolve()):raise ValueError('Unexpected follow-up location')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=review['followup_sha256']:raise ValueError('Follow-up plan changed after review')
    plan=json.loads(path.read_text())
    if Path(plan['project']).resolve()!=Path(row['project']).resolve():raise ValueError('Follow-up belongs to another project')
    from plan_runner import validate
    from project_map import scan
    root=Path(row['project'])
    validate(root,plan)
    if scan(root,['.'])['snapshot']!=review['snapshot']:raise ValueError('Project changed after review; request a fresh review before adopting its follow-up')
    return store.update(ident,plan=str(path),run_dir=None,status='Reviewer follow-up ready to run')
