"""Refresh shadow artifacts and verify that they describe the current tree."""
import json
from pathlib import Path
from project_map import scan, write_map


def refresh(root: Path, prefixes: list[str], output: Path) -> dict:
    """Generate current prototypes, recording parse failures rather than old interfaces."""
    root = root.resolve()
    if output.resolve().is_relative_to(root):
        raise ValueError('Keep the generated shadow outside the source project')
    return write_map(scan(root, prefixes), output)


def verify(data: dict, after: dict) -> list[str]:
    """Reject missing or stale prototypes, including corrupted generated content."""
    output = data.get('shadow')
    if not output:
        return ['No shadow configured for this task']
    folder = Path(output)
    try:
        saved = json.loads((folder / 'manifest.json').read_text())
        if saved != after:
            return ['Shadow manifest is stale; refresh after every edit']
        from architecture_map import render
        if (folder / 'architecture.md').read_bytes().decode('utf-8') != render(after):
            return ['Shadow architecture map is stale; refresh after every edit']
        if (folder / 'knowledge.md').read_bytes().decode('utf-8') != after.get('knowledge', {}).get('text', '# Project knowledge\nNo research brief yet.\n'):
            return ['Shadow knowledge brief is stale; refresh after every edit']
        import architecture_sections
        index = architecture_sections.build(after)
        if json.loads((folder / 'architecture-map.json').read_text()) != index or (folder / 'architecture-map.md').read_text() != architecture_sections.artifact(index):
            return ['Shadow architecture section index is stale; refresh after every edit']
        from project_map import outline
        for record in after['files']:
            if (folder / 'prototypes' / (record['path'] + '.txt')).read_text() != outline(record):
                return ['Shadow prototype is stale: ' + record['path']]
    except (OSError, ValueError):
        return ['Shadow missing or unreadable; refresh before completion']
    return []
