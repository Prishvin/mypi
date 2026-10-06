"""Validate concise researched facts against exact privately archived sources."""
import collections
import json
from pathlib import Path
from research_briefs import distill, load_source


def validate(session, request):
    """Require fetched evidence for every fact and implementation pointer."""
    topics = request.get('topics', [])
    reason = request.get('skipped_reason', '')
    if not isinstance(topics, list) or len(topics) > 4 or not isinstance(reason, str) or len(reason) > 400:
        raise ValueError('Research at most four relevant topics and keep skip reasons short')
    if not topics and not reason.strip():
        raise ValueError('Explain why no external research is needed')
    verified, names, words = [], set(), collections.Counter()
    for topic in topics:
        keyword, why = topic['keyword'], topic['why']
        if not isinstance(keyword, str) or not 1 <= len(keyword) <= 80 or keyword.casefold() in names:
            raise ValueError('Use unique short research keywords')
        if not isinstance(why, str) or not 1 <= len(why) <= 200:
            raise ValueError('State briefly why this term affects the requested work')
        names.add(keyword.casefold())
        findings = topic['findings']
        if not 1 <= len(findings) <= 3 or any(len(r['claim']) > 300 for r in findings):
            raise ValueError('Keep 1-3 concise source-backed facts per topic')
        result = distill(session / 'research', keyword, findings, why, [])
        for row in result['brief']['findings']:
            words[row['url']] += len(row['evidence'].split())
            if words[row['url']] > 25:
                raise ValueError('Evidence quotes exceed 25 words total for a source')
        implementations = topic.get('implementation_artifacts', [])
        if len(implementations) > 2:
            raise ValueError('Use at most two exact implementation pointers per topic')
        links = [load_source(session / 'research', item)['url'] for item in implementations]
        verified.append({'keyword': keyword, 'why': why,
                         'findings': result['brief']['findings'], 'implementations': links,
                         'brief_path': result['brief_path']})
    return {'version': 1, 'topics': verified, 'skipped_reason': reason}


def save(session, request, output):
    """Persist a verified draft outside source; publication belongs to the service."""
    result = validate(session, request)
    if len(json.dumps(result).encode()) > 20000:
        raise ValueError('Research draft is too large')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    return {'draft': str(output), 'topics': [t['keyword'] for t in result['topics']],
            'note': 'Source presence and hashes verified; semantic applicability still requires review.'}
