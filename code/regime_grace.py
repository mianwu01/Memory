"""Regime-conditioned discovery (GRACE v1) — the multiplicative-gate estimator.

Milestone M0 of docs/agentic-experiment-plan.md, and the method contribution the
formulation actually claims. Everything shipped before this was either

  * BLIND      : discovery on the pooled series, regime u_t ignored, or
  * AUGMENTED  : u_t appended as extra NODES (code/e0_grace.py) -- the "A2
                 auxiliary variable" move, which is ADDITIVE,

and both are wrong for a gated edge. A gated read edge is MULTIPLICATIVE:

    x_j(t) = sum_i sum_l  [ a_ijl * g_ijl(u_t) ] * x_i(t-l) + eps

The edge (i->j at lag l) exists with strength a_ijl but is switched on and off by
g_ijl(u_t). Adding u_t as one more parent lets the model shift the MEAN of x_j
per regime; it cannot make the COEFFICIENT on x_i depend on the regime. That is
why E0's augmented arm still misses the read edge, and why the MINJA analysis had
to split the sample by hand instead of asking a discovery method.

This module estimates the gate directly. Two estimators, same interface:

  fit_regime_conditioned(...)  per-regime coefficient fitting (ridge + BH-FDR),
                               then an edge is reported if it is significant in
                               ANY regime, and flagged GATED if its coefficient
                               differs across regimes beyond sampling error.
  fit_grace_per_regime(...)    the same split, but each subsample is handed to
                               causalts GRACE, so the nonlinear/L0 machinery is
                               kept. Falls back to the ridge estimator if
                               causalts is unavailable.

Both return a RegimeResult carrying, per edge, the per-regime weights and a gate
verdict -- so downstream code can ask "is this edge active only under u=1?",
which is exactly the question the P3 audit needs and the memory mask consumes.

CPU-only. Usage:
    python3 code/regime_grace.py            # runs the E0 evaluation below
"""
from __future__ import annotations

import os as _os
# CPU-only by contract; `import torch` (via causalts) probes the driver over NVML.
_os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


# --------------------------------------------------------------------------- #
# result container
# --------------------------------------------------------------------------- #
@dataclass
class RegimeResult:
    """Discovered lagged edges plus their per-regime behaviour.

    weights[(i, j, lag)][r] is the fitted coefficient of x_i(t-lag) on x_j(t)
    inside regime r. `edges` is the union over regimes of what survived testing;
    `gated` is the subset whose coefficient is regime-dependent.
    """
    var_names: List[str]
    regimes: List[int]
    weights: Dict[Tuple[int, int, int], Dict[int, float]] = field(default_factory=dict)
    pvalues: Dict[Tuple[int, int, int], Dict[int, float]] = field(default_factory=dict)
    edges: set = field(default_factory=set)
    gated: set = field(default_factory=set)
    n_per_regime: Dict[int, int] = field(default_factory=dict)

    def active_in(self, regime: int) -> set:
        """Edges significant inside one regime."""
        return {e for e in self.edges
                if self.pvalues.get(e, {}).get(regime, 1.0) < self._alpha}

    _alpha: float = 0.01

    def describe(self, top: int = 12) -> str:
        out = []
        for e in sorted(self.edges, key=lambda e: -max(
                abs(v) for v in self.weights[e].values())):
            i, j, l = e
            w = "  ".join(f"u={r}:{self.weights[e][r]:+.2f}" for r in self.regimes)
            tag = "  <-- GATED" if e in self.gated else ""
            out.append(f"  {self.var_names[i]}->{self.var_names[j]}@{l}   {w}{tag}")
            if len(out) >= top:
                break
        return "\n".join(out)


# --------------------------------------------------------------------------- #
# design matrix
# --------------------------------------------------------------------------- #
def _lagged_design(X: np.ndarray, target: int, max_lag: int,
                   valid: np.ndarray,
                   within_step_order: Optional[Sequence[int]] = None
                   ) -> Tuple[np.ndarray, np.ndarray, List[Tuple[int, int]]]:
    """Build an ordered within-step plus lagged design.

    ``within_step_order`` is an instrumentation-derived partial order.  When it
    is supplied, x_i(t) may predict x_j(t) only if order[i] < order[j].  This is
    needed for agent traces where retrieval and action share a round index but
    the runtime tells us unambiguously that retrieval happened first.  Equal
    ranks never predict one another, and lagged predictors remain unrestricted.
    Without the order this is the original lag-only estimator.
    """
    T, n = X.shape
    rows, cols = [], []
    if within_step_order is not None:
        if len(within_step_order) != n:
            raise ValueError("within_step_order must have one rank per variable")
        for i in range(n):
            if i != target and within_step_order[i] < within_step_order[target]:
                cols.append((i, 0))
    for l in range(1, max_lag + 1):
        for i in range(n):
            cols.append((i, l))
    ts = [t for t in range(max_lag, T) if valid[t]]
    if not ts:
        return np.empty((0, len(cols))), np.empty((0,)), cols
    D = np.empty((len(ts), len(cols)))
    for r, t in enumerate(ts):
        for c, (i, l) in enumerate(cols):
            D[r, c] = X[t - l, i]
    y = X[np.asarray(ts), target]
    return D, y, cols


