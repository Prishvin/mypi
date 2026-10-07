"""Read bounded current text after a rejected edit; never repair or mutate source."""
import argparse
import hashlib
import json
from pathlib import Path
import re

MAX_REQUEST = 65536
MAX_RESULT = 12000


def encoded_size(value):
    """Count serialized evidence bytes, including JSON escapes."""
    return len(json.dumps(value, ensure_ascii=False).encode('utf-8'))


def current_span(text, old):
    """Locate one exact unique line anchor, without fuzzy replacement guesses."""
    if old in text:
        return {'status': 'old_text_present', 'occurrences': text.count(old)}
    rows = text.splitlines(keepends=True)
    positions = {}
    for index, row in enumerate(rows):
        positions.setdefault(row.rstrip('\r\n'), []).append(index)
    for old_index, line in enumerate(old.splitlines()):
        # Punctuation-only braces and short common statements aren't useful anchors.
        if len(line.strip()) < 12 or not re.search(r'[A-Za-z_]{3}', line):
            continue
        matches = positions.get(line, [])
        if len(matches) != 1:
            continue
        anchor = matches[0]
        start = max(0, anchor - min(old_index, 8))
        stop = start
        source = ''
        for row in rows[start:start + min(80, max(12, len(old.splitlines()) + 4))]:
            if encoded_size(source + row) > 8000:
                break
            source += row
            stop += 1
        if stop <= anchor:
            continue
        return {'status': 'unique_line_anchor', 'anchor_line': anchor + 1,
                'old_anchor_line': old_index + 1, 'start_line': start + 1,
                'end_line': stop, 'source': source, 'next_offset': stop,
                'more': stop < len(rows)}
    return {'status': 'no_unique_anchor',
            'hint': 'Use source_query search with an exact distinctive fragment, then file with its line offset.'}


def collect(root, state, request):
    """Enforce frozen editable scope before reading one UTF-8 file snapshot."""
    if not isinstance(request, dict):
        raise ValueError('Edit evidence request must be an object')
    root = root.resolve()
    contract = json.loads(state.read_text())
    if Path(contract['before']['root']).resolve() != root:
        raise ValueError('Edit evidence root differs from the frozen task')
    relative = request.get('path')
    if not isinstance(relative, str) or not relative:
        raise ValueError('Edit evidence requires an exact file path')
    path = (root / relative).resolve()
    allowed = {(root / name).resolve() for name in contract['task']['files']}
    if not path.is_relative_to(root) or path not in allowed:
        raise ValueError('Edit evidence file is outside the frozen editable scope')
    if not path.is_file():
        raise ValueError('Edit evidence requires an existing regular file')
    edits = request.get('old_texts')
    if (not isinstance(edits, list) or not 1 <= len(edits) <= 8
            or any(not isinstance(old, str) or not old for old in edits)
            or encoded_size(request) > MAX_REQUEST):
        raise ValueError('Provide 1-8 nonempty oldText values within 64 KiB')
    with path.open('rb') as stream:
        raw = stream.read(1048577)
    if len(raw) > 1048576:
        raise ValueError('File exceeds 1 MiB; retrieve selected symbols instead')
    try:
        text = raw.decode('utf-8')
    except UnicodeError:
        raise ValueError('Edit evidence requires UTF-8 text') from None
    if '\x00' in text:
        raise ValueError('Edit evidence requires text without NUL bytes')
    result = {'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(raw).hexdigest(),
              'readonly': True, 'excerpts': [], 'omitted_edits': 0}
    for index, old in enumerate(edits):
        row = {'edit_index': index, **current_span(text, old)}
        candidate = {**result, 'excerpts': [*result['excerpts'], row]}
        if encoded_size(candidate) > MAX_RESULT:
            result['omitted_edits'] += 1
        else:
            result['excerpts'].append(row)
    return result


def main():
    """Receive edit text via a private temporary JSON file, never shell arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--input', required=True, type=Path)
    args = parser.parse_args()
    try:
        with args.input.open('rb') as stream:
            raw = stream.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise ValueError('Edit evidence request exceeds 64 KiB')
        result = collect(args.root, args.state, json.loads(raw))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
