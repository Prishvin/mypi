"""Keep observed assertion fields attached to their test, without evaluating values."""
import json
import re

HEADER = re.compile(r'^(?:✖\s+(?!failing tests:)(.+)|(?:FAIL|ERROR):\s+(.+)|not ok \d+ - (.+))$')
CAUSE = re.compile(r'^(?:[\w.]*Error|[\w.]*Exception)(?:\s+\[[^\]\r\n]{1,80}\])?:')
FIELD = re.compile(r'^(actual|expected|operator):\s*(.*)$')


def grouped(lines, max_bytes=6000, max_cases=8):
    """Parse reporter-labelled blocks; omit whole excess cases and mark field truncation."""
    cases, current = [], None

    def finish():
        nonlocal current
        if current and current.get('causes') and current not in cases:
            cases.append(current)
        current = None

    for line in lines:
        header = HEADER.match(line)
        if header:
            finish()
            name=next(value for value in header.groups() if value is not None)
            name=re.sub(r'\s+\([\d.]+ms\)$','',name)
            current={'test':name[:240], 'causes':[]}
            if len(name)>240:current['name_truncated']=True
        elif line.startswith(('test at ', '✔ ', 'ℹ ', '# tests ', 'Ran ', 'FAILED ')):
            finish()
        elif current is not None:
            if CAUSE.match(line) or line.startswith('error:'):
                cause=line[:300]
                if cause not in current['causes']:
                    if len(current['causes'])<2:current['causes'].append(cause)
                    else:current['omitted_causes']=current.get('omitted_causes',0)+1
                if len(line)>300:current['cause_truncated']=True
            elif current['causes']:
                field=FIELD.match(line)
                if field:
                    key,value=field.groups();value=value.rstrip(',')
                    current[key]=value[:160]
                    if len(value)>160 or value in ('{','['):
                        current.setdefault('partial_fields',[]).append(key)
    finish()
    kept=[]
    for row in cases:
        if len(kept)>=max_cases or len(json.dumps([*kept,row],ensure_ascii=False).encode())>max_bytes:
            break
        kept.append(row)
    return kept,len(cases)-len(kept)
