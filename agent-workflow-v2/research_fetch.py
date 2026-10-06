"""Fetch bounded public research material without access to local services."""
import ipaddress
import json
import re
import socket
import gzip
from io import BytesIO
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

MAX_BYTES = 1048576


def public_url(url: str) -> str:
    """Allow public HTTP(S) pages and reject credentials, local DNS and private IPs."""
    parts = urlsplit(url)
    if parts.scheme not in ['http', 'https'] or not parts.hostname or parts.username or parts.password:
        raise ValueError('Use a public http(s) URL without credentials')
    if parts.port not in [None, 80, 443] or parts.hostname in ['localhost', 'localhost.localdomain']:
        raise ValueError('Local services and nonstandard ports are unavailable to research')
    addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80))
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('Research cannot access private or local network addresses')
    return url


class PublicRedirects(HTTPRedirectHandler):
    """Validate redirects as well as the original public destination."""
    max_redirections = 3

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Reject a redirect into a local service before opening it."""
        public_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def get(url: str, browser_style=False) -> tuple[str, str, str]:
    """Read a public page with a timeout and a hard response-size bound."""
    public_url(url)
    headers = {'User-Agent':'PiWorkflowResearch/1.0 (public documentation research)',
               'Accept':'text/html,application/json,text/plain', 'Accept-Encoding':'identity'}
    if browser_style:
        headers.update({'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
                        'Accept-Language':'en-US,en;q=0.9'})
    request = Request(url, headers=headers)
    with build_opener(PublicRedirects()).open(request, timeout=12) as response:
        final = public_url(response.url)
        content_type = response.headers.get_content_type()
        raw = response.read(MAX_BYTES+1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Page exceeds 1 MiB; select a smaller documentation page')
        if response.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.GzipFile(fileobj=BytesIO(raw)).read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:
                raise ValueError('Decompressed page exceeds 1 MiB')
        if content_type not in ['text/html','text/plain','text/markdown','application/json','application/xml','text/xml']:
            raise ValueError(f'Unsupported research content type {content_type}')
        return raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace'), final, content_type


class PageText(HTMLParser):
    """Extract prose and links while dropping scripts, styles and navigation chrome."""
    def __init__(self):
        """Initialize bounded parser state for one fetched page."""
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.hidden = [], [], []
        self.link = None

    def handle_starttag(self, tag, attrs):
        """Track hidden blocks, readable line boundaries and candidate links."""
        if tag in ['script','style','noscript','nav','header','footer']:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag in ['p','div','li','h1','h2','h3','pre','br','article','section']:
            self.parts.append('\n')
        if tag == 'a':
            self.link = {'url':dict(attrs).get('href',''), 'title':''}

    def handle_endtag(self, tag):
        """Finish visible links and resume prose after a hidden block."""
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag == 'a' and self.link:
            self.links.append(self.link); self.link = None
        if tag in ['p','div','li','pre']:
            self.parts.append('\n')

    def handle_data(self, data):
        """Keep readable text and candidate link labels."""
        if self.hidden:
            return
        self.parts.append(data)
        if self.link is not None:
            self.link['title'] += data

    def text(self) -> str:
        """Normalize whitespace without merging separate paragraphs."""
        return '\n'.join(line for line in (re.sub(r'\s+',' ',x).strip() for x in ''.join(self.parts).splitlines()) if line)


def extract(raw: str) -> str:
    """Convert a public HTML fragment into compact searchable text."""
    parser = PageText(); parser.feed(raw)
    return parser.text()


def fetch(url: str) -> dict:
    """Prefer model cards and community APIs, with normal HTML as the generic path."""
    parts = urlsplit(url)
    host, path = parts.hostname or '', parts.path
    if host == 'huggingface.co' and re.fullmatch(r'/[^/]+/[^/]+/?', path):
        raw, final, kind = get(url.rstrip('/')+'/resolve/main/README.md')
        return {'url':url, 'fetched_url':final, 'text':raw, 'source_type':'model-card'}
    if host.endswith('stackoverflow.com') and re.match(r'/questions/\d+', path):
        identifier = path.split('/')[2]
        api = 'https://api.stackexchange.com/2.3/questions/'+identifier
        query = '?'+urlencode({'site':'stackoverflow','filter':'withbody'})
        question = json.loads(get(api+query)[0])
        answers = json.loads(get(api+'/answers'+query+'&sort=votes&order=desc')[0])
        entries = question.get('items', []) + answers.get('items', [])[:5]
        text = '\n\n'.join(f"Score {row.get('score')}; accepted={row.get('is_accepted',False)}; updated={row.get('last_activity_date')}\n"+
                           row.get('title','')+'\n'+extract(row.get('body','')) for row in entries)
        if not text:
            raise ValueError('Stack Exchange returned no question/answers; retry later or select another source')
        return {'url':url, 'fetched_url':api+query, 'text':text, 'source_type':'community-answer'}
    if host in ['reddit.com','www.reddit.com','old.reddit.com'] and '/comments/' in path:
        try:
            raw, final, kind = get('https://www.reddit.com'+path.rstrip('/')+'.json?raw_json=1&limit=15',browser_style=True)
            listings = json.loads(raw)
            post = listings[0]['data']['children'][0]['data']
            comments = [row['data'] for row in listings[1]['data']['children'] if row.get('kind')=='t1']
            text = post.get('title','')+'\n'+post.get('selftext','')+'\n\n'
            text += '\n\n'.join(f"Score {c.get('score')}; created={c.get('created_utc')}\n{c.get('body','')}" for c in comments[:15])
            return {'url':url, 'fetched_url':final, 'text':text, 'source_type':'community-report'}
        except (OSError, ValueError, KeyError, IndexError):
            pass
    raw, final, kind = get(url,browser_style=host in ['reddit.com','www.reddit.com','old.reddit.com'])
    if kind == 'text/html':
        from research_content import article, links
        text, extraction = article(raw,final)
        targets=links(raw,final)
    else:
        text, extraction = raw, 'public-text'
        targets=[]
    if len(text) < 80 or any(x in text.casefold()[:3000] for x in ['verify you are human','unusual traffic','you\'ve been blocked']):
        raise ValueError('Source is blocked or has too little readable content; select another source')
    return {'url':url, 'fetched_url':final, 'text':text, 'source_type':'community-report' if 'reddit' in host else 'web-page','extraction':extraction,'links':targets}
