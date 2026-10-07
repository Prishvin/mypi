"""Bounded structural retrieval for a coding agent; no project-wide code dumps."""
import ast
import os
import json
import hashlib
from pathlib import Path
import subprocess
from project_map import inspect_file


def source_path(root: Path, relative: str) -> Path:
    """Resolve a specific source inside the project and reject parent escapes."""
    root = root.resolve()
    target = (root / relative).resolve()
    if not target.is_file():
        raise ValueError('Not a project file: ' + relative)
    if not target.is_relative_to(root):
        state = os.environ.get('QWEN_WORKFLOW_STATE')
        allowed = json.loads(Path(state).read_text()).get('readonly_tests', {}) if state else {}
        if str(target) not in allowed or hashlib.sha256(target.read_bytes()).hexdigest() != allowed[str(target)]:
            raise ValueError('Not a project file or pinned read-only acceptance fixture: ' + relative)
    return target


def read_symbol(root: Path, relative: str, name: str, offset=0, limit=100) -> dict:
    """Return one exact function/class span in bounded pages with source identity."""
    path = source_path(root, relative)
    record = inspect_file(path, root.resolve() if path.is_relative_to(root.resolve()) else path.parent)
    matches = [s for s in record['symbols'] if s['name'] == name]
    if len(matches) != 1:
        candidates = [s['name'] for s in record['symbols']
                      if s['name'].split('.')[-1].split('#')[0] == name][:8]
        raise ValueError('Use an exact qualified symbol name. Candidates: ' + json.dumps(candidates))
    symbol = matches[0]
    if 'start_byte' in symbol:
        rows = path.read_bytes()[symbol['start_byte']:symbol['end_byte']].decode().splitlines()
    else:
        rows = path.read_text().splitlines()[symbol['line'] - 1:symbol['end']]
    start = max(0, offset)
    stop = min(len(rows), start + max(1, min(limit, 120)))
    excerpt = '\n'.join(f'{symbol["line"] + i}: {rows[i]}' for i in range(start, stop))
    if len(excerpt.encode()) > 12000:
        raise ValueError('Symbol page too large; request fewer lines')
    return {'path': relative, 'sha256': record['sha256'], 'symbol': name,
            'total_lines': symbol['lines'], 'next_offset': stop,
            'more': stop < len(rows), 'source': excerpt}


def read_fixture(root: Path, relative: str, offset=0) -> dict:
    """Read a bounded page of an exact, hash-pinned acceptance fixture only."""
    path = source_path(root, relative)
    state = os.environ.get('QWEN_WORKFLOW_STATE')
    allowed = json.loads(Path(state).read_text()).get('readonly_tests', {}) if state else {}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if allowed.get(str(path)) != digest:
        raise ValueError('Only a pinned acceptance fixture can be read with this action')
    rows = path.read_text().splitlines()
    start = max(0, offset)
    stop = min(len(rows), start + 120)
    excerpt = '\n'.join(f'{i + 1}: {rows[i]}' for i in range(start, stop))
    if len(excerpt.encode()) > 12000:
        raise ValueError('Acceptance fixture page exceeds source budget')
    return {'path': relative, 'sha256': digest, 'source': excerpt,
            'next_offset': stop, 'more': stop < len(rows), 'readonly': True}


def read_page(root: Path, relative: str, offset=0, fixture=False) -> dict:
    """Read one bounded project page; external files still require a pinned fixture."""
    path=source_path(root,relative)
    if not path.is_relative_to(root.resolve()):return read_fixture(root,relative,offset)
    if path.stat().st_size>1048576:raise ValueError('File exceeds 1 MiB; retrieve named symbols or search instead')
    raw=path.read_bytes()
    try:rows=raw.decode('utf-8').splitlines()
    except UnicodeError:raise ValueError('Source pages require UTF-8 text') from None
    start=max(0,offset);stop=start;lines=[];used=0
    for index in range(start,min(len(rows),start+120)):
        line=f'{index+1}: {rows[index]}'
        size=len((line+'\n').encode())
        if used+size>12000:break
        lines.append(line);used+=size;stop=index+1
    if stop==start and start<len(rows):raise ValueError('Source line exceeds page budget; use named symbols or search')
    result={'path':relative,'sha256':hashlib.sha256(raw).hexdigest(),'source':'\n'.join(lines),
            'next_offset':stop,'more':stop<len(rows),'mode':'project-file'}
    if fixture:result['note']='This is project source, served as a bounded file page. Use action=file; fixture is for pinned acceptance tests.'
    return result


def read_symbols(root: Path, relative: str, names: list[str]) -> dict:
    """Preserve valid bounded spans when one requested symbol is missing."""
    source_path(root, relative)  # Validate scope before handling symbol errors.
    if not 1 <= len(names) <= 8:
        raise ValueError('Read 1-8 exact qualified symbol names per call; split larger requests')
    result = {'symbols': [], 'errors': []}
    for name in dict.fromkeys(names):
        try:
            result['symbols'].append(read_symbol(root, relative, name))
        except ValueError as error:
            result['errors'].append({'symbol': name, 'error': str(error)})
    if len(json.dumps(result).encode()) > 12000:
        raise ValueError('Source budget exceeded; select fewer symbols')
    return result


def variables(root: Path, relative: str, query: str) -> dict:
    """Match each requested variable name without exposing initializer values."""
    path = source_path(root, relative)
    record = inspect_file(path, root.resolve() if path.is_relative_to(root.resolve()) else path.parent)
    queries = query.casefold().replace(',', ' ').split()
    matches = [v for v in record.get('variables', [])
               if not queries or any(q in v['name'].casefold() for q in queries)]
    return {'variables': matches[:40], 'total': len(matches), 'truncated': len(matches) > 40}


def python_variables(text: str) -> list[dict]:
    """Describe assigned variables and their scopes/types, without copying values."""
    tree = ast.parse(text)
    result = []

    def visit(node, scope=()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope = (*scope, node.name)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for item in ast.walk(target):
                    if isinstance(item, (ast.Name, ast.Attribute)):
                        if isinstance(item, ast.Name) and not isinstance(item.ctx, ast.Store):
                            continue
                        result.append({'name': ast.unparse(item), 'scope': '.'.join(scope),
                                       'type': ast.unparse(node.annotation) if isinstance(node, ast.AnnAssign) else None,
                                       'line': node.lineno, 'end': node.end_lineno})
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(tree)
    return result


def search(root: Path, paths: list[str], pattern: str, regex=False) -> dict:
    """Search at most five selected files; bound matches and flag incomplete results."""
    if not 1 <= len(paths) <= 5:
        raise ValueError('Choose 1-5 files using the catalogue first')
    chosen = [str(source_path(root, p)) for p in paths]
    args = ['rg', '-n', '--max-count', '20']
    if not regex:
        args.append('-F')
    result = subprocess.run(args + ['--', pattern, *chosen], capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise ValueError(result.stderr[:1000])
    output = result.stdout.replace(str(root.resolve()) + '/', '')
    return {'matches': output[:12000], 'bounded': True,
            'note': 'At most 20 matches per file. Narrow the pattern if more detail is needed.'}
