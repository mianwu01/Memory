"""Deterministic history-length scaling sweep (docs/hm3-history-scaling-design-2026-09-18.md).

Usage: python3 -m hm3.run_scaling --domains travel shopping32 --seeds 0 1 2 --split dev \
           --conditions native 50 100 500 a100 b100 c100 d100 --out results/development/hm3/scaling/det_dev.json
       python3 -m hm3.run_scaling --summarize results/development/hm3/scaling/det_dev.json
Train and eval are augmented under the same condition; every condition is fitted separately.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .domains import get_domain
from .generate import generate_split
from .learners import make_learners
from .run_det import evaluate_learner
from .scaling import augment_split, scaling_learners

CONDITIONS = {"native": (None, ""), "50": (50, "abcd"), "100": (100, "abcd"), "500": (500, "abcd"),
              "a100": (None, "a"), "b100": (100, "b"), "c100": (100, "c"), "d100": (100, "d")}


def run(domains: List[str], seeds: List[int], conditions: List[str], n_train: int, n_eval: int, split: str,
        out_path: str, learner_names: Optional[List[str]] = None, train_seed_offset: int = 0) -> dict:
    out = Path(out_path)
    results = {"config": {"domains": domains, "seeds": seeds, "conditions": conditions, "n_train": n_train,
                          "n_eval": n_eval, "split": split, "train_seed_offset": train_seed_offset,
                          "condition_specs": {c: CONDITIONS[c] for c in conditions}}, "runs": {}}
    if out.exists():
        results["runs"] = json.load(open(out)).get("runs", {})
    for dname in domains:
        domain = get_domain(dname)
        for seed in seeds:
            train0 = generate_split(domain, seed + train_seed_offset, "train", n_train)
            eval0 = generate_split(domain, seed, split, n_eval)
            for cond in conditions:
                key = f"{dname}/seed{seed}/{cond}"
                if key in results["runs"] and results["runs"][key].get("complete"):
                    continue
                target, mix = CONDITIONS[cond]
                t0 = time.time()
                if target is None and not mix:
                    train, evals, st_tr, st_ev = train0, eval0, {}, {}
                else:
                    train, st_tr = augment_split(domain, train0, target, mix, f"train{seed}")
                    evals, st_ev = augment_split(domain, eval0, target, mix, f"{split}{seed}")
                entry = {"augment_train": st_tr, "augment_eval": st_ev, "augment_seconds": time.time() - t0,
                         "n_train": len(train), "n_eval": len(evals), "learners": {}}
                results["runs"][key] = entry
                for learner in make_learners(seed) + scaling_learners():
                    if learner_names and learner.name not in learner_names:
                        continue
                    t1 = time.time()
                    try:
                        learner.fit(domain, train)
                    except Exception as exc:
                        entry["learners"][learner.name] = {"error": f"fit {type(exc).__name__}: {str(exc)[:200]}"}
                        print(f"{key:28s} {learner.name:14s} FIT ERROR {type(exc).__name__}", flush=True)
                        continue
                    fit_s = time.time() - t1
                    res = evaluate_learner(domain, learner, evals)
                    res["summary"]["fit_seconds"] = fit_s
                    entry["learners"][learner.name] = res
                    s = res["summary"]
                    print(f"{key:28s} {learner.name:14s} EES {s['ees']:.3f} readR {s['required_read_recall']:.2f} "
                          f"reads {s['n_reads']:.1f} illegal {s['illegal_rate']:.2f} fit {fit_s:.1f}s eval {s['seconds']:.1f}s",
                          flush=True)
                entry["complete"] = True
                out.parent.mkdir(parents=True, exist_ok=True)
                json.dump(results, open(out, "w"), indent=1)
    return results


def summarize(path: str, metrics=("ees", "required_read_recall", "n_reads")) -> str:
    data = json.load(open(path))
    runs = data["runs"]
    conds = data["config"]["conditions"]
    lines = []
    domains = sorted({k.split("/")[0] for k in runs})
    for dname in domains:
        methods = []
        for k, v in runs.items():
            if k.startswith(dname + "/"):
                for m in v["learners"]:
                    if m not in methods:
                        methods.append(m)
        aug = {}
        for c in conds:
            sts = [v["augment_eval"] for k, v in runs.items() if k.startswith(dname + "/") and k.endswith("/" + c) and v["augment_eval"]]
            if sts:
                aug[c] = (np.mean([s["mean_records"] for s in sts]), np.mean([s["mean_objects"] for s in sts]),
                          np.mean([s["drop_rate"] for s in sts]), sum(s["a_diff"] for s in sts), sum(s["a_keys"] for s in sts))
        lines.append(f"\n#### {dname}\n")
        lines.append("| condition | " + " | ".join(conds) + " |")
        lines.append("|---|" + "---:|" * len(conds))
        lines.append("| mean records / objects | " + " | ".join(
            (f"{aug[c][0]:.0f} / {aug[c][1]:.0f}" if c in aug else "native") for c in conds) + " |")
        lines.append("| eval drop rate | " + " | ".join((f"{aug[c][2]:.2f}" if c in aug else "0") for c in conds) + " |")
        lines.append("| A implied-differs / keys | " + " | ".join((f"{aug[c][3]}/{aug[c][4]}" if c in aug and aug[c][4] else "—") for c in conds) + " |")
        for metric in metrics:
            lines.append(f"\n**{metric}** (mean ± sd over seeds)\n")
            lines.append("| method | " + " | ".join(conds) + " |")
            lines.append("|---|" + "---:|" * len(conds))
            for m in methods:
                cells = []
                for c in conds:
                    vals = [v["learners"][m]["summary"][metric] for k, v in runs.items()
                            if k.startswith(dname + "/") and k.endswith("/" + c) and m in v["learners"]
                            and "summary" in v["learners"][m] and v["learners"][m]["summary"].get(metric) is not None]
                    cells.append(f"{np.mean(vals):.3f} ± {np.std(vals):.3f}" if vals else "—")
                lines.append(f"| {m} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="+", default=["travel", "shopping32"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--conditions", nargs="+", default=list(CONDITIONS))
    ap.add_argument("--n_train", type=int, default=200)
    ap.add_argument("--n_eval", type=int, default=60)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--learners", nargs="*", default=None)
    ap.add_argument("--train_seed_offset", type=int, default=0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--summarize", default=None)
    a = ap.parse_args()
    if a.summarize:
        print(summarize(a.summarize))
    else:
        run(a.domains, a.seeds, a.conditions, a.n_train, a.n_eval, a.split, a.out, a.learners, a.train_seed_offset)
