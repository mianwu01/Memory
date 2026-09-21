"""Established temporal causal discovery on HM3's event logs: PCMCI+ skeleton and GRACE refinement.

Answers the question raised on 2026-09-20 (Yujia): can the structure the pipeline uses be obtained with an
existing, well-established causal discovery algorithm on the same event logs, so that the word "causal" has a
clean provenance?  Inputs are exactly the panels of hm3.tcd_logs (one binary variable per object type, one row
per record, user interventions marked exogenous; or one row per intervention segment); nothing downstream
changes.  Two configurations of the official library (causalts 0.26, the GRACE reference implementation):

  grace        Step 1 skeleton from tigramite PCMCI+ (ParCorr, multi-trial), Step 2/3 GRACE gated refinement on
               trial-respecting windows (the recipe of code/travel_grace_discovery.py, reused verbatim).
  grace_open   the same GRACE model with an all-ones skeleton, so the Hard-Concrete gates alone decide the
               graph (no CI-test prefilter; the PCMCI+ ParCorr test is conservative on binary indicators).

Output per (domain, seed, encoding): the lagged gate array, the positive type edges, and the comparison with the
interventional skeleton (precision / recall), in the same JSON shape as hm3.tcd_logs so hm3.tcd_logs.TCDSelect
can consume it (estimator "grace" / "grace_open" load the file).

Environment: GRACE's own dependencies (numba, statsmodels, causalts, lightning) live in the older scratchpad
library; run with PYTHONPATH=<pylib_tcd>:<pylib2>:<old pylib> and CUDA_VISIBLE_DEVICES="" (CPU by contract).

Usage: python3 -m hm3.grace_logs --domains travel shopping32 --seeds 0 1 2 --max_lag 3 \
           --out ../results/development/hm3/tcd/grace_graphs_dev.json
"""
from __future__ import annotations

import argparse
import json
import math
import time
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .tcd_logs import compare, event_panel, positive_type_edges, skeleton_type_edges, type_vocab

warnings.filterwarnings("ignore")


def build_windows(trials: List[np.ndarray], max_lag: int):
    """Unfold WITHIN each trial, then concatenate (mirrors causalts prepare_data per trial)."""
    import torch
    from torch.utils.data import TensorDataset
    chunks = []
    for A in trials:
        if len(A) <= max_lag:
            continue
        tt = torch.tensor(np.asarray(A, dtype=np.float32))
        chunks.append(tt.T.unfold(1, max_lag + 1, 1).permute(1, 0, 2))   # [T-L, d, L+1]
    if not chunks:
        raise ValueError("no trial is longer than max_lag")
    return TensorDataset(torch.cat(chunks, 0))


def pcmci_skeleton(trials: List[np.ndarray], var_names: List[str], max_lag: int, pc_alpha: float = 0.05,
                   test: str = "parcorr") -> np.ndarray:
    from tigramite import data_processing as pp
    from tigramite.pcmci import PCMCI
    if test == "gsquared":
        from tigramite.independence_tests.gsquared import Gsquared
        data = {k: X.astype(int) for k, X in enumerate(trials) if len(X) > max_lag + 1}
        df = pp.DataFrame(data, analysis_mode="multiple", var_names=var_names,
                          data_type={k: np.ones_like(X, dtype=int) for k, X in data.items()})
        ci = Gsquared(significance="analytic")
    else:
        from tigramite.independence_tests.parcorr import ParCorr
        data = {k: X for k, X in enumerate(trials) if len(X) > max_lag + 1}
        df = pp.DataFrame(data, analysis_mode="multiple", var_names=var_names)
        ci = ParCorr(significance="analytic")
    res = PCMCI(dataframe=df, cond_ind_test=ci, verbosity=0).run_pcmciplus(tau_min=0, tau_max=max_lag, pc_alpha=pc_alpha)
    g = res["graph"]
    d = len(var_names)
    skel = np.zeros((d, d, max_lag + 1), dtype=np.int8)
    for i in range(d):
        for j in range(d):
            for l in range(max_lag + 1):
                if g[i, j, l] in ("-->", "o-o", "x-x", "<--") and not (l == 0 and i == j):
                    skel[i, j, l] = 1
    return skel


