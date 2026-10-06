"""Remove HTML chrome and select bounded, question-relevant source passages."""
import math
import re
from collections import Counter
from trafilatura import extract

STOP = set('a an and are as at be by can do does for from how i in is it of on or that the this to use used using was what when where which with would you your'.split())


def article(raw, url=''):
    """Extract main prose/tables; exclude menus, banners, adverts and comments."""
    text=extract(raw,url=url or None,include_comments=False,include_tables=True,
                 include_images=False,include_links=False,favor_precision=True,deduplicate=True)
    if text and len(text.strip())>=80:return text.strip(), 'trafilatura-main-content'
    from research_fetch import extract as simple_extract
    return simple_extract(raw), 'bounded-html-fallback'


def words(text):
    """Keep technical identifiers/numbers and ignore common query boilerplate."""
    return [w for w in re.findall(r'[\w.+-]+',text.casefold()) if len(w)>1 and w not in STOP]


def chunks(text, maximum=650):
    """Split long paragraphs at sentence/word boundaries without paraphrasing."""
    output=[]
    for paragraph in text.splitlines():
        paragraph=paragraph.strip()
        while paragraph:
            end=min(maximum,len(paragraph))
            if end<len(paragraph):
                boundary=max(paragraph.rfind('. ',0,end),paragraph.rfind(' ',0,end))
                if boundary>maximum//2:end=boundary+1
            output.append(paragraph[:end].strip());paragraph=paragraph[end:].strip()
    return output


def focus(text, query, max_bytes=2400):
    """Rank exact passages, preserving source order and explicitly marking omissions."""
    if not 512<=max_bytes<=4800:raise ValueError('Focused excerpts require 512–4800 bytes')
    passages=chunks(text);terms=set(words(query));tokens=[Counter(words(p)) for p in passages]
    count=len(passages);frequency=Counter(t for t in terms for row in tokens if t in row)
    average=sum(sum(row.values()) for row in tokens)/max(1,count)
    scores=[]
    for index,row in enumerate(tokens):
        length=sum(row.values());score=0
        for term in terms:
            f=row[term]
            if f:
                idf=math.log(1+(count-frequency[term]+.5)/(frequency[term]+.5))
                score+=idf*f*2.2/(f+1.2*(.25+.75*length/max(1,average)))
        scores.append((score,index))
    matches=any(score>0 for score,_ in scores)
    ranking=sorted(scores,key=lambda x:(-x[0],x[1])) if matches else [(0,i) for i in range(count)]
    selected=set();size=0
    for score,index in ranking:
        if matches and score<=0:continue
        # Keep neighboring lines so wrapped sentences and their qualifications survive.
        for candidate in [index, max(0,index-1), min(count-1,index+1)]:
            if candidate in selected:continue
            cost=len(passages[candidate].encode())+len('\n[…]\n'.encode())
            if size+cost<=max_bytes:selected.add(candidate);size+=cost
    ordered=sorted(selected);pieces=[]
    for position,index in enumerate(ordered):
        if position:pieces.append('\n' if index==ordered[position-1]+1 else '\n[…]\n')
        pieces.append(passages[index])
    excerpt=''.join(pieces)
    if not excerpt and passages:excerpt=passages[ranking[0][1]].encode()[:max_bytes].decode(errors='ignore')
    return {'excerpt':excerpt,'query_match':matches,'truncated':len(selected)<count,
            'source_characters':len(text),'returned_bytes':len(excerpt.encode()),
            'method':'Main content extraction, then BM25-ranked exact passages; local model writes the final summary.'}


def links(raw,base):
    """Keep bounded exact documentation links for subsequent focused reads."""
    from urllib.parse import urljoin,urlsplit
    from research_fetch import PageText
    parser=PageText();parser.feed(raw);result=[];seen=set()
    for row in parser.links:
        url=urljoin(base,row['url']);parts=urlsplit(url)
        if parts.scheme not in ('https','http') or parts.username or parts.password or len(url)>800 or url in seen:continue
        title=' '.join(row['title'].split())[:120]
        if not title:continue
        result.append({'title':title,'url':url});seen.add(url)
        if len(result)>=40:break
    return result


def relevant_links(candidates,query):
    """Return at most two exact link targets, ranked by topic overlap."""
    terms=set(words(query));ranked=[]
    for index,row in enumerate(candidates):
        score=len(terms&set(words(row['title']+' '+row['url'])))
        if score:ranked.append((score,index,row))
    return [row for _,_,row in sorted(ranked,key=lambda x:(-x[0],x[1]))[:2]]
