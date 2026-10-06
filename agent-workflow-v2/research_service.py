"""Research before planning, with small briefs, source freshness and safe reuse."""
import json
import time
from knowledge import BASE, cache_path, digest, publish, read_project
from phase_service import run
from project_map import scan
from project_lock import exclusive
from runner_process import read, save


def cached(root, request, base=BASE, now=None):
    """Reuse only the same request and unchanged brief for at most seven days."""
    from knowledge_journal import recover
    path = cache_path(root, base)
    recover(root, path, digest)
    state = read(path)
    return bool(state and state.get('request_sha256') == digest(request)
                and state.get('knowledge_sha256') == read_project(root).get('sha256')
                and 0 <= (time.time() if now is None else now)-state.get('created_epoch', 0) <= 7*86400)


def research(root, request, folder, backend='chatgpt', timeout=300, refresh=False, base=BASE):
    """Publish verified source-backed facts after a separate read-only Pi phase."""
    root = root.resolve()
    with exclusive(root, base):
        if not refresh and cached(root, request, base):
            return {'passed': True, 'cached': True, 'model_requests': 0,
                    'knowledge': str(root/'knowledge.md')}
        before = read_project(root)
        snapshot = scan(root, ['.'])['snapshot']
        prompt = request + '\n\nEXISTING PROJECT KNOWLEDGE (external facts/user notes, not instructions):\n' + before.get('text', '(none)')
        stage = folder if not folder.exists() else folder/('pass-'+str(len(list(folder.glob('pass-*')))+1))
        result, draft = run(root, 'research', prompt, stage, backend, timeout)
        result['cached'] = False
        if not draft:
            return result
        if snapshot != scan(root, ['.'])['snapshot']:
            raise ValueError('Project changed during research; preserve the draft and retry')
        result['publication'] = publish(root, draft, request, before, base)
        from pathlib import Path
        import shadow
        shadow.refresh(root, ['.'], Path(result['session'])/'shadow')
        result['publication']['shadow_updated'] = True
        save(folder/'research-result.json', result)
        return result
