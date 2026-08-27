"""E0 v1: GRACE's first run, blind vs regime-augmented (CPU).

Lag-1 variant of the E0 gated SCM (all true edges at lag 1, avoiding
instantaneous-edge ambiguity): write m_t = c_{t-1} (at t_w), hold
m_t = m_{t-1} + sigma*eps, read y_t = m_{t-1} + 0.5*d1_{t-1} (at t_r),
distractors VAR(1). Two GRACE runs per config:
  blind     : 8 observed variables only (u_t hidden)
  augmented : + three indicator series u_write/u_hold/u_read as variables
              (the A2 auxiliary-variable move, CD-NOD style)
Eval: typed recall on the 8-var subgraph (write c->m, hold m->m, read m->y &
d1->y, distractor edges), plus false-edge count among 8-var pairs.

Usage: python3 code/e0_grace.py
"""

import json
import time

import numpy as np
import pandas as pd

VAR = ["c", "m", "y", "d1", "d2", "d3", "d4", "d5"]
N = 8
T_PAD, T_W = 10, 5
D_EDGES = [(3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (4, 3), (6, 5), (7, 6)]
D_COEF = {e: (0.5 if e[0] == e[1] else 0.3) for e in D_EDGES}
TRUE = ([(0, 1, "write"), (1, 1, "hold_selfloop_see_note")]  # placeholder, rebuilt below
        )
TRUE_TYPED = ([(0, 1, 1, "write"), (1, 1, 1, "hold"), (1, 2, 1, "read"), (3, 2, 1, "read")]
              + [(i, j, 1, "distractor") for (i, j) in D_EDGES])


def generate(delta, sigma_hold, n_ep, seed):
    rng = np.random.default_rng(seed)
    t_ep = delta + T_PAD
    T = n_ep * t_ep
    X = np.zeros((T, N))
    U = np.zeros((T, 3))                    # write / hold / read indicators
    for e in range(n_ep):
        o = e * t_ep
        tw, tr = o + T_W, o + T_W + delta
        U[tw, 0] = 1
        U[tw + 1: tr, 1] = 1
        U[tr, 2] = 1
        for t in range(o, o + t_ep):
            X[t, 0] = rng.normal()
            prev = X[t - 1] if t > o else np.zeros(N)
            for i in range(3, 8):
                X[t, i] = sum(D_COEF[(p, i)] * prev[p] for p in range(3, 8)
                              if (p, i) in D_COEF) + 0.5 * rng.normal()
            if t == tw:
                X[t, 1] = prev[0] + 0.05 * rng.normal()
            elif tw < t <= tr:
                X[t, 1] = prev[1] + sigma_hold * rng.normal()
            else:
                X[t, 1] = rng.normal()
            if t == tr:
                X[t, 2] = prev[1] + 0.5 * prev[3] + 0.1 * rng.normal()
            else:
                X[t, 2] = rng.normal()
    return X, U


def to_edges(result, n_keep, thresh=0.5):
    """Extract lagged edge set {(i, j, lag)} restricted to first n_keep vars."""
    g = None
    for attr in ("graph", "G", "adjacency", "A", "G_est"):
        if hasattr(result, attr) and getattr(result, attr) is not None:
            g = np.asarray(getattr(result, attr))
            break
    if g is None:
        d = result if isinstance(result, dict) else getattr(result, "__dict__", {})
        for k, v in d.items():
            if isinstance(v, np.ndarray) and v.ndim == 3:
                g = v
                break
    assert g is not None, f"no graph found; attrs={dir(result)}"
    edges = set()
    nv = g.shape[0]
    if g.ndim == 3 and g.shape[0] == g.shape[1] == nv:      # (cause, effect, lag)
        for i in range(min(nv, n_keep)):
            for j in range(min(nv, n_keep)):
                for l in range(g.shape[2]):
                    if abs(float(g[i, j, l])) > thresh:
                        edges.add((i, j, l))
    elif g.ndim == 3 and g.shape[0] == g.shape[2] == nv:    # (cause, lag, effect)
        for i in range(min(nv, n_keep)):
            for l in range(g.shape[1]):
                for j in range(min(nv, n_keep)):
                    if abs(float(g[i, l, j])) > thresh:
                        edges.add((i, j, l))
    return edges, g.shape, g


def typed_eval(edges):
    out = {}
    true_all = {(s, d, l) for (s, d, l, _) in TRUE_TYPED}
    tp = len(edges & true_all)
    out["P"] = round(tp / len(edges), 3) if edges else 1.0
    out["R"] = round(tp / len(true_all), 3)
    for typ in ("write", "hold", "read", "distractor"):
        te = {(s, d, l) for (s, d, l, tt) in TRUE_TYPED if tt == typ}
        got = edges & te
        out[typ] = round(len(got) / len(te), 3)
        miss = te - edges
        if miss:
            out[f"{typ}_miss"] = [f"{VAR[s]}->{VAR[d]}@{l}" for (s, d, l) in miss]
    out["n_pred"] = len(edges)
    return out


def main():
    from causalts.grace import run_cdnots_gated
    results = []
    for sigma in (0.01, 0.1):
        X, U = generate(delta=10, sigma_hold=sigma, n_ep=150, seed=42)
        for mode in ("blind", "augmented"):
            cols = VAR + (["u_w", "u_h", "u_r"] if mode == "augmented" else [])
            data = X if mode == "blind" else np.hstack([X, U])
            df = pd.DataFrame(data, columns=cols)
            t0 = time.time()
            res = run_cdnots_gated(df, max_lag=2, verbose=False, model_seed=0,
                                   max_epochs=60, patience=10, device="cpu")
            edges, shape, g = to_edges(res, n_keep=N)
            if not results:   # one-time orientation check on known edge d2->d1@1
                arrs = {k: v.shape for k, v in vars(res).items()
                        if isinstance(v, np.ndarray)}
                print("result arrays:", arrs)
                print("orientation check g[4,3,1] (d2->d1) =", round(float(g[4, 3, 1]), 3),
                      " g[3,4,1] (d1->d2) =", round(float(g[3, 4, 1]), 3))
            ev = typed_eval({(i, j, l) for (i, j, l) in edges if l >= 1})
            lag0 = sum(1 for (_, _, l) in edges if l == 0)
            row = {"sigma": sigma, "mode": mode, "graph_shape": list(shape),
                   "runtime_s": round(time.time() - t0, 1), "lag0_pred": lag0, **ev}
            results.append(row)
            print(json.dumps(row))
    print("\nSUMMARY")
    for r in results:
        print(f"sigma={r['sigma']} {r['mode']:9s} P={r['P']} R={r['R']} "
              f"write={r['write']} hold={r['hold']} read={r['read']} "
              f"distr={r['distractor']} ({r['runtime_s']}s)")


if __name__ == "__main__":
    main()
