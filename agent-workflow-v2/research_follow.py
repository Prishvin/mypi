"""DuckDuckGo discovery followed by exactly its first two public result pages."""
import json
from concurrent.futures import ThreadPoolExecutor
from research_search import search
from research_fetch import fetch
from research_briefs import save_source
from research_content import focus, relevant_links


def read_page(row, question, folder):
    """Archive bounded readable evidence, exposing only a focused exact excerpt."""
    try:
        source=fetch(row['url']);brief=focus(source['text'],question)
        archived=save_source(folder,source)
        return {'title':row['title'],'url':row['url'],'fetched_url':source.get('fetched_url'),
                'artifact_id':archived['artifact_id'],'source_type':source['source_type'],
                **brief,'links':relevant_links(source.get('links',[]),question),'status':'read'}
    except (OSError,ValueError,KeyError) as error:
        return {'title':row['title'],'url':row['url'],'status':'unavailable','error':str(error)[:240]}


def research(query, question, folder):
    """Attempt the first two results in order; do not crawl sites or substitute links."""
    discovery=search(query,'duckduckgo',2,fallback=False);links=discovery['results'][:2]
    with ThreadPoolExecutor(max_workers=2) as pool:
        pages=list(pool.map(lambda row:read_page(row,question,folder),links))
    result={'engine':'duckduckgo','pages':pages,
            'attempted_links':len(pages),'read_links':sum(p['status']=='read' for p in pages),
            'note':'Only the first two result pages were attempted. Exact focused evidence, not a whole-site crawl or a factual guarantee. Unavailable sources remain explicit.'}
    while len(json.dumps(result,ensure_ascii=False).encode())>7000:
        longest=max((p for p in pages if p.get('excerpt')),key=lambda p:len(p['excerpt'].encode()),default=None)
        if longest is None:raise ValueError('Source metadata exceeds the research result budget')
        longest['excerpt']=longest['excerpt'].encode()[:-256].decode(errors='ignore')
        longest['truncated']=True;longest['returned_bytes']=len(longest['excerpt'].encode())
    return result
