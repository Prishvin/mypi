"""Portable paths and the measured Qwen host recipe, separate from client settings."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parent
REPO = BASE.parent


def recipe():
    """Read immutable model revision, hashes, serving controls and guard limits."""
    return json.loads((BASE / 'recipe.json').read_text())


def root():
    return Path(os.environ.get('MYPI_QWEN_ROOT', str(Path.home() / '.local/share/mypi/qwen'))).expanduser().resolve()


def read(path):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {}


def save(path, value):
    """Publish complete private host state atomically, never in client preferences."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.qwen-')
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(value, output, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def configuration():
    """Use the installed model path, port and shared GPU lock when supplied."""
    folder = root(); settings = read(folder / 'config.json')
    return {**settings, 'root': str(folder),
            'model_dir': settings.get('model_dir', str(Path.home() / 'Models' / recipe()['model']['directory'])),
            'port': settings.get('port', 8000),
            'gpu_lock': os.environ.get('MYPI_GPU_LOCK') or settings.get('gpu_lock', str(folder / 'local-gpu.lock'))}


def supported_host():
    """This exact MLX/Metal recipe is for a 64 GiB+ Apple Silicon Mac."""
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('The Qwen host requires Apple Silicon macOS; Linux runs the mypi client against that host.')
    if sys.version_info[:2] != (3, 12):
        raise ValueError('Use Python 3.12 for the pinned Qwen host environment (MYPI_PYTHON=python3.12).')
    total = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True))
    if total < 64 * 1024**3:
        raise ValueError('This measured 96k / 48G-memory-limit recipe requires a 64 GiB+ Mac.')
    return {'system': platform.system(), 'machine': platform.machine(), 'ram_bytes': total}


def command(settings, logs):
    """Build explicit controls matching the retained Quality service."""
    s = recipe()['serving']
    argv = [str(Path(settings['root']) / '.venv/bin/mtplx'), 'serve', '--model', settings['model_dir'],
            '--model-id', s['model_id'], '--host', '127.0.0.1', '--port', str(settings['port'])]
    for key in ('context_window', 'max_tokens', 'memory_limit', 'generation_mode', 'depth',
                'reasoning', 'reasoning_effort', 'preserve_thinking', 'scheduler_mode', 'fan_mode',
                'ssd_session_cache', 'ssd_session_cache_max_size'):
        argv += ['--' + key.replace('_', '-'), str(s[key])]
    return argv + ['--profile', 'turbo', '--paged-kv-quantization', s['kv_cache'],
                   '--ssd-session-cache-dir', str(logs / 'session-cache'), '--no-stats-footer']


def environment(logs):
    """Remove inherited MTPLX experiments; enable only the reviewed adapter/guard."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('MTPLX_')}
    env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               PYTHONPATH=str(REPO / 'mtplx-pi-adapter'), MTPLX_PI_THINKING_CAPS='1',
               MTPLX_CONFIG=str(logs / 'config.toml'),
               MTPLX_REQUEST_LOG_JSONL=str(logs / 'requests.jsonl'),
               MTPLX_FLIGHT_RECORDER=str(logs / 'flight.jsonl'), MTPLX_FLIGHT_TEXT='off',
               MTPLX_THINKING_BUDGET=str(recipe()['serving']['thinking_budget']),
               MTPLX_THINKING_GUARD_SCOPE='all')
    return env


def verify_server_source(folder):
    """Reject a different server even if its package version has the same name."""
    sites = list((Path(folder) / '.venv/lib').glob('python*/site-packages/mtplx/server/openai.py'))
    if len(sites) != 1:
        raise ValueError('Pinned MTPLX server source is missing or ambiguous')
    actual = hashlib.sha256(sites[0].read_bytes()).hexdigest()
    if actual != recipe()['runtime']['server_sha256']:
        raise ValueError('MTPLX source differs from the tested adapter; do not bypass its hash check.')
    return actual
