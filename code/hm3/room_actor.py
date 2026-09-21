"""Frozen RoomEnv world-model/text-memory bridge to the actual LLM actor."""
from __future__ import annotations
import argparse
from collections import defaultdict,Counter
import hashlib
import json
from pathlib import Path
import random
import re

from .continuation_actor import write_once
from .observed_room import init,selection
from .paired_actor import CONFIG,run_jobs,load_rows
from .room_source_audit import load_model,collect,intervene,belief
from .structure_alignment import digest


SYSTEM="""You answer location questions using a learned deterministic world model and timestamped memory observations.
Return exactly one JSON object {"room": "room_name"}, or {"room": null} if the retained observations and model do not determine a unique location. Do not guess an unknown phase.
Time t means BEFORE movement t->t+1. A sight record gives the object's location at that time. Each wall has a periodic bit pattern learned in a DIFFERENT training episode. In the current episode each wall's cyclic phase offset is unknown and constant; infer allowed offsets from its timestamped wall observations, not from the training pattern's initial alignment.
The transition table maps current object location and the ordered bits of the walls incident to that location to its location one step later. Start at the object's most recent retained sighting. Evolve it to the query time using the phase-consistent wall bits and transition table. Keep all possible locations if evidence is insufficient. Other objects' sightings do not directly locate the queried object. Only memory observations at or before the question time may be used.
The model is a shared trained component, not the true phase or the answer to this test episode. No source permissions are provided to you; just answer the ordinary location question."""


def prepare(args):
    base,old=init(args.checkout,'small-01',120)
    model,graph=load_model(args.model,base)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    jobs=[];truths={};profiles=[]
    o='mary';t=50
    knowledge=dict(rooms=sorted({r for _,r,_ in model['table']}),
       patterns=model['patterns'],incident_walls={r:sorted(ws) for r,ws in model['incident'].items()},
       transitions=[dict(room=r,wall_bits=list(bits),next_room=nxt)
                    for (obj,r,bits),nxt in sorted(model['table'].items()) if obj==o])
    write_once(out/'shared_learned_model.json',knowledge)
    for seed in range(6100,6104):
        data=collect(base,model,seed);memory=data['snapshots'][t]['records'];case=f'room-s{seed}-t{t}-{o}'
        truths[case]=data['truth'][o,t]
        blocked,changed=intervene(memory,'living|kitchen|vertical',data['patterns'])
        neutral,_=intervene(memory,'office|den|vertical',data['patterns'])
        arms=dict(full=memory,
                  learned8=selection('learned',memory,o,t,8,model,graph,random.Random(seed),old),
                  topology8=selection('topology',memory,o,t,8,model,graph,random.Random(seed),old),
                  source_blocked=blocked,source_changed=changed,neutral_blocked=neutral)
        profiles.append(dict(case=case,truth=truths[case],records={a:len(v) for a,v in arms.items()},
                             decoder_beliefs={a:sorted(belief(old,v,o,t,model,data['rooms'])) for a,v in arms.items()}))
        for arm,records in arms.items():
            user='LEARNED MODEL\n'+json.dumps(knowledge,sort_keys=True)+'\nMEMORY RECORDS [kind,time,entity,value]\n'+json.dumps(records)+'\nQUESTION\n'+json.dumps(dict(object=o,time=t))
            messages=[dict(role='system',content=SYSTEM),dict(role='user',content=user)]
            sha=digest(messages)
            for mode in ['enabled','disabled']:
                for repeat in range(3):
                    jobs.append(dict(case=case,arm=arm,mode=mode,repeat=repeat,
                        messages=messages,prompt_sha256=sha,records=len(records),
                        job_id=digest([case,arm,mode,repeat,sha,'room_actor_v1'])))
    write_once(out/'case_profiles.json',profiles)
    return truths,jobs


def parse(text):
    objects=re.findall(r'\{[^{}]*\}',text)
    for item in reversed(objects):
        try:obj=json.loads(item)
        except json.JSONDecodeError:continue
        if isinstance(obj,dict) and 'room' in obj and (obj['room'] is None or isinstance(obj['room'],str)):
            return True,obj['room']
    return False,None


def report(out):
    out=Path(out);last={r['job_id']:r for r in load_rows(out/'ledger.jsonl')}
    jobs=json.loads((out/'manifest.json').read_text());by=defaultdict(list)
    for j in jobs:by[j['mode'],j['arm']].append(last.get(j['job_id'],{**j,'event':'missing'}))
    table={}
    for (mode,arm),rows in by.items():
        valid=[r for r in rows if r['event']=='result']
        per={c:dict(correct=sum(r.get('correct',False) for r in rows if r['case']==c),
             completed=sum(r['event']=='result' for r in rows if r['case']==c),
             answers=[r.get('answer') for r in rows if r['case']==c]) for c in sorted({r['case'] for r in rows})}
        table[f'{mode}/{arm}']=dict(correct=sum(r['correct'] for r in valid),completed=len(valid),
            expected=len(rows),per_case=per,stable=sum(v['correct']==3 and v['completed']==3 for v in per.values()),
            truncations=sum(r['finish_reason']=='length' for r in valid),
            thinking_observed=sum(r.get('thinking_observed',False) for r in valid),
            input_tokens=sum(r['usage'].get('prompt_tokens',0) for r in valid),
            output_tokens=sum(r['usage'].get('completion_tokens',0) for r in valid),
            reasoning_tokens=sum((r['usage'].get('completion_tokens_details') or {}).get('reasoning_tokens',0) or 0 for r in valid),
            returned_models=dict(Counter(r['returned_model'] for r in valid)))
    result=dict(table=table,scope='Four fixed controlled model-based memory questions; not a native unassisted LLM benchmark',
                source_policy='living|kitchen wall stream externally restricted in the audit scenario; labels absent from actor prompt')
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


def main(args):
    truths,jobs=prepare(args)
    if args.prepare:
        print(json.dumps({'jobs':len(jobs),'cases':len(truths)}));return
    if args.report:report(args.out);return
    def scorer(job,text):
        ok,answer=parse(text)
        return dict(correct=ok and answer==truths[job['case']],parse_ok=ok,answer=answer)
    config={**CONFIG,'workers':8,'tasks':4,'seed_panel':list(range(6100,6104)),
            'shuffle_seed':2026092203,'stage':'room_actor_v1','source_sha':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'protocol':'docs/observed-memory-next-protocol-2026-09-22.md'}
    run_jobs(args.out,jobs,scorer,args.key_file,config)
    report(args.out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkout',default='/tmp/observed-memory-20260922-LMbAYg/room-env')
    p.add_argument('--model',default='results/development/hm3/observed_room_small')
    p.add_argument('--out',default='results/development/hm3/room_actor_v1')
    p.add_argument('--key-file',default='api/api.txt')
    p.add_argument('--prepare',action='store_true');p.add_argument('--report',action='store_true')
    main(p.parse_args())
