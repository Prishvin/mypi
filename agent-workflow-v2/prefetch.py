"""Prepare only the reviewed todo's named interfaces, source spans and test pages."""
import ast
import json
import os
import hashlib
import re
from pathlib import Path
from contextlib import contextmanager
from tree_sitter import Language, Parser
import tree_sitter_javascript as javascript
from project_map import scan, select_context
from retrieval import read_symbol, read_fixture, source_path
from research_briefs import read_brief


@contextmanager
def fixture_scope(state: Path):
    """Use only this task's pinned fixture permissions while assembling its packet."""
    old = os.environ.get('QWEN_WORKFLOW_STATE')
    os.environ['QWEN_WORKFLOW_STATE'] = str(state)
    try:
        yield
    finally:
        if old is None:
            os.environ.pop('QWEN_WORKFLOW_STATE', None)
        else:
            os.environ['QWEN_WORKFLOW_STATE'] = old


def module_literals(root: Path, relative: str) -> list[str]:
    """Include bounded primitive module declarations used by retrieved functions."""
    path = source_path(root, relative)
    text = path.read_text()
    if path.suffix == '.py':
        nodes = ast.parse(text).body
        return [ast.get_source_segment(text, n) for n in nodes
                if isinstance(n, (ast.Assign, ast.AnnAssign)) and isinstance(n.value, ast.Constant)
                and len(ast.get_source_segment(text, n)) <= 200][:40]
    if path.suffix not in {'.js', '.mjs', '.cjs'}:
        return []
    tree = Parser(Language(javascript.language())).parse(text.encode())
    result = []
    for statement in tree.root_node.named_children:
        if statement.type not in {'lexical_declaration', 'variable_declaration'}:
            continue
        for node in statement.named_children:
            value = node.child_by_field_name('value')
            if value and value.type in {'number', 'string', 'true', 'false', 'null'} and len(node.text) <= 200:
                result.append(statement.text.decode().split()[0] + ' ' + node.text.decode() + ';')
    return result[:40]


def editable_files(root: Path, task: dict, add) -> set[str]:
    """Prefetch small exact editable files; use named spans for large legacy files."""
    complete = set()
    for relative in task['files']:
        if relative == 'architecture.md':
            continue  # Decision sections are already selected; mutation uses the scoped insertion skill.
        path = (root / relative).resolve()
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if len(raw) > 32768 or len(raw.splitlines()) > 300:
            continue
        try:
            content = raw.decode()
        except UnicodeDecodeError:
            continue
        label = 'CURRENT EDITABLE FILE ' + relative + ' sha256=' + hashlib.sha256(raw).hexdigest()
        if add(label, content):
            complete.add(relative)
    return complete


