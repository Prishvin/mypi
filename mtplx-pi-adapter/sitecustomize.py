"""Opt-in import adapter; reject an unreviewed MTPLX source upgrade."""
import hashlib
import importlib.abc
import importlib.machinery
import json
import os
from pathlib import Path
import sys


if os.environ.get('MTPLX_PI_THINKING_CAPS') == '1':
    class PiLoader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            expected = json.loads((Path(__file__).parent/'manifest.json').read_text())['server_sha256']
            source = Path(self.path).read_bytes()
            if hashlib.sha256(source).hexdigest() != expected:
                raise ImportError('Review the private Pi thinking-cap adapter after this MTPLX upgrade')
            marker = 'if __name__ == "__main__":'
            text = source.decode()
            if text.count(marker) != 1:
                raise ImportError('Unknown MTPLX server entry point')
            # The CLI starts python -m: runpy calls get_code, not exec_module.
            injected = 'from pi_thinking_adapter import install as _pi_install\nimport sys as _pi_sys\n_pi_install(_pi_sys.modules[__name__])\n\n'
            return compile(text.replace(marker, injected+marker), self.path, 'exec')

    class PiFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname != 'mtplx.server.openai':
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec and spec.origin:
                spec.loader = PiLoader(fullname, spec.origin)
            return spec

    sys.meta_path.insert(0, PiFinder())
