"""Generate only owned shadow artifacts for the orchestrator-bound project."""
import json
import sys
from pathlib import Path
from shadow import refresh

root=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]).resolve()
result=refresh(root,['.'],output)
print(json.dumps({'shadow':str(output),'project':str(root),'snapshot':result['snapshot'],
                  'files':result['files'],'symbols':result['symbols'],
                  'parse_errors':result['parse_errors'][:8],'parse_error_count':len(result['parse_errors']),'missing_descriptions':result['missing_descriptions'],
                  'architecture':str(output/'architecture.md'),'catalog':str(output/'INDEX.txt')}))
