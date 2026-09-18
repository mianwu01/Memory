"""Pooled arms from outside packages: PCMCI+ (tigramite) and the official
causalts GRACE (CDNOTS skeleton + Hard Concrete refinement).  Both ignore u by
construction; their output is a single graph G, reported as active in every
regime (the only reading a regime-free graph admits)."""
from __future__ import annotations

import time
import warnings

import numpy as np

from .linear import Estimate, refit_coefficients
from .scm import K


def pcmci_pooled(X: np.ndarray, u: np.ndarray, max_lag: int = 1, alpha: float = 0.01,
                 names=None, plus: bool = False) -> Estimate:
    from tigramite import data_processing as pp
    from tigramite.independence_tests.parcorr import ParCorr
    from tigramite.pcmci import PCMCI
    t0 = time.time()
    T, n = X.shape
    df = pp.DataFrame(X, var_names=names or [f"x{i}" for i in range(n)])
    pcmci = PCMCI(dataframe=df, cond_ind_test=ParCorr(), verbosity=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if plus:
            res = pcmci.run_pcmciplus(tau_min=0, tau_max=max_lag, pc_alpha=alpha)
            g = res["graph"]
            edges = np.zeros((n, max_lag, n), bool)
            for i in range(n):
                for j in range(n):
                    for l in range(1, max_lag + 1):
                        edges[i, l - 1, j] = g[i, j, l] == "-->"
        else:
            res = pcmci.run_pcmci(tau_min=1, tau_max=max_lag, pc_alpha=alpha)
            q = pcmci.get_corrected_pvalues(p_matrix=res["p_matrix"], tau_min=1, tau_max=max_lag,
                                            fdr_method="fdr_bh")
            edges = np.zeros((n, max_lag, n), bool)
            for l in range(1, max_lag + 1):
                edges[:, l - 1, :] = q[:, :, l] < alpha
    active = np.repeat(edges[..., None], K, axis=-1)
    coef = np.repeat(refit_coefficients(X, np.zeros_like(u), active, max_lag)[..., :1], K, -1)
    return Estimate("pcmci_plus" if plus else "pcmci", False, coef, active, None,
                    {"runtime_s": time.time() - t0, "regime_convention": "all"})


def grace_official(X: np.ndarray, u: np.ndarray, max_lag: int = 1, names=None, seed: int = 0,
                   max_epochs: int = 150, patience: int = 20) -> Estimate:
    import pandas as pd
    from causalts.grace import run_cdnots_gated
    t0 = time.time()
    T, n = X.shape
    df = pd.DataFrame(X, columns=names or [f"x{i}" for i in range(n)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = run_cdnots_gated(df, max_lag=max_lag, device="cpu", verbose=False, model_seed=seed,
                               max_epochs=max_epochs, patience=patience)
    G = np.asarray(res.cg_tig)                       # [cause, effect, lag 0..L]
    edges = np.zeros((n, max_lag, n), bool)
    for l in range(1, max_lag + 1):
        edges[:, l - 1, :] = G[:, :, l] == 1
    skel = np.asarray(res.skeleton) if res.skeleton is not None else None
    active = np.repeat(edges[..., None], K, axis=-1)
    coef = np.repeat(refit_coefficients(X, np.zeros_like(u), active, max_lag)[..., :1], K, -1)
    info = {"runtime_s": time.time() - t0, "regime_convention": "all",
            "lambda_l0": float(res.lambda_l0) if res.lambda_l0 is not None else None,
            "n_lag0_edges": int((G[:, :, 0] == 1).sum()),
            "skeleton_edges_lag1": int(skel[:, :, 1].sum()) if skel is not None and skel.shape[2] > 1 else None}
    return Estimate("grace_official", False, coef, active, None, info)
