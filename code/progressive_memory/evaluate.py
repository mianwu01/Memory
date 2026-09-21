"""Frozen reader evaluation; byte-identical method inputs share one response."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import pickle

from .collect import references
from .discovery import trajectories,load_projection
from .runtime import API,save,score
from .selection import selections


def run(args):
    out=Path(args.out)
    projection=load_projection(Path(args.discovery)/'projection.pkl')
    fit=json.loads((Path(args.discovery)/'fit.json').read_text())
    adjacency=fit['primary']['adjacency']
    planned=[selections(tr,projection,adjacency) for tr in trajectories(args.trajectories,args.start,args.end)]
    save(out/'frozen_selections.json',planned)
    save(out/'config.json',dict(scope=fit['scope'],reader_source=Path('code/progressive_memory/collect.py').read_text(),selection_source=Path('code/progressive_memory/selection.py').read_text(),discovery=str(args.discovery)))
    api=API(out/'api',max_requests=200);refs=references();jobs={};existing={}
    for case in planned:
        original=Path(args.trajectories)/'reader'/f"case{case['case']:03d}_repeat0.json"
        if original.exists():
            row=json.loads(original.read_text());existing[row['prompt_sha256']]=row
        for method,data in case['methods'].items():jobs.setdefault(data['prompt_sha256'],(case['case'],data['request']))
    def worker(item):
        sha,(case,req)=item
        if sha in existing:return sha,existing[sha]
        response=api.call(f'evaluation/{sha}',req);ch=response.choices[0]
        result=dict(case=case,prompt_sha256=sha,**score(ch.message.content or '',refs[case]),finish_reason=ch.finish_reason,returned_model=response.model,
                    reasoning_observed=bool(getattr(ch.message,'reasoning_content',None)),answer=ch.message.content or '')
        save(out/'responses'/f'{sha}.json',result);return sha,result
    with ThreadPoolExecutor(max_workers=4) as pool:results=dict(pool.map(worker,jobs.items()))
    rows=[]
    for case in planned:
        for method,data in case['methods'].items():
            r=results[data['prompt_sha256']]
            rows.append(dict(case=case['case'],method=method,**{k:v for k,v in r.items() if k not in ('case','answer')},
                content_tokens=data['content_tokens'],indices=data['indices'],token_residual_to_discovered=data['content_tokens']-case['methods']['discovered']['content_tokens'],
                identical_to_discovered=data['prompt_sha256']==case['methods']['discovered']['prompt_sha256']))
    save(out/'results.json',dict(scope=fit['scope'],rows=rows,distinct_inputs=len(jobs),method_rows=len(rows),reused_full_inputs=len(set(jobs)&set(existing))))
    print(json.dumps(dict(method_rows=len(rows),distinct_inputs=len(jobs),scores={m:sum(r['correct'] for r in rows if r['method']==m) for m in planned[0]['methods']})))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trajectories',required=True);p.add_argument('--discovery',required=True);p.add_argument('--out',required=True);p.add_argument('--start',type=int,default=0);p.add_argument('--end',type=int,default=10);run(p.parse_args())
