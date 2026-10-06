"""Maintain a small project knowledge brief while preserving human-authored notes."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from knowledge_sources import save

START, END = '<!-- pi-research:start -->', '<!-- pi-research:end -->'
BASE = Path(__file__).resolve().parent


def digest(text):
    """Identify exact brief bytes for caching and source freshness checks."""
    return hashlib.sha256(text.encode()).hexdigest()


def read_project(root):
    """Read brief research context only, never implementation or arbitrary files."""
    path = root / 'knowledge.md'
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file():
        raise ValueError('knowledge.md must be a regular project file')
    text = path.read_text()
    if len(text.encode()) > 8192 or len(text.splitlines()) > 80:
        raise ValueError('Keep knowledge.md within 80 lines and 8 KiB; archive detailed notes separately')
    return {'path': 'knowledge.md', 'text': text, 'sha256': digest(text)}


def inline(text):
    """Keep agent prose on one Markdown line without HTML directives."""
    return ' '.join(text.split()).replace('<', '&lt;').replace('>', '&gt;')


def render(topics):
    """Render facts and exact URLs, omitting raw evidence, logs and source bodies."""
    lines = [START, '## Researched facts', '', 'External evidence; apply to the task after review.', '']
    for topic in topics:
        lines += ['### ' + inline(topic['keyword']), inline(topic['why'])]
        for row in topic['findings']:
            url = row['url']
            if urlsplit(url).scheme not in ['http', 'https']:
                raise ValueError('Knowledge links require public source URLs')
            lines.append('- ' + inline(row['claim']) + ' [Source](<' + url + '>).')
        for url in topic['implementations']:
            lines.append('- [Implementation reference](<' + url + '>).')
        lines.append('')
    if not topics:
        lines += ['No external facts were required by the completed research pass.', '']
    return '\n'.join(lines + [END])


def split(text):
    """Find only this workflow's managed section; leave surrounding notes intact."""
    if not text:
        return '# Project knowledge\n\n', '', ''
    if START not in text and END not in text:
        return text.rstrip() + '\n\n', '', ''
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) >= text.index(END):
        raise ValueError('Malformed managed knowledge section; preserve it for manual review')
    first, rest = text.split(START, 1)
    body, last = rest.split(END, 1)
    return first, START + body + END, last


def cache_path(root, base=BASE):
    """Keep detailed provenance and cache state outside the source project."""
    return base / 'knowledge-cache' / digest(str(root.resolve()))[:16] / 'index.json'


def publish(root, draft, request, expected, base=BASE):
    """Merge verified topics, reject concurrent edits, and replace only owned notes."""
    current = read_project(root)
    if current != expected:
        raise ValueError('knowledge.md changed during research; preserve evidence and retry deliberately')
    first, owned, last = split(current.get('text', ''))
    cache = cache_path(root, base)
    from knowledge_journal import recover, commit
    recover(root, cache, digest)
    prior = json.loads(cache.read_text()) if cache.exists() else {}
    if owned and owned != render(prior.get('topics', [])):
        raise ValueError('Managed knowledge changed or its provenance cache is missing; do not overwrite it')
    merged = {t['keyword'].casefold(): t for t in prior.get('topics', [])}
    merged.update({t['keyword'].casefold(): t for t in draft['topics']})
    topics = list(merged.values())
    text = first + render(topics) + last
    if len(topics) > 12 or len(text.encode()) > 8192 or len(text.splitlines()) > 80:
        raise ValueError('Knowledge brief is full; shorten or archive topics explicitly, never silently discard them')
    state = {'version': 1, 'project': str(root), 'request_sha256': digest(request),
             'knowledge_sha256': digest(text), 'topics': topics, 'skipped_reason': draft['skipped_reason'],
             'created_epoch': time.time()}
    commit(root, cache, state, text)
    return {'path': str(root / 'knowledge.md'), 'bytes': len(text.encode()), 'topics': [t['keyword'] for t in topics]}


def main():
    """Validate a model's fact draft without giving the research role source edits."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(save(args.session, json.loads(args.request.read_text()), args.output)))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)[:2000]}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
