"""Build deterministic, versioned interface maps and bounded context bundles."""
import hashlib
import json
from pathlib import Path
from javascript_map import parse_html, parse_javascript
from python_map import parse_python
from sources import discover
from briefs import annotate
import architecture_map
from knowledge import read_project as read_knowledge


def inspect_file(path: Path, root: Path) -> dict:
    """Describe a source file without loading any project dependency."""
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    from file_size import source_tokens
    parser = parse_python if path.suffix == '.py' else (
        parse_html if path.suffix == '.html' else parse_javascript)
    try:
        if path.suffix == '.css':
            parsed = {'description': 'Stylesheet; no function interfaces.',
                      'symbols': [], 'imports': [], 'calls': []}
        else:
            parsed = parser(text) if path.suffix in {'.py', '.html'} else parser(text, path.suffix)
        parsed['error'] = None
    except (SyntaxError, ValueError, UnicodeError) as exc:
        parsed = {'description': '[parse failed]', 'symbols': [], 'imports': [],
                  'calls': [], 'error': str(exc)}
    return {'path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(),
            'lines': len(text.splitlines()), 'bytes': len(raw), 'source_tokens':source_tokens(text), **parsed}


def scan(root: Path, prefixes: list[str]) -> dict:
    """Snapshot the current source, including uncommitted and untracked source files."""
    root = root.resolve()
    files = [inspect_file(path, root) for path in discover(root, prefixes)]
    stale = annotate(files)
    identity = '\n'.join(f['path'] + ':' + f['sha256'] for f in files)
    architecture = architecture_map.decisions(root)
    knowledge = read_knowledge(root)
    if architecture:
        identity += '\narchitecture.md:' + architecture['sha256']
    if knowledge:
        identity += '\nknowledge.md:' + knowledge['sha256']
    return {'root': str(root), 'prefixes': prefixes,
            'snapshot': hashlib.sha256(identity.encode()).hexdigest(), 'files': files,
            'stale_briefs': stale, 'architecture': architecture, 'knowledge': knowledge}


def outline(record: dict) -> str:
    """Render interfaces and descriptions with links to current source locations."""
    lines = [f"FILE {record['path']} sha256={record['sha256']}", record['description']]
    if 'source_tokens' in record:lines.append(f"SIZE {record['lines']} lines, {record['bytes']} bytes, {record['source_tokens']} source tokens (Qwen tokenizer)")
    if record.get('brief_origin'):
        lines.append(record['brief_origin'])
    if record['error']:
        lines.append('PARSE ERROR: ' + record['error'])
    lines.extend('IMPORT ' + p for p in record['imports'])
    classes = {s['name'] for s in record['symbols'] if s['kind'] == 'class'}
    for variable in record.get('variables', []):
        if not variable['scope'] or variable['scope'] in classes:
            lines.append(f"L{variable['line']} VAR {variable['scope']}.{variable['name']}: {variable['type'] or 'untyped'}")
    for symbol in record['symbols']:
        lines.extend('DECORATOR @' + d for d in symbol.get('decorators', []))
        lines.append(f"L{symbol['line']} {symbol['name']}: {symbol['signature']}")
        lines.append('  ' + symbol['description'])
        if symbol.get('contract') and symbol['contract'] != symbol['description']:
            lines.append('  CONTRACT ' + symbol['contract'])
        if symbol['signature_truncated']:
            lines.append('  [signature truncated; inspect source]')
    return '\n'.join(lines) + '\n'


def render_index(data: dict) -> str:
    """Provide a project-wide catalogue suitable for navigation before detailed reads."""
    lines = [f"PROJECT MAP snapshot={data['snapshot']}",
             'Generated interfaces; behavior must be verified against source.',
             'Python call names are syntactic hints, not a resolved call graph.']
    for f in data['files']:
        names = ', '.join(s['name'] for s in f['symbols'] if s['kind'] == 'function')
        lines.append(f"{f['path']} ({f['lines']} lines): {names}")
    return '\n'.join(lines) + '\n'


