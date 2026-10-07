"""Observe test discovery from declared framework output, without model judgment."""
import re


def count(argv,text):
    """Return measured unittest or Node test-runner counts; unknown frameworks remain explicit."""
    if any(argv[i:i+2]==['-m','unittest'] for i in range(len(argv)-1)):
        matches=re.findall(r'Ran (\d+) tests?\b',text)
        return int(matches[-1]) if matches else None
    if '--test' in argv and argv[0].rsplit('/',1)[-1] in ('node', 'nodejs'):
        clean=re.sub(r'\x1b\[[0-9;]*m','',text)
        matches=re.findall(r'(?m)^(?:#|ℹ) tests (\d+)\s*$',clean)
        return int(matches[-1]) if matches else None
    return None
