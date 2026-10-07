"""Execute the frozen finalization recipe, with no arbitrary project command input."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from task_finalize import finalize
print(json.dumps(finalize(Path(sys.argv[1]),json.loads(Path(sys.argv[2]).read_text()))))
