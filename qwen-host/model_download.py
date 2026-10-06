"""Sequential resumable pinned downloads, byte hashes and safetensors index gates."""
import hashlib
import argparse
import json
from pathlib import Path
import struct
import time
from qwen_config import save


def target(directory, entry):
    """Reject unsafe manifest paths before any file access or download."""
    path = Path(directory) / entry['rfilename']
    if path.is_symlink() or not path.resolve().is_relative_to(Path(directory).resolve()):
        raise ValueError('Model manifest file escapes its directory')
    return path


def checksum(path, entry):
    """Use SHA-256 for LFS objects and Git blob SHA-1 for ordinary files."""
    if path.stat().st_size != entry['size']:
        raise ValueError('Model size mismatch: ' + entry['rfilename'])
    large = entry.get('lfs')
    digest = hashlib.sha256() if large else hashlib.sha1()
    if not large: digest.update(f"blob {entry['size']}\0".encode())
    tick = time.monotonic()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(16 * 1024**2), b''):
            digest.update(chunk)
            if time.monotonic() - tick >= 30:
                print('Verifying ' + entry['rfilename'], flush=True); tick = time.monotonic()
    expected = large['sha256'] if large else entry['blob_id']
    if digest.hexdigest() != expected:
        raise ValueError('Model checksum mismatch: ' + entry['rfilename'])
    return digest.hexdigest()


def header(path):
    """Read only a bounded safetensors header, never allocate tensor payloads."""
    with path.open('rb') as source:
        raw = source.read(8)
        if len(raw) != 8: raise ValueError('Truncated safetensors file')
        length = struct.unpack('<Q', raw)[0]
        if not 2 <= length <= 32 * 1024**2: raise ValueError('Invalid safetensors header size')
        return json.loads(source.read(length))


def verify_index(directory):
    """Ensure each indexed tensor exists and the MTP sidecar has payload tensors."""
    directory = Path(directory)
    mapping = json.loads((directory / 'model.safetensors.index.json').read_text())['weight_map']
    headers = {name: header(target(directory, {'rfilename': name})) for name in set(mapping.values())}
    for tensor, shard in mapping.items():
        if tensor not in headers[shard]: raise ValueError('Indexed tensor missing: ' + tensor)
    sidecar = header(directory / 'mtp.safetensors')
    if not any(name != '__metadata__' for name in sidecar): raise ValueError('Empty MTP sidecar')
    return len(mapping)


def download(model, directory, state_dir, *, verify_only=False, downloader=None):
    """Reuse verified files; repair only failed ones, one pinned file at a time."""
    if downloader is None and not verify_only:
        from huggingface_hub import hf_hub_download
        downloader = hf_hub_download
    directory = Path(directory); state_dir = Path(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    status_path = state_dir / 'download-status.json'
    verified = []; complete = 0
    for number, entry in enumerate(model['files'], 1):
        file = target(directory, entry); valid = False
        if file.exists():
            try: digest = checksum(file, entry); valid = True
            except ValueError:
                if verify_only: raise
        if not valid:
            if verify_only: raise ValueError('Missing model file: ' + entry['rfilename'])
            save(status_path, {'status': 'downloading', 'file': entry['rfilename'],
                              'verified_bytes': complete, 'total_bytes': model['total_bytes'], 'updated': time.time()})
            print(f"[{number}/{len(model['files'])}] Downloading {entry['rfilename']}", flush=True)
            downloader(model['repo'], entry['rfilename'], revision=model['revision'], local_dir=directory,
                       force_download=file.exists())
            digest = checksum(file, entry)
        complete += entry['size']
        verified.append({'file': entry['rfilename'], 'bytes': entry['size'], 'checksum': digest,
                         'mtime_ns': file.stat().st_mtime_ns, 'verified': True})
        save(status_path, {'status': 'verifying', 'file': entry['rfilename'], 'verified_bytes': complete,
                          'total_bytes': model['total_bytes'], 'percent': round(100 * complete / model['total_bytes'], 2), 'updated': time.time()})
        print(f"[{number}/{len(model['files'])}] Verified {entry['rfilename']}", flush=True)
    report = {'repo': model['repo'], 'revision': model['revision'], 'model_dir': str(directory),
              'total_bytes': complete, 'files': verified, 'indexed_tensors': verify_index(directory),
              'verified_at': time.time(), 'model_loaded': False}
    save(state_dir / 'model-verification.json', report)
    save(status_path, {'status': 'complete', 'percent': 100, 'verified_bytes': complete, 'total_bytes': complete, 'updated': time.time()})
    return report


def main():
    """Use the isolated server interpreter for HF downloads, never global pip."""
    from qwen_config import recipe
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    download(recipe()['model'], args.model_dir, args.state_dir, verify_only=args.verify_only)


if __name__ == '__main__': main()
