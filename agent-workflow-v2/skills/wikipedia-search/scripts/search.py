"""Read bounded Wikipedia search results and introductory extracts from its API."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, quote
from research_fetch import get


def search(query, language='en', limit=3):
    """Return attributable introductory evidence, never entire articles."""
    if not re.fullmatch('[a-z]{2,3}', language) or not 1 <= limit <= 3:
        raise ValueError('Invalid Wikipedia language or limit')
    base = f'https://{language}.wikipedia.org'
    payload, _, _ = get(base+'/w/rest.php/v1/search/page?'+urlencode({'q':query,'limit':limit}))
    pages = json.loads(payload).get('pages', [])
    results = []
    for page in pages:
        title = page['title']
        params = {'action':'query','format':'json','prop':'extracts','exintro':'1','explaintext':'1',
                  'exchars':1400,'titles':title}
        raw, _, _ = get(base+'/w/api.php?'+urlencode(params))
        entry = next(iter(json.loads(raw)['query']['pages'].values()))
        results.append({'title':title,'url':base+'/wiki/'+quote(title.replace(' ','_')),
                        'excerpt':entry.get('extract','')[:1400]})
    return {'engine':'wikipedia','query':query,'results':results}


if __name__ == '__main__':
    data=json.loads(Path(sys.argv[1]).read_text())
    print(json.dumps(search(data['query'],data.get('language','en'),data.get('limit',3)),ensure_ascii=False))
