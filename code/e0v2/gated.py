"""Hard-Concrete L0 gate family for E0 v2 (CPU only).

Three ways to place the gates, one code path:

    pooled        z_e            one gate per candidate edge, regime ignored
                                 (GRACE's own object, re-implemented here so the
                                 comparison with the regime version is controlled)
    per_regime    z_e^(u)        one pooled model per regime subsample
    regime        z_e(u)         one model, one gate per edge x regime, trained on
                                 every sample; the gate that applies to a sample is
                                 the one of its regime.  This is Regime-GRACE.

Regime-GRACE's gate logit is  log_alpha[e, u] = a_e + b_{e,u}: a shared
edge-level term (the skeleton, which sees every sample) plus a regime deviation
(the activation, which sees only that regime's samples).  ``hierarchical=False``
drops the shared term and is the ablation "independent gates per regime".

The Hard Concrete parameterisation (temperature 2/3, stretch [-0.1, 1.1], init
-0.5, differentiable L0 = sigmoid(log_alpha - t log(-gamma/zeta))) and the
closed-form lambda (Eq. 11 of the GRACE paper) are copied from causalts so the
pooled arm here is the same estimator as the official one up to the encoder.

Predictor: linear  x_j(t) = sum_{i,l} z_ilj(u) w_ilj x_i(t-l) + b_j(u), which is
literally the formulation's a_ijl g_ijl(u); or a GRACE-style nonlinear
encoder/decoder when ``nonlinear=True``.  Gaussian NLL with a learned scale per
(variable, regime).  After training, coefficients are re-estimated by OLS on the
selected parents inside each regime (relaxed fit), which is what the heatmaps
show.
"""
from __future__ import annotations

import math
import os
import time
from typing import Optional

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_cache = os.environ.get("TORCHINDUCTOR_CACHE_DIR", "")
if not (_cache and os.access(os.path.dirname(_cache.rstrip("/")) or "/", os.W_OK)):
    os.environ["TORCHINDUCTOR_CACHE_DIR"] = os.path.join(_ROOT, ".tmp", "torchinductor")

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from .linear import Estimate, refit_coefficients, per_regime as _per_regime_lin, pooled_ridge as _pooled_lin
from .scm import K

torch.set_num_threads(max(1, int(os.environ.get("E0V2_THREADS", "2"))))

GAMMA, ZETA, TEMP = -0.1, 1.1, 2.0 / 3.0
EPS = 1e-6
L0_SHIFT = TEMP * math.log(-GAMMA / ZETA)


def compute_lambda(d: int, T: int, density: float) -> float:
    """GRACE Eq. 11: max(0.007 + 0.16 rho, 1/d + 4/T - 0.4 rho^0.8)."""
    return max(0.007 + 0.16 * density, 1.0 / d + 4.0 / T - 0.4 * density ** 0.8)


