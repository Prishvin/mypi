"""Measure normalized text without importing any project or making model calls."""
import json
from pathlib import Path
import sys

text = json.loads(Path(sys.argv[1]).read_text())['text']
print(json.dumps({'characters': len(text), 'bytes': len(text.encode()),
                  'lines': len(text.splitlines()), 'words': len(text.split()), 'token_count': None}))
