"""Resolve a bounded set of symbol queries across explicit source paths."""
import json
from retrieval import source_path, symbol_matches, read_symbol
from project_map import inspect_file


def read_across(root, paths, names):
    """Return path-labelled matches; never pair filenames and symbols by position."""
    if not 1 <= len(paths) <= 5 or not 1 <= len(names) <= 8:
        raise ValueError('Select 1-5 explicit paths and 1-8 symbol names')
    paths = list(dict.fromkeys(paths)); names = list(dict.fromkeys(names))
    targets = [(name, source_path(root, name)) for name in paths]
    result = {'symbols': [], 'errors': []}
    found, ambiguous = set(), set()
    for relative, path in targets:
        if path.stat().st_size > 1048576:
            raise ValueError('Source file exceeds 1 MiB; select a smaller source file')
        record = inspect_file(path, root.resolve() if path.is_relative_to(root.resolve()) else path.parent)
        if record.get('error'):
            result['errors'].append({'path': relative, 'error': record['error']})
            continue
        for name in names:
            matches = symbol_matches(record, name)
            if len(matches) > 1:
                ambiguous.add(name)
                result['errors'].append({'path': relative, 'symbol': name,
                    'error': 'Ambiguous within this file; choose an exact qualified name',
                    'candidates': [row['name'] for row in matches[:8]]})
            elif len(matches) == 1:
                result['symbols'].append(read_symbol(root, relative, name))
                found.add(name)
    result['errors'] += [{'symbol': name, 'error': 'Not found in the selected files'}
                         for name in names if name not in found | ambiguous]
    result['passed'] = bool(result['symbols'])
    if len(json.dumps(result, indent=2).encode()) > 12000:
        raise ValueError('Source budget exceeded; select fewer files/symbols or page one symbol')
    return result
