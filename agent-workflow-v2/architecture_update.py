"""Append or insert scoped decisions with compare-and-swap and fresh shadow evidence."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from architecture_sections import parse


def digest(raw):
    """Hash original bytes, including line endings, for stale-write detection."""
    return hashlib.sha256(raw).hexdigest() if raw else ''


def insertion(raw, request):
    """Preserve every existing byte and insert only explicitly supplied decision text."""
    text = raw.decode('utf-8')
    newline = '\r\n' if '\r\n' in text else '\n'
    content = request['text']
    if not isinstance(content, str) or not content.strip() or len(content.encode()) > 4096:
        raise ValueError('Decision text must contain 1-4096 UTF-8 bytes')
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    if any(line.lstrip().startswith(('```', '~~~', '#')) for line in content.splitlines()):
        raise ValueError('Decision text must be prose; headings/fences require separate sections')
    action = request['action']
    if action == 'append_section':
        title = request.get('title', '')
        if not isinstance(title, str) or not title.strip() or len(title) > 120 or any(c in title for c in '\r\n#'):
            raise ValueError('New section needs a plain single-line title of 1-120 characters')
        addition = '\n\n## ' + title.strip() + '\n\n' + content.strip() + '\n'
        offset = len(raw)
    elif action == 'insert':
        identifier = request.get('section_id')
        section = next((s for s in parse(text) if s['id'] == identifier), None)
        if section is None:
            raise ValueError('Unknown architecture section ID; reload the index')
        offset = len(''.join(text.splitlines(keepends=True)[:section['direct_end_line']]).encode())
        addition = '\n' + content.strip() + '\n\n'
    else:
        raise ValueError('Use insert or append_section; replacement/deletion is unavailable')
    inserted = addition.replace('\n', newline).encode()
    return raw[:offset] + inserted + raw[offset:]


def binding(session):
    """Bind source document writes to the immutable coding launch and frozen task scope."""
    launch = json.loads((session / 'launch.json').read_text())
    if launch.get('role') != 'code' or not launch.get('state'):
        raise ValueError('Architecture updates require a coding task contract')
    state = Path(launch['state'])
    contract = json.loads(state.read_text())
    root = Path(launch['project']).resolve()
    if Path(contract['before']['root']).resolve() != root or 'architecture.md' not in contract['task']['files']:
        raise ValueError('architecture.md is outside the frozen task scope; request a replan')
    return launch, state, contract, root


def update(session, request):
    """Serialize document updates, reject stale writers, refresh maps and save a receipt."""
    launch, state, contract, root = binding(session)
    path = root / 'architecture.md'
    locks = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'mypi/architecture-locks'
    locks.mkdir(parents=True, exist_ok=True)
    lock_path = locks / (hashlib.sha256(str(root).encode()).hexdigest() + '.lock')
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError('architecture.md must be a regular project file')
        existed = path.exists()
        raw = path.read_bytes() if existed else b''
        current_hash = hashlib.sha256(raw).hexdigest() if existed else ''
        if request.get('expected_sha256') != current_hash:
            raise ValueError('Architecture changed; reload its index and replan the insertion')
        changed = insertion(raw, request)
        handle, temporary = tempfile.mkstemp(prefix='.mypi-architecture-', dir=root)
        try:
            with os.fdopen(handle, 'wb') as stream:
                stream.write(changed)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, path.stat().st_mode & 0o777 if existed else 0o644)
            if path.is_symlink() or path.exists() != existed or (existed and path.read_bytes() != raw):
                raise ValueError('Architecture changed during insertion; reload before retrying')
            os.replace(temporary, path)
        finally:
            if Path(temporary).exists():
                Path(temporary).unlink()
        import shadow
        # A failed refresh leaves the visible edit for recovery, never a false success receipt.
        receipt_path = state.parent / 'architecture-update.json'
        receipt_path.unlink(missing_ok=True)
        summary = shadow.refresh(root, contract['before']['prefixes'], Path(contract['shadow']))
        receipt = dict(action=request['action'], before_sha256=current_hash,
                       after_sha256=hashlib.sha256(changed).hexdigest(), snapshot=summary['snapshot'],
                       state=str(state.resolve()), section_id=request.get('section_id'),
                       sections=summary['architecture_sections'])
        receipt_path.write_text(json.dumps(receipt, indent=2))
        return receipt
