"""Index Markdown decisions by stable heading IDs without changing the document."""
import re
import hashlib
from collections import Counter
from pathlib import PurePosixPath
from urllib.parse import unquote


def headings(text):
    """Recognize ATX/Setext headings outside fenced code; preserve source line numbers."""
    lines = text.splitlines(keepends=True)
    result, fence, paragraph = [], None, False
    for pos, line in enumerate(lines):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= fence[1] and not marker[2].strip():
                fence = None
            paragraph = False
            continue
        if marker:
            fence = (marker[1][0], len(marker[1]))
            paragraph = False
            continue
        atx = re.match(r'^ {0,3}(#{1,6})(?:[ \t]+|$)(.*)', line.rstrip('\r\n'))
        if atx:
            result.append((pos, len(atx[1]), re.sub(r'[ \t]+#+[ \t]*$', '', atx[2]).strip()))
        elif paragraph and pos and re.fullmatch(r' {0,3}(?:=+|-+)[ \t]*\r?\n?', line) and lines[pos-1].strip():
            if not any(h[0] == pos-1 for h in result):
                result.append((pos-1, 1 if line.lstrip().startswith('=') else 2, lines[pos-1].strip()))
        paragraph = bool(line.strip()) and not atx and not re.fullmatch(r' {0,3}(?:=+|-+)[ \t]*\r?\n?', line) and not line.startswith(('    ', '\t'))
    return lines, result


def slug(title):
    """Use readable Unicode IDs; hierarchy distinguishes repeated names in branches."""
    explicit = re.search(r'\{#([\w-]+)\}\s*$', title)
    value = explicit[1] if explicit else re.sub(r'\W+', '-', title.casefold()).strip('-')
    if len(value) > 32:
        import hashlib
        value = value[:24] + '-' + hashlib.sha256(value.encode()).hexdigest()[:7]
    return value or 'section'


def parse(text):
    """Return inclusive section ranges and direct-body boundaries, including preamble."""
    lines, found = headings(text)
    if lines and (not found or found[0][0] > 0):
        found.insert(0, (0, 0, 'Preamble'))
    stack, counts, sections = [], Counter(), []
    for index, (pos, level, title) in enumerate(found):
        while stack and stack[-1]['level'] >= level:
            stack.pop()
        parent = stack[-1]['id'] if stack else None
        base = (parent + '/' if parent else '') + slug(title)
        counts[base] += 1
        identifier = base if counts[base] == 1 else base + '~' + str(counts[base])
        end = next((p for p, depth, _ in found[index+1:] if depth <= level), len(lines))
        direct_end = found[index+1][0] if index+1 < len(found) else len(lines)
        section = dict(id=identifier, title=title, level=level, parent=parent,
                       start_line=pos+1, end_line=end, direct_end_line=direct_end)
        sections.append(section)
        if level:
            stack.append(section)
    return sections


def associations(text, paths):
    """Link literal paths/directories and unique filenames; expose ambiguous basenames."""
    known = set(paths)
    basenames = {}
    for path in paths:
        basenames.setdefault(PurePosixPath(path).name, []).append(path)
    links, unresolved = set(), set()
    # Markdown link destinations and inline literals share the same path grammar.
    candidates = re.findall(r'[\w.@+-]+(?:/[\w.@+-]+)*/?', unquote(text))
    for token in candidates:
        token = token.removeprefix('./').rstrip('.,:;')
        if token in known:
            links.add(token)
        elif token.endswith('/'):
            links.update(p for p in paths if p.startswith(token))
        elif token in basenames:
            matches = basenames[token]
            if len(matches) == 1:
                links.add(matches[0])
            else:
                unresolved.add(token)
    return sorted(links), sorted(unresolved)


