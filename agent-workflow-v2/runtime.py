"""Keep each running task on one immutable version of the workflow tools."""
import hashlib
import json
from pathlib import Path
import shutil


def capture(base: Path, session: Path) -> Path:
    """Copy local tool modules and rules before Pi starts; retain content hashes."""
    output = session / 'runtime'
    output.mkdir()
    files = sorted(path for path in base.glob('*.py') if not path.name.startswith('test_'))
    files.extend(path for path in base.glob('*.mjs') if not path.name.startswith('test_'))
    files.extend(base / name for name in ('qwen-rules.txt', 'architect-rules.txt', 'research-rules.txt', 'intake-rules.txt', 'reviewer-rules.txt','memory-rules.txt'))
    if (base/'chat-rules.txt').exists():
        files.append(base/'chat-rules.txt')
    if (base/'inspect-rules.txt').exists():
        files.append(base/'inspect-rules.txt')
    if (base/'architect-recovery-rules.txt').exists():
        files.append(base/'architect-recovery-rules.txt')
    if (base/'architect-review-rules.txt').exists():
        files.append(base/'architect-review-rules.txt')
    if (base/'skills.json').exists():
        files.append(base/'skills.json')
    hashes = {}
    for source in files:
        shutil.copy2(source, output / source.name)
        hashes[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    for name in ('profiles', 'prompts', 'skills'):
        directory = base / name
        if directory.is_dir():
            shutil.copytree(directory, output / name)
            for source in sorted(directory.rglob('*')):
                if source.is_file():
                    hashes[str(source.relative_to(base))] = hashlib.sha256(source.read_bytes()).hexdigest()
    tokenizer = base / 'qwen-tokenizer.json'
    if tokenizer.exists():
        shutil.copy2(tokenizer, output / tokenizer.name)
        hashes[tokenizer.name] = hashlib.sha256(tokenizer.read_bytes()).hexdigest()
    (output / 'manifest.json').write_text(json.dumps(hashes, indent=2))
    if (base / '.venv').exists():
        (output / '.venv').symlink_to((base / '.venv').resolve(), target_is_directory=True)
    return output
