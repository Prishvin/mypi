"""Run the fixed shadow skill before planning, reusing verified current maps."""
import hashlib
import json
from pathlib import Path
from config import FLOW
from project_map import scan
from shadow import verify
from skill_runner import prepare,run


def ensure(job,project):
    """Generate or refresh a shadow outside source; leave existing project files intact."""
    project=project.resolve()
    row=job.store.get(job.ident);old=row.get('shadow_project')
    if old and Path(old).is_dir():
        current=scan(project,['.'])
        if not verify({'shadow':old},current):return {'shadow':old,'cached':True,'snapshot':current['snapshot']}
    identity=hashlib.sha256(str(project).encode()).hexdigest()[:12]
    session=job.store.folder/job.ident/'shadow-setup'/identity
    session.mkdir(parents=True,exist_ok=True)
    (session/'launch.json').write_text(json.dumps({'project':str(project)}))
    job.note('Creating project shadow with shadow-project skill')
    prepare(session,'shadow-project','architect',FLOW)
    result=run(session,'shadow-project',{},'architect',FLOW)
    job.store.update(job.ident,shadow_project=result['data']['shadow'],shadow_skill=result)
    return result['data']
