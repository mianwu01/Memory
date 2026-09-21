"""Source-group interventions and an explicit authorized sensor in RoomEnv.

All wall-source scenarios are evaluated, including irrelevant/unused sources.
The sensor extension is controlled and privileged, never an original native API.
"""
from __future__ import annotations
import argparse
from collections import defaultdict, Counter
import json
from pathlib import Path
import random

from .continuation_actor import write_once
from .observed_room import init


def load_model(directory,base):
    d=Path(directory)
    model=base.train(json.loads((d/'training_trajectories.json').read_text()))
    fit=json.loads((d/'discovery.json').read_text())
    graph=defaultdict(set)
    for e in fit['edges']:
        if e['source'] in model['walls']:graph[e['object'],e['room']].add(e['source'])
    return model,graph


def collect(base,model,seed):
    env,rooms=base.make_env(seed);rng=random.Random(seed)
    memory=[];snapshots=[];sensor={};truth={}
    patterns={'|'.join(w):list(p) for w,p in env.wall_configs.items()}
    for _ in range(base.T-1):
        t=env.current_step;ar=env.agent_location
        # Separate global sensor measurement, never fed to the ordinary reader.
        for wk,(r1,r2,d) in model['dmap'].items():
            sensor[wk,t]=int(env.room_connections[r1].get(d)=='wall')
        for o in sorted(env.moving_locations):
            truth[o,t]=env.moving_locations[o]
            if env.moving_locations[o]==ar:memory.append(('sight',t,o,ar))
        for wk in sorted(model['incident'].get(ar,[])):
            r1,r2,d=model['dmap'][wk];d=d if ar==r1 else base.OPP[d]
            memory.append(('wall',t,wk,int(env.room_connections[ar].get(d)=='wall')))
        snapshots.append(dict(time=t,records=list(memory)))
        env.step(('x',rng.choice(base.DIRS+['stay'])))
    return dict(seed=seed,rooms=rooms,snapshots=snapshots,sensor=sensor,truth=truth,patterns=patterns)


def belief(old,records,o,t,model,rooms):
    prior,B=old.answer(records,o,t,model,rooms)
    return set(rooms) if prior is not None else set(B)


def candidate_walls(old,records,o,t,model,graph):
    sights=[r for r in records if r[0]=='sight' and r[2]==o]
    if not sights:return set(),set()
    _,ts,_,rs=sights[-1]
    reachable,top=old.reachable_walls(model,o,rs,t-ts)
    return set().union(*(graph.get((o,r),set()) for r in reachable)),top


def intervene(records,source,patterns):
    blocked=[r for r in records if not (r[0]=='wall' and r[2]==source)]
    p=patterns[source]
    changed=[(r[0],r[1],r[2],p[(r[1]+1)%len(p)]) if r[0]=='wall' and r[2]==source else r for r in records]
    return blocked,changed


