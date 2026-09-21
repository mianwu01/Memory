"""p_theta trade-off sweep at a given history length (dev seeds): balanced/unbalanced GBM x threshold x record/segment level;
EES, records read, recall/precision against the replay-verified frontier of each evaluation episode.
Usage (from code/): PYTHONPATH=. python3 -m hm3.replay_sweep --domain travel --seed 1 --length 500
Writes <out>/sweep_<domain>_s<seed>_<length>.json and prints one line per setting."""
import numpy as np, json, sys
from hm3.domains import get_domain
from hm3.generate import generate_split
from hm3.scaling import augment_split
from hm3.replay import discover, ExecutorOracle, FrontierModel, reach_all, reach_by_type_edges, record_features, visible_objects
from hm3.core import score_plan, restricted_est, execute_intervention, FallbackTracker
import argparse
ap=argparse.ArgumentParser(); ap.add_argument("--domain", default="travel"); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--length", type=int, default=500); ap.add_argument("--out", default="../results/development/hm3/replay"); a=ap.parse_args(); dom, seed = a.domain, a.seed
d=get_domain(dom)
train0=generate_split(d, seed+100, "train", 200); ev0=generate_split(d, seed, "dev", 60)
if a.length:
    train,_=augment_split(d, train0, a.length, "abcd", f"train{seed}"); ev,_=augment_split(d, ev0, a.length, "abcd", f"dev{seed}")
else:
    train, ev = train0, ev0
sets=discover(d, train, lambda ep: ExecutorOracle(d, ep))
results=[]
# replay-verified frontier on the eval episodes (for record-level precision/recall of the classifier)
ev_sets={ep.id:set(s["frontier"]) for ep,s in zip(ev, discover(d, ev, lambda ep: ExecutorOracle(d, ep))) if s["full_ok"]}
for balanced in (True, False):
    m=FrontierModel(balanced=balanced).fit(d, train, sets, reach_all)
    edges=set(m.type_edges)
    for thr in (0.2,0.3,0.5,0.7):
        for seg in (False, True):
            ees=[];nr=[];prec=[];rec=[]
            for ep in ev:
                reached=reach_by_type_edges(ep, edges)
                recs=m.predict(d, ep, reached, thr, seg)
                objs=sorted(set(reached)|set(visible_objects(ep, recs)))
                est=restricted_est(d, ep.H, ep.S0, recs); post=ep.S0.copy()
                try: _,txns,_=execute_intervention(d, est, post, ep.I, FallbackTracker(est))
                except Exception: txns=[]
                ees.append(score_plan(d, ep, txns, {"objects":objs,"records":recs})["ees"]); nr.append(len(recs))
                if ep.id in ev_sets and ev_sets[ep.id]:
                    F=ev_sets[ep.id]; S=set(recs); prec.append(len(F&S)/max(1,len(S))); rec.append(len(F&S)/len(F))
            row={"balanced":balanced,"thr":thr,"segment":seg,"ees":float(np.mean(ees)),"records":float(np.mean(nr)),"frontier_recall":float(np.mean(rec)),"frontier_precision":float(np.mean(prec))}
            results.append(row)
            print(f"{dom} seed{seed} {a.length} balanced={balanced} thr={thr} seg={seg}: EES {row['ees']:.3f} records {row['records']:.1f} frontier-recall {row['frontier_recall']:.2f} frontier-precision {row['frontier_precision']:.2f}", flush=True)
import os; os.makedirs(a.out, exist_ok=True)
json.dump({"domain":dom,"seed":seed,"length":a.length,"rows":results}, open(f"{a.out}/sweep_{dom}_s{seed}_{a.length}.json","w"), indent=1)
