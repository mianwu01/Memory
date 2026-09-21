"""Repair degenerate label-permuted controls without altering the primary fit."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
from pathlib import Path
import numpy as np

from .collect import references
from .discovery import trajectories
from .runtime import API,save,score
from .selection import ancestors,make_selection,rank_entries


def deranged_graphs():
    choices=[p for p in itertools.permutations(range(4)) if all(i!=p[i] for i in range(4))]
    used=set();output={}
    for seed in [17,29,43]:
        order=np.random.default_rng(seed).permutation(len(choices))
        perm=next(choices[i] for i in order if choices[i] not in used);used.add(perm)
        graph=np.zeros((4,4),dtype=bool)
        for i,target in enumerate(perm):graph[i,target]=True
        output[f'rewired_{seed}']=graph.tolist()
    return output


def run(args):
    base=Path(args.base);source=base/'dev_v2';out=base/'evaluation_rewired_dev';evaluation=base/'evaluation_dev'
    original=json.loads((evaluation/'frozen_selections.json').read_text());bycase={r['case']:r for r in original}
    graphs=deranged_graphs();assert len({json.dumps(g) for g in graphs.values()})==3
    save(out/'config.json',dict(graphs=graphs,source=Path(__file__).read_text(),protocol=Path('docs/progressive-wrong-graph-amendment-2026-09-22.md').read_text(),reuse_protocol=Path('docs/progressive-reuse-control-amendment-2026-09-22.md').read_text()))
    planned=[]
    for tr in trajectories(source,0,10):
        plan=bycase[tr['case']];ranking=sorted(range(len(tr['entries'])),key=lambda i:(-plan['bm25'][i],i))
        methods={}
        for name,graph in graphs.items():
            allowed=ancestors(graph,plan['seed_topic'])
            indices=[i for i in ranking if plan['entry_topics'][i] in allowed][:2]
            methods[name]=make_selection(tr,indices)
        answers=[f"Subquery {e['session']+1}: {e['query']}\n\nPredicted Answer: {e['answer']}" for e in tr['events']]
        qrank,_=rank_entries(tr['final_question'],[e['query'] for e in tr['events']])
        methods['last_answer_reuse']=make_selection(tr,[len(answers)-1],raw_entries=answers)
        methods['question_answer_reuse']=make_selection(tr,qrank[:1],raw_entries=answers)
        planned.append(dict(case=tr['case'],methods=methods))
    save(out/'frozen_selections.json',planned)
    existing={}
    for path in list((evaluation/'responses').glob('*.json'))+list((source/'reader').glob('*repeat0.json')):
        r=json.loads(path.read_text());existing[r['prompt_sha256']]=r
    jobs={}
    for plan in planned:
        for d in plan['methods'].values():jobs.setdefault(d['prompt_sha256'],(plan['case'],d['request']))
    api=API(out/'api',max_requests=60);refs=references()
    def worker(item):
        sha,(case,req)=item
        if sha in existing:return sha,existing[sha]
        response=api.call(f'evaluation/{sha}',req);ch=response.choices[0]
        r=dict(case=case,prompt_sha256=sha,**score(ch.message.content or '',refs[case]),finish_reason=ch.finish_reason,returned_model=response.model,
               reasoning_observed=bool(getattr(ch.message,'reasoning_content',None)),answer=ch.message.content or '')
        save(out/'responses'/f'{sha}.json',r);return sha,r
    with ThreadPoolExecutor(max_workers=3) as pool:results=dict(pool.map(worker,jobs.items()))
    rows=[]
    for plan in planned:
        reference=bycase[plan['case']]['methods']['discovered']
        for name,d in plan['methods'].items():
            r=results[d['prompt_sha256']]
            rows.append(dict(case=plan['case'],method=name,**{k:v for k,v in r.items() if k not in ('case','answer')},
                content_tokens=d['content_tokens'],indices=d['indices'],token_residual_to_discovered=d['content_tokens']-reference['content_tokens'],
                identical_to_discovered=d['prompt_sha256']==reference['prompt_sha256']))
    save(out/'results.json',dict(rows=rows,graphs=graphs,distinct_inputs=len(jobs),reused_inputs=len(set(jobs)&set(existing)),source='Post-fit degenerate-control repair; primary results unchanged'))
    print(json.dumps(dict(control_rows=len(rows),distinct_inputs=len(jobs),new_requests=len(set(jobs)-set(existing)))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='results/development/progressive_search');run(p.parse_args())