def build(data, counter=None):
    """Create a deterministic index tied to both source decisions and source interfaces."""
    if counter is None:
        from shadow_navigation import count
        counter = count
    brief = data.get('architecture', {})
    text = brief.get('text', '')
    lines = text.splitlines(keepends=True)
    paths = [record['path'] for record in data['files']]
    sections = parse(text)
    interfaces = []
    for record in data['files']:
        symbols = record['symbols']
        interfaces.append(dict(path=record['path'], functions=[s['name'] for s in symbols if s['kind'] == 'function'],
                               classes=[s['name'] for s in symbols if s['kind'] == 'class'],
                               keywords=sorted({s['name'] for s in symbols if s['kind'] not in {'function', 'class'}} |
                                               {v['name'] for v in record.get('variables', [])[:8]} | {(re.search(r'(?:from|import)\s+([\w.]+)', item).group(1) if re.search(r'(?:from|import)\s+([\w.]+)', item) else item[:80]) for item in record.get('imports', [])[:4]})[:12]))
    symbol_owners = {}
    for record in interfaces:
        for name in record['functions'] + record['classes']:
            symbol_owners.setdefault(name, set()).add(record['path'])
    for section in sections:
        content = ''.join(lines[section['start_line']-1:section['end_line']])
        files, ambiguous = associations(content, paths)
        linked = set(files)
        ambiguous_symbols = []
        words = set(re.findall(r'[\w.]+', content))
        for name in words & symbol_owners.keys():
            # Avoid interpreting common prose verbs as architectural symbol references.
            if len(name) < 4 or name in {'main', 'test', 'print', 'open', 'read', 'write', 'close'}:
                continue
            owners = symbol_owners[name]
            if len(owners) == 1:
                linked.update(owners)
            else:
                ambiguous_symbols.append(name)
        files = sorted(linked)
        direct = ''.join(lines[section['start_line']-1:section['direct_end_line']])
        section.update(tokens=counter(content), content_sha256=hashlib.sha256(content.strip().encode()).hexdigest(),
                       files=files, ambiguous_files=ambiguous,
                       ambiguous_symbols=sorted(ambiguous_symbols),
                       keywords=keywords(section['title'] + '\n' + direct))
    return dict(version=1, source='architecture.md', source_sha256=brief.get('sha256', ''),
                snapshot=data['snapshot'], sections=sections, files=interfaces)


def render(index, offset=0, limit=10):
    """Page headings and links, never duplicate the architecture prose in navigation."""
    from architecture_map import cell
    rows = index['sections'][offset:offset+limit]
    lines = ['# Architecture section index', '', 'Source SHA256: ' + index['source_sha256'],
             'Source snapshot: ' + index['snapshot'], '',
             '| Section ID | Heading / keywords | Lines | Tokens | Shadow source files |',
             '| --- | --- | --- | --- | --- |']
    for row in rows:
        files = ', '.join(row['files'][:5])
        if len(row['files']) > 5:
            files += f" (+{len(row['files'])-5} more; use section reads or module pages)"
        lines.append(f"| {cell(row['id'])} | {cell(row['title'] + ' / ' + ', '.join(row['keywords']))} | {row['start_line']}-{row['end_line']} | {row['tokens']} | {cell(files)} |")
    lines += ['', f"Sections {offset+len(rows)} of {len(index['sections'])}; next section offset {offset+len(rows)}.",
              'Read selected IDs with architecture-section and source_sha256. Line ranges are navigation labels, not stable identities.']
    return '\n'.join(lines) + '\n'


def selected(data, identifiers, expected_sha256=None):
    """Resolve complete selected sections, rejecting unknown IDs or stale decisions."""
    index = build(data)
    if expected_sha256 is not None and index['source_sha256'] != expected_sha256:
        raise ValueError('Architecture changed; reload the section index and replan')
    if not identifiers or any(not isinstance(i,str) for i in identifiers) or len(identifiers) > 5 or len(set(identifiers)) != len(identifiers):
        raise ValueError('Select 1-5 distinct architecture section IDs')
    lookup = {row['id']: row for row in index['sections']}
    lines = data.get('architecture', {}).get('text', '').splitlines(keepends=True)
    result = []
    for identifier in identifiers:
        if identifier not in lookup:
            raise ValueError('Unknown architecture section ID: ' + identifier)
        row = lookup[identifier]
        result.append((row, ''.join(lines[row['start_line']-1:row['end_line']])))
    return result


def page(data, identifier, expected_sha256, offset=0, max_bytes=8000):
    """Read a bounded character page, even when a section has one enormous line."""
    row, text = selected(data, [identifier], expected_sha256)[0]
    if type(offset) is not int or offset < 0 or offset > len(text):
        raise ValueError('Section offset must be within its current character range')
    if not 256 <= max_bytes <= 8000:
        raise ValueError('Section page budget must be 256-8000 bytes')
    chunk = text[offset:].encode()[:max_bytes].decode('utf-8', errors='ignore')
    next_offset = offset + len(chunk)
    return dict(section_id=row['id'], source_sha256=expected_sha256, start_line=row['start_line'],
                end_line=row['end_line'], offset=offset, next_offset=next_offset,
                more=next_offset < len(text), section_sha256=row['content_sha256'], text=chunk, files=row['files'][:5],
                remaining_files=max(0, len(row['files'])-5), ambiguous_files=row['ambiguous_files'][:5])


