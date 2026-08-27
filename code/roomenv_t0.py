"""RoomEnv-v3 T0: gold graph by intervention + recovery by CI discovery (CPU-only).

World variables per step t: L_o(t) = room of moving object o (categorical),
W_w(t) = active bit of periodic wall w. Dynamics are deterministic and factorized
(room3.py:151-162), so gold direct edges W_w(t) -> L_o(t+1) are derived
COUNTERFACTUALLY: flip one wall bit in an observed context, recompute the
object's forced move; the wall is a true parent iff the outcome changes in >=1
observed context (the do()-based carrier criterion, D1 of the formulation).
Discovery: per-object multinomial logistic regression, drop-one-parent
likelihood-ratio tests, BH-FDR. Negative control: cross-object edges (gold: none).

Usage: python3 code/roomenv_t0.py
"""

import json
import random
import sys
from collections import defaultdict

import numpy as np
from scipy import stats as st
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "benchmarks/room-env")
from room_env.envs.room3 import RoomEnv3  # noqa: E402

import os
K_ROLLOUTS = int(os.environ.get("K", 40)); T_STEPS = int(os.environ.get("T", 100)); ROOM = os.environ.get("ROOM", "small-01")
DIRS = ["north", "east", "south", "west"]


def rollout(seed):
    random.seed(seed)
    env = RoomEnv3(terminates_at=T_STEPS - 1, room_size=ROOM)
    env.reset()
    rooms = list(env.room_connections.keys())
    env.moving_locations = {o: random.choice(rooms) for o in env.moving_locations}
    for w in env.wall_configs:                       # intervene on exogenous phase
        p = env.wall_configs[w]
        k = random.randrange(len(p))
        env.wall_configs[w] = p[k:] + p[:k]
    env._update_wall_layout()
    rec = []
    for _ in range(T_STEPS):
        t = env.current_step
        rec.append({"loc": dict(env.moving_locations),
                    "walls": {"|".join(w): p[t % len(p)] for w, p in env.wall_configs.items()},
                    "conn": {r: dict(c) for r, c in env.room_connections.items()}})
        _, _, done, _, _ = env.step(("x", "stay"))
        if done:
            break
    prefs = dict(env.movement_preferences)
    return rec, prefs


def wall_dir_map(recs, wall_keys):
    """For wall r1|r2|kind, find the direction d with conn[r1][d]==r2 when inactive."""
    m = {}
    for rec in recs:
        for step in rec:
            for wk in wall_keys:
                if wk in m or step["walls"][wk] == 1:
                    continue
                r1, r2, _ = wk.split("|")
                for d in DIRS:
                    if step["conn"][r1].get(d) == r2:
                        m[wk] = (r1, r2, d)
                        break
    return m


def next_room(loc, conn, pref):
    for d in pref:
        if conn[loc].get(d, "wall") != "wall":
            return conn[loc][d]
    return loc


def flip_conn(conn, wk, bit, dmap):
    """Return connections with wall wk forced to `bit`."""
    r1, r2, d = dmap[wk]
    opp = {"north": "south", "south": "north", "east": "west", "west": "east"}
    c = {r: dict(x) for r, x in conn.items()}
    if bit == 1:
        c[r1][d] = "wall"
        c[r2][opp[d]] = "wall"
    else:
        c[r1][d] = r2
        c[r2][opp[d]] = r1
    return c


