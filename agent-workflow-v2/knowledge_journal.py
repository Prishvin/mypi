"""Recover publication if interrupted between the Markdown and provenance writes."""
import json
from pathlib import Path
from runner_process import save


def recover(root, cache, hash_text):
    """Finalize only the pending provenance whose document bytes are present."""
    pending = cache.with_name('pending.json')
    if not pending.exists():
        return
    state = json.loads(pending.read_text())
    path = root/'knowledge.md'
    if path.is_file() and not path.is_symlink() and hash_text(path.read_text()) == state['knowledge_sha256']:
        save(cache, state)
        pending.unlink()


def commit(root, cache, state, text):
    """Write recovery evidence first, then atomically replace document and index."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    pending = cache.with_name('pending.json')
    save(pending, state)
    temporary = root/'.pi-knowledge.tmp'
    if temporary.is_symlink():
        raise ValueError('Refuse a symlink at the knowledge temporary path')
    temporary.write_text(text)
    temporary.replace(root/'knowledge.md')
    save(cache, state)
    pending.unlink()
