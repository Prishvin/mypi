"""Extract Python interfaces with AST parsing; never execute inspected modules."""
import ast
from sources import brief


def signature(node: ast.AST) -> str:
    """Preserve argument types/defaults and return types in an interface declaration."""
    if isinstance(node, ast.ClassDef):
        return 'class ' + node.name + '(' + ', '.join(ast.unparse(b) for b in node.bases) + ')'
    prefix = 'async def ' if isinstance(node, ast.AsyncFunctionDef) else 'def '
    result = prefix + node.name + '(' + ast.unparse(node.args) + ')'
    if node.returns:
        result += ' -> ' + ast.unparse(node.returns)
    return result


def parse_python(text: str) -> dict:
    """Collect named symbols, imports and syntactic calls, including private helpers."""
    tree = ast.parse(text)
    symbols = []
    imports = []
    variables = []
    byte_lines = [0]
    for line in text.encode().splitlines(keepends=True):
        byte_lines.append(byte_lines[-1] + len(line))

    def visit(node, parents=()):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(ast.unparse(node))
        named = isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        scope = parents
        if named:
            scope = (*parents, node.name)
            declaration = signature(node)
            first_line = min([node.lineno] + [d.lineno for d in node.decorator_list])
            first_column = node.decorator_list[0].col_offset - 1 if node.decorator_list else node.col_offset
            symbols.append({
                'name': '.'.join(scope), 'kind': 'class' if isinstance(node, ast.ClassDef) else 'function',
                'signature': declaration[:600], 'signature_truncated': len(declaration) > 600,
                'description': brief(ast.get_docstring(node)),
                'contract': (ast.get_docstring(node) or '')[:1200],
                'line': first_line, 'end': node.end_lineno,
                'lines': node.end_lineno - first_line + 1,
                'start_byte': byte_lines[first_line - 1] + first_column,
                'end_byte': byte_lines[node.end_lineno - 1] + node.end_col_offset,
                'decorators': [ast.unparse(d) for d in node.decorator_list],
            })
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for item in ast.walk(target):
                    if isinstance(item, (ast.Name, ast.Attribute)) and isinstance(item.ctx, ast.Store):
                        variables.append({'name': ast.unparse(item), 'scope': '.'.join(parents),
                                          'type': ast.unparse(node.annotation) if isinstance(node, ast.AnnAssign) else None,
                                          'line': node.lineno, 'end': node.end_lineno})
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(tree)
    calls = sorted({ast.unparse(n.func) for n in ast.walk(tree)
                    if isinstance(n, ast.Call)})
    return {'description': brief(ast.get_docstring(tree)), 'symbols': symbols,
            'imports': sorted(set(imports)), 'calls': calls, 'variables': variables}
