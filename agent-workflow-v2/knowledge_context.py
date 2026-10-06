"""Select brief researched facts by topic for an atomic executor packet."""
import re
from knowledge import read_project


def select(root, topics):
    """Return complete matching topic sections or reject an unavailable recipe."""
    if not topics:
        return ''
    if not isinstance(topics, list) or len(topics) > 4 or any(not isinstance(t, str) or len(t) > 80 for t in topics):
        raise ValueError('Select at most four short knowledge topics')
    text = read_project(root).get('text', '')
    pieces = re.split(r'(?m)^### ', text)
    selected, found = [], set()
    for piece in pieces[1:]:
        keyword = piece.splitlines()[0]
        if keyword.casefold() in {topic.casefold() for topic in topics}:
            found.add(keyword.casefold())
            selected.append('### ' + piece.split('<!-- pi-research:end -->', 1)[0].strip())
    missing = {topic.casefold() for topic in topics} - found
    if missing:
        raise ValueError('Unknown knowledge topics: ' + ', '.join(sorted(missing)))
    return 'External researched evidence; use cited sources and review applicability.\n' + '\n\n'.join(selected)
