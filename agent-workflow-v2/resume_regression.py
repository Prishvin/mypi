"""Check accepted behavior without treating new unfinished tests as regressions."""
from pathlib import Path
import shutil
import tempfile
from runner_process import read, save


def check(root, completed, pending, folder):
    """Run original commands; isolate new pending discovery files only for resume."""
    from runner_evidence import regression
    result = regression(root, completed, folder)
    if result['passed'] or result['reason'] != 'regressions_passed':
        return result
    accepted = set()
    for task in completed:
        frozen = read(Path(task['evidence']).parent/'task-state.json')
        if not frozen.get('shadow'):
            return result
        manifest = read(Path(frozen['shadow'])/'manifest.json')
        if not manifest.get('files'):
            return result
        accepted.update(f['path'] for f in manifest['files'])
        accepted.update(task['files'])
    pending_files = {name for task in pending for name in task['files']}
    omitted = set()
    for row in result['tests']:
        if row['exit_code'] == 0:
            continue
        argv = row['argv']
        # Only exact Node directory discovery is recognized. Unknown runners fail closed.
        if len(argv) != 3 or Path(argv[0]).name != 'node' or argv[1] != '--test':
            return result
        directory = Path(argv[2])
        if directory.is_absolute() or '..' in directory.parts or not (root/directory).is_dir():
            return result
        new = {str(p.relative_to(root)) for p in (root/directory).rglob('*')
               if p.is_file() and str(p.relative_to(root)) not in accepted}
        if not new or not new <= pending_files:
            return result
        omitted.update(new)
    if not omitted:
        return result
    original = folder/'resume-full-regression.json'
    save(original, result)
    with tempfile.TemporaryDirectory(prefix='resume-check-', dir=folder) as tmp:
        view = Path(tmp)/'project'

        def ignore(directory, names):
            """Omit only identified unfinished files and repository administration."""
            relative = Path(directory).relative_to(root)
            return [name for name in names if name == '.git' or str(relative/name) in omitted]

        shutil.copytree(root, view, symlinks=True, ignore=ignore)
        evidence = folder/'resume-accepted-regression'; evidence.mkdir(exist_ok=True)
        checked = regression(view, completed, evidence)
    checked.update(full_suite_evidence=str(original), pending_discovery_files=sorted(omitted),
        note='Resume-only accepted-test view. The unchanged full commands run in the live project before task acceptance.')
    save(folder/'resume-regression.json', checked)
    return checked