def _ridge_with_se(D: np.ndarray, y: np.ndarray, lam: float = 1e-3):
    """Ridge fit returning coefficients, standard errors and two-sided p-values."""
    from scipy import stats
    n, p = D.shape
    if n <= p + 1:
        return None
    Dc = np.hstack([np.ones((n, 1)), D])
    A = Dc.T @ Dc + lam * np.eye(p + 1)
    try:
        Ainv = np.linalg.inv(A)
    except np.linalg.LinAlgError:
        return None
    beta = Ainv @ Dc.T @ y
    resid = y - Dc @ beta
    dof = max(1, n - p - 1)
    s2 = float(resid @ resid) / dof
    cov = s2 * (Ainv @ (Dc.T @ Dc) @ Ainv)
    se = np.sqrt(np.clip(np.diag(cov), 1e-18, None))
    tstat = beta / se
    pval = 2 * (1 - stats.t.cdf(np.abs(tstat), dof))
    return beta[1:], se[1:], pval[1:]          # drop intercept


def _bh(pvals: Sequence[float], alpha: float) -> np.ndarray:
    """Benjamini-Hochberg; returns a boolean keep-mask."""
    p = np.asarray(pvals, float)
    m = len(p)
    if m == 0:
        return np.zeros(0, bool)
    order = np.argsort(p)
    thresh = alpha * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    keep = np.zeros(m, bool)
    if passed.any():
        cut = np.max(np.nonzero(passed)[0])
        keep[order[: cut + 1]] = True
    return keep


# --------------------------------------------------------------------------- #
# estimator 1: per-regime coefficients (the multiplicative gate, directly)
# --------------------------------------------------------------------------- #
def fit_regime_conditioned(X: np.ndarray, u: np.ndarray, max_lag: int = 1,
                           alpha: float = 0.01, gate_ratio: float = 4.0,
                           var_names: Optional[List[str]] = None,
                           min_rows: int = 30,
                           within_step_order: Optional[Sequence[int]] = None
                           ) -> RegimeResult:
    """Fit x_j(t) ~ x_i(t-l) SEPARATELY inside each regime, then compare.

    An edge is reported if it clears BH-FDR in at least one regime -- this is the
    part that rescues a gated edge, because pooling dilutes it below threshold in
    proportion to how rare the active regime is.

    An edge is flagged GATED when its largest per-regime |coefficient| exceeds
    `gate_ratio` times its smallest, i.e. the coefficient itself moves with u,
    which is precisely what an additive u-as-a-node model cannot express.
    """
    X = np.asarray(X, float)
    u = np.asarray(u).astype(int).ravel()
    T, n = X.shape
    if u.shape[0] != T:
        raise ValueError(f"u has {u.shape[0]} steps but X has {T}")
    names = var_names or [f"x{i}" for i in range(n)]
    regimes = sorted(set(u.tolist()))
    res = RegimeResult(var_names=names, regimes=regimes)
    res._alpha = alpha

    for r in regimes:
        mask = (u == r)
        res.n_per_regime[r] = int(mask.sum())

    for j in range(n):
        for r in regimes:
            D, y, cols = _lagged_design(
                X, j, max_lag, valid=(u == r),
                within_step_order=within_step_order)
            if D.shape[0] < min_rows:
                continue
            fit = _ridge_with_se(D, y)
            if fit is None:
                continue
            beta, _se, pval = fit
            keep = _bh(pval, alpha)
            for c, (i, l) in enumerate(cols):
                key = (i, j, l)
                res.weights.setdefault(key, {})[r] = float(beta[c])
                res.pvalues.setdefault(key, {})[r] = float(pval[c])
                if keep[c]:
                    res.edges.add(key)

    # gate verdict: does the coefficient itself depend on the regime?
    for e in res.edges:
        w = [abs(v) for v in res.weights.get(e, {}).values()]
        if len(w) >= 2 and min(w) >= 0 and max(w) > gate_ratio * max(min(w), 1e-9):
            res.gated.add(e)
    return res


