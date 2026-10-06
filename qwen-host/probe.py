"""Confirm pinned dependencies and inject the adapter without allocating a model."""
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from qwen_config import BASE, command, configuration, environment, recipe, verify_server_source


def main():
    settings = configuration()
    actual = verify_server_source(settings['root'])
    for line in (BASE / 'requirements.txt').read_text().splitlines():
        if not line or line.startswith('#'): continue
        name, expected = line.split('==')
        if importlib.metadata.version(name) != expected: raise ValueError('Dependency mismatch: ' + name)
    with tempfile.TemporaryDirectory() as directory:
        logs = Path(directory); (logs / 'config.toml').write_text('')
        result = subprocess.run(command(settings, logs) + ['--help'], env=environment(logs), capture_output=True, text=True, check=True)
        for option in ('--preserve-thinking', '--paged-kv-quantization', '--context-window'):
            if option not in result.stdout: raise ValueError('Unsupported Qwen option: ' + option)
        injected = subprocess.run([sys.executable, '-c', 'import mtplx.server.openai as m; print(m.create_app.__wrapped__.__name__)'],
                                  env=environment(logs), capture_output=True, text=True, check=True)
        if injected.stdout.strip() != 'create_app': raise ValueError('Thinking-cap adapter not installed')
    print(json.dumps({'mtplx': importlib.metadata.version('mtplx'), 'server_sha256': actual,
                      'adapter': 'installed', 'model_loaded': False}))


if __name__ == '__main__': main()
