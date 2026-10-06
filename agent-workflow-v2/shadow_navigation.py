"""Measure planning material and enforce architecture-led reads for large projects."""
import json
import hashlib
import os
from functools import lru_cache
from pathlib import Path
from tokenizers import Tokenizer
import architecture_map
from project_map import outline, scan

THRESHOLD = 32768
MAX_FILES = 5
MAX_SELECTED_TOKENS = 8192


@lru_cache(maxsize=4)
def tokenizer(path: str):
    """Load the private tokenizer once per process; never approximate with bytes."""
    return Tokenizer.from_file(path)


def count(text: str, path=None) -> int:
    """Count text tokens without model-specific special tokens or a chat envelope."""
    path = path or os.environ.get('QWEN_WORKFLOW_TOKENIZER', str(Path(__file__).with_name('qwen-tokenizer.json')))
    return len(tokenizer(str(path)).encode(text, add_special_tokens=False).ids)


def measure(data: dict, counter=count) -> dict:
    """Count canonical prototypes once plus the generated architecture navigation map."""
    prototypes = '\n'.join(outline(record) for record in data['files'])
    shadow_tokens = counter(prototypes)
    architecture_tokens = counter(architecture_map.render(data))
    total = shadow_tokens + architecture_tokens
    return {'snapshot': data['snapshot'], 'shadow_tokens': shadow_tokens,
            'architecture_tokens': architecture_tokens, 'total_tokens': total,
            'threshold_tokens': THRESHOLD, 'architecture_only_navigation': total > THRESHOLD,
            'selected_file_limit': MAX_FILES, 'selected_token_limit': MAX_SELECTED_TOKENS,
            'method': 'Sum of tokenizer text counts for ALL-PROTOTYPES.txt and generated architecture.md; excludes duplicate indexes and chat overhead.'}


def instructions(policy: dict) -> str:
    """Give either planner provider the measured decision and retrieval sequence."""
    text = (f"SHADOW SIZE: prototypes={policy['shadow_tokens']} tokens; "
            f"architecture={policy['architecture_tokens']} tokens; total={policy['total_tokens']}; "
            f"threshold={THRESHOLD}. These are text counts, not the complete request budget.\n")
    if policy['architecture_only_navigation']:
        return text + ("Large-project planning: use ONLY generated architecture.md for project-wide navigation. "
            "Call project_map architecture first, paging module offset and section_offset separately. Read relevant section IDs with architecture-section and the current source_sha256 before making granular todos. Determine task-relevant module paths "
            "from that map, then inspect at most 5 selected shadow files per read, at most 8192 text tokens. "
            "Explain their relevance before reading them. Use query to narrow named interfaces when needed. "
            "locate must include explicit paths already seen in architecture. Global catalogues and "
            "unscoped symbol searches are blocked. Never accumulate the entire shadow through batches; "
            "select only contracts needed for the current task. Account for selected contracts in todo estimates.")
    return text + "Read architecture first, then use bounded navigation and task-relevant prototypes."


def initialize(data: dict, session: Path, tokenizer_path=None) -> dict:
    """Persist admission evidence and instructions outside the user's project."""
    path = Path(tokenizer_path or os.environ.get('QWEN_WORKFLOW_TOKENIZER', str(Path(__file__).with_name('qwen-tokenizer.json')))).resolve()
    if not path.is_file():
        raise ValueError('Shadow sizing requires the configured tokenizer: ' + str(path))
    policy = measure(data, lambda text: count(text, path))
    policy.update(tokenizer_path=str(path), tokenizer_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (session / 'shadow-budget.json').write_text(json.dumps(policy, indent=2))
    (session / 'plan-navigation.txt').write_text(instructions(policy))
    return policy


def planning_context(args, root: Path, prefixes: list[str]):
    """Recheck the snapshot for each planning tool; edits invalidate prior navigation."""
    if os.environ.get('QWEN_WORKFLOW_ROLE') not in ('architect', 'reviewer'):
        return None
    if args.command not in ('architecture', 'architecture-section', 'architecture-search', 'catalog', 'locate', 'context', 'save-plan'):
        return None
    session = Path(os.environ['QWEN_WORKFLOW_SESSION'])
    data = scan(root, prefixes)
    output = os.environ.get('QWEN_WORKFLOW_SHADOW')
    if output:
        import architecture_consistency
        report = architecture_consistency.check(root, prefixes, Path(output))
        if report['rebuild_required']:
            raise ValueError('Navigation is out of sync: ' + '; '.join(report['reasons']) + '. Ask the user to run /rebuild before continuing.')
    budget_path = session / 'shadow-budget.json'
    policy = json.loads(budget_path.read_text()) if budget_path.exists() else {}
    if policy.get('snapshot') != data['snapshot']:
        policy = initialize(data, session)
    state_path = session / 'navigation-state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get('snapshot') != data['snapshot']:
        state = {'snapshot': data['snapshot'], 'architecture_read': False, 'seen_paths': []}
    authorize(policy, state, args.command, getattr(args, 'paths', None))
    return data, policy, state, state_path


def authorize(policy: dict, state: dict, command: str, paths=None) -> None:
    """Block global alternate maps and require selection from architecture evidence."""
    if not policy['architecture_only_navigation'] or command == 'architecture':
        return
    if command == 'catalog':
        raise ValueError('Shadow exceeds 32768 tokens: navigate with project_map architecture, not catalog')
    if not state.get('architecture_read'):
        raise ValueError('Shadow exceeds 32768 tokens: read project_map architecture before planning or prototypes')
    if command in ('context', 'locate'):
        selected = set(paths or [])
        if not selected or len(selected) > MAX_FILES:
            raise ValueError('Select 1-5 explicit task-relevant paths from architecture.md')
        unknown = selected - set(state.get('seen_paths', [])) - {'architecture.md', 'knowledge.md'}
        if unknown:
            raise ValueError('Read the architecture page for these paths first: ' + ', '.join(sorted(unknown)))
        if command == 'locate' and selected & {'architecture.md', 'knowledge.md'}:
            raise ValueError('locate needs source module paths selected from architecture.md')


def record_architecture(context, paths, offset: int, limit: int) -> None:
    """Remember only modules returned by a successful architecture page."""
    data, _, state, state_path = context
    records = data['files']
    if paths is not None:
        records = [record for record in records if record['path'] in set(paths)]
    seen = set(state['seen_paths']) | {record['path'] for record in records[offset:offset + limit]}
    state.update(architecture_read=True, seen_paths=sorted(seen))
    state_path.write_text(json.dumps(state, indent=2))


def check_selected(policy: dict, text: str, counter=None) -> None:
    """Reject oversized prototype supplements without truncating their contracts."""
    if not policy['architecture_only_navigation']:
        return
    tokens = counter(text) if counter else count(text, policy.get('tokenizer_path'))
    if tokens > MAX_SELECTED_TOKENS:
        raise ValueError('Selected shadow exceeds 8192 tokens; select fewer files or named interfaces')


def record_section(context, paths):
    """Record only associated paths actually exposed by a bounded section read."""
    _, _, state, state_path = context
    state['seen_paths'] = sorted(set(state['seen_paths']) | set(paths))
    state_path.write_text(json.dumps(state, indent=2))
