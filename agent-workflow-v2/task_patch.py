"""Measure the final task patch against its preserved original source baseline."""
from difflib import SequenceMatcher
from pathlib import Path

LIMIT = 300


def measure(data):
    """Share exact gate accounting with recovery; failed edits never reset the budget."""
    root = Path(data['before']['root'])
    counts = {}
    for name, original in data.get('declared_text', {}).items():
        path = root / name
        current = path.read_text() if path.is_file() else ''
        lines = sum(b - a + d - c for tag, a, b, c, d in
                    SequenceMatcher(a=original.splitlines(), b=current.splitlines(),
                                    autojunk=False).get_opcodes() if tag != 'equal')
        if lines:
            counts[name] = lines
    total = sum(counts.values())
    return {'changed_lines': total, 'limit': LIMIT, 'by_file': counts,
            'over_limit_by': max(0, total - LIMIT),
            'baseline_policy': 'Cumulative final diff against the original unfinished task baseline, '
                'including source, tests and declared architecture edits. The next repair inherits '
                'this baseline; existing failed files are not accepted legacy code. A small incremental '
                'repair does not erase existing size debt. estimated_changed_lines must estimate '
                'the final cumulative patch. Preserve behavior, readable code and coverage; do not '
                'minify code or drop tests to fit. If this requires splitting scope, report that need.'}
