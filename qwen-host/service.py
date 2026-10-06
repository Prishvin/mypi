"""Own one optional Mac Qwen guard; reuse compatible servers without signaling them."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import uuid
from urllib.request import urlopen
from qwen_config import BASE, configuration, read, recipe, save, supported_host, verify_server_source


def health(settings, path='/health'):
    try:
        with urlopen(f"http://127.0.0.1:{settings['port']}" + path, timeout=3) as response:
            return json.load(response)
    except (OSError, ValueError): return None


def compatible(data, settings):
    """Actual native health must match the measured checkpoint and controls."""
    s = recipe()['serving']
    return bool(data and data.get('ok') and data.get('model') == s['model_id']
                and Path(data.get('model_path', '')).resolve() == Path(settings['model_dir']).resolve()
                and data.get('context_window') == s['context_window']
                and data.get('generation_mode') == s['generation_mode'] and data.get('depth') == s['depth']
                and data.get('paged_kv_quantization') == s['kv_cache']
                and data.get('preserve_thinking') == s['preserve_thinking'])


def capable(settings):
    caps = health(settings, '/pi-workflow/capabilities') or {}
    return caps.get('version') == 1 and caps.get('thinking_cap') == 'request-local' and caps.get('field') == 'pi_thinking_cap'


def owned(state):
    """Match this guard's nonce and command before any PID signal."""
    pid = state.get('guard_pid'); identity = state.get('identity')
    if type(pid) is not int or pid <= 1 or not identity: return False
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True)
    return result.returncode == 0 and str(BASE / 'guard.py') in result.stdout and '--identity ' + identity in result.stdout


def verified(settings):
    """Startup trusts a hash report only while all verified files stay unchanged."""
    folder = Path(settings['root']); report = read(folder / 'model-verification.json')
    m = recipe()['model']
    if (report.get('repo') != m['repo'] or report.get('revision') != m['revision']
            or Path(report.get('model_dir', '/nonexistent')).resolve() != Path(settings['model_dir']).resolve()
            or len(report.get('files', [])) != len(m['files'])):
        raise ValueError('Run ./setup-qwen.sh before starting the Qwen host.')
    for row in report['files']:
        path = Path(settings['model_dir']) / row['file']
        if not path.is_file() or path.stat().st_size != row['bytes'] or path.stat().st_mtime_ns != row.get('mtime_ns'):
            raise ValueError('Model changed since verification; run ./setup-qwen.sh --verify-only.')
    verify_server_source(folder)


def status(settings):
    current = health(settings); state = read(Path(settings['root']) / 'service.json')
    ready = compatible(current, settings) and capable(settings)
    return {'status': 'ready' if ready else 'other-configuration' if current else 'starting' if owned(state) else 'stopped',
            'owned': owned(state), 'endpoint': f"http://localhost:{settings['port']}/v1",
            'context': current.get('context_window') if current else None,
            'generation': current.get('generation_mode') if current else None,
            'depth': current.get('depth') if current else None,
            'kv': current.get('paged_kv_quantization') if current else None,
            'logs': state.get('logs')}


def start(settings, timeout=300):
    """Serialize launch, refuse incompatible ports, and reuse the current Mac model."""
    supported_host(); verified(settings)
    folder = Path(settings['root']); state_path = folder / 'service.json'
    with (folder / 'service.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = health(settings)
        if compatible(current, settings) and capable(settings):
            print('Reused compatible Quality: 96k · MTP3 · normal KV · request-local thinking caps')
            return status(settings)
        if current: raise RuntimeError('Port serves different controls or lacks the thinking adapter; stop its owner explicitly.')
        state = read(state_path)
        if not owned(state):
            try:
                with socket.create_connection(('127.0.0.1', settings['port']), timeout=.3):
                    raise RuntimeError('Qwen port is occupied by another service.')
            except ConnectionRefusedError: pass
            logs = folder / 'logs' / time.strftime('%Y%m%d-%H%M%S'); logs.mkdir(parents=True, exist_ok=False)
            identity = uuid.uuid4().hex
            argv = [str(folder / '.venv/bin/python'), str(BASE / 'guard.py'), '--root', str(folder),
                    '--logs', str(logs), '--identity', identity]
            with (logs / 'launcher.log').open('ab') as output:
                process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
            state = {'guard_pid': process.pid, 'identity': identity, 'logs': str(logs), 'started_epoch': time.time()}
            save(state_path, state)
        deadline = time.monotonic() + timeout; tick = 0
        while time.monotonic() < deadline:
            current = health(settings)
            if compatible(current, settings) and capable(settings): return status(settings)
            if current: raise RuntimeError('Unexpected Qwen controls; inspect ' + state['logs'])
            if not owned(state): raise RuntimeError('Qwen guard exited; inspect ' + state['logs'])
            if time.monotonic() >= tick:
                print('Waiting for GPU lock / Qwen startup: ' + state['logs'], flush=True); tick = time.monotonic() + 30
            time.sleep(1)
        raise RuntimeError('Startup timed out; guard remains visible in mypi qwen status. Inspect ' + state['logs'])


def stop(settings):
    """Only this host service's verified guard can unload its model."""
    folder = Path(settings['root']); folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'service.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(folder / 'service.json')
        if not owned(state):
            if health(settings): raise ValueError('This Qwen instance belongs to another launcher; stop its owner.')
            return {'status': 'stopped'}
        os.kill(state['guard_pid'], signal.SIGTERM)
        deadline = time.monotonic() + 30
        while owned(state) and time.monotonic() < deadline: time.sleep(.2)
        if owned(state): raise RuntimeError('Guard is still cleaning up; inspect ' + state['logs'])
        return {'status': 'stopped'}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='mypi qwen', description=__doc__)
    parser.add_argument('action', choices=['start', 'status', 'stop'])
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args(argv); settings = configuration()
    result = start(settings, args.timeout) if args.action == 'start' else stop(settings) if args.action == 'stop' else status(settings)
    print(json.dumps(result, indent=2)); return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print('Qwen host: ' + str(error), file=sys.stderr); raise SystemExit(1)
