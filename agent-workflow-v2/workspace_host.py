"""Reuse the conversation workspace inside a standalone monitor HTTP server."""
import importlib.util
from pathlib import Path
import sys


def create(folder, addresses):
    """Initialize a separate conversation store; no model starts until a user acts."""
    root=Path(__file__).resolve().parent.parent
    sys.path[:0]=[str(root/'pi-web'),str(root)]
    spec=importlib.util.spec_from_file_location('mypi_embedded_web',root/'pi-web/server.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    app=module.App(folder/'.ui-workspace')
    return app,module.handler(app,addresses)
