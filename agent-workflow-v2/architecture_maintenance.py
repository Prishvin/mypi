"""Classify source changes and maintain architecture, shadow and compact map in Python."""
import json
from pathlib import Path
from project_map import scan
import architecture_sync
import shadow


def interface_identity(record):
    """Compare contracts rather than implementation bodies when classifying an edit."""
    if record is None:
        return None
    return {'symbols':[{k:s.get(k) for k in ('name','kind','signature','description')} for s in record['symbols']],
            'variables':record.get('variables',[]), 'imports':record.get('imports',[]), 'error':record.get('error')}


def changes(before, after):
    """Detect additions/deletions/edits and unambiguous exact-content renames."""
    old = {r['path']:r for r in before['files']}
    new = {r['path']:r for r in after['files']}
    rows = []
    for path in sorted(old.keys() | new.keys()):
        previous, current = old.get(path), new.get(path)
        if (previous or {}).get('sha256') == (current or {}).get('sha256'):
            continue
        kind = 'added' if previous is None else 'deleted' if current is None else 'modified'
        rows.append(dict(path=path, type=kind, interface_changed=interface_identity(previous)!=interface_identity(current)))
    deleted = [row for row in rows if row['type']=='deleted']
    added = [row for row in rows if row['type']=='added']
    for row in deleted:
        candidates = [r for r in added if new[r['path']]['sha256']==old[row['path']]['sha256']]
        same_deleted = [r for r in deleted if old[r['path']]['sha256']==old[row['path']]['sha256']]
        if len(candidates)==len(same_deleted)==1:
            target = candidates[0]
            target.update(type='renamed', from_path=row['path'])
            rows.remove(row)
    return rows


def maintain(root, prefixes, output, state):
    """Refresh automatically after authorized mutations, rebuilding missing/stale maps only."""
    root, output = root.resolve(), output.resolve()
    if not root.is_dir() or output.is_relative_to(root):
        raise ValueError('Use an existing project and a shadow outside source')
    contract = json.loads(state.read_text())
    if Path(contract['before']['root']).resolve()!=root or Path(contract['shadow']).resolve()!=output:
        raise ValueError('Maintenance binding differs from the frozen task')
    try:
        previous = json.loads((output/'manifest.json').read_text())
        if Path(previous['root']).resolve()!=root or previous['prefixes']!=prefixes:
            raise ValueError('Wrong prior project or scope')
    except (OSError,ValueError,KeyError):
        previous = contract['before']
    architecture_changed = architecture_sync.sync(state)
    current = scan(root,prefixes)
    change_types = changes(previous,current)
    stale = shadow.verify({'shadow':str(output)},current)
    if stale:
        summary = shadow.refresh(root,prefixes,output)
    else:
        index = json.loads((output/'architecture-map.json').read_text())
        summary = dict(snapshot=current['snapshot'], files=len(current['files']),
                       symbols=sum(len(f['symbols']) for f in current['files']),
                       architecture_sections=len(index['sections']),
                       parse_errors=[f['path'] for f in current['files'] if f['error']])
    errors = shadow.verify({'shadow':str(output)},current) + architecture_sync.verify(contract,current) + architecture_sync.verify_owned(current)
    if errors:
        raise ValueError('Maintenance is not current: '+'; '.join(errors))
    return {**summary, 'changes':change_types, 'architecture_updated':architecture_changed,
            'architecture_sha256':current.get('architecture', {}).get('sha256', ''),
            'map_rebuilt':bool(stale), 'in_sync':True, 'implementation':'Python; no model request'}
