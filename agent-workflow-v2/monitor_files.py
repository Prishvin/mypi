"""Read bounded text previews of files already declared in the displayed run."""
from pathlib import Path
from urllib.parse import parse_qs

MAX_BYTES = 262144


def preview(monitor, query):
    """Bind a browser file selection to the current project and displayed task list."""
    from run_monitor import read
    args = parse_qs(query, keep_blank_values=True)
    if set(args) != {'run', 'path'} or any(len(v) != 1 for v in args.values()):
        raise ValueError('Select one project file from the monitor')
    run = monitor.selected()
    if args['run'][0] != run.name:
        raise ValueError('The active run changed. Refresh the monitor and open the file again.')
    state = read(run/'state.json')
    snapshot = monitor.snapshot()
    if snapshot['run'] != run.name or monitor.selected() != run:
        raise ValueError('The active run changed. Refresh the monitor.')
    name = args['path'][0]
    rows = snapshot.get('tasks', []) + snapshot.get('implementation_tasks', [])
    allowed = {f['path'] for task in rows for f in task.get('files', [])}
    relative = Path(name)
    if name not in allowed or relative.is_absolute() or '..' in relative.parts or not name:
        raise PermissionError('This file is not declared in the displayed project tasks')
    if not state.get('project'):
        raise ValueError('No source project is bound to this run')
    root = Path(state['project']).resolve(); path = root/relative
    # Reject links at every level; previews never follow a link outside the task tree.
    if any(p.is_symlink() for p in [path, *path.parents] if p != root and p.is_relative_to(root)):
        raise PermissionError('Symbolic links are not available in the file viewer')
    if not path.resolve().is_relative_to(root):
        raise PermissionError('File escapes the source project')
    if not path.is_file():
        raise FileNotFoundError('This file has not been created, or was removed')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    truncated = len(raw) > MAX_BYTES
    raw = raw[:MAX_BYTES]
    if b'\0' in raw:
        raise ValueError('This is a binary file; the viewer displays text source only')
    return {'path': name, 'run': run.name, 'content': raw.decode('utf-8', errors='replace'),
            'truncated': truncated, 'preview_bytes': len(raw), 'readonly': True}