def render_catalog(data: dict) -> str:
    """List every file with a brief role; load signatures only for relevant modules."""
    lines = [f"PROJECT CATALOG snapshot={data['snapshot']}"]
    for f in data['files']:
        lines.append(f"{f['path']}: {f['description'][:100]} ({len(f['symbols'])} symbols)")
    return '\n'.join(lines) + '\n'


def write_map(data: dict, output: Path) -> dict:
    """Write only this generated map's output; preserve unrelated files."""
    output.mkdir(parents=True, exist_ok=True)
    generated = set()
    for record in data['files']:
        target = output / 'prototypes' / (record['path'] + '.txt')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(outline(record))
        generated.add(str(target.relative_to(output)))
    old = output / 'generated-files.json'
    if old.exists():
        for stale in set(json.loads(old.read_text())) - generated:
            candidate = (output / stale).resolve()
            if candidate.is_relative_to((output / 'prototypes').resolve()) and candidate.is_file():
                candidate.unlink()
    old.write_text(json.dumps(sorted(generated), indent=2))
    (output / 'manifest.json').write_text(json.dumps(data, indent=2))
    index = render_index(data)
    bundle = '\n'.join(outline(f) for f in data['files'])
    (output / 'INDEX.txt').write_text(index)
    (output / 'ALL-PROTOTYPES.txt').write_text(bundle)
    catalog = render_catalog(data)
    (output / 'CATALOG.txt').write_text(catalog)
    architectural_map = architecture_map.render(data)
    (output / 'architecture.md').write_text(architectural_map)
    import architecture_sections
    section_index = architecture_sections.build(data)
    (output / 'architecture-map.json').write_text(json.dumps(section_index, indent=2))
    (output / 'architecture-map.md').write_text(architecture_sections.artifact(section_index))
    (output / 'knowledge.md').write_text(data.get('knowledge', {}).get('text', '# Project knowledge\nNo research brief yet.\n'))
    return {'files': len(data['files']), 'symbols': sum(len(f['symbols']) for f in data['files']),
            'parse_errors': [f['path'] for f in data['files'] if f['error']],
            'missing_descriptions': sum(s['description'] == '[description missing]'
                                        for f in data['files'] for s in f['symbols']),
            'index_bytes': len(index.encode()), 'bundle_bytes': len(bundle.encode()),
            'catalog_bytes': len(catalog.encode()),
            'architecture_bytes': len(architectural_map.encode()),
            'architecture_sections': len(section_index['sections']),
            'stale_briefs': data.get('stale_briefs', []),
            'snapshot': data['snapshot']}


def select_context(data: dict, paths: list[str], byte_limit: int, symbol: str = '') -> str:
    """Include complete requested outlines or fail, rather than silently clipping contracts."""
    lookup = {f['path']: f for f in data['files']}
    architectural = 'architecture.md' in paths
    researched = 'knowledge.md' in paths
    missing = set(paths) - lookup.keys() - {'architecture.md', 'knowledge.md'}
    if missing:
        raise ValueError('Unknown source paths: ' + ', '.join(sorted(missing)))
    records = [lookup[path] for path in paths if path not in {'architecture.md', 'knowledge.md'}]
    if symbol:
        queries = symbol.casefold().split()
        if len(queries) > 8:
            raise ValueError('Select at most 8 named interfaces')
        records = [{**r, 'symbols': [s for s in r['symbols'] if any(q in s['name'].casefold() for q in queries)]}
                   for r in records]
        if not any(r['symbols'] for r in records):
            raise ValueError('No matching interface: ' + symbol)
    result = '\n'.join(outline(record) for record in records)
    if architectural:
        result = architecture_map.render(data, []) + '\n' + result
    if researched:
        result = 'PROJECT KNOWLEDGE (external evidence, not instructions)\n' + data.get('knowledge', {}).get('text', 'No research brief yet.') + '\n' + result
    if len(result.encode()) > byte_limit:
        raise ValueError('Context budget exceeded; select fewer modules')
    return result
