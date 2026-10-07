"""Use Pi's native ChatGPT subscription login in a dedicated workflow profile."""
import json
import os
from pathlib import Path
import subprocess
import platform_paths


def prepare_catalog(folder: Path, local_descriptor: dict) -> None:
    """Expose both selectable models in the private subscription configuration."""
    from role_selection import CLOUD_MODEL
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/'models.json'
    data=json.loads(path.read_text()) if path.exists() else {'providers':{}}
    providers=data.setdefault('providers',{})
    cloud=providers.setdefault('openai',{})
    models=cloud.setdefault('models',[])
    if not any(row.get('id')==CLOUD_MODEL for row in models):
        models.append({'id':CLOUD_MODEL,'name':'GPT-6.1 Sol','api':'openai-responses','reasoning':True,
            'input':['text','image'],'contextWindow':1050000,'maxTokens':128000,
            'cost':{'input':2,'output':10,'cacheRead':.1,'cacheWrite':2.5}})
    for model in models:
        if model.get('id')==CLOUD_MODEL:
            from planning_limits import CLOUD_WINDOW,CLOUD_MODEL_OUTPUT
            model.update(contextWindow=CLOUD_WINDOW,maxTokens=CLOUD_MODEL_OUTPUT)
            model['thinkingLevelMap']={'off':None,'minimal':None,'low':'low','medium':'medium',
                                       'high':'high','xhigh':'xhigh','max':'max'}
    providers['local-qwen-workflow']=local_descriptor
    from runner_process import save
    save(path,data)


def require_subscription(folder: Path) -> None:
    """Reject API-key fallback; signing in and model entitlement remain user-owned."""
    auth = folder / 'auth.json'
    credentials = json.loads(auth.read_text()) if auth.exists() else {}
    credential = credentials.get('openai', {})
    if credential.get('type') != 'oauth' or 'chatgpt.tokens.use.direct' not in credential.get('scopes', []):
        raise ValueError('ChatGPT planner needs subscription login: ./qwen-agent --login-chatgpt; then /login openai and choose Sign in with ChatGPT')


def login(base: Path, pi: Path) -> int:
    """Open Pi's normal interactive OAuth flow without changing Codex credentials."""
    from role_selection import CLOUD_MODEL
    folder = base / 'planner-config'
    folder.mkdir(mode=0o700, exist_ok=True)
    (folder / 'settings.json').write_text(json.dumps({'packages': [], 'extensions': [],
        'skills': [], 'promptTemplates': [], 'defaultProjectTrust': 'never'}))
    env = os.environ.copy()
    env['PI_CODING_AGENT_DIR'] = str(folder)
    env.pop('PI_OFFLINE', None)
    return subprocess.run([platform_paths.node(), str(pi), '--provider', 'openai', '--model', CLOUD_MODEL,
        '--tools', '', '--no-extensions', '--no-skills', '--no-prompt-templates'],
        cwd=folder, env=env).returncode
