"""E0 v0: synthetic write-hold-read SCM + Layer-1 discovery (CPU only).

Instantiates the gated SCM of causal_memory_formulation.tex (A2 gated stationarity)
in a linear-Gaussian v0 and runs two Layer-1 procedures:
  (a) blind PCMCI+ (ParCorr) on the pooled series, ignoring the regime u_t;
  (b) regime-aware lagged regression (poor-man's CD-NOD): OLS per regime subsample
      with BH-FDR on coefficients, using observed u_t.
Metrics: edge precision/recall/F1 split by edge type (write / hold / read / distractor),
plus frontier F_t precision/recall at a mid-hold step.
Pass criterion (tex E0): read-edge F1 > 0.7 at (Delta, k, sigma) = (10, 1, 0.01).

Usage: python3 code/e0_synth.py
"""

import itertools
import json

import numpy as np
from scipy import stats

# variables: 0=c(cue) 1=m(memory) 2=y(readout) 3..7=d1..d5 distractors
VAR = ["c", "m", "y", "d1", "d2", "d3", "d4", "d5"]
N = len(VAR)
T_PAD = 10          # episode length = Delta + T_PAD, write at t_w=5
T_W = 5

# distractor VAR(1): self-persistence 0.5 + a few cross edges (stable)
D_EDGES = [(3, 3), (4, 4), (5, 5), (6, 6), (7, 7),          # self lag-1
           (4, 3), (6, 5), (7, 6)]                          # d2->d1, d4->d3, d5->d4
D_COEF = {e: (0.5 if e[0] == e[1] else 0.3) for e in D_EDGES}

# ground-truth typed edges: (src, dst, lag, type, regime)
TRUE_EDGES = (
    [(0, 1, 0, "write", "write"), (1, 1, 1, "hold", "hold"),
     (1, 2, 0, "read", "read"), (3, 2, 0, "read", "read")]
    + [(i, j, 1, "distractor", "*") for (i, j) in D_EDGES]
)


def generate(delta, sigma_hold, n_ep, seed):
    rng = np.random.default_rng(seed)
    t_ep = delta + T_PAD
    T = n_ep * t_ep
    X = np.zeros((T, N))
    u = np.array(["idle"] * T, dtype=object)
    for e in range(n_ep):
        o = e * t_ep
        tw, tr = o + T_W, o + T_W + delta
        u[tw], u[tr] = "write", "read"
        u[tw + 1: tr] = "hold"
        for t in range(o, o + t_ep):
            X[t, 0] = rng.normal()                                   # cue: fresh noise
            for i in range(3, 8):                                    # distractors VAR(1)
                prev = X[t - 1] if t > o else np.zeros(N)
                X[t, i] = sum(D_COEF[(p, i)] * prev[p] for p in range(3, 8)
                              if (p, i) in D_COEF) + 0.5 * rng.normal()
            if t == tw:
                X[t, 1] = X[t, 0] + 0.05 * rng.normal()              # write: m <- c
            elif tw < t <= tr:
                X[t, 1] = X[t - 1, 1] + sigma_hold * rng.normal()    # hold
            else:
                X[t, 1] = rng.normal()
            if t == tr:
                X[t, 2] = X[t, 1] + 0.5 * X[t, 3] + 0.1 * rng.normal()   # read: y <- m,d1
            else:
                X[t, 2] = rng.normal()
    return X, u


def f1(pred, true):
    tp = len(pred & true)
    p = tp / len(pred) if pred else 1.0
    r = tp / len(true) if true else 1.0
    return {"P": round(p, 3), "R": round(r, 3),
            "F1": round(2 * p * r / (p + r), 3) if p + r else 0.0}


def eval_edges(pred, label):
    out = {"method": label, "n_pred": len(pred)}
    true_all = {(s, d, l) for (s, d, l, _, _) in TRUE_EDGES}
    out["overall"] = f1(pred, true_all)
    for typ in ["write", "hold", "read", "distractor"]:
        te = {(s, d, l) for (s, d, l, tt, _) in TRUE_EDGES if tt == typ}
        miss = te - pred
        out[typ] = {"R": round(len(pred & te) / len(te), 3)}
        if miss:
            out[typ]["miss"] = sorted(f"{VAR[s]}->{VAR[d]}@{l}" for (s, d, l) in miss)
    return out


def active(reg, u_t):
    """Edge activation: the hold mechanism still carries m at the read step."""
    return (reg == "*" or (reg == "write" and u_t == "write")
            or (reg == "hold" and u_t in ("hold", "read"))
            or (reg == "read" and u_t == "read"))


def run_pcmci_blind(X, tau_max=2, alpha=0.01):
    from tigramite import data_processing as pp
    from tigramite.independence_tests.parcorr import ParCorr
    from tigramite.pcmci import PCMCI
    df = pp.DataFrame(X, var_names=VAR)
    pcmci = PCMCI(dataframe=df, cond_ind_test=ParCorr(), verbosity=0)
    res = pcmci.run_pcmciplus(tau_min=0, tau_max=tau_max, pc_alpha=alpha)
    g = res["graph"]
    pred = set()
    for i in range(N):
        for j in range(N):
            for tau in range(tau_max + 1):
                s = g[i, j, tau]
                if s == "-->":
                    pred.add((i, j, tau))
                elif tau == 0 and s in ("o-o", "x-x") and i < j:
                    pred.add((i, j, 0))
                    pred.add((j, i, 0))
    return pred


