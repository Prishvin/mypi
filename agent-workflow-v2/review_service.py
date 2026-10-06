"""Run one final evidence-based review and preserve its follow-up plan separately."""
import hashlib
import json
from pathlib import Path
from runner_process import BASE, invoke, read, save
from review_packet import build
from project_lock import exclusive
from project_map import scan
from role_selection import backend as normalize, load, CLOUD_MODEL


def review(root, plan, run_dir, reviewer=None, timeout=600, output=None):
    """Reuse an unchanged completed review; failures never re-execute accepted todos."""
    root,plan,run_dir=root.resolve(),plan.resolve(),run_dir.resolve()
    selected=normalize(reviewer) if reviewer else load(root)['reviewer']
    folder=output.resolve() if output else run_dir/'final-review'
    if folder.is_relative_to(root):raise ValueError('Keep review artifacts outside the project')
    with exclusive(root,BASE):
        packet=build(root,plan,run_dir)
        prior=read(folder/'result.json')
        if prior.get('passed'):
            if prior['packet_sha256']!=packet['packet_sha256'] or prior['reviewer']!=selected:
                raise ValueError('Review inputs or backend changed; use --out for a new review')
            report=folder/'review.json'
            if hashlib.sha256(report.read_bytes()).hexdigest()!=prior['report_sha256']:
                raise ValueError('Saved review changed; choose a new review output')
            saved=read(report)
            if saved.get('followup_plan') and hashlib.sha256(Path(saved['followup_plan']).read_bytes()).hexdigest()!=saved['followup_sha256']:
                raise ValueError('Saved follow-up plan changed; choose a new review output')
            return {**prior,'cached':True,'new_model_requests':0}
        folder.mkdir(parents=True,exist_ok=True)
        save(folder/'packet.json',packet)
        prompt='Review this completed run and plan only useful tests/fixes.\n'+json.dumps(packet)
        existing=folder/'followup-plan.json'
        if existing.exists():
            prompt+='\nA follow-up plan was already saved in an interrupted review. Do not call plan_store again. Review this proposal and finish review_store; if it needs changes, stop and request a new review output.\n'+existing.read_text()
        if len(prompt.encode())>80000:raise ValueError('Split oversized review evidence before retrying')
        request=folder/'request.txt';request.write_text(prompt)
        attempt=folder/('attempt-'+str(len(list(folder.glob('attempt-*')))+1))
        command=[str(BASE/'qwen-agent'),'--profile','chatgpt-quality' if selected=='chatgpt' else 'mtplx-quality',
            '--project',str(root),'--role','reviewer','--batch','--json','--quiet',
            '--prompt-file',str(request),'--review-packet',str(folder/'packet.json'),
            '--phase-output',str(folder/'review.json'),'--plan',str(folder/'followup-plan.json'),
            '--input-tokens','40960','--output-tokens','32768','--context','98304',
            '--thinking','on','--reasoning','xhigh' if selected=='chatgpt' else 'medium']
        result=invoke(command,attempt,timeout)
        from run_metrics import collect
        result.update(metrics=collect(result,attempt),reviewer=selected,packet_sha256=packet['packet_sha256'],
                      model=CLOUD_MODEL if selected=='chatgpt' else 'mtplx-quality',cached=False)
        result['passed']=result['exit_code']==0 and scan(root,['.'])['snapshot']==packet['snapshot']
        if result['passed']:
            from review_store import validate
            report=read(folder/'review.json')
            try:
                validate(report,packet,folder/'followup-plan.json')
                result.update(verdict=report['verdict'],review=str(folder/'review.json'),followup_plan=report['followup_plan'],
                              report_sha256=hashlib.sha256((folder/'review.json').read_bytes()).hexdigest())
            except (OSError,ValueError,KeyError,TypeError) as error:
                result.update(passed=False,validation_error=str(error))
        save(folder/'result.json',result)
        return result
