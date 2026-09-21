"""A disclosed development repair: authorized facts exclude writer hypotheses."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from .collect import normalized_trace,reader_request,references
from .discovery import trajectories
from .runtime import API,digest,normalize,save,score


def evidence_entry(source,question):
    trace=[r for r in normalized_trace(source['combined']) if r['type']=='tool_call']
    return f'Subquery 1: {question}\n\nTrace: '+json.dumps(trace,ensure_ascii=False)


def run(args):
    base=Path(args.base);out=base/'audit_evidence_only_dev';audit=base/'audit_dev';refs=references()
    eligible=json.loads((audit/'authorized_ready.json').read_text())['cases'];ts={t['case']:t for t in trajectories(base/'dev_v2',0,10)}
    planned=[]
    for case in eligible:
        source=json.loads((audit/f'case_{case:03d}'/'authorized_source.json').read_text())
        entry=evidence_entry(source,ts[case]['final_question']);req=reader_request(ts[case]['final_question'],[entry],[0])
        planned.append(dict(case=case,request=req,prompt_sha256=digest(req),actual_docids=source['actual_docids'],denied_docids=source['denied_docids']))
    save(out/'frozen_inputs.json',planned)
    save(out/'config.json',dict(source=Path(__file__).read_text(),protocol=Path('docs/progressive-authorized-evidence-amendment-2026-09-22.md').read_text(),cases=eligible))
    api=API(out/'api',max_requests=60)
    def worker(job):
        p,repeat=job
        response=api.call(f"evidence_only/{p['prompt_sha256']}/repeat{repeat}",p['request']);ch=response.choices[0]
        row=dict(case=p['case'],repeat=repeat,prompt_sha256=p['prompt_sha256'],**score(ch.message.content or '',refs[p['case']]),
                 finish_reason=ch.finish_reason,returned_model=response.model,reasoning_observed=bool(getattr(ch.message,'reasoning_content',None)),answer=ch.message.content or '')
        row['abstained_strict']=normalize(row['extracted'])=='unknown';row['abstained_prefix']=normalize(row['extracted']).startswith('unknown')
        save(out/'responses'/f"case{p['case']:03d}_repeat{repeat}.json",row);return row
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(worker,[(p,r) for p in planned for r in range(3)]))
    save(out/'results.json',dict(scope='Post-observation development repair, all five frozen eligible cases; no new source retrieval',rows=rows,
        correct=sum(r['correct'] for r in rows),abstained_strict=sum(r['abstained_strict'] for r in rows),abstained_prefix=sum(r['abstained_prefix'] for r in rows),truncated=sum(r['finish_reason']=='length' for r in rows)))
    print(json.dumps(dict(completed=len(rows),correct=sum(r['correct'] for r in rows))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='results/development/progressive_search');run(p.parse_args())
