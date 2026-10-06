"""Maintain a small owned interface record while preserving authored architecture prose."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from project_map import scan

START = '<!-- mypi-interfaces:start -->'
END = '<!-- mypi-interfaces:end -->'


def scoped(task):
    """Declare architecture maintenance before freezing the coding task, never afterward."""
    from sources import EXTENSIONS
    files = list(task['files'])
    maintained = any(Path(path).suffix in EXTENSIONS for path in files)
    if maintained and 'architecture.md' not in files:
        files.append('architecture.md')
    if len(files) > 8:
        raise ValueError('Reserve a task file for architecture maintenance; split into at most 7 source files')
    return {**task, 'files': files, 'architecture_maintenance': maintained}


def records(text):
    """Read only the explicitly owned metadata block, refusing malformed ownership markers."""
    if START not in text and END not in text:
        return {}, None
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) >= text.index(END):
        raise ValueError('Malformed mypi interface markers; repair the owned block before continuing')
    start, end = text.index(START), text.index(END) + len(END)
    block = text[start+len(START):text.index(END)].strip()
    try:
        data = json.loads(block)
        if not isinstance(data, dict) or any(not isinstance(v, dict) for v in data.values()):
            raise ValueError('Expected path/interface objects')
    except ValueError as error:
        raise ValueError('Malformed mypi interface metadata: ' + str(error)) from error
    return data, (start, end)


def desired(contract, data, previous):
    """Refresh named interfaces for changed or previously tracked task files, including deletion."""
    before = {r['path']: r for r in contract['before']['files']}
    after = {r['path']: r for r in data['files']}
    result = dict(previous)
    for path in contract['task']['files']:
        old, current = before.get(path), after.get(path)
        if old is None and current is None and path not in previous:
            continue
        if path not in previous and (old or {}).get('sha256') == (current or {}).get('sha256'):
            continue
        if current is None:
            result[path] = {'deleted': True}
        else:
            symbols = current['symbols']
            result[path] = dict(sha256=current['sha256'], purpose=current['description'],
                                functions=[s['name'] for s in symbols if s['kind'] == 'function'],
                                classes=[s['name'] for s in symbols if s['kind'] == 'class'],
                                parse_error=current['error'])
    return result


def sync(state):
    """Insert or refresh the owned block atomically; existing prose remains byte-for-byte."""
    contract = json.loads(state.read_text())
    return sync_contract(contract)


def sync_contract(contract):
    """Refresh only owned architecture metadata from a bound maintenance contract."""
    if not contract['task'].get('architecture_maintenance'):
        return False
    if 'architecture.md' not in contract['task']['files']:
        raise ValueError('Architecture maintenance requires frozen architecture.md scope')
    root = Path(contract['before']['root']).resolve()
    path = root / 'architecture.md'
    locks = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'mypi/architecture-locks'
    locks.mkdir(parents=True, exist_ok=True)
    lock_path = locks / (hashlib.sha256(str(root).encode()).hexdigest() + '.lock')
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.is_symlink() or path.exists() and not path.is_file():
            raise ValueError('architecture.md must be a regular project file')
        raw = path.read_bytes() if path.exists() else b''
        text = raw.decode('utf-8')
        previous, region = records(text)
        data = scan(root, contract['before']['prefixes'])
        updated = desired(contract, data, previous)
        if updated == previous:
            return False
        newline = '\r\n' if '\r\n' in text else '\n'
        payload = '{\n' + ',\n'.join(json.dumps(key, ensure_ascii=False) + ': ' + json.dumps(value, ensure_ascii=False, sort_keys=True) for key, value in sorted(updated.items())) + '\n}'
        payload = payload.replace('<', '\\u003c')
        block = START + '\n' + payload + '\n' + END
        block = block.replace('\n', newline)
        if region:
            revised = text[:region[0]] + block + text[region[1]:]
        else:
            revised = text + (newline if text and not text.endswith('\n') else '') + newline + '## Maintained shadow interfaces {#mypi-interfaces}' + newline + newline + block + newline
        handle, temporary = tempfile.mkstemp(prefix='.mypi-architecture-', dir=root)
        try:
            with os.fdopen(handle, 'wb') as stream:
                stream.write(revised.encode())
                stream.flush(); os.fsync(stream.fileno())
            os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
            if path.is_symlink() or (path.read_bytes() if path.exists() else b'') != raw:
                raise ValueError('Architecture changed during maintenance; retry with fresh evidence')
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return True


def verify(contract, data):
    """Block completion when current code interfaces have no corresponding maintained record."""
    if not contract['task'].get('architecture_maintenance'):
        return []
    try:
        text = data.get('architecture', {}).get('text', '')
        previous, _ = records(text)
        if desired(contract, data, previous) != previous:
            return ['Architecture interface record is stale; refresh after every code edit']
    except ValueError as error:
        return [str(error)]
    return []


def verify_owned(data):
    """Detect stale tracked interface entries even in a read-only inspection session."""
    try:
        previous, _ = records(data.get('architecture', {}).get('text', ''))
        current = {record['path']: record for record in data['files']}
        errors = []
        for path, entry in previous.items():
            if not any(pre == '.' or path == pre or path.startswith(pre.rstrip('/')+'/') for pre in data['prefixes']):
                continue
            record = current.get(path)
            valid = (record is None and entry.get('deleted') is True) or (record is not None and
                    entry.get('sha256') == record['sha256'] and not entry.get('deleted'))
            if not valid:
                errors.append('Maintained architecture interface is stale: ' + path)
        return errors
    except (ValueError, KeyError) as error:
        return ['Cannot validate maintained architecture: ' + str(error)]
