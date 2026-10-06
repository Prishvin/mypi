"""Validate a review against its evidence and separately saved follow-up plan."""
import argparse
import hashlib
import json
from pathlib import Path
from plan_runner import validate as validate_plan
from runner_process import save


def validate(data, packet, plan_path):
    """Require traceable findings and executable granular follow-up contracts."""
    verdict=data.get('verdict'); findings=data.get('findings',[]); summary=data.get('summary')
    if verdict not in ('clean','followup') or not isinstance(summary,str) or not 1<=len(summary)<=1500:
        raise ValueError('Review needs a clean/followup verdict and concise summary')
    if not isinstance(findings,list) or len(findings)>8:
        raise ValueError('Keep at most eight concrete review findings')
    if (verdict=='clean') != (len(findings)==0):
        raise ValueError('Clean means no actionable findings; followup needs findings')
    plan=None
    if verdict=='followup':
        plan=json.loads(plan_path.read_text()); validate_plan(Path(packet['project']),plan)
        if any(t['status']!='todo' for t in plan['tasks']):
            raise ValueError('Review follow-up tasks must be pending')
    elif plan_path.exists():
        raise ValueError('A saved follow-up plan requires a followup verdict')
    identifiers={t['id'] for t in plan['tasks']} if plan else set()
    covered=set(); allowed=set(packet['evidence_ids']+packet['source_paths'])
    for finding in findings:
        if finding.get('kind') not in ('unit-test-gap','e2e-test-gap','integration-test-gap','observed-bug','risk'):
            raise ValueError('Classify each review finding')
        if not isinstance(finding.get('observation'),str) or not 1<=len(finding['observation'])<=800:
            raise ValueError('Keep findings concise')
        refs=finding.get('evidence',[]); todo=finding.get('tasks',[])
        if not refs or not set(refs)<=allowed or not todo or not set(todo)<=identifiers:
            raise ValueError('Each finding needs real packet evidence and follow-up task IDs')
        covered.update(todo)
    if identifiers!=covered: raise ValueError('Every follow-up todo must address a review finding')
    return {'version':1,'verdict':verdict,'summary':summary,'findings':findings,
            'snapshot':packet['snapshot'],'packet_sha256':packet['packet_sha256'],
            'followup_plan':str(plan_path) if plan else None,
            'followup_sha256':hashlib.sha256(plan_path.read_bytes()).hexdigest() if plan else None,
            'limitation':packet['limits']}


def main():
    """Save a bounded review without granting the model project writes."""
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('request','packet','plan','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try:
        data=json.loads(args.request.read_text());packet=json.loads(args.packet.read_text())
        result=validate(data,packet,args.plan)
        if result['verdict']=='followup':
            plan=json.loads(args.plan.read_text())
            plan['replan_lineage']={'parent_plan':packet['original_plan'],'reason':'final_review_followup',
                'completed':packet['completed_contracts'],'snapshot':packet['snapshot']}
            plan['acceptance_fixtures']={**packet.get('acceptance_fixtures',{}),**plan.get('acceptance_fixtures',{})}
            validate_plan(Path(packet['project']),plan);save(args.plan,plan)
            result=validate(data,packet,args.plan)
        save(args.output,result);print(json.dumps({'output':str(args.output),'verdict':result['verdict']}));return 0
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({'error':str(error)[:2000]}));return 1


if __name__=='__main__':raise SystemExit(main())
