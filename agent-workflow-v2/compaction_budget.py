"""Fit deterministic handoffs to measured request tokens, preserving the full task."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
from tokenizers import Tokenizer
from token_budget import ADMISSION_FACTOR, TEMPLATE_RESERVE, REQUEST_TRANSFORM_RESERVE


def fit(candidate, payload, input_limit, counter):
    """Keep actual system/tools, bound history headroom, and omit optional source whole."""
    if type(input_limit) is not int or input_limit < 512:
        raise ValueError('Compaction requires a valid effective input token limit')
    field = 'messages' if isinstance(payload.get('messages'), list) else 'input'
    if not isinstance(payload.get(field), list) or not isinstance(payload.get('tools'), list):
        raise ValueError('Missing recorded request envelope for compaction measurement')
    prefix, raw = candidate['summary'].split('\n', 1)
    data = json.loads(raw)
    task = copy.deepcopy(data['task'])
    stats = copy.deepcopy(candidate['stats'])
    budget = max(512, math.floor(input_limit * .75) - REQUEST_TRANSFORM_RESERVE)
    projected = copy.deepcopy(payload)
    system = [message for message in projected[field]
              if isinstance(message, dict) and message.get('role') in ('system', 'developer')]
    if not system and not (field == 'input' and isinstance(projected.get('instructions'), str)
                           and projected['instructions'].strip()):
        raise ValueError('Recorded compaction envelope has no system instructions')
    # Responses may otherwise replay server-side history in addition to the handoff.
    projected.pop('previous_response_id', None)
    projected.pop('conversation', None)

    def measure():
        summary = prefix+'\n'+json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        projected[field] = system + [{'role': 'user', 'content': [
            {'type': 'text' if field == 'messages' else 'input_text',
             'text': 'Continue using the complete frozen task and current evidence.\n<summary>\n'+summary+'\n</summary>'}]}]
        tokens = counter(json.dumps(projected, ensure_ascii=False, separators=(',', ':')))
        admitted = math.ceil(tokens * ADMISSION_FACTOR) + TEMPLATE_RESERVE
        return summary, tokens, admitted

    summary, tokens, admitted = measure()
    memory = data.get('retrieved_sources', {})
    while admitted > budget and memory.get('entries'):
        memory['entries'].pop(); stats['retained'] -= 1; stats['omitted'] += 1
        memory['omitted'] = stats['omitted']
        summary, tokens, admitted = measure()
    if admitted > budget:
        investigation = data.get('investigation', {})
        investigation['omitted_recent_tools'] = len(investigation.get('recent_tools', []))
        investigation['recent_tools'] = []
        if investigation:
            investigation['local_evidence'] = 'execution-progress.json retains the original observations'
        for row in data.get('failures', []):
            row['omitted_failed_names'] = row.get('omitted_failed_names', 0) + len(row.pop('failed_names', []))
        summary, tokens, admitted = measure()
    if admitted > budget:
        raise ValueError(f'Complete frozen handoff needs {admitted} estimated admission tokens; '
                         f'compaction budget is {budget} of input cap {input_limit}. Split the task; no contract fields were removed.')
    assert data['task'] == task
    return {'summary': summary, 'stats': stats, 'budget': {
        'estimated_input_tokens': tokens, 'admission_tokens': admitted,
        'handoff_budget_tokens': budget, 'input_limit': input_limit, 'passed': True,
        'method': 'Recorded system/tools plus proposed handoff, Qwen tokenizer, 25% + 256 admission margin; '
                  'reserve 25% of input and 1024 tokens for further work. Actual next request is admitted again.'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--limit', required=True, type=int)
    args = parser.parse_args()
    if args.candidate.resolve().parent != args.session.resolve():
        raise ValueError('Compaction candidate must belong to the active session')
    candidate = json.loads(args.candidate.read_text())
    payload = json.loads((args.session/'request-budget.json').read_text())
    tokenizer = Tokenizer.from_file(os.environ.get('QWEN_WORKFLOW_TOKENIZER', str(Path(__file__).with_name('qwen-tokenizer.json'))))
    result = fit(candidate, payload, args.limit, lambda text: len(tokenizer.encode(text).ids))
    (args.session/'compaction-budget-result.json').write_text(json.dumps(result['budget'], indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
