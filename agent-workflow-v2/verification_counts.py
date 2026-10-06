"""Observe test discovery from declared framework output, without model judgment."""
import re


def count(argv,text):
    """Return a measured unittest count, or None for other commands/unrecognized output."""
    if any(argv[i:i+2]==['-m','unittest'] for i in range(len(argv)-1)):
        matches=re.findall(r'Ran (\d+) tests?\b',text)
        return int(matches[-1]) if matches else None
    return None
