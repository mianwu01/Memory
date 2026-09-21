"""Deterministic replication: every learner on every domain over seeds.

Usage: python3 -m hm3.run_det --domains travel shopping search formal \
           --seeds 0 1 2 --n_train 200 --n_eval 60 --split dev --out results/...
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import numpy as np

from .core import Episode, plan_to_txns, restricted_est, score_plan
from .domains import ALL_DOMAINS, get_domain
from .generate import generate_split
from .learners import make_learners

METRICS = ["ees", "legal", "exact_action_set", "affected_precision", "affected_recall", "affected_f1",
           "collateral_txns", "value_accuracy", "required_read_recall", "n_reads", "regret", "n_plan"]


def evaluate_learner(domain, learner, eval_eps: List[Episode]) -> Dict:
    rows = []
    t0 = time.time()
    for ep in eval_eps:
        out = learner.predict(domain, ep)
        reads = out.get("reads") or {"objects": [], "records": []}
        if out.get("txns") is not None:
            txns = out["txns"]
            info = {}
        else:
            est = restricted_est(domain, ep.H, ep.S0, reads.get("records", []))
            txns, info = plan_to_txns(domain, ep.S0, ep.I, out["plan"], est)
        s = score_plan(domain, ep, txns, reads)
        s["episode"] = ep.id
        s["unknown_params"] = len(info.get("unknown_params", []))
        rows.append(s)
    agg = {}
    for m in METRICS:
        vals = [r[m] for r in rows if r[m] is not None]
        agg[m] = float(np.mean(vals)) if vals else None
    agg["n"] = len(rows)
    agg["seconds"] = time.time() - t0
    agg["illegal_rate"] = float(np.mean([not r["legal"] for r in rows]))
    return {"summary": agg, "rows": rows}


def run(domains, seeds, n_train, n_eval, split, out_path, learner_names=None, train_seed_offset=0):
    results = {"config": {"domains": domains, "seeds": seeds, "n_train": n_train, "n_eval": n_eval,
                          "split": split}, "runs": {}}
    for dname in domains:
        domain = get_domain(dname)
        for seed in seeds:
            t0 = time.time()
            train = generate_split(domain, seed + train_seed_offset, "train", n_train)
            evals = generate_split(domain, seed, split, n_eval)
            gen_s = time.time() - t0
            key = f"{dname}/seed{seed}"
            results["runs"][key] = {"generation_seconds": gen_s, "learners": {}}
            for learner in make_learners(seed):
                if learner_names and learner.name not in learner_names:
                    continue
                t1 = time.time()
                learner.fit(domain, train)
                fit_s = time.time() - t1
                res = evaluate_learner(domain, learner, evals)
                res["summary"]["fit_seconds"] = fit_s
                results["runs"][key]["learners"][learner.name] = res
                s = res["summary"]
                print(f"{key:16s} {learner.name:14s} EES {s['ees']:.3f} exact {s['exact_action_set']:.3f} "
                      f"F1 {s['affected_f1']:.3f} coll {s['collateral_txns']:.2f} readR {s['required_read_recall']:.2f} "
                      f"illegal {s['illegal_rate']:.2f} fit {fit_s:.1f}s", flush=True)
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w") as f:
                json.dump(results, f, indent=1)
    return results


def summarize(results: dict) -> Dict[str, Dict[str, dict]]:
    """domain -> learner -> mean metrics across seeds."""
    acc = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for key, run_ in results["runs"].items():
        dname = key.split("/")[0]
        for lname, res in run_["learners"].items():
            for m, v in res["summary"].items():
                if isinstance(v, (int, float)) and v is not None:
                    acc[dname][lname][m].append(v)
    out = {}
    for dname, ls in acc.items():
        out[dname] = {}
        for lname, ms in ls.items():
            out[dname][lname] = {m: (float(np.mean(v)), float(np.std(v))) for m, v in ms.items()}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="+", default=ALL_DOMAINS)
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--n_train", type=int, default=200)
    ap.add_argument("--n_eval", type=int, default=60)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--learners", nargs="*", default=None)
    ap.add_argument("--train_seed_offset", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    run(a.domains, a.seeds, a.n_train, a.n_eval, a.split, a.out, a.learners, a.train_seed_offset)
