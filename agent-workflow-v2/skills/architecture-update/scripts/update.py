"""Run the reviewed architecture insertion against this session's frozen scope."""
import json
from pathlib import Path
import sys
from architecture_update import update
print(json.dumps(update(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text()))))
