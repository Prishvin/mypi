"""Discover source without importing the project or following symbolic links."""
from pathlib import Path
import subprocess

EXTENSIONS = {'.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.html', '.css'}


def discover(root: Path, prefixes: list[str]) -> list[Path]:
    """Return Git-visible source paths restricted to the configured components."""
    result = subprocess.run(
        ['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others',
         '--exclude-standard'], capture_output=True)
    if result.returncode:
        return discover_plain(root,prefixes)
    paths = set(result.stdout.decode().split('\0')) - {''}
    return sorted(root / p for p in paths
                  if Path(p).suffix in EXTENSIONS
                  and not any(part in {'.venv', 'venv', 'node_modules', 'build', 'dist'} for part in Path(p).parts)
                  and any(pre == '.' or p == pre or p.startswith(pre.rstrip('/') + '/')
                          for pre in prefixes)
                  and not (root / p).is_symlink() and (root / p).is_file())


def discover_plain(root, prefixes):
    """Inspect non-Git folders without initializing Git or executing project code."""
    import os
    root=root.resolve();paths=[];total=0
    excluded={'.git','.venv','venv','node_modules','build','dist','__pycache__','.pytest_cache','.mypy_cache'}
    visited=0
    for base,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if d not in excluded and not (Path(base)/d).is_symlink()]
        visited+=1
        if visited>5000:raise ValueError('Folder is too broad for inspection; select a smaller project folder')
        for name in names:
            path=Path(base)/name;relative=path.relative_to(root).as_posix()
            if path.suffix not in EXTENSIONS or path.is_symlink():continue
            if not any(pre=='.' or relative==pre or relative.startswith(pre.rstrip('/')+'/') for pre in prefixes):continue
            size=path.stat().st_size;total+=size;paths.append(path)
            if size>1048576 or total>33554432 or len(paths)>2000:
                raise ValueError('Source map exceeds bounded inspection limits; select a smaller project folder')
    return sorted(paths)


def brief(text: str | None) -> str:
    """Extract a bounded first description; mark missing documentation explicitly."""
    if not text:
        return '[description missing]'
    return ' '.join(text.strip().splitlines()[0].split())[:180]