def grace_multitrial(trials, var_names, max_lag: int, skeleton: np.ndarray, gate_threshold: float = 0.5,
                     max_epochs: int = 60, patience: int = 10, model_seed: int = 0,
                     batch_size: Optional[int] = None, lambda_scale: float = 1.0, **model_kwargs):
    """GRACE Step 2/3 (gated refinement) over a trial-respecting window set; verbatim recipe from
    code/travel_grace_discovery.py.  Returns (gate array [cause, effect, lag], lambda_l0, seconds)."""
    import torch
    from torch.utils.data import DataLoader
    from causalts.grace.gated_discovery import (GatedCausalDiscovery, _detect_accelerator, _silence_lightning,
                                                compute_lambda)
    from pytorch_lightning import Trainer, seed_everything
    from pytorch_lightning.callbacks import EarlyStopping
    t0 = time.time()
    d = len(var_names)
    dataset = build_windows(trials, max_lag)
    N = len(dataset)
    n_possible = d * d * (max_lag + 1) - d
    density = float(skeleton.sum()) / n_possible if n_possible else 0.0
    lambda_l0 = compute_lambda(d, N, density) * lambda_scale
    if batch_size is None:
        batch_size = max(32, min(N // 8, 256))
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    seed_everything(model_seed, workers=True)
    model_kwargs.setdefault("lambda_lag_group", 0.0)
    model = GatedCausalDiscovery(num_vars=d, max_lag=max_lag, lambda_l0=float(lambda_l0), normalize_l0=True,
                                 steps_per_epoch=math.ceil(N / batch_size), **model_kwargs)
    model.init_from_skeleton(skeleton)
    model.set_skeleton_mask(skeleton)
    _silence_lightning()
    trainer = Trainer(max_epochs=max_epochs, accelerator=_detect_accelerator(), deterministic="warn",
                      callbacks=[EarlyStopping(monitor="train_loss", patience=patience, mode="min")],
                      enable_progress_bar=False, enable_model_summary=False, logger=False, enable_checkpointing=False)
    trainer.fit(model, train_dataloaders=loader)
    _, gates = model.get_estimated_graph(threshold=None)
    gates = np.asarray(gates, dtype=float)
    np.fill_diagonal(gates[:, :, 0], 0.0)
    return gates, float(lambda_l0), time.time() - t0


def fit_grace(trials_exo: List[Tuple[np.ndarray, np.ndarray]], types: List[str], max_lag: int = 3,
              skeleton_mode: str = "pcmci", gate_threshold: float = 0.5, seed: int = 0, max_epochs: int = 60,
              patience: int = 10, lambda_scale: float = 1.0) -> dict:
    """Fit GRACE on the event panel; returns the tcd_logs-style dict (edges with the gate value as 'coef')."""
    trials = [X for X, _exo in trials_exo]
    d = len(types)
    t0 = time.time()
    if skeleton_mode == "pcmci":
        skel = pcmci_skeleton(trials, types, max_lag, test="parcorr")
    elif skeleton_mode == "pcmci_g2":
        skel = pcmci_skeleton(trials, types, max_lag, test="gsquared")
    else:
        skel = np.ones((d, d, max_lag + 1), dtype=np.int8)
        np.fill_diagonal(skel[:, :, 0], 0)
    gates, lam, secs = grace_multitrial(trials, types, max_lag, skel, gate_threshold=gate_threshold,
                                        model_seed=seed, max_epochs=max_epochs, patience=patience, lambda_scale=lambda_scale)
    edges = {}
    for i in range(d):
        for j in range(d):
            for l in range(1, max_lag + 1):
                if gates[i, j, l] >= gate_threshold:
                    edges[f"{types[i]}->{types[j]}@{l}"] = {"coef": float(gates[i, j, l]), "p": 0.0}
    lag0 = [f"{types[i]}->{types[j]}@0" for i in range(d) for j in range(d) if i != j and gates[i, j, 0] >= gate_threshold]
    return {"estimator": f"grace_{skeleton_mode}", "max_lag": max_lag, "gate_threshold": gate_threshold, "lambda_scale": lambda_scale,
            "lambda_l0": lam, "n_trials": len(trials), "n_windows": int(sum(max(0, len(X) - max_lag) for X in trials)),
            "skeleton_edges": int(skel[:, :, 1:].sum()), "seconds": time.time() - t0, "edges": edges,
            "lag0_edges": lag0, "gates_max_over_lags": {f"{types[i]}->{types[j]}": float(gates[i, j, 1:].max())
                                                       for i in range(d) for j in range(d) if i != j}}


def run(domains: List[str], seeds: List[int], n_train: int, out: str, max_lag: int, train_seed_offset: int,
        encodings=("event", "segment"), modes=("pcmci", "open"), max_epochs: int = 60, patience: int = 10) -> dict:
    from .domains import get_domain
    from .generate import generate_split
    from .learners import LearnedGraph
    results = {"config": {"domains": domains, "seeds": seeds, "n_train": n_train, "max_lag": max_lag,
                          "library": "causalts 0.26 GRACE; tigramite PCMCI+ ParCorr", "max_epochs": max_epochs, "patience": patience}, "runs": {}}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    for dname in domains:
        domain = get_domain(dname)
        for seed in seeds:
            train = generate_split(domain, seed + train_seed_offset, "train", n_train)
            types = type_vocab(train)
            g = LearnedGraph()
            g.fit(domain, train)
            ref = skeleton_type_edges(g)
            entry = {"types": types, "skeleton_type_edges": sorted(f"{a}->{b}" for a, b in ref), "encodings": {}}
            for enc in encodings:
                trials = event_panel(train, types, enc)
                encs = {"n_trials": len(trials)}
                for mode in modes:
                    # a mode may carry a sparsity multiplier: open, open_x3, open_x10
                    base, _, mult = mode.partition("_x")
                    ls = float(mult) if mult else 1.0
                    try:
                        fit = fit_grace(trials, types, max_lag, base, seed=seed, max_epochs=max_epochs, patience=patience, lambda_scale=ls)
                    except Exception as exc:
                        encs[f"grace_{mode}"] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
                        print(f"{dname}/seed{seed} {enc} grace_{mode}: ERROR {type(exc).__name__}: {str(exc)[:120]}", flush=True)
                        continue
                    pos = positive_type_edges(fit)
                    fit["positive_type_edges"] = sorted(f"{a}->{b}" for a, b in pos)
                    fit["self_edges"] = sorted(k for k in fit["edges"] if k.split("->")[0] == k.split("->")[1].split("@")[0])
                    fit["vs_skeleton"] = compare(pos, ref)
                    encs[f"grace_{mode}"] = fit
                    vs = fit["vs_skeleton"]
                    print(f"{dname}/seed{seed} {enc} grace_{mode}: P={vs['precision']} R={vs['recall']} "
                          f"edges={sorted(pos)} self={len(fit['self_edges'])} skel={fit['skeleton_edges']} {fit['seconds']:.0f}s", flush=True)
                entry["encodings"][enc] = encs
            results["runs"][f"{dname}/seed{seed}"] = entry
            json.dump(results, open(out, "w"), indent=1, default=str)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="+", default=["travel", "shopping32"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--n_train", type=int, default=200)
    ap.add_argument("--max_lag", type=int, default=3)
    ap.add_argument("--train_seed_offset", type=int, default=0)
    ap.add_argument("--encodings", nargs="+", default=["event", "segment"])
    ap.add_argument("--modes", nargs="+", default=["pcmci", "pcmci_g2", "open", "open_x3", "open_x10"])
    ap.add_argument("--max_epochs", type=int, default=60)
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    run(a.domains, a.seeds, a.n_train, a.out, a.max_lag, a.train_seed_offset, a.encodings, a.modes, a.max_epochs, a.patience)
