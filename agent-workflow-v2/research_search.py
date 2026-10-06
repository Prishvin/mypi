"""Search public web indexes and report fallback behavior explicitly."""
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlsplit, parse_qs, unquote
from research_fetch import get, PageText


def html_results(raw: str, engine: str, limit: int) -> list[dict]:
    """Extract external result links without treating search snippets as evidence."""
    parser = PageText(); parser.feed(raw)
    results, seen = [], set()
    for row in parser.links:
        url = row['url']
        if url.startswith('//'):
            url = 'https:'+url
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if parts.path == '/url':
            url = query.get('q',query.get('url',['']))[0]
        elif 'uddg' in query:
            url = unquote(query['uddg'][0])
        target = urlsplit(url)
        if target.scheme not in ['https','http'] or not target.hostname or not row['title'].strip():
            continue
        if any(target.hostname == domain or target.hostname.endswith('.'+domain) for domain in
               ['google.com','googleusercontent.com','duckduckgo.com','bing.com','microsoft.com']):
            continue
        if url not in seen:
            results.append({'title':row['title'].strip()[:250], 'url':url})
            seen.add(url)
        if len(results) >= limit:
            break
    return results


def search(query: str, engine='google', limit=5, fallback=True) -> dict:
    """Try Google first, then alternate indexes if the requested index is blocked."""
    if not query.strip() or len(query) > 400 or engine not in ['google','duckduckgo','bing']:
        raise ValueError('Use a concise public query (1-400 characters) and a supported engine')
    limit = max(1,min(8,limit))
    errors = []
    order = [engine] + ([x for x in ['duckduckgo','bing'] if x != engine] if fallback else [])
    for candidate in order:
        try:
            if candidate == 'google':
                raw, _, _ = get('https://www.google.com/search?'+urlencode({'q':query,'num':limit,'gbv':'1'}),browser_style=True)
                results = html_results(raw,candidate,limit)
            elif candidate == 'duckduckgo':
                raw, _, _ = get('https://lite.duckduckgo.com/lite/?'+urlencode({'q':query}))
                results = html_results(raw,candidate,limit)
            else:
                raw, _, _ = get('https://www.bing.com/search?'+urlencode({'q':query,'format':'rss'}))
                tree = ET.fromstring(raw)
                results = [{'title':item.findtext('title','')[:250], 'url':item.findtext('link','')}
                           for item in tree.findall('./channel/item')[:limit]]
            if results:
                return {'query':query,'requested_engine':engine,'used_engine':candidate,
                        'fallback_errors':errors,'results':results,
                        'note':'Discovery links only. Fetch relevant sources before citing claims.'}
            errors.append(candidate+': no readable results (possibly blocked)')
        except (OSError, ValueError, ET.ParseError) as error:
            errors.append(candidate+': '+str(error)[:300])
    raise ValueError('Search unavailable: '+'; '.join(errors))
