"""P1-P4 judgement for the HM3 scaling dev panel (design §5): paired per episode, 95% bootstrap CI.
Usage: python3 judge_p1p4.py det_dev_travel.json [det_dev_shopping32.json ...]
Read-only over the runner's JSON; no code/ change."""
import json, sys, os
import numpy as np
G = os.environ.get("GRAPH", "graph")  # learner judged for P1/P2

B = 2000
rng = np.random.default_rng(0)

def rows(d, key, learner, metric):
    e = d["runs"].get(key, {})
    L = e.get("learners", {}).get(learner)
    if not L or "rows" not in L: return None
    return {r["episode"]: float(r[metric]) for r in L["rows"]}

def paired(d, dom, seeds, cond, learner, metric, f=lambda a, b: a - b):
    """Return per-episode paired values f(cond, native) across seeds (episode ids include seed)."""
    vals = []
    for s in seeds:
        a = rows(d, f"{dom}/seed{s}/{cond}", learner, metric); b = rows(d, f"{dom}/seed{s}/native", learner, metric)
        if a is None or b is None: continue
        for ep in a:
            if ep in b: vals.append(f(a[ep], b[ep]))
    return np.array(vals)

def ci(v):
    if len(v) == 0: return (np.nan, np.nan, np.nan)
    bs = [rng.choice(v, len(v)).mean() for _ in range(B)]
    return (v.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5))

def ratio_ci(num, den):
    """bootstrap CI of mean(num)/mean(den) over paired episodes"""
    if len(num) == 0: return (np.nan, np.nan, np.nan)
    idx = np.arange(len(num)); bs = []
    for _ in range(B):
        i = rng.choice(idx, len(idx)); bs.append(num[i].mean() / den[i].mean())
    return (num.mean() / den.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5))

def pairs(d, dom, seeds, cond, learner, metric):
    A, Bn = [], []
    for s in seeds:
        a = rows(d, f"{dom}/seed{s}/{cond}", learner, metric); b = rows(d, f"{dom}/seed{s}/native", learner, metric)
        if a is None or b is None: continue
        for ep in a:
            if ep in b: A.append(a[ep]); Bn.append(b[ep])
    return np.array(A), np.array(Bn)

for path in sys.argv[1:]:
    d = json.load(open(path)); cfg = d["config"]; dom = cfg["domains"][0]; seeds = cfg["seeds"]
    conds = [c for c in cfg["conditions"] if c != "native"]
    done = {k for k, v in d["runs"].items() if v.get("complete")}
    print(f"\n### {dom}  (complete cells: {len(done)}/{len(seeds)*len(cfg['conditions'])})")
    # P1: graph n_reads(500)/n_reads(native) <= 1.25
    n5, nn = pairs(d, dom, seeds, "500", G, "n_reads")
    m, lo, hi = ratio_ci(n5, nn)
    print(f"P1 {G} reads ratio 500/native = {m:.3f} [{lo:.3f}, {hi:.3f}]  (n={len(n5)})  -> {'PASS' if m <= 1.25 else 'FAIL'} (criterion ≤ 1.25)")
    for c in conds:
        a, b = pairs(d, dom, seeds, c, G, "n_reads")
        if len(a): print(f"     graph reads {c:>5}: {a.mean():.2f} vs native {b.mean():.2f}  ratio {a.mean()/b.mean():.3f}")
    # P2: |paired EES diff| <= 0.05 at every condition
    print(f"P2 {G} EES paired diff vs native (criterion |diff| ≤ 0.05 at each condition):")
    p2 = True
    for c in conds:
        v = paired(d, dom, seeds, c, G, "ees")
        if len(v) == 0: continue
        m, lo, hi = ci(v); ok = abs(m) <= 0.05; p2 &= ok
        print(f"     {c:>5}: diff {m:+.3f} [{lo:+.3f}, {hi:+.3f}] n={len(v)} {'ok' if ok else 'VIOLATED'}")
    print(f"     -> {'PASS' if p2 else 'FAIL'}")
    if "--flips" in sys.argv[0:1] or True:
        for c in conds:
            for s_ in seeds:
                ka, kb = f"{dom}/seed{s_}/{c}", f"{dom}/seed{s_}/native"
                La = d["runs"].get(ka, {}).get("learners", {}).get(G); Lb = d["runs"].get(kb, {}).get("learners", {}).get(G)
                if not La or not Lb or "rows" not in La: continue
                ra = {r["episode"]: r for r in La["rows"]}; rb = {r["episode"]: r for r in Lb["rows"]}
                for ep in ra:
                    if ep in rb and ra[ep]["ees"] != rb[ep]["ees"]:
                        a, b = ra[ep], rb[ep]
                        print(f"       flip {c:>5} {ep}: ees {b['ees']}->{a['ees']} legal {b['legal']}->{a['legal']} valacc {b['value_accuracy']:.2f}->{a['value_accuracy']:.2f} "
                              f"readR {b['required_read_recall']:.2f}->{a['required_read_recall']:.2f} unknown {b['unknown_params']}->{a['unknown_params']} err {a['error']}")
    # P3: retrieval_k16 required_read_recall native - 500 >= 0.20
    v = paired(d, dom, seeds, "500", "retrieval_k16", "required_read_recall", lambda a, b: b - a)
    m, lo, hi = ci(v)
    print(f"P3 retrieval_k16 recall drop native−500 = {m:.3f} [{lo:.3f}, {hi:.3f}] n={len(v)} -> {'PASS' if m >= 0.20 else 'FAIL'} (criterion ≥ 0.20)")
    for L in ("retrieval_k8", "retrieval_k16", "recency_k16"):
        for c in conds:
            a, b = pairs(d, dom, seeds, c, L, "required_read_recall")
            if len(a): print(f"     {L:13s} {c:>5}: recall {a.mean():.3f} vs native {b.mean():.3f}")
    # P4: slope of n_reads vs total records ≈ 1 for full-history readers
    print("P4 n_reads slope vs (records+objects) (criterion ≈ 1; native size = knn reads):")
    recs = {}
    for c in cfg["conditions"]:
        xs = []
        for s in seeds:
            k = f"{dom}/seed{s}/{c}"
            if k not in done: continue
            ae = d["runs"][k]["augment_eval"]
            if ae.get("mean_records") is not None: xs.append(ae["mean_records"] + ae["mean_objects"])
            else:
                r = rows(d, k, "knn", "n_reads")  # native: knn reads every record and object, so its reads = size
                if r: xs.append(float(np.mean(list(r.values()))))
        if xs: recs[c] = float(np.mean(xs))
    for L in ("knn", "flat", "flat_est", "gnn", "gnn_est", "graph", "program", "oracle"):
        pts = []
        for c, x in recs.items():
            ys = []
            for s in seeds:
                r = rows(d, f"{dom}/seed{s}/{c}", L, "n_reads")
                if r: ys.extend(r.values())
            if ys: pts.append((x, float(np.mean(ys))))
        if len(pts) >= 2:
            X = np.array([p[0] for p in pts]); Y = np.array([p[1] for p in pts])
            slope = np.polyfit(X, Y, 1)[0]
            print(f"     {L:10s} slope {slope:.3f}  points {[(round(x,1), round(y,1)) for x,y in sorted(pts)]}")