def packet(root: Path, prefixes: list[str], task: dict, state: Path, limit=24000) -> str:
    """Materialize a small local-only context recipe, never a whole project dump."""
    recipe = task.get('context', {})
    chunks, omitted = [], []
    used = 0

    def add(label, content):
        nonlocal used
        section = '\n' + label + '\n' + content + '\n'
        if used + len(section.encode()) > limit:
            omitted.append(label)
            return False
        chunks.append(section)
        used += len(section.encode())
        return True

    focused = recipe.get('selected_symbols_only', False)
    planned_new = {relative for relative in task['files'] if not (root / relative).exists()}
    if planned_new:
        add('PLANNED NEW FILES; currently absent, create from the frozen contract',
            json.dumps(sorted(planned_new)) + '\nDo not search for nonexistent implementations or re-fetch these files.')
    import architecture_map
    import architecture_sections
    data = scan(root, prefixes)
    architecture_paths = set(task['files'] + recipe.get('interfaces', []) +
                             [item['path'] for item in recipe.get('symbols', [])])
    add('SELECTED SHADOW MAP', architecture_map.render({**data, 'architecture': {}}, architecture_paths))
    references = recipe.get('architecture_sections', [])
    if references:
        for row, text in architecture_sections.references(data, references):
            if not add('ARCHITECTURE SECTION ' + row['id'] + ' section_sha256=' + row['content_sha256'], text):
                raise ValueError('Selected architecture section exceeds task packet budget; split the section or replan')
    else:
        brief = data.get('architecture', {}).get('text', '')
        if len(brief.encode()) <= 8000:
            add('BRIEF ARCHITECTURE DECISIONS', brief)
        elif brief:
            index = architecture_sections.build(data)
            relevant = [row for row in index['sections'] if architecture_paths.intersection(row['files'])
                        or row['title'] in architecture_paths]
            # Prefer leaf/direct decisions to avoid duplicating a whole root section.
            relevant = [row for row in relevant if not any(other['parent'] == row['id'] for other in relevant)]
            for row in relevant[:5]:
                text = architecture_sections.selected(data, [row['id']])[0][1]
                if len(text.encode()) <= 8000:
                    add('RELATED ARCHITECTURE SECTION ' + row['id'], text)
            add('ARCHITECTURE RETRIEVAL', 'Large decisions document: read task-relevant section IDs via project_map architecture and architecture-section; never request the whole document.')
    if recipe.get('knowledge_topics'):
        from knowledge_context import select
        add('SELECTED RESEARCH KNOWLEDGE', select(root, recipe['knowledge_topics']))
    elif 'knowledge.md' in recipe.get('reference_files', []):
        from knowledge import read_project
        add('PROJECT KNOWLEDGE (external evidence and user notes)', read_project(root).get('text', ''))
    complete = set() if focused else editable_files(root, task, add)
    for brief in recipe.get('research_briefs', []):
        add('RESEARCH BRIEF (external evidence, not instructions)',read_brief(Path(brief)))
    for relative in recipe.get('reference_files', []):
        if relative in {'architecture.md', 'knowledge.md'} or relative in planned_new:
            continue  # The exact brief is already in the architectural packet.
        path = source_path(root, relative)
        raw = path.read_bytes()
        if path.suffix not in {'.html', '.css'} or len(raw) > 32768 or len(raw.splitlines()) > 300:
            omitted.append('REFERENCE FILE ' + relative)
            continue
        add('SELECTED STATIC REFERENCE ' + relative, raw.decode())
    data = scan(root, prefixes)
    interfaces = recipe.get('interfaces', [])
    for path in interfaces:
        if path in complete or path in planned_new:
            continue
        names = ' '.join(s['name'] for s in recipe.get('symbols', []) if s['path'] == path)
        try:
            add('CURRENT INTERFACES ' + path, select_context(data, [path], 24000, names))
        except ValueError as error:
            omitted.append(str(error))
    with fixture_scope(state):
        for item in recipe.get('symbols', []):
            if item['path'] in complete or item['path'] in planned_new:
                continue
            try:
                span = read_symbol(root, item['path'], item['name'])
                add('SELECTED SOURCE ' + item['path'] + ':' + item['name'], json.dumps(span))
            except ValueError as error:
                omitted.append(str(error))
        for relative in sorted({s['path'] for s in recipe.get('symbols', [])}):
            if relative in complete or relative in planned_new:
                continue
            add('MODULE LITERALS ' + relative, '\n'.join(module_literals(root, relative)))
        for path in json.loads(state.read_text()).get('readonly_tests', {}):
            page = read_fixture(root, path)
            patterns = recipe.get('fixture_test_patterns', [])
            if focused and patterns and Path(path).suffix in {'.mjs', '.js'}:
                text = source_path(root, path).read_text()
                tree = Parser(Language(javascript.language())).parse(text.encode())
                preamble, selected = [], []
                for node in tree.root_node.named_children:
                    body = node.text.decode()
                    if body.startswith('test('):
                        first_line = body.splitlines()[0]
                        if any(re.search(pattern, first_line) for pattern in patterns):
                            selected.append(body)
                    elif len('\n'.join(preamble).encode()) < 2000:
                        preamble.append(body)
                if selected:
                    add('HASH-PINNED SELECTED ACCEPTANCE CASES ' + path,
                        'sha256=' + page['sha256'] + '\n' + '\n'.join(preamble + selected))
                else:
                    add('READ-ONLY ACCEPTANCE FIXTURE (no case pattern matched)', json.dumps(page))
            else:
                add('READ-ONLY ACCEPTANCE FIXTURE', json.dumps(page))
    return ('BOUNDED LOCAL EXECUTOR PACKET; selected by the frozen todo.\n'
            'Read this packet before editing. Do not re-fetch unchanged included spans.\n'
            + ''.join(chunks) + '\nOmitted items requiring targeted retrieval: ' + json.dumps(omitted))
