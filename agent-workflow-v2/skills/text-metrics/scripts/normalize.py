"""Normalize only line endings and save the intermediate artifact for the next step."""
import json
from pathlib import Path
import sys

text = json.loads(Path(sys.argv[1]).read_text())['text'].replace('\r\n', '\n').replace('\r', '\n')
Path(sys.argv[2]).write_text(json.dumps({'text': text}))
print(json.dumps({'normalized': True}))
