"""Qualify finished fixed development trajectories while others are collected."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

from .collect import reader_request,references
from .runtime import API,digest,save,score


def run(args):
    out=Path(args.directory);api=API(out/'api_reader',max_requests=90);refs=references()
    save(out/'config_reader_incremental.json',dict(cases=list(range(10)),repeats=3,source=Path(__file__).read_text(),reader_source=Path('code/progressive_memory/collect.py').read_text()))
    results=[]
    def worker(job):
        tr,repeat=job;req=reader_request(tr['final_question'],tr['entries'])
        response=api.call(f"reader_dev/case{tr['case']}/full/repeat{repeat}",req);choice=response.choices[0]
        row=dict(case=tr['case'],repeat=repeat,prompt_sha256=digest(req),**score(choice.message.content or '',refs[tr['case']]),
                 finish_reason=choice.finish_reason,returned_model=response.model,
                 reasoning_observed=bool(getattr(choice.message,'reasoning_content',None)),all_memory_retained=tr['all_memory_retained'],
                 writers_complete=all(e['finish_reason']=='stop' and not e['tool_calls_remaining'] for e in tr['events']))
        save(out/'reader'/f"case{tr['case']:03d}_repeat{repeat}.json",row)
        return row
    futures={};submitted=set()
    with ThreadPoolExecutor(max_workers=3) as pool:
        while len(submitted)<10:
            for case in range(10):
                path=out/f'case_{case:03d}'/'trajectory.json'
                if case in submitted or not path.exists():continue
                tr=json.loads(path.read_text());submitted.add(case)
                for repeat in range(3):futures[pool.submit(worker,(tr,repeat))]=(case,repeat)
            if len(submitted)<10:time.sleep(10)
        results=[f.result() for f in futures]
    results.sort(key=lambda r:(r['case'],r['repeat']))
    stable=sum(all(r['correct'] for r in results if r['case']==c) for c in range(10))
    report=dict(completed=len(results),correct=sum(r['correct'] for r in results),stable_cases=stable,
                truncations=sum(r['finish_reason']=='length' for r in results),cases=10,rows=results,
                model_versions=sorted(set(r['returned_model'].casefold() for r in results)))
    report['passed']=len(results)==30 and report['correct']>=27 and stable>=9 and report['truncations']==0 and report['model_versions']==['deepseek-v4-flash-0731'] and all(r['finish_reason']=='stop' and r['all_memory_retained'] and r['reasoning_observed'] and r['writers_complete'] for r in results)
    save(out/'reader_gate.json',report);print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',default='results/development/progressive_search/dev_v2');run(p.parse_args())
