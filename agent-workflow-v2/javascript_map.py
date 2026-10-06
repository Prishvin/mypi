"""Parse JavaScript/TypeScript and inline HTML scripts with tree-sitter."""
from html.parser import HTMLParser
import re
from tree_sitter import Language, Parser
import tree_sitter_javascript as javascript
import tree_sitter_typescript as typescript
from sources import brief

FUNCTIONS = {'function_declaration', 'function_expression', 'generator_function_declaration',
             'generator_function', 'arrow_function', 'method_definition'}
CLASSES = {'class_declaration', 'class'}


def preceding_comment(node):
    """Find documentation on a callable or its owning declaration/property."""
    previous = node.prev_named_sibling
    if previous is not None and previous.type == 'comment':
        return previous
    owner = node
    wrappers = {'variable_declarator', 'lexical_declaration', 'variable_declaration',
                'pair', 'public_field_definition', 'assignment_expression',
                'expression_statement', 'export_statement'}
    while owner.parent is not None and owner.parent.type in wrappers:
        owner = owner.parent
        if owner.type in {'pair', 'public_field_definition'}:
            break
    previous = owner.prev_named_sibling
    return previous if previous is not None and previous.type == 'comment' else None


def node_name(node) -> str:
    """Resolve declaration names and names assigned to function expressions."""
    name = node.child_by_field_name('name')
    if name is not None:
        return name.text.decode()
    parent = node.parent
    if parent and parent.type in {'variable_declarator', 'pair', 'public_field_definition'}:
        name = parent.child_by_field_name('name') or parent.child_by_field_name('key')
        if name is not None:
            return name.text.decode()
    if parent and parent.type == 'assignment_expression':
        name = parent.child_by_field_name('left')
        if name is not None:
            return name.text.decode()
    return f'<callback@{node.start_point.row + 1}>'


def parse_javascript(text: str, suffix='.js', offset=0) -> dict:
    """Extract named and anonymous callable interfaces; reject syntax errors."""
    language = typescript.language_tsx() if suffix == '.tsx' else (
        typescript.language_typescript() if suffix == '.ts' else javascript.language())
    tree = Parser(Language(language)).parse(text.encode())
    if tree.root_node.has_error:
        raise ValueError('JavaScript/TypeScript syntax error')
    symbols, imports, variables = [], [], []
    occurrences = {}

    def visit(node, parents=()):
        scope = parents
        if node.type == 'import_statement':
            imports.append(node.text.decode())
        if node.type in {'variable_declarator', 'public_field_definition'}:
            variable = node.child_by_field_name('name')
            annotation = node.child_by_field_name('type')
            if variable is not None:
                variables.append({'name': variable.text.decode(), 'scope': '.'.join(parents),
                                  'type': annotation.text.decode() if annotation else None,
                                  'line': node.start_point.row + 1 + offset,
                                  'end': node.end_point.row + 1 + offset})
        if node.type in FUNCTIONS | CLASSES:
            name = node_name(node)
            key = (parents, name)
            occurrences[key] = occurrences.get(key, 0) + 1
            if occurrences[key] > 1:
                name += '#' + str(occurrences[key])
            scope = (*parents, name)
            body = node.child_by_field_name('body')
            raw = node.text[:body.start_byte - node.start_byte] if body else node.text
            previous = preceding_comment(node)
            description = None
            if previous is not None and previous.type == 'comment':
                description = re.sub(r'^[/\s*]+|[*/\s]+$', '', previous.text.decode())
                description = re.sub(r'\n\s*\* ?', '\n', description)
            elif node.type in FUNCTIONS and body and body.named_children:
                first = body.named_children[0]
                if first.type == 'comment':
                    description = re.sub(r'^[/\s*]+|[*/\s]+$', '', first.text.decode())
            start, end = node.start_point.row + 1 + offset, node.end_point.row + 1 + offset
            declaration = ' '.join(raw.decode().split())
            symbols.append({'name': '.'.join(scope),
                            'kind': 'class' if node.type in CLASSES else 'function',
                            'signature': declaration[:600], 'signature_truncated': len(declaration) > 600,
                            'description': brief(description),
                            'contract': (description or '')[:1200],
                            'line': start, 'end': end, 'lines': end - start + 1})
            symbols[-1].update(start_byte=node.start_byte, end_byte=node.end_byte)
        for child in node.named_children:
            visit(child, scope)

    visit(tree.root_node)
    first = tree.root_node.named_children[0] if tree.root_node.named_children else None
    module_brief = brief(first.text.decode().strip('/* \n')) if first and first.type == 'comment' else '[description missing]'
    return {'description': module_brief, 'symbols': symbols,
            'imports': sorted(set(imports)), 'calls': [], 'variables': variables}


class Scripts(HTMLParser):
    """Collect inline executable scripts and their original line positions."""
    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.inline, self.external = [], []
        self.current = None
        self.text = text

    def handle_starttag(self, tag, attrs):
        if tag != 'script':
            return
        attrs = dict(attrs)
        if attrs.get('src'):
            self.external.append(attrs['src'])
        elif attrs.get('type', '') in {'', 'module', 'text/javascript', 'application/javascript'}:
            line, column = self.getpos()
            tag_text = self.get_starttag_text()
            start = sum(len(row) for row in self.text.splitlines(keepends=True)[:line - 1]) + column + len(tag_text)
            self.current = (line - 1 + tag_text.count('\n'), [], len(self.text[:start].encode()))

    def handle_data(self, data):
        if self.current is not None:
            self.current[1].append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.current is not None:
            self.inline.append((self.current[0], ''.join(self.current[1]), self.current[2]))
            self.current = None


def parse_html(text: str) -> dict:
    """Index inline scripts; document external script dependencies."""
    scripts = Scripts(text)
    scripts.feed(text)
    result = {'description': 'HTML view; inline JavaScript interfaces below.',
              'symbols': [], 'imports': scripts.external, 'calls': [], 'variables': []}
    for offset, code, byte_start in scripts.inline:
        parsed = parse_javascript(code, offset=offset)
        for symbol in parsed['symbols']:
            symbol['start_byte'] += byte_start
            symbol['end_byte'] += byte_start
        result['symbols'].extend(parsed['symbols'])
        result['imports'].extend(parsed['imports'])
        result['variables'].extend(parsed['variables'])
    return result