def keywords(text):
    """Keep a small vocabulary of architectural subjects, rather than prose or code."""
    stop = {'the','and','for','with','from','this','that','into','only','use','uses','are','not','has','its','section','project','mypi'}
    words = re.findall(r'[\w.-]{3,}', text.casefold())
    ranked = Counter(word for word in words if word not in stop and not word.isdigit())
    return [word for word, _ in ranked.most_common(12)]


def artifact(index):
    """Write a compact grep map; the complete local JSON registry remains searchable."""
    lines = ['# Architecture-to-shadow map', 'Source SHA256: ' + index['source_sha256'],
             'Snapshot: ' + index['snapshot'], '',
             'section ID | current lines | title / keywords | source files', '']
    for row in index['sections']:
        lines.append(row['id'] + f" | {row['start_line']}-{row['end_line']} | " +
                     row['title'] + ' / ' + ','.join(row['keywords']) + ' | ' + ','.join(row['files']))
    lines += ['', '# Shadow interface vocabulary', '']
    for record in index['files']:
        names = sorted(record['functions'], key=lambda name: (name.startswith('_'), '.' in name, name))
        lines.append(record['path'] + ' | functions: ' + ', '.join(names[:6]) +
                     ' | classes: ' + ', '.join(record['classes'][:4]) + ' | keywords: ' + ', '.join(record['keywords'][:4]) +
                     (f" | +{len(names)-6} functions in local JSON registry" if len(names)>6 else ''))
    lines += ['', 'Compact vocabulary shows representative names; architecture-map.json retains ALL function/class names for native literal search. Never load the whole registry into model context.']
    return '\n'.join(lines) + '\n'


def search(index, query, offset=0, limit=10):
    """Search literal terms in the small map; return section IDs and interface hits."""
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        raise ValueError('Supply a literal map query of 1-200 characters')
    if type(offset) is not int or offset < 0 or not 1 <= limit <= 10:
        raise ValueError('Use a nonnegative result offset and limit 1-10')
    terms = query.casefold().split()
    matches = []
    matched_files = set()
    for record in index['files']:
        vocabulary = ' '.join([record['path'], *record['functions'], *record['classes'], *record['keywords']]).casefold()
        if all(term in vocabulary for term in terms):
            matched_files.add(record['path'])
            matches.append({'kind': 'file', 'path': record['path'],
                            'functions': sorted(record['functions'], key=lambda name: not any(t in name.casefold() for t in terms))[:12],
                            'classes': sorted(record['classes'], key=lambda name: not any(t in name.casefold() for t in terms))[:12],
                            'keywords': record['keywords'][:12],
                            'interface_count': len(record['functions'])+len(record['classes'])})
    for section in index['sections']:
        vocabulary = ' '.join([section['id'], section['title'], *section['keywords'], *section['files']]).casefold()
        if matched_files.intersection(section['files']) or all(term in vocabulary for term in terms):
            matches.append({'kind': 'section', **{k:v for k,v in section.items() if k not in {'files','ambiguous_files','ambiguous_symbols'}},
                            'files': section['files'][:5], 'file_count':len(section['files'])})
    rows = matches[offset:offset+limit]
    return dict(source_sha256=index['source_sha256'], snapshot=index['snapshot'], total=len(matches),
                matches=rows, next_offset=offset+len(rows), more=offset+len(rows)<len(matches))


def references(data, refs):
    """Pin todo decisions by section content, allowing unrelated edits and line shifts."""
    if not isinstance(refs, list) or not 1 <= len(refs) <= 5 or any(not isinstance(r, dict) or set(r) != {'id','sha256'} for r in refs):
        raise ValueError('Select 1-5 architecture sections with id and sha256')
    pairs = selected(data, [r['id'] for r in refs])
    document_hash = data.get('architecture', {}).get('sha256', '')
    for ref, (row, text) in zip(refs, pairs):
        # Current document hashes remain accepted for older saved recipes.
        if not isinstance(ref['sha256'],str) or not re.fullmatch(r'[a-f0-9]{64}', ref['sha256']) or ref['sha256'] not in {row['content_sha256'],document_hash}:
            raise ValueError('Selected architecture section changed; reload its evidence and replan: ' + row['id'])
    return pairs
