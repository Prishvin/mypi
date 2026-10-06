"""Validate concise model-distilled memory against its exact supplied response."""
import argparse
import json
from pathlib import Path
import re
from knowledge import digest, inline
from runner_process import save


def validate(draft, packet):
    """Reject invented evidence, new URLs and oversized notes before publication."""
    source=packet['response']
    items=draft.get('items')
    if not isinstance(items,list) or len(items)>min(6,packet.get('max_items',6)):
        raise ValueError('Memory needs at most six concise items')
    verified=[]
    for item in items:
        text=item.get('text');evidence=item.get('evidence')
        if (not isinstance(text,str) or not text.strip() or len(text)>500 or
                '\n' in text or '```' in text or '<!--' in text):
            raise ValueError('Each memory item must be one short plain-text line')
        if not isinstance(evidence,str) or not 1<=len(evidence)<=400 or evidence not in source:
            raise ValueError('Memory evidence must be an exact excerpt from the selected response')
        for url in re.findall(r'https?://[^\s<>\]\)]+',text):
            if url not in source:
                raise ValueError('Memory cannot introduce a new URL')
        verified.append({'text':text.strip(),'evidence':evidence})
    summary='\n'.join('- '+inline(item['text']) for item in verified)
    if len(summary.encode())>min(1800,packet['max_summary_bytes']) or len(summary.split())>160:
        raise ValueError('Distilled memory exceeds the available brief budget')
    reason=draft.get('skipped_reason','')
    if not isinstance(reason,str) or len(reason)>300 or (not items and not reason.strip()):
        raise ValueError('Explain briefly when there is nothing useful to save')
    return {'version':1,'items':verified,'skipped_reason':reason,
            'source_sha256':digest(source),'summary':summary}


def main():
    """Validate a store tool result without granting it source-write access."""
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('packet','request','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    result=validate(json.loads(args.request.read_text()),json.loads(args.packet.read_text()))
    save(args.output,result)
    print(json.dumps({'draft':str(args.output),'items':len(result['items'])}))


if __name__=='__main__':main()
