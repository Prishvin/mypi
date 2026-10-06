"""Index architecture and shadow vocabulary, then retrieve only selected map evidence."""
import json
from pathlib import Path
import sys
from architecture_sections import build, page, render, search
from shadow import refresh
project, output, request_path = map(Path, sys.argv[1:4])
launch = json.loads((Path(sys.argv[4]) / 'launch.json').read_text())
from architecture_consistency import check
report = check(project, launch.get('prefixes', ['.']), Path(launch['shadow']), launch.get('state'))
if report['rebuild_required']:
    raise ValueError('; '.join(report['reasons']) + '. ' + report['question'])
request = json.loads(request_path.read_text())
summary = refresh(project, ['.'], output)
data = json.loads((output / 'manifest.json').read_text())
index = build(data)
action = request['action']
if action == 'search':
    result = search(index, request['query'], request.get('offset', 0), limit=5)
elif action == 'section':
    result = page(data, request['section_id'], request['sha256'], request.get('offset', 0), max_bytes=4000)
else:
    result = {'index_page': render(index, request.get('offset', 0), limit=5),
              'source_sha256': index['source_sha256'], 'sections': summary['architecture_sections']}
result['map_artifact'] = str(output / 'architecture-map.md')
print(json.dumps(result))
