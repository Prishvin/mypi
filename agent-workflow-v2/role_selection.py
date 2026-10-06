"""Persist per-project planner/reviewer choices outside source and frozen plans."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
from runner_process import save

BASE = Path(__file__).resolve().parent
CLOUD_MODEL = 'gpt-6.1-sol'
DEFAULTS = {'planner':'qwen','reviewer':'qwen'}


def backend(value):
    """Accept a friendly local alias while keeping one internal provider spelling."""
    if value in ('local','qwen'):
        return 'qwen'
    if value == 'chatgpt':
        return value
    raise ValueError('Choose chatgpt or local')


def path_for(project, base=BASE):
    """Bind preferences to the canonical project without adding source files."""
    return base/'project-settings'/(hashlib.sha256(str(project.resolve()).encode()).hexdigest()+'.json')


def load(project, base=BASE):
    """Return validated preferences with explicit effective models and efforts."""
    path=path_for(project,base)
    values=json.loads(path.read_text()) if path.exists() else {}
    result={role:backend(values.get(role,default)) for role,default in DEFAULTS.items()}
    result['models']={role:{'backend':result[role], 'model':CLOUD_MODEL if result[role]=='chatgpt' else 'mtplx-quality',
                           'reasoning':'xhigh' if result[role]=='chatgpt' else 'medium'} for role in DEFAULTS}
    return result


def select(project, role, value, base=BASE):
    """Update one role atomically without losing a concurrent change to the other."""
    if role not in DEFAULTS:
        raise ValueError('Unknown selectable role')
    value=backend(value); path=path_for(project,base); path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        values=json.loads(path.read_text()) if path.exists() else {}
        values[role]=value
        save(path,values)
    return load(project,base)


def main():
    """Bridge slash commands and scripts to the same preferences."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--role',choices=DEFAULTS)
    parser.add_argument('--value')
    args=parser.parse_args()
    print(json.dumps(select(args.project,args.role,args.value) if args.role else load(args.project)))


if __name__=='__main__': main()
