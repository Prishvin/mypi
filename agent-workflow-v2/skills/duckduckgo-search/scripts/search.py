"""Discover public sources with explicit DuckDuckGo provenance and no fallback."""
import json
from pathlib import Path
import sys
from research_search import search

request = json.loads(Path(sys.argv[1]).read_text())
print(json.dumps(search(request['query'], 'duckduckgo', request.get('limit', 5), fallback=False)))