# --------------------------------------------------------------------------- #
# estimator 2: GRACE inside each regime
# --------------------------------------------------------------------------- #
def fit_grace_per_regime(X: np.ndarray, u: np.ndarray, max_lag: int = 1,
                         var_names: Optional[List[str]] = None,
                         thresh: float = 0.5, min_rows: int = 60,
                         **grace_kw) -> RegimeResult:
    """Run causalts GRACE on each regime subsample and merge the graphs.

    Keeps GRACE's gating/L0 machinery while making the REGIME the conditioning
    variable rather than an extra node. Falls back to fit_regime_conditioned if
    causalts is not importable, so callers always get a RegimeResult.
    """
    try:
        import pandas as pd
        from causalts.grace import run_cdnots_gated
    except Exception as exc:                                  # pragma: no cover
        res = fit_regime_conditioned(X, u, max_lag=max_lag, var_names=var_names)
        res.weights.setdefault(("fallback",), {})             # marker, harmless
        res.weights.pop(("fallback",), None)
        print(f"[regime_grace] causalts unavailable ({exc}); used ridge estimator")
        return res

    X = np.asarray(X, float)
    u = np.asarray(u).astype(int).ravel()
    n = X.shape[1]
    names = var_names or [f"x{i}" for i in range(n)]
    regimes = sorted(set(u.tolist()))
    res = RegimeResult(var_names=names, regimes=regimes)

    kw = dict(max_lag=max(1, max_lag), verbose=False, model_seed=0,
              max_epochs=60, patience=10, device="cpu")
    kw.update(grace_kw)

    for r in regimes:
        sub = X[u == r]
        res.n_per_regime[r] = int(sub.shape[0])
        if sub.shape[0] < min_rows:
            continue
        out = run_cdnots_gated(pd.DataFrame(sub, columns=names), **kw)
        g = _extract_graph(out)
        if g is None:
            continue
        for i in range(min(n, g.shape[0])):
            for j in range(min(n, g.shape[1])):
                for l in range(g.shape[2]):
                    w = float(g[i, j, l])
                    if l == 0 and i == j:
                        continue
                    res.weights.setdefault((i, j, l), {})[r] = w
                    if abs(w) > thresh:
                        res.edges.add((i, j, l))
                        res.pvalues.setdefault((i, j, l), {})[r] = 0.0
                    else:
                        res.pvalues.setdefault((i, j, l), {})[r] = 1.0

    for e in res.edges:
        w = [abs(v) for v in res.weights.get(e, {}).values()]
        if len(w) >= 2 and max(w) > 4.0 * max(min(w), 1e-9):
            res.gated.add(e)
    return res


def _extract_graph(result):
    """Pull the (cause, effect, lag) array out of whatever GRACE returned."""
    for attr in ("graph", "G", "adjacency", "A", "G_est"):
        v = getattr(result, attr, None)
        if v is not None:
            return np.asarray(v)
    d = result if isinstance(result, dict) else getattr(result, "__dict__", {})
    for v in d.values():
        if isinstance(v, np.ndarray) and v.ndim == 3:
            return v
    return None


# --------------------------------------------------------------------------- #
# E0 evaluation: does regime conditioning recover the gated read edge?
# --------------------------------------------------------------------------- #
def evaluate_on_e0(deltas=(10,), sigmas=(0.0, 0.01, 0.1), n_ep: int = 150,
                   seed: int = 42) -> List[Dict]:
    """Blind vs additive-augmented vs regime-conditioned on the E0 gated SCM.

    Reuses code/e0_grace.py's generator so this is the same data the frozen P1
    result was measured on. Typed recall focuses on the READ edges (m->y, d1->y),
    which are the ones the gate switches on.
    """
    import e0_grace as E0

    rows = []
    for delta in deltas:
        for sigma in sigmas:
            X, U = E0.generate(delta=delta, sigma_hold=sigma, n_ep=n_ep, seed=seed)
            # regime label: 0 = hold/idle, 1 = the read step (the gate is open)
            u = U[:, 2].astype(int)

            # (a) BLIND: one pooled fit, regime ignored
            blind = fit_regime_conditioned(X, np.zeros_like(u), max_lag=1,
                                           var_names=E0.VAR)
            # (b) AUGMENTED: u as an extra NODE (additive), still one pooled fit
            Xa = np.hstack([X, U])
            aug = fit_regime_conditioned(Xa, np.zeros(len(Xa), int), max_lag=1,
                                         var_names=E0.VAR + ["u_w", "u_h", "u_r"])
            # (c) OURS: condition on the regime (multiplicative gate)
            ours = fit_regime_conditioned(X, u, max_lag=1, var_names=E0.VAR)

            read = {(1, 2, 1), (3, 2, 1)}          # m->y@1, d1->y@1
            row = {
                "delta": delta, "sigma": sigma,
                "blind_read": len(read & blind.edges),
                "augmented_read": len(read & {(i, j, l) for (i, j, l) in aug.edges
                                              if i < 8 and j < 8}),
                "regime_read": len(read & ours.edges),
                "regime_read_gated": len(read & ours.gated),
                "n_regime": dict(ours.n_per_regime),
            }
            rows.append(row)
            print(f"delta={delta} sigma={sigma}: read edges recovered  "
                  f"blind={row['blind_read']}/2  augmented={row['augmented_read']}/2  "
                  f"regime={row['regime_read']}/2 (gated-flagged "
                  f"{row['regime_read_gated']}/2)", flush=True)
    return rows


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/regime_grace_e0.json")
    ap.add_argument("--n_ep", type=int, default=150)
    a = ap.parse_args()
    print("E0: blind vs additive-augmented vs regime-conditioned\n")
    rows = evaluate_on_e0(n_ep=a.n_ep)
    from pathlib import Path
    p = Path(a.out); p.parent.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(p, "w"), indent=1)
    print(f"\nwrote {p}")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
