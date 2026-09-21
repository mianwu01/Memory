"""Actual source interventions using the same fitted graph as memory selection."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import fcntl
import json
from pathlib import Path
import re

from .collect import SYSTEM,normalized_trace,reader_request,references
from .corpus import Corpus
from .discovery import trajectories
from .runtime import API,NativeClient,canonical,digest,extract,native_runtime,normalize,save,score


def document_ids(event):
    found=set()
    for read in event['source_reads']:
        if read['tool']=='search':found.update(str(r['docid']) for r in read['results'])
        elif read.get('result'):found.add(str(read['result']['docid']))
    return sorted(found)


def modified_conditions(tr,plan,baseline):
    candidates=plan['methods']['discovered']['indices']
    if not candidates:return dict(applicable=False,reason='Discovery selected no record',case=tr['case'])
    target=min(candidates,key=lambda i:(-plan['bm25'][i],i))
    complete=min(range(len(tr['entries'])),key=lambda i:(-plan['bm25'][i],i))
    answer=baseline['extracted'] or ''
    substitute=f"Counterfactual Entity {tr['case']}"
    pattern=re.compile(r'(?<!\w)'+re.escape(answer)+r'(?!\w)',re.I) if len(answer)>=3 and normalize(answer)!='unknown' else None
    updated=tr['entries'].copy()
    updated[target],count=pattern.subn(substitute,updated[target]) if pattern else (updated[target],0)
    neutral=tr['entries'].copy();neutral[target]+='\nArchive metadata: format version 1; retained record.'
    def request(entries,indices):return reader_request(tr['final_question'],[entries[i] for i in indices],indices)
    all_ids=list(range(len(tr['entries'])))
    denied=set(document_ids(tr['events'][target]))
    direct_tainted=[i for i,e in enumerate(tr['events']) if denied&set(document_ids(e))]
    first_tainted=min([target]+direct_tainted)
    # Each later native writer reads the entire prior memory. This is a
    # conservative read-provenance closure, not a causal-minimal source set.
    source_blocked_indices=[i for i in all_ids if i<first_tainted]
    conditions=dict(blocked=request(tr['entries'],[i for i in all_ids if i!=target]),changed=request(updated,all_ids),
                    neutral=request(neutral,all_ids),complete_blocked=request(tr['entries'],[i for i in all_ids if i!=complete]),
                    source_blocked=request(tr['entries'],source_blocked_indices),
                    no_evidence=reader_request(tr['final_question'],[]))
    return dict(applicable=True,case=tr['case'],target=target,complete_target=complete,same_locator=target==complete,
                original_answer=answer,counterfactual_answer=substitute,replacements=count,
                answer_occurrences_outside_target=sum(len(pattern.findall(e)) for i,e in enumerate(tr['entries']) if i!=target) if pattern else 0,
                denied_docids=sorted(denied),direct_tainted_records=direct_tainted,conservative_source_block_remaining=source_blocked_indices,conditions=conditions)


def authorized_fetch(tr,planned,api,index,out):
    target=out/f"case_{tr['case']:03d}"/'authorized_source.json'
    if target.exists():return json.loads(target.read_text())
    reads=[];corpus=Corpus(index,reads,blocked=planned['denied_docids']);native=native_runtime()
    handler=native['SearchToolHandler'](corpus,k=5,snippet_max_tokens=None)
    request=native['build_request'](tr['final_question'],'deepseek-v4-flash',131072,handler,system_prompt=SYSTEM,query_template='QUERY_TEMPLATE',temperature=0)
    client=NativeClient(api,f"authorized/case{tr['case']}")
    response,combined,usage,_=native['run_conversation_with_tools'](client,request,handler,max_iterations=12)
    native_finish=response.choices[0].finish_reason
    if response.choices[0].message.tool_calls:
        response=client.create(model='deepseek-v4-flash',max_tokens=32768,messages=canonical(request['messages']+combined)+[dict(role='user',content='The search budget is now exhausted. Give your final answer using the evidence already retrieved. If it does not establish an answer, return Exact Answer: UNKNOWN. Use the requested Explanation, Exact Answer, Confidence format. Do not request more tools.')])
        combined.append(dict(role='assistant',content=response.choices[0].message.content or ''))
    answer=response.choices[0].message.content or ''
    entry=f"Subquery 1: {tr['final_question']}\n\nPredicted Answer: {answer}\n\nTrace: "+json.dumps(normalized_trace(combined),ensure_ascii=False)
    actual=document_ids(dict(source_reads=reads))
    assert not set(actual)&set(planned['denied_docids'])
    denied_sources=[corpus.db.execute('SELECT url,sha256 FROM docs WHERE docid=?',(docid,)).fetchone() for docid in planned['denied_docids']]
    denied_urls={r['url'] for r in denied_sources if r and r['url']};denied_hashes={r['sha256'] for r in denied_sources if r}
    observed=[]
    for read in reads:
        observed.extend(read['results'] if read['tool']=='search' else ([read['result']] if read.get('result') else []))
    reference=normalize(references()[tr['case']])
    literal_support=sorted({r['docid'] for r in observed if reference and reference in normalize(r['text'])})
    repeated_origins=sorted({r['docid'] for r in observed if r.get('url') in denied_urls or r.get('original_sha256') in denied_hashes})
    row=dict(case=tr['case'],denied_docids=planned['denied_docids'],actual_docids=actual,source_reads=reads,
             actual_authorized_reads=bool(actual),literal_reference_support_docids=literal_support,same_origin_as_denied_docids=repeated_origins,
             answer=answer,memory_entry=entry,native_finish_reason=native_finish,
             finish_reason=response.choices[0].finish_reason,combined=canonical(combined),usage=usage,
             request=reader_request(tr['final_question'],[entry],[0]))
    save(target,row);return row


def run(args):
    out=Path(args.out);source=Path(args.trajectories)
    trs=trajectories(source,args.start,args.end)
    selection={r['case']:r for r in json.loads((Path(args.evaluation)/'frozen_selections.json').read_text())}
    plans=[];full={};qualified=[]
    for tr in trs:
        rows=[json.loads((source/'reader'/f"case{tr['case']:03d}_repeat{r}.json").read_text()) for r in range(3)]
        full[tr['case']]=rows
        good=all(r['correct'] and r['finish_reason']=='stop' and r.get('writers_complete',False) and r['all_memory_retained'] for r in rows)
        if good:
            plan=modified_conditions(tr,selection[tr['case']],rows[0])
            if plan['applicable']:qualified.append(tr)
        else:plan=dict(case=tr['case'],applicable=False,reason='Full reader is not stably correct with complete writers',full_results=rows)
        plans.append(plan)
    save(out/'frozen_interventions.json',plans)
    save(out/'config.json',dict(protocol=Path('docs/progressive-audit-protocol-2026-09-22.md').read_text(),source=Path(__file__).read_text(),all_cases=[t['case'] for t in trs]))
    api=API(out/'api',max_requests=450);bycase={p['case']:p for p in plans};refs=references()
    def fetch(tr):return tr['case'],authorized_fetch(tr,bycase[tr['case']],api,args.index,out)
    with ThreadPoolExecutor(max_workers=3) as pool:authorized=dict(pool.map(fetch,qualified))
    save(out/'authorized_ready.json',dict(cases=sorted(authorized)))
    if args.prefetch_only:
        print(json.dumps(dict(event='authorized_prefetch_complete',cases=sorted(authorized))),flush=True)
        return
    jobs={};mapping=[];existing={}
    for tr in qualified:
        case=tr['case'];conditions={**bycase[case]['conditions'],'authorized':authorized[case]['request']}
        for repeat,r in enumerate(full[case]):existing[(r['prompt_sha256'],repeat)]=r
        for path in (Path(args.evaluation)/'responses').glob('*.json'):
            r=json.loads(path.read_text())
            if r['case']==case:existing[(r['prompt_sha256'],0)]=r
        for condition,req in conditions.items():
            for repeat in range(3):
                sha=digest(req);key=(sha,repeat);jobs.setdefault(key,(case,req))
                mapping.append(dict(case=case,condition=condition,repeat=repeat,prompt_sha256=sha))
    def worker(item):
        (sha,repeat),(case,req)=item
        if (sha,repeat) in existing:return (sha,repeat),existing[(sha,repeat)]
        response=api.call(f'audit/{sha}/repeat{repeat}',req);ch=response.choices[0]
        row=dict(case=case,repeat=repeat,prompt_sha256=sha,**score(ch.message.content or '',refs[case]),finish_reason=ch.finish_reason,returned_model=response.model,
                 reasoning_observed=bool(getattr(ch.message,'reasoning_content',None)),answer=ch.message.content or '')
        save(out/'responses'/f'{sha}_{repeat}.json',row);return (sha,repeat),row
    with ThreadPoolExecutor(max_workers=4) as pool:results=dict(pool.map(worker,jobs.items()))
    rows=[]
    for m in mapping:
        r=results[(m['prompt_sha256'],m['repeat'])]
        rows.append({**m,**{k:v for k,v in r.items() if k not in ('answer','repeat')},
            'counterfactual_followed':normalize(r.get('extracted'))==normalize(bycase[m['case']]['counterfactual_answer']),
            'abstained':normalize(r.get('extracted'))=='unknown'})
    save(out/'results.json',dict(all_cases=[t['case'] for t in trs],eligible_cases=[t['case'] for t in qualified],baseline=full,rows=rows,
        authorized_provenance={str(c):dict(actual_authorized_reads=r['actual_authorized_reads'],actual_docids=r['actual_docids'],denied_docids=r['denied_docids'],finish_reason=r['finish_reason'],literal_reference_support_docids=r['literal_reference_support_docids'],same_origin_as_denied_docids=r['same_origin_as_denied_docids']) for c,r in authorized.items()},
        ineligible=[p for p in plans if not p['applicable']],distinct_reader_inputs_repeats=len(jobs),reader_responses_reused=len(set(jobs)&set(existing))))
    print(json.dumps(dict(all_cases=len(trs),eligible_cases=len(qualified),treatment_rows=len(rows),distinct_input_repeats=len(jobs))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trajectories',required=True);p.add_argument('--evaluation',required=True);p.add_argument('--out',required=True);p.add_argument('--index',required=True);p.add_argument('--start',type=int,default=0);p.add_argument('--end',type=int,default=10);p.add_argument('--prefetch-only',action='store_true');args=p.parse_args()
    Path(args.out).mkdir(parents=True,exist_ok=True)
    with (Path(args.out)/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        run(args)
