"""Validate a bounded ambiguity decision; question scheduling belongs to Python."""
import argparse
import json
from pathlib import Path
from runner_process import save


def strings(value, maximum, limit):
    """Require short nonempty lists of observations without coercing model output."""
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError('Invalid intake list')
    if any(not isinstance(x, str) or not x.strip() or len(x.encode()) > limit for x in value):
        raise ValueError('Invalid intake list item')
    return value


def validate(data, rounds):
    """Reject a third question and incomplete or oversized refined prompts."""
    if type(rounds) is not int or not 0 <= rounds <= 2:
        raise ValueError('Invalid clarification round count')
    mode = data.get('mode')
    if mode not in ('ask', 'ready', 'blocked'):
        raise ValueError('Intake mode must be ask, ready or blocked')
    result = {'version': 1, 'mode': mode,
              'assumptions': strings(data.get('assumptions', []), 8, 500),
              'unresolved': strings(data.get('unresolved', []), 8, 500)}
    if mode == 'ask':
        if rounds >= 2:
            raise ValueError('Two clarification rounds exhausted; no third question')
        question = data.get('question', {})
        text = question.get('text')
        if not isinstance(text, str) or not text.strip() or len(text.encode()) > 1000:
            raise ValueError('Ask one short focused question')
        options = strings(question.get('options', []), 4, 300)
        if len(options) == 1:
            raise ValueError('Supply zero or 2-4 suggested answers')
        result['question'] = {'text': text, 'options': options}
    if mode == 'ready':
        text = data.get('refined_prompt')
        if not isinstance(text, str) or not text.strip() or len(text.encode()) > 8192:
            raise ValueError('Ready needs one nonempty refined prompt within 8 KiB')
        if result['unresolved']:
            raise ValueError('Essential unresolved uncertainty requires blocked, not ready')
        result['refined_prompt'] = text
    if mode == 'blocked' and not result['unresolved']:
        raise ValueError('Blocked requires explicit unresolved uncertainty')
    return result


def main():
    """Save only a checked decision outside the source project."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, required=True)
    args = parser.parse_args()
    try:
        data = validate(json.loads(args.request.read_text()), args.rounds)
        save(args.output, data)
        print(json.dumps({'output': str(args.output), 'mode': data['mode']}))
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
