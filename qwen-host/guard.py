"""Keep one host-owned Qwen process behind the GPU, cooling and memory guards."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
from qwen_config import command, configuration, environment, read, recipe, save


def memory():
    """Read actual macOS pressure and swap; do not change GPU or power limits."""
    swap = subprocess.check_output(['sysctl', 'vm.swapusage'], text=True)
    vm = subprocess.check_output(['vm_stat'], text=True)
    return {'epoch': time.time(),
            'swap_used_bytes': float(re.search(r'used = ([\d.]+)M', swap)[1]) * 1024**2,
            'swapouts_bytes': int(re.search(r'Swapouts:\s+(\d+)', vm)[1]) * int(re.search(r'page size of (\d+)', vm)[1]),
            'pressure': int(subprocess.check_output(['sysctl', '-n', 'kern.memorystatus_vm_pressure_level'], text=True))}


def exceeds(current, baseline):
    """Stop on critical pressure or >8 GiB new swap, matching the tested guard."""
    rules = recipe()['guard']
    return current['pressure'] >= rules['critical_pressure_level'] or max(
        current['swap_used_bytes'] - baseline['swap_used_bytes'],
        current['swapouts_bytes'] - baseline['swapouts_bytes']) > rules['swap_growth_limit_bytes']


def run(settings, logs):
    """Hold a shared lock for the entire model lifetime, including cleanup."""
    stop = False; process = None; started = False
    def request_stop(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, request_stop); signal.signal(signal.SIGINT, request_stop)
    state = {'guard_pid': os.getpid(), 'status': 'waiting-for-gpu'}
    def update(**values):
        state.update(values, updated=time.time()); save(logs / 'guard-status.json', state)
    gpu = Path(settings['gpu_lock']); gpu.parent.mkdir(parents=True, exist_ok=True)
    cooling = gpu.parent / 'cooling-state.json'
    awake = subprocess.Popen(['caffeinate', '-i', '-w', str(os.getpid())])
    update()
    with gpu.open('a') as lock:
        while not stop:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); break
            except BlockingIOError: time.sleep(1)
        try:
            remaining = max(0, recipe()['guard']['cooldown_seconds'] - (time.time() - read(cooling).get('last_gpu_end', 0)))
            deadline = time.monotonic() + remaining
            while not stop and time.monotonic() < deadline:
                update(status='cooling'); time.sleep(.5)
            if stop: return 0
            # Another launcher may have occupied the port while this guard waited.
            with socket.socket() as connection:
                connection.settimeout(.3)
                if connection.connect_ex(('127.0.0.1', settings['port'])) == 0:
                    raise RuntimeError('Qwen port became occupied while waiting; no second model loaded.')
            baseline = memory()
            if baseline['pressure'] >= recipe()['guard']['critical_pressure_level']:
                raise RuntimeError('Critical memory pressure before Qwen load')
            (logs / 'config.toml').write_text('')
            argv = command(settings, logs); env = environment(logs)
            save(logs / 'command.json', {'command': argv, 'environment': {k: v for k, v in env.items() if k.startswith('MTPLX_')}, 'baseline': baseline})
            with (logs / 'server.log').open('ab') as output, (logs / 'memory.jsonl').open('a', buffering=1) as telemetry:
                process = subprocess.Popen(argv, env=env, stdout=output, stderr=output, start_new_session=True)
                started = True; update(status='loading-or-serving', server_pid=process.pid)
                while process.poll() is None and not stop:
                    sample = memory(); telemetry.write(json.dumps(sample) + '\n')
                    if exceeds(sample, baseline): raise RuntimeError('Critical pressure or >8 GiB additional swap')
                    time.sleep(2)
                update(status='stopped' if stop else 'exited', returncode=process.poll())
                return 0 if stop else process.returncode
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            update(status='failed', error=str(error)); return 1
        finally:
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try: process.wait(timeout=20)
                except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait()
            if started: save(cooling, {'last_gpu_end': time.time(), 'kind': 'mypi-qwen'})
            awake.terminate(); update(ended=time.time())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--logs', type=Path, required=True)
    parser.add_argument('--identity', required=True)
    args = parser.parse_args(); os.environ['MYPI_QWEN_ROOT'] = str(args.root)
    return run(configuration(), args.logs)


if __name__ == '__main__': raise SystemExit(main())