def main():
    data = [rollout(s) for s in range(K_ROLLOUTS)]
    recs = [r for r, _ in data]
    prefs = data[0][1]
    objs = sorted(prefs.keys())
    walls = sorted(recs[0][0]["walls"].keys())
    dmap = wall_dir_map(recs, walls)
    assert set(dmap) == set(walls), f"unresolved wall directions: {set(walls)-set(dmap)}"

    # ---- gold by counterfactual intervention over observed contexts ----
    gold = set()
    for rec in recs:
        for step in rec[:-1]:
            for o in objs:
                base = next_room(step["loc"][o], step["conn"], prefs[o])
                for wk in walls:
                    cf = next_room(step["loc"][o],
                                   flip_conn(step["conn"], wk, 1 - step["walls"][wk], dmap),
                                   prefs[o])
                    if cf != base:
                        gold.add((wk, o))
    gold |= {(f"self:{o}", o) for o in objs}

    # sanity: replicate env transitions exactly
    mism = sum(next_room(rec[i]["loc"][o], rec[i]["conn"], prefs[o]) != rec[i + 1]["loc"][o]
               for rec in recs for i in range(len(rec) - 1) for o in objs)
    print("transition replication mismatches:", mism)

    skip_pooled = os.environ.get("SKIP_POOLED") == "1"
    # ---- discovery: multinomial logistic + drop-one LRT + BH ----
    rooms = sorted({step["loc"][o] for rec in recs for step in rec for o in objs})
    ridx = {r: i for i, r in enumerate(rooms)}
    blocks, X_cols = {}, []
    rows_X, rows_Y = [], {o: [] for o in objs}
    for rec in recs:
        for i in range(len(rec) - 1):
            f = []
            for o in objs:                             # candidate: L_o(t), one-hot
                oh = [0.0] * len(rooms)
                oh[ridx[rec[i]["loc"][o]]] = 1.0
                f += oh
            f += [float(rec[i]["walls"][wk]) for wk in walls]   # candidate: W_w(t)
            rows_X.append(f)
            for o in objs:
                rows_Y[o].append(ridx[rec[i + 1]["loc"][o]])
    X = np.array(rows_X)
    col = 0
    for o in objs:
        blocks[f"self:{o}" if True else o] = list(range(col, col + len(rooms)))
        blocks[f"L:{o}"] = list(range(col, col + len(rooms)))
        col += len(rooms)
    for j, wk in enumerate(walls):
        blocks[wk] = [col + j]

    def fit_ll(Xs, y):
        if Xs.shape[1] == 0:
            p = np.bincount(y, minlength=len(rooms)) / len(y)
            return float(np.log(np.clip(p[y], 1e-12, 1)).sum()), len(set(y)) - 1
        m = LogisticRegression(max_iter=2000, C=1e4).fit(Xs, y)
        ll = -len(y) * __import__("sklearn.metrics", fromlist=["log_loss"]).log_loss(
            y, m.predict_proba(Xs), labels=m.classes_)
        return float(ll), Xs.shape[1] * (len(m.classes_) - 1)

    cand = [f"L:{o}" for o in objs] + walls
    pvals, keys = [], []
    for o in (objs if not skip_pooled else []):
        y = np.array(rows_Y[o])
        ll_full, df_full = fit_ll(X, y)
        for c in cand:
            keep = [j for j in range(X.shape[1]) if j not in blocks[c]]
            ll_r, df_r = fit_ll(X[:, keep], y)
            lr = max(0.0, 2 * (ll_full - ll_r))
            df = max(1, df_full - df_r)
            pvals.append(st.chi2.sf(lr, df))
            keys.append((c, o))
    order = np.argsort(pvals)
    m = len(pvals)
    thr = 0.0
    for r_, oi in enumerate(order, 1):
        if pvals[oi] <= 0.01 * r_ / m:
            thr = pvals[oi]
    pred = {k for k, p in zip(keys, pvals) if thr > 0 and p <= thr}
    pred = {(("self:" + k.split(":")[1]) if k.startswith("L:") and k.split(":")[1] == o else k, o)
            for (k, o) in pred}

    # ---- context-conditioned discovery (the E0 "regime-aware" analog):
    # condition on L_o(t)=r, test each wall against the next room ----
    ctx_p, ctx_keys = [], []
    for o in objs:
        by_room = defaultdict(list)
        for rec in recs:
            for i in range(len(rec) - 1):
                by_room[rec[i]["loc"][o]].append(
                    ({wk: rec[i]["walls"][wk] for wk in walls}, rec[i + 1]["loc"][o]))
        for r, trans in by_room.items():
            if len(trans) < 30:
                continue
            for wk in walls:
                tab = defaultdict(lambda: defaultdict(int))
                for wbits, nxt in trans:
                    tab[wbits[wk]][nxt] += 1
                if len(tab) < 2:
                    continue
                nxts = sorted({n for d in tab.values() for n in d})
                if len(nxts) < 2:
                    continue
                M = np.array([[tab[b].get(n, 0) for n in nxts] for b in sorted(tab)])
                try:
                    _, p, _, _ = st.chi2_contingency(M)
                except ValueError:
                    continue
                ctx_p.append(p)
                ctx_keys.append((wk, o))
    order2 = np.argsort(ctx_p)
    thr2, m2 = 0.0, len(ctx_p)
    for r_, oi in enumerate(order2, 1):
        if ctx_p[oi] <= 0.01 * r_ / m2:
            thr2 = ctx_p[oi]
    pred_ctx = {k for k, p in zip(ctx_keys, ctx_p) if thr2 > 0 and p <= thr2}
    pred_ctx |= {(f"self:{o}", o) for o in objs}

    gold_n = {(c, o) for (c, o) in gold}
    tp2 = len(pred_ctx & gold_n)
    P2 = tp2 / len(pred_ctx) if pred_ctx else 1.0
    R2 = tp2 / len(gold_n) if gold_n else 1.0
    print(json.dumps({"context_conditioned": {
        "pred_edges": sorted(map(list, pred_ctx)),
        "precision": round(P2, 3), "recall": round(R2, 3),
        "F1": round(2 * P2 * R2 / (P2 + R2), 3) if P2 + R2 else 0.0,
        "false_edges": sorted(map(list, pred_ctx - gold_n))}}, indent=2))

    tp = len(pred & gold_n)
    P = tp / len(pred) if pred else 1.0
    R = tp / len(gold_n) if gold_n else 1.0
    cross = [(c, o) for (c, o) in pred if c.startswith("self:") and c.split(":")[1] != o
             or (c.startswith("L:") and c.split(":")[1] != o)]
    print(json.dumps({
        "rollouts": K_ROLLOUTS, "steps": T_STEPS, "objects": objs, "walls": walls,
        "gold_edges": sorted(map(list, gold_n)),
        "pred_edges": sorted(map(list, pred)),
        "precision": round(P, 3), "recall": round(R, 3),
        "F1": round(2 * P * R / (P + R), 3) if P + R else 0.0,
        "negative_control_cross_object_edges": cross,
    }, indent=2))


if __name__ == "__main__":
    main()
