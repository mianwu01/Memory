"""Explicit TCD-to-memory-selection bridge in unmodified RoomEnv dynamics.

Training world-state visibility is privileged and shared by every reader. Test
memories contain only local sightings/wall observations. No LLM-memory claim.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np

from .continuation_actor import write_once


def init(checkout,room,steps):
    sys.path.insert(0,str(Path(checkout).resolve()))
    import roomenv_c4 as base
    import roomenv_oracle_c4 as old
    base.ROOM=room; base.T=steps
    return base,old


def bh(values,alpha=.01):
    p=np.asarray(values,float); keep=np.zeros(len(p),bool)
    order=np.argsort(p)
    passed=p[order]<=alpha*np.arange(1,len(p)+1)/max(1,len(p))
    if passed.any(): keep[order[:np.flatnonzero(passed)[-1]+1]]=True
    return keep


def discover(recs,model):
    from tigramite import data_processing as pp
    from tigramite.pcmci import PCMCI
    from tigramite.independence_tests.gsquared import Gsquared
    walls,objs=model['walls'],model['objs']
    rooms=sorted({r for rec in recs for s in rec for r in s['loc'].values()})
    rid={r:i for i,r in enumerate(rooms)}
    names=walls+objs; n=len(names)
    arrays={k:np.array([[s['walls'][w] for w in walls]+[rid[s['loc'][o]] for o in objs] for s in rec],int)
            for k,rec in enumerate(recs)}
    raw=[]; counts={}
    for oi,o in enumerate(objs):
        target=len(walls)+oi
        for room in rooms:
            masks={k:np.zeros_like(a,bool) for k,a in arrays.items()}
            y=[]
            for k,a in arrays.items():
                valid=np.zeros(len(a),bool); valid[1:]=a[:-1,target]==rid[room]
                masks[k][:,target]=~valid
                y.extend(a[valid,target].tolist())
            counts[f'{o}/{room}']=len(y)
            if len(y)<30 or len(set(y))<2: continue
            links={i:{} for i in range(n)}
            links[target]={(i,-1):'-?>' for i in range(n) if i!=target}
            df=pp.DataFrame(arrays,mask=masks,analysis_mode='multiple',var_names=names)
            pcmci=PCMCI(dataframe=df,cond_ind_test=Gsquared(significance='analytic',mask_type='y'),verbosity=0)
            fit=pcmci.run_pcmciplus(tau_min=1,tau_max=1,pc_alpha=.05,
                  link_assumptions=links,max_conds_dim=1,max_conds_py=1,max_conds_px=1)
            for i,source in enumerate(names):
                if i!=target:
                    raw.append(dict(source=source,object=o,room=room,
                                    p=float(fit['p_matrix'][i,target,1]),
                                    statistic=float(fit['val_matrix'][i,target,1]),n=len(y)))
    keep=bh([x['p'] for x in raw])
    edges=[x for x,k in zip(raw,keep) if k]
    graph=defaultdict(set)
    for e in edges:
        if e['source'] in walls:graph[e['object'],e['room']].add(e['source'])
    return graph,dict(raw_tests=raw,edges=edges,context_counts=counts,
                     candidates=names,rooms=rooms,train_trajectories=len(recs),
                     train_steps=sum(map(len,recs)),actual_time_lag=1,
                     interpretation='Context-conditioned world dynamics, not hidden thought or agent-state graph')


def gold_reference(base,model,seeds):
    """Call the official transition function after independently flipping a wall."""
    edges=set(); contexts=0
    for seed in seeds:
        env,rooms=base.make_env(seed)
        for _ in range(base.T-1):
            loc=dict(env.moving_locations); conn={r:dict(c) for r,c in env.room_connections.items()}
            env._move_objects(); nxt=dict(env.moving_locations)
            for wk in model['walls']:
                r1,r2,d=model['dmap'][wk]; opp=base.OPP[d]
                env.moving_locations=dict(loc)
                env.room_connections={r:dict(c) for r,c in conn.items()}
                if conn[r1][d]=='wall':
                    env.room_connections[r1][d]=r2;env.room_connections[r2][opp]=r1
                else:
                    env.room_connections[r1][d]='wall';env.room_connections[r2][opp]='wall'
                env._move_objects()
                for o in model['objs']:
                    if env.moving_locations[o]!=nxt[o]:edges.add((o,loc[o],wk))
            env.moving_locations=loc;env.room_connections=conn
            env.step(('x','stay'));contexts+=1
    return edges,contexts


def selection(policy,records,o,t,k,model,graph,rng,old):
    past=[r for r in records if r[1]<=t]
    if policy=='full':return past
    if policy=='random':return sorted(rng.sample(past,min(k,len(past))),key=lambda r:r[1])
    if policy=='recency':return past[-k:]
    sights=[r for r in past if r[0]=='sight' and r[2]==o]
    chosen=[sights[-1]] if sights else []
    if sights and policy!='ledger':
        _,ts,_,rs=sights[-1]
        reachable,topology=old.reachable_walls(model,o,rs,t-ts)
        if policy=='topology': rel=topology
        elif policy=='complete':rel=set(model['walls'])
        else:
            rel=set().union(*(graph.get((o,r),set()) for r in reachable))
            if policy.startswith('wrong_'):
                perm=list(model['walls']);random.Random(int(policy.split('_')[1])).shuffle(perm)
                mapping=dict(zip(model['walls'],perm));rel={mapping[w] for w in rel}
        queues=[]
        for wk in sorted(rel):
            q=[r for r in past if r[0]=='wall' and r[2]==wk]
            if q:queues.append(list(reversed(q)))
        while len(chosen)<k and any(queues):
            for q in queues:
                if q and len(chosen)<k:chosen.append(q.pop(0))
    # Shared padding and chronology. Tuple equality is record identity (one per slot/time).
    for r in reversed(past):
        if len(chosen)>=k:break
        if r not in chosen:chosen.append(r)
    return sorted(chosen,key=lambda r:r[1])


def evaluate(base,old,model,graph,seeds,out):
    policies=['full','learned','complete','topology','wrong_17','wrong_29','wrong_43','ledger','recency','random']
    records_out=[]; rows=[]
    for seed in seeds:
        env,rooms=base.make_env(seed);rng=random.Random(seed)
        memory=[];queries=[]
        for _ in range(base.T-1):
            t=env.current_step;ar=env.agent_location
            writes=[]
            for o in sorted(env.moving_locations):
                if env.moving_locations[o]==ar:writes.append(('sight',t,o,ar))
            for wk in sorted(model['incident'].get(ar,[])):
                r1,r2,d=model['dmap'][wk];d=d if ar==r1 else base.OPP[d]
                writes.append(('wall',t,wk,int(env.room_connections[ar].get(d)=='wall')))
            memory.extend(writes)
            if t>=10 and t%10==0:
                for o in model['objs']:
                    truth=env.moving_locations[o];qr=[]
                    for k in [8,16]:
                        selected={}
                        for pol in policies:
                            sel=selection(pol,memory,o,t,k,model,graph,random.Random(seed*10000+t),old)
                            prior,B=old.answer(sel,o,t,model,rooms)
                            score=prior if prior is not None else old.score(B,truth,rooms)
                            selected[pol]=sel
                            row=dict(seed=seed,time=t,object=o,budget=k,policy=pol,score=score,
                                     records=len(sel),selection_sha=hashlib.sha256(json.dumps(sel).encode()).hexdigest(),
                                     selected_records=sel,belief=sorted(B) if isinstance(B,set) else B)
                            rows.append(row);qr.append(row)
                        for pol in policies:
                            next(r for r in qr if r['budget']==k and r['policy']==pol)['same_as_learned']=selected[pol]==selected['learned']
                    queries.append(dict(time=t,object=o,truth=truth))
            records_out.append(dict(seed=seed,time=t,agent_room=ar,writes=writes,memory_size=len(memory),
                                    slot_latest={str((r[0],r[2])):r for r in memory}))
            env.step(('x',rng.choice(base.DIRS+['stay'])))
        print(json.dumps({'episode':seed,'queries':len(queries),'memory_records':len(memory)}),flush=True)
    write_once(out/'memory_snapshots.json',records_out)
    write_once(out/'query_rows.json',rows)
    return rows


def summary(rows):
    by=defaultdict(list)
    for r in rows:by[r['policy'],r['budget']].append(r)
    table={}
    for (pol,k),rr in by.items():
        table[f'{pol}@{k}']=dict(score=float(np.mean([r['score'] for r in rr])),
            records=float(np.mean([r['records'] for r in rr])),queries=len(rr),
            same_as_learned=sum(r['same_as_learned'] for r in rr),
            episode_scores={str(s):float(np.mean([r['score'] for r in rr if r['seed']==s])) for s in sorted({r['seed'] for r in rr})})
    return table


def main(args):
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    base,old=init(args.checkout,args.room,120)
    config=dict(room=args.room,steps=120,training_seeds=list(range(3000,3064)),
                test_seeds=list(range(args.test_start,args.test_start+args.episodes)),
                protocol='docs/observed-memory-next-protocol-2026-09-22.md',
                source_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    write_once(out/'protocol.json',config)
    start=time.monotonic()
    recs=[base.full_rollout(s)[0] for s in config['training_seeds']]
    model=base.train(recs)
    write_once(out/'training_trajectories.json',recs)
    graph,fit=discover(recs,model)
    write_once(out/'discovery.json',fit)
    reference,contexts=gold_reference(base,model,range(7000,7016))
    pred={(o,r,w) for (o,r),ws in graph.items() for w in ws}
    check=dict(predicted=sorted(pred),reference=sorted(reference),true_positive=len(pred&reference),
               false_positive=len(pred-reference),false_negative=len(reference-pred),
               reference_contexts=contexts,reference_is_finite_support=True)
    write_once(out/'structure_validation.json',check)
    rows=evaluate(base,old,model,graph,config['test_seeds'],out)
    result=dict(table=summary(rows),structure=check,seconds=time.monotonic()-start,
                claim_scope='Controlled world-dynamics prior for partial-observation memory selection; shared privileged training, fixed decoder',
                llm_calls=0)
    write_once(out/'report.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkout',default='/tmp/observed-memory-20260922-LMbAYg/room-env')
    p.add_argument('--room',default='small-01')
    p.add_argument('--test-start',type=int,default=4000)
    p.add_argument('--episodes',type=int,default=8)
    p.add_argument('--out',default='results/development/hm3/observed_room_small')
    main(p.parse_args())
