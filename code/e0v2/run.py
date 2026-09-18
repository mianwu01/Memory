"""E0 v2 experiment driver.

    python3 code/e0v2/run.py --exp e0a --seeds 0 1 2 3 4 --workers 5
    python3 code/e0v2/run.py --exp e0b --seeds 0 1 2 3 4 --workers 6
    python3 code/e0v2/run.py --exp e0c --seeds 0 1 2 --workers 3

Every (dataset, arm) pair is one job; results append to results/e0v2/<exp>.jsonl
as they finish, and a rerun skips the keys already present, so an interrupted
sweep resumes.  Workers are CPU-only (CUDA_VISIBLE_DEVICES is emptied before
torch is imported) and use E0V2_THREADS torch threads each.

External packages (tigramite, causalts) are optional; point E0V2_PYLIB at a
``pip install --target`` directory that holds them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""
if os.environ.get("E0V2_PYLIB"):
    sys.path.insert(0, os.environ["E0V2_PYLIB"])
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from e0v2 import scm, linear, metrics

ROOT = Path(__file__).resolve().parents[2]

PRESETS = {                     # read-rarity presets for E0b (realised p_read is recorded)
    "default": {},
    "p20": dict(idle_range=(1, 1), delta_range=(1, 2), gap_range=(1, 2), p_second_write=0.0, p_second_read=0.0),
    "p10": dict(idle_range=(1, 3), delta_range=(3, 7), gap_range=(1, 4), p_second_write=0.0, p_second_read=0.0),
    "p05": dict(idle_range=(2, 6), delta_range=(8, 16), gap_range=(1, 6), p_second_write=0.3, p_second_read=0.0),
    "p02": dict(idle_range=(12, 24), delta_range=(18, 38), gap_range=(2, 8), p_second_write=0.3, p_second_read=0.0),
    "p01": dict(idle_range=(25, 45), delta_range=(40, 70), gap_range=(2, 8), p_second_write=0.3, p_second_read=0.0),
}

LINEAR_ARMS = ["pooled_ridge", "additive_u", "interaction_u", "interaction_u_hc", "per_regime"]
GATE_ARMS = ["gates_pooled", "grace_per_regime", "regime_grace", "regime_grace_shared",
             "regime_grace_screen_pooled", "regime_grace_screen_union"]
EXTERNAL_ARMS = ["pcmci", "grace_official"]
CONTROL_ARMS = ["per_regime@shuffle", "interaction_u_hc@shuffle", "regime_grace@shuffle"]
MLP_ARMS = ["gates_pooled_mlp", "regime_grace_mlp"]


def run_arm(arm: str, X, u, names, o: dict):
    L, seed, ls = o["max_lag"], o["seed"], o["lambda_scale"]
    ep = o.get("epochs", 150)
    if arm == "pooled_ridge":
        return linear.pooled_ridge(X, u, L)
    if arm == "additive_u":
        return linear.additive_u(X, u, L)
    if arm == "interaction_u":
        return linear.interaction_u(X, u, L)
    if arm == "interaction_u_hc":
        return linear.interaction_u_hc(X, u, L)
    if arm == "per_regime":
        return linear.per_regime(X, u, L)
    if arm in ("pcmci", "pcmci_plus", "grace_official"):
        from e0v2 import external
        if arm.startswith("pcmci"):
            return external.pcmci_pooled(X, u, L, names=names, plus=arm == "pcmci_plus")
        return external.grace_official(X, u, L, names=names, seed=seed, max_epochs=ep)
    from e0v2 import gated
    common = dict(max_lag=L, seed=seed, lambda_scale=ls, epochs=ep, name=arm)
    if arm == "gates_pooled":
        return gated.fit_gated(X, u, mode="pooled", **common)
    if arm == "gates_pooled_mlp":
        return gated.fit_gated(X, u, mode="pooled", nonlinear=True, **common)
    if arm == "grace_per_regime":
        return gated.fit_gated(X, u, mode="per_regime", **common)
    if arm == "regime_grace":
        return gated.fit_gated(X, u, mode="regime", hierarchical=False, **common)
    if arm == "regime_grace_mlp":
        return gated.fit_gated(X, u, mode="regime", hierarchical=False, nonlinear=True, **common)
    if arm == "regime_grace_shared":
        return gated.fit_gated(X, u, mode="regime", hierarchical=True, **common)
    if arm == "regime_grace_screen_pooled":
        return gated.fit_gated(X, u, mode="regime", hierarchical=False, skeleton="pooled", **common)
    if arm == "regime_grace_screen_union":
        return gated.fit_gated(X, u, mode="regime", hierarchical=False, skeleton="regime_union", **common)
    raise ValueError(arm)


def job(spec: dict) -> dict:
    t0 = time.time()
    cfg = scm.Config(n_dist=spec["n_dist"], sigma_hold=spec["sigma"], mechanism=spec["mechanism"],
                     **PRESETS[spec["preset"]])
    X, u, dinfo = scm.generate(cfg, spec["T"], seed=spec["seed"])
    truth, etype = scm.ground_truth(cfg)
    if spec["max_lag"] > 1:                                   # truth is lag 1 only; pad lags 2..L with zeros
        pad = np.zeros((truth.shape[0], spec["max_lag"] - 1, truth.shape[2], truth.shape[3]))
        truth = np.concatenate([truth, pad], axis=1)
    mem = scm.memory_targets(cfg)
    names = cfg.var_names()
    arm, _, ctrl = spec["arm"].partition("@")
    uu = u
    if ctrl == "shuffle":
        uu = np.random.default_rng(1000 + spec["seed"]).permutation(u)
    try:
        est = run_arm(arm, X, uu, names, spec)
    except Exception as exc:                                  # keep the sweep alive
        return {"key": spec["key"], "spec": spec, "data": dinfo, "error": repr(exc),
                "elapsed_s": time.time() - t0}
    ev = metrics.evaluate(truth, etype, est, mem, mechanism=cfg.mechanism)
    if ctrl == "shuffle":
        ev_true_u = None
    hm = metrics.heatmap_rows(truth, etype, est, names)
    info = {k: v for k, v in est.info.items() if k != "gate_values_mem"}
    return {"key": spec["key"], "spec": spec, "data": dinfo, "metrics": ev, "heatmap": hm,
            "info": info, "elapsed_s": time.time() - t0}


def make_specs(exp: str, a) -> list:
    specs = []
    base = dict(exp=exp, max_lag=a.max_lag, lambda_scale=a.lambda_scale, epochs=a.epochs)
    if exp in ("e0a", "e0a_lag2"):
        arms = a.arms or (LINEAR_ARMS + GATE_ARMS + EXTERNAL_ARMS + CONTROL_ARMS)
        if exp == "e0a_lag2":
            base["max_lag"] = 2
            arms = a.arms or ["pooled_ridge", "per_regime", "regime_grace"]
        for sigma in a.sigmas:
            for seed in a.seeds:
                for arm in arms:
                    specs.append(dict(base, seed=seed, sigma=sigma, T=a.T, n_dist=a.n_dist,
                                      mechanism="linear", preset="default", arm=arm))
    elif exp == "e0b":
        arms = a.arms or ["pooled_ridge", "interaction_u_hc", "per_regime", "gates_pooled", "regime_grace"]
        for preset in a.presets:
            for T in a.Ts:
                for seed in a.seeds:
                    for arm in arms:
                        specs.append(dict(base, seed=seed, sigma=a.sigmas[0], T=T, n_dist=a.n_dist,
                                          mechanism="linear", preset=preset, arm=arm))
    elif exp == "e0c":
        arms = a.arms or ["pooled_ridge", "interaction_u", "per_regime", "gates_pooled", "regime_grace"]
        for d in a.ds:
            for seed in a.seeds:
                for arm in arms:
                    specs.append(dict(base, seed=seed, sigma=a.sigmas[0], T=a.T, n_dist=d - 12,
                                      mechanism="linear", preset="default", arm=arm))
    elif exp == "e0c_mlp":
        arms = a.arms or ["pooled_ridge", "interaction_u_hc", "per_regime", "gates_pooled", "regime_grace",
                          "gates_pooled_mlp", "regime_grace_mlp"]
        for seed in a.seeds:
            for arm in arms:
                specs.append(dict(base, seed=seed, sigma=a.sigmas[0], T=a.T, n_dist=a.n_dist,
                                  mechanism="mlp", preset="default", arm=arm))
    else:
        raise ValueError(exp)
    for s in specs:
        s["key"] = "|".join(f"{k}={s[k]}" for k in ("exp", "arm", "seed", "sigma", "T", "n_dist",
                                                    "mechanism", "preset", "max_lag", "lambda_scale"))
    return specs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, choices=["e0a", "e0a_lag2", "e0b", "e0c", "e0c_mlp"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--sigmas", type=float, nargs="+", default=[0.0, 0.01, 0.1])
    ap.add_argument("--T", type=int, default=10000)
    ap.add_argument("--Ts", type=int, nargs="+", default=[1000, 2000, 5000, 10000, 20000, 50000])
    ap.add_argument("--n_dist", type=int, default=20)
    ap.add_argument("--ds", type=int, nargs="+", default=[50, 200, 1000])
    ap.add_argument("--presets", nargs="+", default=["p20", "p10", "p05", "p02", "p01"])
    ap.add_argument("--arms", nargs="+", default=None)
    ap.add_argument("--max_lag", type=int, default=1)
    ap.add_argument("--lambda_scale", type=float, default=1.0)
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--out", default=None)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    os.environ["E0V2_THREADS"] = str(a.threads)
    out = Path(a.out or ROOT / "results" / "e0v2" / f"{a.exp}{a.tag}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["key"])
    specs = [s for s in make_specs(a.exp, a) if s["key"] not in done]
    print(f"{a.exp}: {len(specs)} jobs to run ({len(done)} already done) -> {out}", flush=True)
    t0 = time.time()
    if a.workers <= 1:
        it = map(job, specs)
    else:
        from multiprocessing import get_context
        pool = get_context("fork").Pool(a.workers, maxtasksperchild=4)
        it = pool.imap_unordered(job, specs)
    with open(out, "a") as fh:
        for k, rec in enumerate(it, 1):
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            m = rec.get("metrics")
            line = (f"[{k}/{len(specs)} {time.time() - t0:6.0f}s] {rec['spec']['arm']:28s} seed={rec['spec']['seed']} "
                    f"sigma={rec['spec']['sigma']} T={rec['spec']['T']} n={rec['spec']['n_dist'] + 12} "
                    f"preset={rec['spec']['preset']} ")
            if m:
                line += (f"edgeF1={m['edge']['F1']:.3f} cellF1={m['cell']['F1']:.3f} "
                         f"cellMemF1={m['cell_mem']['F1']:.3f} gate={m['gate_exact']:.2f} "
                         f"read={m['recall_cell_read']} ({rec['elapsed_s']:.0f}s)")
            else:
                line += f"ERROR {rec.get('error')}"
            print(line, flush=True)


if __name__ == "__main__":
    main()
