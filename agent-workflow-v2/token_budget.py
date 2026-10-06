"""Count serialized local-Qwen request material before sending it to the server."""
import argparse
import os
import json
import math
from pathlib import Path
from tokenizers import Tokenizer


def count_request(path: Path, limit: int, tokenizer: Path) -> dict:
    """Count the full payload and add headroom for differing backend serialization."""
    tokens = len(Tokenizer.from_file(str(tokenizer)).encode(path.read_text()).ids)
    admitted = math.ceil(tokens * 1.25) + 256
    return {'estimated_input_tokens': tokens, 'admission_tokens': admitted,
            'limit': limit, 'passed': admitted <= limit,
            'method': 'Tokenizer on serialized payload + 25% + 256 template tokens; estimate, not exact backend count.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    parser.add_argument('--limit', type=int, required=True)
    args = parser.parse_args()
    result = count_request(args.request, args.limit, Path(os.environ.get('QWEN_WORKFLOW_TOKENIZER', str(Path(__file__).with_name('qwen-tokenizer.json')))))
    print(json.dumps(result))
    raise SystemExit(int(not result['passed']))