class GatedModel(nn.Module):
    """Gates z_e(u), regime-specific coefficients under a shared skeleton logit.

    The coefficient of an edge is regime-specific (w[i, l, j, u]).  A single
    coefficient shared across regimes is destroyed by heteroscedasticity: the
    near-deterministic hold rows (sigma ~ 0.01, precision ~ 1e4) pin the shared
    weight of any edge that is inactive in hold to zero whenever its hold gate
    is sampled open, and the write/read gates then have nothing to open for.
    Sharing therefore lives in the gate logit a_e (skeleton), where it belongs.
    """

    def __init__(self, n: int, L: int, n_regimes: int, regime_gates: bool,
                 hierarchical: bool = True, nonlinear: bool = False, hidden: int = 16,
                 mask: Optional[np.ndarray] = None, use_u_stats: bool = True):
        super().__init__()
        self.n, self.L, self.K = n, L, n_regimes
        self.regime_gates, self.hierarchical, self.nonlinear = regime_gates, hierarchical, nonlinear
        self.Kg = n_regimes if regime_gates else 1
        self.use_u_stats = use_u_stats and regime_gates
        Ks = self.Kg
        if regime_gates and not hierarchical:
            self.a_shared = None
            self.b_regime = nn.Parameter(torch.full((n, L, n, n_regimes), -0.5))
        else:
            self.a_shared = nn.Parameter(torch.full((n, L, n), -0.5))
            self.b_regime = nn.Parameter(torch.zeros(n, L, n, n_regimes)) if regime_gates else None
        m = torch.ones(n, L, n, dtype=torch.bool) if mask is None else torch.as_tensor(mask, dtype=torch.bool)
        self.register_buffer("mask", m)
        self.bias = nn.Parameter(torch.zeros(n, Ks))
        self.log_sigma = nn.Parameter(torch.zeros(n, Ks))
        if nonlinear:
            self.enc_w = nn.Parameter(torch.randn(n, L, hidden) * (2.0 ** 0.5))
            self.enc_b = nn.Parameter(torch.zeros(n, L, hidden))
            self.dec_w1 = nn.Parameter(torch.randn(Ks, n, hidden, hidden) / hidden ** 0.5)
            self.dec_b1 = nn.Parameter(torch.zeros(Ks, n, hidden))
            self.dec_w2 = nn.Parameter(torch.randn(Ks, n, hidden) / hidden ** 0.5)
        else:
            self.w = nn.Parameter(torch.randn(n, L, n, Ks) * 0.1)

    # -- gates ---------------------------------------------------------------
    def log_alpha(self) -> torch.Tensor:
        if self.a_shared is not None:
            la = self.a_shared[..., None].expand(self.n, self.L, self.n, self.Kg)
            if self.b_regime is not None:
                la = la + self.b_regime
        else:
            la = self.b_regime
        return la.masked_fill(~self.mask[..., None], -1e10)

    def gates(self) -> torch.Tensor:
        la = self.log_alpha()
        if self.training:
            uu = torch.rand_like(la).clamp(EPS, 1 - EPS)
            s = torch.sigmoid((torch.log(uu) - torch.log(1 - uu) + la) / TEMP)
        else:
            s = torch.sigmoid(la)
        z = (s * (ZETA - GAMMA) + GAMMA).clamp(0.0, 1.0)
        return z * self.mask[..., None]

    def l0(self) -> torch.Tensor:
        return (torch.sigmoid(self.log_alpha() - L0_SHIFT) * self.mask[..., None]).sum()

    def gate_values(self) -> np.ndarray:
        with torch.no_grad():
            la = self.log_alpha()
            z = (torch.sigmoid(la) * (ZETA - GAMMA) + GAMMA).clamp(0, 1) * self.mask[..., None]
        return z.numpy()

    # -- predictor -----------------------------------------------------------
    def forward(self, x: torch.Tensor, u: torch.Tensor):
        B = x.shape[0]
        z = self.gates()
        mu = torch.zeros(B, self.n, dtype=x.dtype)
        groups = torch.unique(u).tolist() if self.Kg > 1 else [None]
        for k in groups:
            idx = torch.ones(B, dtype=torch.bool) if k is None else (u == k)
            kk = 0 if k is None else int(k)
            zk = z[..., kk]
            xk = x[idx]
            if self.nonlinear:
                enc = torch.tanh(xk[..., None] * self.enc_w + self.enc_b)              # [b, n, L, H]
                h = torch.einsum("bilh,ilj->bjh", enc, zk)
                h = F.relu(torch.einsum("bjh,jhg->bjg", h, self.dec_w1[kk]) + self.dec_b1[kk])
                out = torch.einsum("bjg,jg->bj", h, self.dec_w2[kk])
            else:
                W = (zk * self.w[..., kk]).reshape(self.n * self.L, self.n)
                out = xk.reshape(xk.shape[0], -1) @ W
            mu[idx] = out + self.bias[:, kk]
        if self.Kg > 1:
            sigma = torch.exp(self.log_sigma)[:, u].T
        else:
            sigma = torch.exp(self.log_sigma)[:, 0][None, :].expand(B, self.n)
        return mu, sigma


def _train(model: GatedModel, xlag: torch.Tensor, y: torch.Tensor, u: torch.Tensor,
           lam: float, epochs: int, batch: int, lr: float, patience: int, seed: int):
    torch.manual_seed(seed)
    N = xlag.shape[0]
    steps = math.ceil(N / batch)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    best, bad, hist = float("inf"), 0, []
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(N)
        tot = 0.0
        for s in range(steps):
            idx = perm[s * batch:(s + 1) * batch]
            mu, sig = model(xlag[idx], u[idx])
            nll = (((y[idx] - mu) ** 2) / (2 * sig ** 2) + torch.log(sig)).sum(1).mean()
            loss = nll + lam / steps * model.l0()
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item()
        hist.append(tot / steps)
        if hist[-1] < best - 1e-4:
            best, bad = hist[-1], 0
        else:
            bad += 1
            if bad >= patience:
                break
    return hist


def _prepare(X: np.ndarray, u: np.ndarray, max_lag: int):
    T, n = X.shape
    mu, sd = X.mean(0), X.std(0) + 1e-8
    Xn = (X - mu) / sd
    rows = np.arange(max_lag, T)
    xlag = np.stack([Xn[rows - l] for l in range(1, max_lag + 1)], axis=-1)   # [N, n, L]
    return (torch.tensor(xlag, dtype=torch.float32), torch.tensor(Xn[rows], dtype=torch.float32),
            torch.tensor(u[rows], dtype=torch.long), sd)


