"""E3: localising the record that caused an anomaly with the same read-intervention primitive.

Incidents are built exactly as in hm3.provenance (one required witness minimally corrupted, graph_select
executor).  Localisation = adaptive elimination over candidate blocks with a clean-replacement replay as the
test (replace the block by its clean version; does the plan return to the clean one?), candidates ordered by
(a) the structural trace, (b) BM25 against the anomaly, (c) history order.  Reports replays to localise.
Output: results/real/hm3/replay/localise_<domain>.json"""
from __future__ import annotations
import argparse, json, math, random
from pathlib import Path
import numpy as np
from .domains import get_domain
from .generate import generate_split
from .scaling import augment_split
from .learners import LearnedGraph
from .core import canonical_txn
from .provenance import _run, corrupt, anomalous_objects, trace, baseline_rankings, replace_record
from .scaling import SelectExecute


def localise(order, test, max_calls=64):
    """Binary search over a candidate order: find the smallest prefix whose replacement restores the plan,
    then the single record in it.  Returns (rid or None, calls)."""
    calls = 0
    if not order:
        return None, 0
    # exponential + binary search on the prefix length
    lo, hi = 0, 1
    found = False
    while True:
        h = min(hi, len(order))
        calls += 1
        if test(order[:h]):
            found = True
            hi = h
            break
        if h == len(order):
            break
        lo, hi = h, hi * 2
    if not found:
        return None, calls
    # binary search in (lo, hi]
    a, b = lo, hi
    while b - a > 1:
        mid = (a + b) // 2
        calls += 1
        if test(order[:mid]):
            b = mid
        else:
            a = mid
    return order[b - 1], calls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="+", default=["travel"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[30, 31, 32])
    ap.add_argument("--history", default="native")
    ap.add_argument("--n_eval", type=int, default=60)
    ap.add_argument("--out", default="../results/real/hm3/replay")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    res = {}
    for dom in a.domains:
        d = get_domain(dom)
        for seed in a.seeds:
            train = generate_split(d, seed + 100, "train", 200)
            evals = generate_split(d, seed, "test", a.n_eval)
            if a.history != "native":
                target, mix = a.history.split(":")
                evals, _ = augment_split(d, evals, int(target), mix, f"test{seed}")
            g = SelectExecute(); g.fit(d, train)
            rng = random.Random(seed * 7919 + 17)
            rows = []
            for ep in evals:
                clean_txns, clean_reads, clean_score = _run(d, g, ep)
                if not clean_score["ees"]:
                    continue
                got = corrupt(d, ep, rng)
                if got is None:
                    continue
                bad, gold_rid, key = got
                bad_txns, bad_reads, bad_score = _run(d, g, bad)
                clean_set = {canonical_txn(t) for t in clean_txns}
                if bad_score["ees"] or {canonical_txn(t) for t in bad_txns} == clean_set:
                    continue
                anomalies = anomalous_objects(d, bad, bad_txns, bad_score)
                structural, _ = trace(d, g.g, bad, anomalies, bad_reads, k=12)
                read_set = list(bad_reads["records"])
                hist_order = [r["rid"] for r in bad.H]
                bm25 = baseline_rankings(bad, anomalies).get("bm25_anomaly", [])   # key fixed 2026-09-21 (was "bm25": empty)
                orders = {"structural": structural + [r for r in hist_order if r not in structural],
                          "bm25": bm25 + [r for r in hist_order if r not in bm25],
                          "history": hist_order,
                          "reads_then_history": read_set + [r for r in hist_order if r not in read_set]}

                def test(block):
                    fixed = bad
                    for rid in block:
                        fixed = replace_record(fixed, ep, rid)
                    f_txns, _r, _s = _run(d, g, fixed)
                    return {canonical_txn(t) for t in f_txns} == clean_set
                row = {"episode": ep.id, "gold": gold_rid, "n_records": len(bad.H), "n_reads": len(read_set)}
                for name, order in orders.items():
                    found, calls = localise(order, test)
                    row[name] = {"found": found, "hit": found == gold_rid, "calls": calls}
                rows.append(row)
            summ = {"incidents": len(rows)}
            for name in ("structural", "bm25", "history", "reads_then_history"):
                calls = [r[name]["calls"] for r in rows]
                summ[name] = {"hit": float(np.mean([r[name]["hit"] for r in rows])) if rows else None,
                              "calls_median": float(np.median(calls)) if calls else None,
                              "calls_p90": float(np.percentile(calls, 90)) if calls else None,
                              "calls_mean": float(np.mean(calls)) if calls else None}
            res[f"{dom}/seed{seed}"] = {"summary": summ, "rows": rows}
            print(dom, seed, json.dumps(summ), flush=True)
    json.dump(res, open(out / f"localise_{'_'.join(a.domains)}_{a.history.replace(':', '')}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
