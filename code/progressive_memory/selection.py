"""One frozen graph consumer and explicit simple controls."""
import json
from pathlib import Path
import pickle
import re

import numpy as np
from rank_bm25 import BM25Okapi
import tiktoken
from .collect import reader_request
from .runtime import digest

ENC=tiktoken.get_encoding('cl100k_base')


def tokens(text):return re.findall(r'\w+',text.lower())


def rank_entries(question,entries):
    values=BM25Okapi([tokens(e) for e in entries]).get_scores(tokens(question))
    return sorted(range(len(entries)),key=lambda i:(-values[i],i)),values.tolist()


def ancestors(adjacency,seed):
    seen={int(seed)};changed=True
    while changed:
        changed=False
        for source in range(len(adjacency)):
            if source not in seen and any(adjacency[source][target] for target in seen):seen.add(source);changed=True
    return seen


def trim_entries(entries,indices,budget=16384,per_entry=8192):
    encoded=[ENC.encode(entries[i],disallowed_special=()) for i in indices]
    sizes=[min(len(t),per_entry) for t in encoded]
    # Deterministic water filling shares the same total content-token budget.
    allocations=[0]*len(sizes)
    remaining=budget
    while remaining and any(a<s for a,s in zip(allocations,sizes)):
        active=[i for i,(a,s) in enumerate(zip(allocations,sizes)) if a<s]
        increment=max(1,remaining//len(active))
        for i in active:
            add=min(increment,sizes[i]-allocations[i],remaining)
            allocations[i]+=add;remaining-=add
    return [ENC.decode(t[:a]) for t,a in zip(encoded,allocations)],allocations


def make_selection(tr,indices,budget=16384,raw_entries=None):
    entries=tr['entries'] if raw_entries is None else raw_entries
    indices=sorted(indices)
    selected,alloc=trim_entries(entries,indices,budget)
    request=reader_request(tr['final_question'],selected,indices)
    return dict(indices=indices,entries=selected,content_tokens=sum(alloc),allocation=alloc,request=request,prompt_sha256=digest(request))


def selections(tr,projection,adjacency):
    entries=tr['entries'];ranking,bm25=rank_entries(tr['final_question'],entries)
    topics=np.argmax(projection.transform(entries),axis=1)
    q=projection.transform([tr['final_question']])[0];seed=int(np.argmax(q))
    outputs={}
    def graph_select(a):
        allowed=ancestors(a,seed)
        return [i for i in ranking if int(topics[i]) in allowed][:2]
    outputs['discovered']=make_selection(tr,graph_select(adjacency))
    outputs['topic_only']=make_selection(tr,graph_select(np.zeros((4,4),dtype=bool)))
    outputs['complete']=make_selection(tr,ranking[:2])
    outputs['bm25']=make_selection(tr,ranking[:2])
    outputs['recency']=make_selection(tr,list(range(max(0,len(entries)-2),len(entries))))
    budget=outputs['discovered']['content_tokens'];count=len(outputs['discovered']['indices'])
    outputs['bm25_matched']=make_selection(tr,ranking[:count],budget)
    outputs['recency_matched']=make_selection(tr,list(range(max(0,len(entries)-count),len(entries))) if count else [],budget)
    for random_seed in [17,29,43]:
        rng=np.random.default_rng(random_seed);perm=rng.permutation(4)
        wrong=np.asarray(adjacency)[np.ix_(perm,perm)].tolist()
        outputs[f'wrong_{random_seed}']=make_selection(tr,graph_select(wrong))
        indices=rng.choice(len(entries),size=count,replace=False).tolist()
        outputs[f'random_{random_seed}']=make_selection(tr,indices,budget)
    answers=[f"Subquery {e['session']+1}: {e['query']}\n\nPredicted Answer: {e['answer']}" for e in tr['events']]
    outputs['answer_reuse']=make_selection(tr,ranking[:1],raw_entries=answers)
    outputs['query_only']=make_selection(tr,[])
    outputs['full']=dict(indices=list(range(len(entries))),entries=entries,content_tokens=sum(len(ENC.encode(e,disallowed_special=())) for e in entries),
                         request=reader_request(tr['final_question'],entries))
    outputs['full']['prompt_sha256']=digest(outputs['full']['request'])
    return dict(case=tr['case'],seed_topic=seed,query_projection=q.tolist(),entry_topics=topics.tolist(),bm25=bm25,
                allowed_topics=sorted(ancestors(adjacency,seed)),methods=outputs)
