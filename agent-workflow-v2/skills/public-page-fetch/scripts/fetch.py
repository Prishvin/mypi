"""Archive fetched public evidence and expose only a bounded relevant excerpt."""
import json
from pathlib import Path
import sys
from research_fetch import fetch
from research_briefs import save_source
from research_content import focus,relevant_links

request = json.loads(Path(sys.argv[1]).read_text())
try:
    source=fetch(request['url'])
    result=save_source(Path(sys.argv[2]),source)
    result.update(focus(source['text'],request.get('query',''),max_bytes=4800))
    result['links']=relevant_links(source.get('links',[]),request.get('query',''))
    while len(json.dumps(result,ensure_ascii=False).encode())>7000 and result['excerpt']:
        result['excerpt']=result['excerpt'].encode()[:-256].decode(errors='ignore');result['truncated']=True
    print(json.dumps(result,ensure_ascii=False))
except (OSError,ValueError) as error:
    print(json.dumps({'url':request['url'],'status':'unavailable','error':str(error)[:400],'note':'Do not retry this unchanged URL or claim its contents were read.'}))
