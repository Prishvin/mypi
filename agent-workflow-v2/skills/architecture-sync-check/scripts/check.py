"""Check or explicitly rebuild only the project and shadow bound by the launch record."""
import json
from pathlib import Path
import sys
from architecture_consistency import check, rebuild
session = Path(sys.argv[1])
request = json.loads(Path(sys.argv[2]).read_text())
launch = json.loads((session / 'launch.json').read_text())
state = launch.get('state')
if state and launch.get('role') != 'code':
    raise ValueError('Only a bound coding role may rebuild maintained project metadata')
handler = rebuild if request['action'] == 'rebuild' else check
print(json.dumps(handler(Path(launch['project']), launch.get('prefixes', ['.']),
                         Path(launch['shadow']), state)))
