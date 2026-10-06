"""CLI for bounded public research and source-linked briefs in private Pi sessions."""
import argparse
import json
from pathlib import Path
from research_fetch import fetch
from research_search import search
from research_briefs import save_source, distill, load_source


def execute(folder: Path, request: dict) -> dict:
    """Dispatch a bounded search, fetch, archived-page selection or brief creation."""
    action = request['action']
    if action == 'search':
        return search(request['query'],request.get('engine','google'),request.get('limit',5))
    if action == 'fetch':
        return save_source(folder,fetch(request['url']),request.get('query',''))
    if action == 'excerpt':
        return save_source(folder,load_source(folder,request['artifact_id']),request.get('query',''))
    if action == 'brief':
        return distill(folder,request['goal'],request['findings'],request.get('decision',''),request.get('uncertainties',[]))
    raise ValueError('Use search, fetch, excerpt or brief')


def main() -> int:
    """Keep research output separate from project code and frozen acceptance fixtures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--request',type=Path,required=True)
    args = parser.parse_args()
    try:
        result = execute(args.session/'research',json.loads(args.request.read_text()))
        print(json.dumps(result))
        return 0
    except (OSError,ValueError,KeyError,IndexError) as error:
        print(json.dumps({'error':str(error),'retry':'Use another public source or a narrower query; do not fabricate evidence'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