def run_regime_regression(X, u, alpha=0.01):
    """Per regime, OLS of each target on all candidates (lag 0 and 1), BH-FDR."""
    T = len(X)
    cands = [(i, l) for i in range(N) for l in (0, 1)]
    pred = set()
    pvals, keys = [], []
    for regime, targets in [("write", [1]), ("hold", [1]), ("read", [2]),
                            ("idle", list(range(3, 8)))]:
        idx = np.array([t for t in range(1, T) if u[t] == regime or
                        (regime == "idle" and True)])  # distractors: all steps
        idx = np.array([t for t in range(1, T) if (u[t] == regime)]) \
            if regime != "idle" else np.arange(1, T)
        for j in targets:
            cols = [(i, l) for (i, l) in cands if not (i == j and l == 0)]
            A = np.column_stack([X[idx - l, i] for (i, l) in cols])
            b = X[idx, j]
            # drop near-constant columns (deterministic-hold degeneracy shows up here)
            keep = [k for k in range(A.shape[1]) if np.std(A[:, k]) > 1e-10]
            A = A[:, keep]
            cols = [cols[k] for k in keep]
            coef, res_, rank, _ = np.linalg.lstsq(A, b, rcond=None)
            dof = max(1, len(idx) - A.shape[1])
            resid = b - A @ coef
            s2 = float(resid @ resid) / dof
            try:
                cov = s2 * np.linalg.pinv(A.T @ A)
                se = np.sqrt(np.maximum(np.diag(cov), 1e-30))
                tstat = coef / se
                p = 2 * stats.t.sf(np.abs(tstat), dof)
            except np.linalg.LinAlgError:
                p = np.ones(len(cols))
            for (i, l), pv in zip(cols, p):
                keys.append((i, j, l))
                pvals.append(pv)
    # BH-FDR
    order = np.argsort(pvals)
    m = len(pvals)
    thresh = 0.0
    for rank_, oi in enumerate(order, start=1):
        if pvals[oi] <= alpha * rank_ / m:
            thresh = pvals[oi]
    for k, pv in zip(keys, pvals):
        if pv <= thresh and pv > 0 or (thresh > 0 and pv <= thresh):
            pred.add(k)
    return pred


# ---------- frontier ----------

def unrolled_parents(edges_by_regime, u, t):
    """parents of (var, time) under gating schedule u; edges as (src,dst,lag,regime)."""
    return [(s, d, l) for (s, d, l, reg) in edges_by_regime if active(reg, u[t])]


def frontier(edges_by_regime, u, t_now, y_node, t_read, max_back=60):
    """F_{t_now}(Y={y at t_read}): past nodes with an edge into An*(Y) in the future."""
    anc = {(y_node, t_read)}
    frontier_nodes = set()
    stack = [(y_node, t_read)]
    while stack:
        v, t = stack.pop()
        if t <= t_read - max_back:
            continue
        for (s, d, l, reg) in edges_by_regime:
            if d != v:
                continue
            ts = t - l
            if ts < 0 or not active(reg, u[t]):
                continue
            if ts > t_now:
                if (s, ts) not in anc:
                    anc.add((s, ts))
                    stack.append((s, ts))
            else:
                if t > t_now:                      # boundary edge: past -> future ancestor
                    frontier_nodes.add((s, ts))
    return frontier_nodes


def true_edges_regime():
    return [(s, d, l, reg) for (s, d, l, _, reg) in TRUE_EDGES]


def main():
    results = []
    for delta, sig in itertools.product([5, 10, 20], [0.0, 0.01, 0.1]):
        X, u = generate(delta, sig, n_ep=200, seed=42)
        cfg = {"delta": delta, "sigma_hold": sig, "T": len(X)}
        blind = run_pcmci_blind(X)
        regime = run_regime_regression(X, u)
        cfg["blind_pcmci+"] = eval_edges(blind, "pcmci+")
        cfg["regime_regression"] = eval_edges(regime, "regime")
        # frontier at a mid-hold step of a middle episode, using regime-aware learned edges
        t_ep = delta + T_PAD
        o = 100 * t_ep
        t_now, t_read = o + T_W + delta // 2, o + T_W + delta
        # learned regime attribution: assign each learned edge the regime it was found in
        learned_reg = []
        for (s, d, l) in regime:
            if d == 1:
                learned_reg.append((s, d, l, "write" if l == 0 else "hold"))
            elif d == 2:
                learned_reg.append((s, d, l, "read"))
            else:
                learned_reg.append((s, d, l, "*"))
        Ft_true = frontier(true_edges_regime(), u, t_now, 2, t_read)
        Ft_hat = frontier(learned_reg, u, t_now, 2, t_read)
        cfg["frontier"] = {"true": sorted([(VAR[v], t - t_now) for v, t in Ft_true]),
                           **f1(Ft_hat, Ft_true)}
        results.append(cfg)
        print(json.dumps(cfg))
    # pass criterion
    tgt = [r for r in results if r["delta"] == 10 and r["sigma_hold"] == 0.01][0]
    print("\nPASS CRITERION read-edge recall (regime) @ (10,1,0.01):",
          tgt["regime_regression"]["read"], "| blind:", tgt["blind_pcmci+"]["read"])


if __name__ == "__main__":
    main()
