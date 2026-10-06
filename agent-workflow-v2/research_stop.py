"""Recognize only a digest-bound research completion, never a timeout or failure."""
import hashlib
import json
from pathlib import Path


def exit_code(raw, session, output, phase='research'):
    """Treat Pi's deliberate store-and-stop as completion only with its exact marker."""
    if raw not in [0, 1] or not output.is_file():
        return raw or 1
    try:
        marker = json.loads((session / (phase + '-stop.json')).read_text())
        saved = json.loads(output.read_text())
    except (OSError, ValueError):
        return raw or 1
    matches = (marker.get('output') == str(output) and
               marker.get('sha256') == hashlib.sha256(output.read_bytes()).hexdigest() and
               marker.get('reason') == 'Verified ' + phase + ' draft saved' and saved.get('version') == 1)
    return 0 if matches else raw or 1
