"""Noninteractive bridge for Pi's first-message clarification and research hook."""
import argparse
import json
from pathlib import Path
from request_pipeline import prepare
from runner_process import save


def main():
    """Persist pending questions so the parent Pi UI asks without a model loop."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('project','request-file','out','answers-file'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--backend',choices=['qwen','chatgpt'],required=True)
    args = parser.parse_args()
    try:
        request = args.request_file.read_text()
        answers = json.loads(args.answers_file.read_text())
        result = prepare(args.project,request,args.out,args.backend,300,answers=answers)
        save(args.out.with_suffix('.bridge-result.json'),result)
        return 0 if result['passed'] else 2 if result.get('stage')=='awaiting_clarification' else 1
    except (OSError,ValueError,RuntimeError) as error:
        save(args.out.with_suffix('.bridge-result.json'),{'passed':False,'error':str(error)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