def run(args):
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    base,old=init(args.checkout,'small-01',120)
    model,graph=load_model(args.model,base)
    write_once(out/'protocol.json',dict(seeds=list(range(6000,6024)),model=args.model,
        schema='Each wall has a separately assessed externally controlled restricted-source scenario',
        protocol='docs/observed-memory-next-protocol-2026-09-22.md'))
    rows=[];calls=[];trajectory_summaries=[]
    for seed in range(6000,6024):
        data=collect(base,model,seed)
        public_sensor=[dict(wall=w,time=t,value=v) for (w,t),v in data['sensor'].items()]
        write_once(out/'trajectories'/f'{seed}.json',dict(seed=seed,memory_snapshots=data['snapshots'],sensor=public_sensor,
                     truth=[dict(object=o,time=t,room=v) for (o,t),v in data['truth'].items()]))
        first=len(rows)
        for snap in data['snapshots']:
            t=snap['time']
            if t<10 or t%10:continue
            memory=snap['records']
            for o in model['objs']:
                B=belief(old,memory,o,t,model,data['rooms']);true=data['truth'][o,t]
                correct=B=={true}
                learned,top=candidate_walls(old,memory,o,t,model,graph)
                for source in model['walls']:
                    blocked,changed=intervene(memory,source,data['patterns'])
                    BB=belief(old,blocked,o,t,model,data['rooms'])
                    BC=belief(old,changed,o,t,model,data['rooms'])
                    effect=BB!=B or BC!=B
                    present=any(r[0]=='wall' and r[2]==source for r in memory)
                    candidate=source in learned and present
                    alert=candidate and effect
                    result='no_alert';answer=next(iter(B)) if len(B)==1 else None
                    sensor_calls=0
                    if alert:
                        if len(BB)==1:
                            answer=next(iter(BB));result='authorized_memory_only'
                        elif seed%2==0:
                            fetched=[]
                            for r in memory:
                                if r[0]=='wall' and r[2]==source:
                                    value=data['sensor'][source,r[1]]
                                    fetched.append(('wall',r[1],source,value))
                                    calls.append(dict(seed=seed,query_time=t,object=o,source=source,
                                        tool='authorized_historical_sensor',requested_time=r[1],returned=value))
                            sensor_calls=len(fetched)
                            safe=sorted(blocked+fetched,key=lambda r:r[1])
                            BS=belief(old,safe,o,t,model,data['rooms'])
                            answer=next(iter(BS)) if len(BS)==1 else None
                            result='sensor_answer' if answer is not None else 'abstain_after_sensor'
                        else:
                            answer=None;result='abstain_tool_unavailable'
                    rows.append(dict(seed=seed,time=t,object=o,source=source,truth=true,
                        full_belief=sorted(B),blocked_belief=sorted(BB),changed_belief=sorted(BC),
                        normal_correct=correct,source_present=present,behavioral_effect=effect,
                        learned_candidate=candidate,topology_candidate=source in top and present,
                        alert=alert,safe_action=result,safe_answer=answer,
                        final_correct=answer==true,abstained=answer is None,sensor_calls=sensor_calls))
        trajectory_summaries.append(dict(seed=seed,source_scenarios=len(rows)-first))
    normal=[r for r in rows if r['normal_correct']]
    def metrics(field,rr):
        tp=sum(r[field] and r['behavioral_effect'] for r in rr)
        fp=sum(r[field] and not r['behavioral_effect'] for r in rr)
        fn=sum(not r[field] and r['behavioral_effect'] for r in rr)
        return dict(tp=tp,fp=fp,fn=fn,predicted=tp+fp,reference_positive=tp+fn)
    report=dict(all_queries=len(rows)//len(model['walls']),source_scenarios=len(rows),
        normal_correct_queries=len(normal)//len(model['walls']),normal_correct_scenarios=len(normal),
        all_metrics={f:metrics(f,rows) for f in ['source_present','topology_candidate','learned_candidate','alert']},
        normal_correct_metrics={f:metrics(f,normal) for f in ['source_present','topology_candidate','learned_candidate','alert']},
        controller_on_normal=dict(Counter(r['safe_action'] for r in normal)),
        correct_after_control=sum(r['final_correct'] for r in normal),
        abstained_after_control=sum(r['abstained'] for r in normal),
        wrong_after_control=sum(not r['final_correct'] and not r['abstained'] for r in normal),
        authorized_sensor_reads=len(calls),episodes=trajectory_summaries,
        limitations=['Controlled sensor extension, not native RoomEnv tool','Fixed deterministic decoder, not LLM audit',
                     'Finite group deletion and one phase perturbation reference, not all interventions',
                     'Same-query source scenarios are correlated; no independent-sample statistical claim',
                     'Graph narrows candidate causes; known transition-model provenance could also be informative'])
    write_once(out/'cases.json',rows);write_once(out/'tool_calls.json',calls);write_once(out/'report.json',report)
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkout',default='/tmp/observed-memory-20260922-LMbAYg/room-env')
    p.add_argument('--model',default='results/development/hm3/observed_room_small')
    p.add_argument('--out',default='results/real/hm3/room_source_audit')
    run(p.parse_args())
