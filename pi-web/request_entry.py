"""Dispatch only validated intent, with one shared clarification budget."""
import hashlib
import json
import time
import uuid
from pathlib import Path
import classifier
from request_routing import folder_for,without_code,FENCES


def resolve(job,text,resume=False):
    """Classify first; persist at most two answers and a resumable pending intake."""
    row=job.store.get(job.ident);pending=row.get('pending_route') if resume else None
    if resume and not pending:raise ValueError('No interrupted classification to resume')
    request=pending['request'] if pending else text
    answers=pending['answers'] if pending else []
    root=Path(pending['folder']) if pending else job.store.folder/job.ident/'routing'/str(time.time_ns())
    if not pending:job.store.update(job.ident,classification_metrics={})
    while True:
        job.store.update(job.ident,pending_route={'request':request,'answers':answers,'folder':str(root)})
        job.note('Classifying request before selecting tools')
        decision=classifier.classify(job,request,answers,root/('round-'+str(len(answers)))/str(time.time_ns()))
        if decision['route']!='clarify':break
        if len(answers)>=2:raise ValueError('Two clarification rounds exhausted; no development branch started')
        answer=job.dialog({'id':'routing-'+uuid.uuid4().hex,'method':'input','title':decision['question']})
        if not answer or not str(answer).strip():
            job.note('Request intake paused. Resume intake to continue.');return None
        answers.append(decision['question']+'\nUser answer: '+str(answer).strip())
    job.store.update(job.ident,pending_route=None)
    if decision['folder'] and decision['route'] in ('inspect','develop'):
        project=folder_for(decision)
        job.store.update(job.ident,project=str(project))
        job.store.message(job.ident,'notice',('Read-only inspection of ' if decision['route']=='inspect' else 'Development targets ')+str(project))
    job.note('Request classified as '+decision['route'])
    return decision,request,answers


def development_brief(job,decision,text,answers):
    """Keep fenced source local and forward requirements plus prototype locations."""
    row=job.store.get(job.ident);project=Path(row['project']);paths=[]
    # Only stage supplied files in the owned workspace. Existing-folder implementations
    # are inspected through their existing shadow, without adding unsolicited files.
    if project.resolve()==Path(row.get('workspace_project',job.store.folder/job.ident/'project')).resolve():
        for match in FENCES.finditer(text):
            language=match.group(1).strip().split(' ',1)[0].lower()
            suffix={'python':'.py','py':'.py','javascript':'.js','js':'.js','typescript':'.ts','ts':'.ts','html':'.html','css':'.css'}.get(language,'.txt')
            content=match.group(2);relative='_provided/snippet-'+hashlib.sha256(content.encode()).hexdigest()[:12]+suffix
            path=project/relative;path.parent.mkdir(exist_ok=True)
            if path.exists() and path.read_text()!=content:raise ValueError('Supplied-code artifact conflicts with existing content')
            path.write_text(content);paths.append(relative)
    return 'USER REQUIREMENTS (refined by the separate local intake):\n'+decision['goal']+(
        '\n\nSupplied implementations remain local. Inspect their prototypes: '+json.dumps(paths) if paths else '')+(
        '\n\nClarification answers have already been incorporated in the local intake goal.' if answers else '')


def local_branch_request(decision,text,answers):
    """Give the local discussion/inspection agent the resolved intent and exact answers."""
    if not answers:return text
    return text+'\n\nRESOLVED USER INTENT:\n'+decision['goal']+'\nCLARIFICATION ANSWERS:\n'+json.dumps(answers,ensure_ascii=False)
