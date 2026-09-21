"""Offline status, request accounting and native-memory integrity checks."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def summarize(directory,api):
    directory,api=Path(directory),Path(api)
    ledger=[json.loads(x) for x in (api/'ledger.jsonl').read_text().splitlines()] if (api/'ledger.jsonl').exists() else []
    intents=[json.loads(x) for x in (api/'requests.jsonl').read_text().splitlines()] if (api/'requests.jsonl').exists() else []
    responses=[r for r in ledger if r['event']=='result']
    ended={(r['job_id'],r['attempt']) for r in ledger}
    pending=[r for r in intents if (r['job_id'],r['attempt']) not in ended]
    tokens=Counter();models=Counter();finishes=Counter();reasoning=0
    for row in responses:
        r=row['response'];u=r.get('usage') or {};models[r['model']]+=1
        finishes[r['choices'][0]['finish_reason']]+=1
        reasoning+=bool(r['choices'][0]['message'].get('reasoning_content'))
        tokens['input']+=u.get('prompt_tokens',0);tokens['output']+=u.get('completion_tokens',0)
        tokens['cached_input']+=(u.get('prompt_tokens_details') or {}).get('cached_tokens',0) or 0
        tokens['reasoning']+=(u.get('completion_tokens_details') or {}).get('reasoning_tokens',0) or 0
    sessions=[]
    for f in sorted(directory.glob('case*/session*.json')):
        r=json.loads(f.read_text());w=r['write']
        sessions.append(dict(case=r['case'],session=r['session'],finish=r['finish_reason'],budget_finalized=r.get('budget_finalized',False),
            entry_bytes=len(r['memory_entry'].encode()),retained_all=w['retained_all'],changed=w['before']!=w['after'],
            source_reads=len(r['source_reads']),tool_errors=sum((i.get('content') or '').startswith('Error executing ') for i in r['combined'] if i['role']=='tool')))
    return dict(request_attempts=len(intents),completed_responses=len(responses),infrastructure_failures=len(ledger)-len(responses),unresolved_or_inflight=pending,
                returned_models=dict(models),finish_reasons=dict(finishes),reasoning_observed=reasoning,tokens=dict(tokens),
                completed_trajectories=len(list(directory.glob('case*/trajectory.json'))),sessions=sessions)


def preservation(snapshot):
    expected=json.loads(Path(snapshot).read_text());changed=[]
    for filename,value in expected.items():
        p=Path(filename)
        sha=value if isinstance(value,str) else value.get('sha256')
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:changed.append(filename)
    return dict(checked=len(expected),changed=changed)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',default='results/development/progressive_search/dev_v2');p.add_argument('--api',default='results/development/progressive_search/dev_v1/api');p.add_argument('--output');p.add_argument('--preservation',action='store_true');args=p.parse_args()
    obj=summarize(args.directory,args.api)
    if args.preservation:obj['preservation']=preservation('/tmp/hm3-discovery-continuation-start.json')
    if args.output:Path(args.output).write_text(json.dumps(obj,indent=2)+'\n')
    short={k:v for k,v in obj.items() if k not in ('sessions','unresolved_or_inflight')}
    short['completed_sessions']=len(obj['sessions']);short['unresolved_or_inflight']=len(obj['unresolved_or_inflight'])
    print(json.dumps(short,indent=2))
