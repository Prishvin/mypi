"""Report stale architecture, shadow and map evidence without rebuilding anything."""
import json
from pathlib import Path
from project_map import scan
import architecture_sync
import shadow


def check(root, prefixes, output, state=None):
    """Compare current source identities and owned metadata; request explicit rebuild on drift."""
    root = root.resolve()
    reasons = []
    try:
        if not root.is_dir():
            raise ValueError('Project folder is unavailable')
        data = scan(root, prefixes)
        reasons.extend(shadow.verify({'shadow': str(output)}, data))
        reasons.extend(architecture_sync.verify_owned(data))
        if state:
            contract = json.loads(Path(state).read_text())
            if Path(contract['before']['root']).resolve() != root:
                raise ValueError('Consistency check state belongs to a different project')
            reasons.extend(architecture_sync.verify(contract, data))
        snapshot = data['snapshot']
        source_sha256 = data.get('architecture', {}).get('sha256', '')
    except (OSError, ValueError, KeyError) as error:
        reasons.append('Cannot validate current evidence: ' + str(error))
        snapshot, source_sha256 = None, None
    return dict(in_sync=not reasons, rebuild_required=bool(reasons), reasons=reasons,
                snapshot=snapshot, architecture_sha256=source_sha256,
                question='Architecture, shadow or map is out of sync. Rebuild the navigation artifacts now? Use /rebuild.' if reasons else None,
                note='Checks hashes, section links, prototypes and owned interface metadata. Authored architectural meaning still needs review.')


def rebuild(root, prefixes, output, state=None):
    """Rebuild explicitly requested evidence, preserving authored decisions and frozen scope."""
    root = root.resolve()
    if not root.is_dir() or output.resolve().is_relative_to(root):
        raise ValueError('Use an existing project and a shadow outside source')
    if state:
        contract = json.loads(Path(state).read_text())
        if Path(contract['before']['root']).resolve() != root or Path(contract['shadow']).resolve() != output.resolve():
            raise ValueError('Rebuild binding differs from the frozen task')
        architecture_sync.sync(Path(state))
    else:
        current = scan(root, prefixes)
        try:
            previous = json.loads((output / 'manifest.json').read_text())
            if Path(previous['root']).resolve() != root or previous['prefixes'] != prefixes:
                raise ValueError('Previous shadow belongs to a different project or scope')
        except (OSError, ValueError, KeyError):
            previous = current
        owned, _ = architecture_sync.records(current.get('architecture', {}).get('text', ''))
        readable = {r['path'] for r in previous['files']} | {r['path'] for r in current['files']}
        readable |= {p for p in owned if any(pre == '.' or p == pre or p.startswith(pre.rstrip('/')+'/') for pre in prefixes)}
        # User-requested rebuild can maintain this one owned document; it never edits code.
        contract = {'before':previous, 'task':{'files':sorted(readable | {'architecture.md'}), 'architecture_maintenance':True}}
        architecture_sync.sync_contract(contract)
    summary = shadow.refresh(root, prefixes, output)
    report = check(root, prefixes, output, state)
    if not report['in_sync']:
        raise ValueError('Rebuild did not restore consistency: ' + '; '.join(report['reasons']))
    return {'rebuilt':True, 'summary':summary, 'check':report}