def _fit_one(xlag, y, uu, n, L, mode, hierarchical, nonlinear, hidden, mask, lam, epochs,
             batch, lr, patience, seed):
    regime_gates = mode in ("regime",)
    model = GatedModel(n, L, K, regime_gates, hierarchical, nonlinear, hidden, mask,
                       use_u_stats=regime_gates)
    hist = _train(model, xlag, y, uu, lam, epochs, batch, lr, patience, seed)
    model.eval()
    return model, hist


def fit_gated(X: np.ndarray, u: np.ndarray, max_lag: int = 1, mode: str = "regime",
              hierarchical: bool = True, nonlinear: bool = False, hidden: int = 16,
              skeleton: str = "none", alpha_screen: float = 0.1, lam: Optional[float] = None,
              lambda_scale: float = 1.0, epochs: int = 150, batch: int = 256, lr: float = 1e-2,
              patience: int = 20, seed: int = 0, threshold: float = 0.5, min_rows: int = 30,
              name: Optional[str] = None, holdout_frac: float = 0.0) -> Estimate:
    t0 = time.time()
    T, n = X.shape
    L = max_lag
    xlag, y, uu, sd = _prepare(X, u, max_lag)
    N = xlag.shape[0]
    val = None
    if holdout_frac > 0:
        g = torch.Generator().manual_seed(seed + 777)
        perm = torch.randperm(N, generator=g)
        n_val = int(N * holdout_frac)
        vi, ti = perm[:n_val], perm[n_val:]
        val = (xlag[vi], y[vi], uu[vi])
        xlag, y, uu = xlag[ti], y[ti], uu[ti]
    # candidate skeleton (optional high-recall screen)
    if skeleton == "none":
        mask = np.ones((n, L, n), bool)
    elif skeleton == "pooled":
        mask = _pooled_lin(X, u, max_lag, alpha_screen).edges
    elif skeleton == "regime_union":
        mask = _pooled_lin(X, u, max_lag, alpha_screen).edges | _per_regime_lin(X, u, max_lag, alpha_screen).edges
    else:
        raise ValueError(skeleton)
    density = float(mask.mean())
    lam_used = (compute_lambda(n, T, density) if lam is None else lam) * lambda_scale
    info = {"mode": mode, "hierarchical": hierarchical, "nonlinear": nonlinear, "skeleton": skeleton,
            "skeleton_density": density, "n_candidates": int(mask.sum()), "lambda_l0": lam_used,
            "epochs": {}, "batch": batch, "lr": lr}
    active = np.zeros((n, L, n, K), bool)
    gate = np.zeros((n, L, n, K))
    if mode == "per_regime":
        for k in range(K):
            sel = uu == k
            info["epochs"][k] = 0
            if int(sel.sum()) < min_rows:
                continue
            model, hist = _fit_one(xlag[sel], y[sel], uu[sel], n, L, "pooled", True, nonlinear, hidden,
                                   mask, lam_used, epochs, batch, lr, patience, seed + k)
            g = model.gate_values()[..., 0]
            gate[..., k] = g
            active[..., k] = g > threshold
            info["epochs"][k] = len(hist)
    else:
        model, hist = _fit_one(xlag, y, uu, n, L, mode, hierarchical, nonlinear, hidden, mask,
                               lam_used, epochs, batch, lr, patience, seed)
        g = model.gate_values()
        info["epochs"]["all"] = len(hist)
        info["final_loss"] = hist[-1]
        if val is not None:
            info["val_nll"] = heldout_nll(model, *val)
        if mode == "regime":
            gate = g
            active = g > threshold
        else:                                   # pooled: same gate in every regime
            gate = np.repeat(g[..., :1], K, axis=-1)
            active = gate > threshold
            info["regime_convention"] = "all"
    regime_aware = mode in ("regime", "per_regime")
    coef = refit_coefficients(X, u, active, max_lag) if regime_aware else \
        np.repeat(refit_coefficients(X, np.zeros_like(u), active[..., :1].repeat(K, -1), max_lag)[..., :1], K, -1)
    info["runtime_s"] = time.time() - t0
    info["n_open_gates"] = int(active.sum())
    label = name or {"pooled": "gates_pooled", "per_regime": "grace_per_regime",
                     "regime": "regime_grace_shared" if hierarchical else "regime_grace"}[mode]
    if nonlinear:
        label += "_mlp"
    est = Estimate(label, regime_aware, coef, active, None, info)
    est.info["gate_values_mem"] = None      # filled by the driver if wanted
    est.gate = gate
    return est


def heldout_nll(model: GatedModel, xlag, y, uu) -> float:
    model.eval()
    with torch.no_grad():
        mu, sig = model(xlag, uu)
        nll = (((y - mu) ** 2) / (2 * sig ** 2) + torch.log(sig)).sum(1).mean()
    return float(nll)
