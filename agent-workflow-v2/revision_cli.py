"""CLI for proposal-only contract review and separate exact-digest approval."""
import argparse
import json
from pathlib import Path
from contract_revision import propose, approve


def main(argv):
    """Keep generation and approval separate from execution."""
    parser = argparse.ArgumentParser(prog='mypi revision')
    sub = parser.add_subparsers(dest='action', required=True)
    review = sub.add_parser('propose')
    review.add_argument('project', type=Path); review.add_argument('evidence', type=Path)
    review.add_argument('--out', type=Path, required=True, help='New external proposal folder')
    review.add_argument('--reason', required=True)
    review.add_argument('--planner', choices=['qwen', 'chatgpt'], default='qwen')
    review.add_argument('--timeout', type=int, default=1800)
    approval = sub.add_parser('approve')
    approval.add_argument('project', type=Path); approval.add_argument('proposal', type=Path)
    approval.add_argument('--out', type=Path, required=True)
    approval.add_argument('--sha256', required=True); approval.add_argument('--reason', required=True)
    approval.add_argument('--criteria-only', action='store_true', help='Approve exact criterion corrections; retain the original steps, test strategy and controls')
    args = parser.parse_args(argv)
    try:
        result = (propose(args.project, args.evidence, args.out, args.reason, args.planner, args.timeout)
                  if args.action == 'propose' else approve(args.project, args.proposal, args.out, args.sha256, args.reason,
                                                         criteria_only=args.criteria_only))
        print(json.dumps(result, indent=2))
        return int(result.get('passed') is False)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, str(error)+'\n')
