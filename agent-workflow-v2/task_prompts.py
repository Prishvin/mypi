"""Build architectural requests without adding implementation source."""
from pathlib import Path


def planning(request: str, settings: dict) -> str:
    """Wrap a feature request in the granular plan contract and current role budget."""
    template = Path(__file__).with_name('prompts').joinpath('create-plan.txt').read_text()
    return template.replace('{{REQUEST}}', request).replace('{{CONTEXT}}', str(settings['context']))
