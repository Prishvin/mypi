"""Run first-two-link research independently of any project implementation."""
import json
import sys
from pathlib import Path
from research_follow import research
request=json.loads(Path(sys.argv[1]).read_text())
print(json.dumps(research(request['query'],request['question'],Path(sys.argv[2])),ensure_ascii=False))
