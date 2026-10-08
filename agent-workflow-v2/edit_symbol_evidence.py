"""Use exact parsed declaration names as read-only hints after an edit mismatch."""
import json


def locate(text, old, suffix):
    """Return one current unambiguous declaration; never choose replacement text."""
    if suffix not in {'.py', '.js', '.mjs', '.cjs', '.ts', '.tsx'}:
        return None
    from python_map import parse_python
    from javascript_map import parse_javascript
    parser = parse_python if suffix == '.py' else lambda value: parse_javascript(value, suffix)
    try:
        proposed, current = parser(old), parser(text)
    except (SyntaxError, ValueError, UnicodeError):
        return None

    def declarations(record):
        rows = list(record['symbols'])
        names = {row['name'] for row in rows}
        rows += [{**row, 'name': '.'.join(filter(None, [row['scope'], row['name']]))}
                 for row in record.get('variables', [])
                 if '.'.join(filter(None, [row['scope'], row['name']])) not in names]
        return rows

    names = [row['name'] for row in declarations(proposed)
             if '.' not in row['name'] and '#' not in row['name'] and '<' not in row['name']][:3]
    rows = text.splitlines(keepends=True)
    for name in names:
        matches = [row for row in declarations(current)
                   if row['name'].split('.')[-1].split('#')[0] == name]
        if len(matches) != 1 or matches[0]['name'] != name:
            continue
        symbol = matches[0]
        start = symbol['line'] - 1
        stop, source = start, ''
        for row in rows[start:min(symbol['end'], start + 80)]:
            if len(json.dumps(source + row, ensure_ascii=False).encode()) > 8000:
                break
            source += row
            stop += 1
        if not source:
            continue
        return {'status': 'unique_symbol_reference', 'symbol': name,
                'hint': 'Exact parsed name identifies current context only; the old body/signature did not match. No replacement was applied.',
                'start_line': start + 1, 'end_line': stop, 'source': source,
                'next_offset': stop, 'more': stop < len(rows),
                'symbol_truncated': stop < symbol['end']}
    return None
