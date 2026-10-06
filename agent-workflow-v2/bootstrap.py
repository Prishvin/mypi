"""Initialize a private Pi project without a pre-existing Git repository or plan."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shadow

BASE=Path(__file__).resolve().parent


def initialize(project,request=None,create_shadow=True):
    """Create local Git metadata and a request file, preserving existing project content."""
    project=project.resolve();project.mkdir(parents=True,exist_ok=True)
    if not (project/'.git').exists():subprocess.run(['git','init','-q',str(project)],check=True)
    specification=project/'project-request.md'
    if request is not None:
        if specification.exists() and specification.read_text()!=request+'\n':
            raise ValueError('project-request.md already exists; edit it explicitly instead of overwriting it during initialization')
        specification.write_text(request+'\n')
    if not create_shadow:
        return {'project':str(project),'shadow':None,'request_file':str(specification) if specification.exists() else None}
    identity=hashlib.sha256(str(project).encode()).hexdigest()[:12]
    target=BASE/'bootstrap-projects'/identity/'shadow'
    state=shadow.refresh(project,['.'],target)
    return {'project':str(project),'shadow':str(target),'shadow_snapshot':state['snapshot'],
            'request_file':str(specification) if specification.exists() else None,
            'next_step':'qwen-agent --profile PROFILE --project PROJECT --role architect --prompt-file project-request.md',
            'scope':'Local Git metadata only; no remote or cloud upload is required for local planning.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--project',type=Path,required=True);parser.add_argument('--request')
    args=parser.parse_args();print(json.dumps(initialize(args.project,args.request),indent=2))
