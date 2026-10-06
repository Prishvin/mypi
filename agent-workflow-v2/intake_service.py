"""Persist at most two user clarifications and one consolidated planning request."""
import json
from pathlib import Path
from intake import validate
from knowledge import digest
from runner_process import read, save
from phase_service import run


def ask_terminal(question):
    """Ask once per round; EOF is an unanswered question, never agreement."""
    print('\n' + question['text'], flush=True)
    for index, option in enumerate(question['options'], 1):
        print(f'  {index}. {option}', flush=True)
    try:
        answer = input('Answer: ').strip()
    except EOFError:
        return None
    if answer.isdigit() and 1 <= int(answer) <= len(question['options']):
        answer = question['options'][int(answer)-1]
    return answer or None


def decision(project, request, state, folder, backend, timeout):
    """Run only when no durable pending decision exists."""
    if state.get('decision'):
        return validate(state['decision'], len(state['clarifications']))
    rounds = len(state['clarifications'])
    packet = {'original_request': request, 'answered_rounds': rounds,
              'remaining_question_rounds': 2-rounds, 'clarifications': state['clarifications']}
    result, draft = run(project, 'intake', json.dumps(packet, ensure_ascii=False),
                        folder/f'round-{rounds}', backend, timeout)
    state.setdefault('phases', []).append(result)
    if not draft:
        raise RuntimeError('Intake failed; inspect ' + result['log'])
    return validate(draft, rounds)


def refine(project, request, folder, backend='chatgpt', answers=None, interactive=False, timeout=300):
    """Resume pending questions; return before research if an answer is missing."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/'state.json'
    state = read(path) if path.exists() else {'version': 1, 'request_sha256': digest(request),
            'project': str(project.resolve()), 'backend': backend, 'clarifications': []}
    if (state['request_sha256'] != digest(request) or state['project'] != str(project.resolve())
            or state['backend'] != backend):
        raise ValueError('Intake request/project/backend changed; choose a new output path')
    while True:
        choice = decision(project, request, state, folder, backend, timeout)
        state['decision'] = choice
        save(path, state)
        if choice['mode'] != 'ask':
            state['status'] = choice['mode']
            if choice['mode'] == 'ready':
                state['refined_prompt'] = choice['refined_prompt']
                (folder/'refined-prompt.txt').write_text(choice['refined_prompt'])
            save(path, state)
            return state
        index = len(state['clarifications'])
        answer = answers[index] if answers is not None and index < len(answers) else None
        if answer is None and interactive:
            answer = ask_terminal(choice['question'])
        if answer is None:
            state['status'] = 'awaiting_clarification'
            save(path, state)
            return state
        if not isinstance(answer, str) or not answer.strip() or len(answer.encode()) > 8192:
            raise ValueError('A clarification answer must be nonempty and within 8 KiB')
        state['clarifications'].append({'question': choice['question'], 'answer': answer})
        state.pop('decision', None)
        save(path, state)
