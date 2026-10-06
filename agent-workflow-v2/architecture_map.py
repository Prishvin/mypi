"""Keep brief architectural decisions beside a fresh map of shadow interfaces."""
import hashlib
from pathlib import Path
from urllib.parse import quote


def decisions(root: Path) -> dict:
    """Read existing project decisions as written without importing implementation."""
    path = root / 'architecture.md'
    if path.is_symlink():
        raise ValueError('architecture.md must be a regular project file')
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file():
        raise ValueError('architecture.md must be a regular project file')
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    return {'path': 'architecture.md', 'sha256': hashlib.sha256(raw).hexdigest(), 'text': text}


def cell(text: str) -> str:
    """Keep one brief table cell from breaking the generated Markdown map."""
    return ' '.join(text.split())[:160].replace('|', '\\|')


def render(data: dict, paths=None, offset=0, limit=None) -> str:
    """Render decisions and links to selected current prototypes, never bodies."""
    records = data['files']
    if paths is not None:
        selected = set(paths)
        records = [record for record in records if record['path'] in selected]
    total = len(records)
    records = records[offset:offset + limit] if limit is not None else records[offset:]
    brief = data.get('architecture', {})
    lines = ['# Project architecture', '', 'Source snapshot: `' + data['snapshot'] + '`.',
             '', '## Brief decisions', '', brief.get('text', '').strip() or
             'No project decisions recorded yet. Add a brief project architecture.md.',
             '', '## Shadow map', '', '| Module | Responsibility | Prototypes |',
             '| --- | --- | --- |']
    for record in records:
        target = 'prototypes/' + quote(record['path'] + '.txt', safe='/')
        names = ', '.join(s['name'] for s in record['symbols'] if s['kind'] == 'function')
        lines.append('| `' + cell(record['path']) + '` | ' + cell(record['description']) +
                     ' | [Interfaces](' + target + ') ' + cell(names) + ' |')
    if limit is not None:
        lines += ['', f'Modules {offset + len(records)} of {total}; next offset {offset + len(records)}.']
    lines += ['', 'Generated links describe current interfaces; verify behavior with source and tests.']
    if data.get('knowledge'):
        lines += ['', '[Brief researched facts and source URLs](knowledge.md)']
    return '\n'.join(lines) + '\n'


def navigation(data, paths=None, offset=0, limit=10, section_offset=0):
    """Return compact decision headings and a bounded module page."""
    import architecture_sections
    index = architecture_sections.render(architecture_sections.build(data), section_offset, 10)
    without_prose = {**data, 'architecture': {}}
    return index + '\n' + render(without_prose, paths, offset, limit)
