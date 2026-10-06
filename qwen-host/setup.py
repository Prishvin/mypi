"""Install the tested isolated host environment and verified Quality checkpoint."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from qwen_config import BASE, configuration, read, recipe, save, supported_host, verify_server_source


def main(argv=None):
    parser = argparse.ArgumentParser(prog='setup-qwen.sh', description=__doc__)
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--gpu-lock', type=Path, help='Existing shared image/video GPU lock, if applicable')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--verify-only', action='store_true', help='Verify installed artifacts without installing/downloading')
    parser.add_argument('--start', action='store_true', help='Start/reuse the guarded model after successful setup')
    args = parser.parse_args(argv)
    hardware = supported_host()
    if not 1 <= args.port <= 65535: raise ValueError('Port must be 1..65535')
    settings = configuration(); folder = Path(settings['root'])
    if args.model_dir: settings['model_dir'] = str(args.model_dir.expanduser().resolve())
    if args.gpu_lock: settings['gpu_lock'] = str(args.gpu_lock.expanduser().resolve())
    settings['port'] = args.port
    python = folder / '.venv/bin/python'
    if not args.verify_only:
        print('Installing isolated Qwen dependencies into ' + str(folder), flush=True)
        subprocess.run([sys.executable, '-m', 'venv', str(folder / '.venv')], check=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(BASE / 'requirements.txt')], check=True)
    source_hash = verify_server_source(folder)
    subprocess.run([str(python), str(BASE / 'model_download.py'), '--model-dir', settings['model_dir'],
                    '--state-dir', str(folder), *(['--verify-only'] if args.verify_only else [])], check=True)
    report = read(folder / 'model-verification.json')
    # Import/help validates adapter installation and CLI flags without loading weights.
    probe = subprocess.run([str(python), str(BASE / 'probe.py')], capture_output=True, text=True)
    if probe.returncode:
        raise ValueError('Pinned engine/adapter probe failed: ' + probe.stderr[-4000:])
    save(folder / 'installation.json', {'hardware': hardware, 'server_sha256': source_hash,
         'probe': json.loads(probe.stdout), 'model_revision': report['revision']})
    save(folder / 'config.json', {k: v for k, v in settings.items() if k != 'root'})
    print(json.dumps({'ready': True, 'model_dir': settings['model_dir'], 'revision': report['revision'],
                      'context': 98304, 'generation': 'MTP3', 'kv': 'normal', 'next': 'mypi qwen start'}, indent=2))
    if args.start:
        import service
        return service.main(['start'])
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('Qwen setup: ' + str(error), file=sys.stderr); raise SystemExit(1)
