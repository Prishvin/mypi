"""Bound a private Pi process and persist its session, timing and progress."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request
import server_config

BASE = Path(__file__).resolve().parent


def read(path, default=None):
    """Read optional evidence without masking a malformed required plan."""
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def save(path, value):
    """Replace durable runner state atomically."""
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)


def terminate(process, metadata):
    """Stop the launcher and its separately owned Pi group, never a model server."""
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait()
    session = read(metadata).get('session')
    if session:
        owned = read(Path(session) / 'process.json').get('process_group')
        if owned:
            try:
                os.killpg(owned, signal.SIGKILL)
            except ProcessLookupError:
                pass


def memory_sample():
    """Keep native allocation and process RSS separate in progress evidence."""
    from memory_metrics import sample
    return sample()


def invoke(command, folder, timeout):
    """Run one bounded attempt; the model cannot schedule additional todos."""
    folder.mkdir(parents=True, exist_ok=False)
    metadata = folder / 'session.json'
    command = command + ['--session-out', str(metadata), '--timeout-seconds', str(timeout)]
    started = time.monotonic()
    timed_out = False
    with (folder / 'pi.log').open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                   start_new_session=True)
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed >= timeout + 30:
                    timed_out = True; terminate(process, metadata); break
                with (folder / 'memory.jsonl').open('a') as output:
                    output.write(json.dumps(memory_sample()) + '\n')
                print(f'[{int(elapsed)}s] Pi attempt: {folder.name}', flush=True)
                try:
                    process.wait(timeout=min(30, max(.1, timeout + 30 - elapsed)))
                except subprocess.TimeoutExpired:
                    pass
        except BaseException:
            terminate(process, metadata)
            raise
    timed_out = timed_out or process.returncode == 124
    result = {'exit_code': 124 if timed_out else process.returncode,
              'session': read(metadata).get('session'), 'log': str(folder / 'pi.log'),
              'wall_seconds': round(time.monotonic()-started, 3), 'timed_out': timed_out}
    save(folder / 'result.json', result)
    return result
