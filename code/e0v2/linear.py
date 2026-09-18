"""Linear-regression arms for E0 v2.  All four share one design matrix and one
test (OLS t-test + global BH-FDR); they differ only in what they know about u.

    pooled_ridge     x_j(t) ~ x(t-1)                       regime ignored
    additive_u       x_j(t) ~ x(t-1) + onehot(u_t)         u shifts the mean only
    interaction_u    x_j(t) ~ sum_u 1[u_t=u] * x(t-1)      one slope per regime,
                                                          pooled residual variance
    per_regime       x_j(t) ~ x(t-1)  fitted inside each regime separately

Nothing here is told which target a regime "should" explain: every regime is
fitted for every target, and an edge's regime label is simply the set of
regimes in which its coefficient survives the test.  The old E0 code assigned
the label from the target name after the fact; that is gone.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy import stats

from .scm import K


@dataclass
class Estimate:
    """coef/active are [cause i, lag-1, effect j, regime u]."""
    name: str
    regime_aware: bool
    coef: np.ndarray
    active: np.ndarray
    pval: Optional[np.ndarray] = None
    info: dict = field(default_factory=dict)

    @property
    def edges(self) -> np.ndarray:
        return self.active.any(-1)


# --------------------------------------------------------------------------- #
# design and test
# --------------------------------------------------------------------------- #
def lagged_design(X: np.ndarray, max_lag: int):
    """Rows t = max_lag..T-1; column (l-1)*n + i holds x_i(t-l)."""
    T, n = X.shape
    rows = np.arange(max_lag, T)
    D = np.concatenate([X[rows - l] for l in range(1, max_lag + 1)], axis=1)
    return D, rows


def bh_mask(p: np.ndarray, alpha: float) -> np.ndarray:
    flat = p.ravel()
    m = flat.size
    order = np.argsort(flat)
    thresh = alpha * np.arange(1, m + 1) / m
    passed = flat[order] <= thresh
    keep = np.zeros(m, bool)
    if passed.any():
        keep[order[: np.max(np.nonzero(passed)[0]) + 1]] = True
    return keep.reshape(p.shape)


def ols_multi(D: np.ndarray, Yt: np.ndarray):
    """OLS of every column of Yt on D (plus intercept).

    Returns beta [p, m], pval [p, m].  Uses the pseudo-inverse so a
    rank-deficient design gives the minimum-norm fit instead of an error.  For
    a deterministic target (sigma_hold = 0) the residual variance is floored
    and numerically-zero coefficients get p = 1, so an exact fit does not turn
    every coefficient into a false positive.
    """
    n_rows, p = D.shape
    Dc = np.hstack([np.ones((n_rows, 1)), D])
    G = Dc.T @ Dc
    Ainv = np.linalg.pinv(G, rcond=1e-10)
    B = Ainv @ (Dc.T @ Yt)
    resid = Yt - Dc @ B
    dof = max(1, n_rows - p - 1)
    s2 = (resid ** 2).sum(0) / dof
    s2 = np.maximum(s2, 1e-10 * (Yt.var(0) + 1e-12))
    diagV = np.clip(np.diag(Ainv @ G @ Ainv), 0, None)
    se = np.sqrt(np.outer(diagV, s2))
    with np.errstate(divide="ignore", invalid="ignore"):
        tstat = np.where(se > 0, B / se, 0.0)
    pval = 2 * stats.t.sf(np.abs(tstat), dof)
    pval[np.abs(B) < 1e-8] = 1.0
    return B[1:], pval[1:]


def ols_screened(D: np.ndarray, Yt: np.ndarray, k: int):
    """Sure-independence screening then OLS, per target, for rows << features."""
    n_rows, p = D.shape
    m = Yt.shape[1]
    B = np.zeros((p, m))
    P = np.ones((p, m))
    Ds = (D - D.mean(0)) / (D.std(0) + 1e-12)
    for j in range(m):
        y = Yt[:, j]
        ys = (y - y.mean()) / (y.std() + 1e-12)
        corr = np.abs(Ds.T @ ys) / n_rows
        top = np.argsort(-corr)[:k]
        b, pv = ols_multi(D[:, top], y[:, None])
        B[top, j] = b[:, 0]
        P[top, j] = pv[:, 0]
    return B, P


def _fit(D: np.ndarray, Yt: np.ndarray, min_rows: int = 10):
    n_rows, p = D.shape
    if n_rows < min_rows:
        return None
    if n_rows >= p + 5:
        return ols_multi(D, Yt)
    return ols_screened(D, Yt, k=max(1, n_rows // 4))


def _to_4d(B: np.ndarray, n: int, max_lag: int) -> np.ndarray:
    """[(l-1)*n + i, j] -> [i, l-1, j]."""
    return B.reshape(max_lag, n, n).transpose(1, 0, 2)


# --------------------------------------------------------------------------- #
# arms
# --------------------------------------------------------------------------- #
def pooled_ridge(X, u, max_lag=1, alpha=0.01, name="pooled_ridge", extra=None):
    t0 = time.time()
    T, n = X.shape
    D, rows = lagged_design(X, max_lag)
    if extra is not None:
        D = np.hstack([D, extra[rows]])
    B, P = ols_multi(D, X[rows])
    B, P = B[: n * max_lag], P[: n * max_lag]
    keep = bh_mask(P, alpha)
    coef = np.repeat(_to_4d(B, n, max_lag)[..., None], K, axis=-1)
    act = np.repeat(_to_4d(keep, n, max_lag)[..., None], K, axis=-1)
    pv = np.repeat(_to_4d(P, n, max_lag)[..., None], K, axis=-1)
    return Estimate(name, False, coef, act, pv,
                    {"runtime_s": time.time() - t0, "regime_convention": "all",
                     "n_rows": int(len(rows))})


def additive_u(X, u, max_lag=1, alpha=0.01):
    onehot = np.eye(K)[u][:, 1:]                 # idle is the reference level
    return pooled_ridge(X, u, max_lag, alpha, name="additive_u", extra=onehot)


def interaction_u(X, u, max_lag=1, alpha=0.01):
    t0 = time.time()
    T, n = X.shape
    D, rows = lagged_design(X, max_lag)
    onehot = np.eye(K)[u[rows]]
    p = D.shape[1]
    Dint = np.concatenate([D * onehot[:, [k]] for k in range(K)] + [onehot[:, 1:]], axis=1)
    B, P = ols_multi(Dint, X[rows])
    B, P = B[: K * p], P[: K * p]
    keep = bh_mask(P, alpha)
    coef = np.stack([_to_4d(B[k * p:(k + 1) * p], n, max_lag) for k in range(K)], -1)
    act = np.stack([_to_4d(keep[k * p:(k + 1) * p], n, max_lag) for k in range(K)], -1)
    pv = np.stack([_to_4d(P[k * p:(k + 1) * p], n, max_lag) for k in range(K)], -1)
    n_per = {int(k): int((u[rows] == k).sum()) for k in range(K)}
    return Estimate("interaction_u", True, coef, act, pv,
                    {"runtime_s": time.time() - t0, "n_per_regime": n_per,
                     "underdetermined": [k for k, c in n_per.items() if c < p + 5]})


def per_regime(X, u, max_lag=1, alpha=0.01, min_rows=10):
    t0 = time.time()
    T, n = X.shape
    D, rows = lagged_design(X, max_lag)
    p = D.shape[1]
    coef = np.zeros((n, max_lag, n, K))
    pv = np.ones((n, max_lag, n, K))
    n_per, screened = {}, []
    for k in range(K):
        sel = u[rows] == k
        n_per[k] = int(sel.sum())
        fit = _fit(D[sel], X[rows[sel]], min_rows)
        if fit is None:
            continue
        if n_per[k] < p + 5:
            screened.append(k)
        B, P = fit
        coef[..., k] = _to_4d(B, n, max_lag)
        pv[..., k] = _to_4d(P, n, max_lag)
    act = bh_mask(pv, alpha)
    return Estimate("per_regime", True, coef, act, pv,
                    {"runtime_s": time.time() - t0, "n_per_regime": n_per,
                     "screened_regimes": screened})


def refit_coefficients(X, u, active: np.ndarray, max_lag=1, min_rows=10) -> np.ndarray:
    """Given an active set [i, l, j, u], re-estimate coefficients by OLS on the
    selected parents inside each regime (relaxed / debiased estimate)."""
    T, n = X.shape
    D, rows = lagged_design(X, max_lag)
    coef = np.zeros_like(active, dtype=float)
    for k in range(K):
        sel = u[rows] == k
        if sel.sum() < min_rows:
            continue
        Dk, Yk = D[sel], X[rows[sel]]
        for j in range(n):
            cols = np.nonzero(active[:, :, j, k].transpose(1, 0).ravel())[0]   # (l-1)*n+i order
            if cols.size == 0 or sel.sum() < cols.size + 3:
                continue
            b, _ = ols_multi(Dk[:, cols], Yk[:, [j]])
            for c, val in zip(cols, b[:, 0]):
                l, i = divmod(int(c), n)
                coef[i, l, j, k] = val
    return coef


def ols_multi_hc(D: np.ndarray, Yt: np.ndarray):
    """OLS with White (HC0) sandwich standard errors, per target.

    The plain interaction model pools the residual variance across regimes;
    when hold rows are near-deterministic and idle rows are unit-variance the
    pooled variance understates the idle noise and idle slopes look
    significant.  The sandwich estimator repairs that at O(n p^2) per target.
    """
    n_rows, p = D.shape
    Dc = np.hstack([np.ones((n_rows, 1)), D])
    Ainv = np.linalg.pinv(Dc.T @ Dc, rcond=1e-10)
    B = Ainv @ (Dc.T @ Yt)
    resid = Yt - Dc @ B
    dof = max(1, n_rows - p - 1)
    m = Yt.shape[1]
    se = np.zeros_like(B)
    for j in range(m):
        meat = (Dc * resid[:, [j]] ** 2).T @ Dc
        V = Ainv @ meat @ Ainv
        se[:, j] = np.sqrt(np.clip(np.diag(V), 0, None))
    se = np.maximum(se, 1e-12)
    tstat = B / se
    pval = 2 * stats.t.sf(np.abs(tstat), dof)
    pval[np.abs(B) < 1e-8] = 1.0
    return B[1:], pval[1:]


def interaction_u_hc(X, u, max_lag=1, alpha=0.01):
    t0 = time.time()
    T, n = X.shape
    D, rows = lagged_design(X, max_lag)
    onehot = np.eye(K)[u[rows]]
    p = D.shape[1]
    Dint = np.concatenate([D * onehot[:, [k]] for k in range(K)] + [onehot[:, 1:]], axis=1)
    B, P = ols_multi_hc(Dint, X[rows])
    B, P = B[: K * p], P[: K * p]
    keep = bh_mask(P, alpha)
    coef = np.stack([_to_4d(B[k * p:(k + 1) * p], n, max_lag) for k in range(K)], -1)
    act = np.stack([_to_4d(keep[k * p:(k + 1) * p], n, max_lag) for k in range(K)], -1)
    pv = np.stack([_to_4d(P[k * p:(k + 1) * p], n, max_lag) for k in range(K)], -1)
    return Estimate("interaction_u_hc", True, coef, act, pv,
                    {"runtime_s": time.time() - t0, "se": "HC0"})
