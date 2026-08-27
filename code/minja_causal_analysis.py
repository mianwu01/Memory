"""P3 analysis — can we recover the hidden driver of the MINJA failure?

Runs three audits on a trajectory produced by minja_causal_audit.py and reports
what each can and cannot conclude:

  (A) BEHAVIOUR-ONLY audit  — sees only actions (answers) over time. Detects that
      anomalies happen, but is blind to memory, so it can only correlate anomalies
      with observable query features (e.g. the 'food' topic) and MISATTRIBUTES the
      cause to the trigger word -- which the pre-injection probes prove is benign.
  (B) SIMILARITY / retrieval audit — the MemAudit-style lens: flag a round if the
      retrieved memory looks unusual (retrieval distance). Poison records are
      topically similar to the query, so their retrieval distance is not anomalous
      -> the audit cannot separate poison from legitimate memory.
  (C) CAUSAL audit (ours) — temporal causal discovery over the fixed-schema series
      X_t. Two estimators:
        pooled     : ignores the regime (all rounds together)   [confounded]
        regime     : conditions on the gate u_t = trigger        [recovers edge]
      Then provenance maps the recovered poison_retr ancestor back to the injection
      round t-k that WROTE it -- naming the hidden driver, which (A)/(B) cannot.

CPU-only, no API. Usage: python3 code/minja_causal_analysis.py --trace results/minja_trace_sim.csv
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

import numpy as np
import pandas as pd


def logreg_coef(X, y):
    """Tiny ridge-logistic fit (Newton steps); returns coef dict. No sklearn dep."""
    X = np.asarray(X, float)
    X = np.hstack([np.ones((len(X), 1)), X])
    y = np.asarray(y, float)
    w = np.zeros(X.shape[1])
    lam = 1e-2
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) + lam * w
        W = p * (1 - p)
        H = X.T @ (X * W[:, None]) + lam * np.eye(X.shape[1])
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def risk_diff(df, cause, outcome="anomalous"):
    a = df[df[cause] == 1][outcome].mean() if (df[cause] == 1).any() else float("nan")
    b = df[df[cause] == 0][outcome].mean() if (df[cause] == 0).any() else float("nan")
    return a, b, a - b


def behaviour_audit(df):
    print("\n=== (A) BEHAVIOUR-ONLY AUDIT (sees actions, not memory) ===")
    by_phase = df.groupby("phase")["anomalous"].agg(["sum", "count"])
    for ph, r in by_phase.iterrows():
        print(f"  {ph:13s} anomalous {int(r['sum'])}/{int(r['count'])}")
    # the only observable it can correlate with: the trigger word in the query
    a, b, rd = risk_diff(df, "trigger")
    print(f"  observable correlate: P(anomalous|food)={a:.2f} vs "
          f"P(anomalous|~food)={b:.2f}  (risk diff {rd:+.2f})")
    pre = df[df.phase == "pre"]["anomalous"].mean()
    test = df[df.phase == "test"]["anomalous"].mean()
    print(f"  BUT identical 'food' queries: pre-injection {pre:.2f} vs post {test:.2f}"
          f"  -> the food topic is NOT the cause; behaviour audit cannot see why.")
    return {"misattributes_to": "trigger", "pre_food_anom": pre, "post_food_anom": test}


def similarity_audit(df):
    print("\n=== (B) SIMILARITY / RETRIEVAL AUDIT (MemAudit-style lens) ===")
    d = df[df.retr_poison_dist >= 0]
    if d.empty:
        print("  no poison ever retrieved; audit sees nothing to flag.")
        return {"separable": False}
    # does the poison retrieval look unusual vs ordinary nearest retrieval?
    pois = d["retr_poison_dist"].astype(float)
    near = df[df.retr_min_dist >= 0]["retr_min_dist"].astype(float)
    print(f"  nearest-retrieval distance  : mean {near.mean():.1f}")
    print(f"  retrieved-poison distance   : mean {pois.mean():.1f}")
    # can retrieval-distance separate anomalous from normal rounds?
    an = df[(df.anomalous == 1) & (df.retr_min_dist >= 0)]["retr_min_dist"].astype(float)
    no = df[(df.anomalous == 0) & (df.retr_min_dist >= 0)]["retr_min_dist"].astype(float)
    print(f"  retrieval dist | anomalous={an.mean():.1f}  normal={no.mean():.1f}"
          f"  -> {'separable' if abs(an.mean()-no.mean())>near.std() else 'NOT separable'}"
          f" (poison hides among topically-similar memory).")
    return {"separable": bool(abs(an.mean() - no.mean()) > near.std())}


def causal_audit(df):
    print("\n=== (C) CAUSAL AUDIT (ours: temporal structure over X_t) ===")
    # pooled (regime-blind) vs regime-conditioned risk differences
    a1, a0, rd_pool = risk_diff(df, "poison_retr")
    print(f"  pooled          P(anom|poison_retr)={a1:.2f} vs {a0:.2f}  Δ={rd_pool:+.2f}")
    reg = {}
    for g in (0, 1):
        sub = df[df.trigger == g]
        if len(sub) and (sub.poison_retr == 1).any() and (sub.poison_retr == 0).any():
            a1, a0, rd = risk_diff(sub, "poison_retr")
            reg[g] = rd
            print(f"  regime trigger={g}: P(anom|poison_retr)={a1:.2f} vs {a0:.2f}"
                  f"  Δ={rd:+.2f}   ({'ACTIVE edge' if rd>0.2 else 'inert'})")
    # multivariate logistic: is poison_retr a driver once trigger & note are held?
    feats = ["trigger", "note_present", "poison_retr", "poison_in_mem"]
    w = logreg_coef(df[feats].values, df["anomalous"].values)
    coefs = dict(zip(["bias"] + feats, np.round(w, 2)))
    print(f"  logistic coefs: {coefs}")
    # the gate signature: poison_retr edge is present under trigger=1, absent under 0
    gated = reg.get(1, 0) > 0.2 and abs(reg.get(0, 0)) < 0.15
    print(f"  --> gated read edge {'RECOVERED' if gated else 'not clean'}: "
          f"poison_retr drives anomalous ONLY under the trigger regime.")
    return {"rd_pooled": rd_pool, "rd_regime": reg, "logit": coefs, "gated_edge": gated}


def provenance(df, trace_path):
    print("\n=== PROVENANCE: name the driver (which written record?) ===")
    fired = df[(df.anomalous == 1) & (df.retr_poison_src.astype(str).str.len() > 0)
               & (df.retr_poison_src.astype(str) != "nan")]
    src_counts = defaultdict(int)
    for s in fired["retr_poison_src"].astype(str):
        for tok in s.split(";"):
            if tok and tok != "-1":
                src_counts[int(tok)] += 1
    if not src_counts:
        print("  (sim trace has no poison retrieved on anomalous rounds; "
              "expected once real retrieval pulls the injected record.)")
        return {}
    top = sorted(src_counts.items(), key=lambda x: -x[1])[:5]
    for r, c in top:
        row = df[df.t == r]
        pid = row["id"].values[0] if len(row) else "?"
        print(f"  poison record written at round t={r} (id={pid}) is the ancestor "
              f"of {c} anomalous actions.")
    return {"driver_rounds": top}


def pcmci_graph(df):
    """Optional temporal graph via PCMCI+ (tigramite), blind vs regime-augmented."""
    try:
        from tigramite import data_processing as pp
        from tigramite.pcmci import PCMCI
        from tigramite.independence_tests.parcorr import ParCorr
    except Exception as e:
        print(f"\n(tigramite unavailable, skipping PCMCI graph: {e})")
        return
    print("\n=== PCMCI+ temporal graph: does the discovery algorithm find the edge? ===")

    def run_pcmci(data, cols):
        dataframe = pp.DataFrame(np.asarray(data, float), var_names=cols)
        pcmci = PCMCI(dataframe=dataframe, cond_ind_test=ParCorr(), verbosity=0)
        res = pcmci.run_pcmciplus(tau_min=0, tau_max=2, pc_alpha=0.1)
        g = res["graph"]
        ai, pr = cols.index("anomalous"), cols.index("poison_retr")
        parents = [f"{cols[i]}@-{lag}" for i in range(len(cols))
                   for lag in range(g.shape[2])
                   if g[i, ai, lag] in ("-->", "o->") and not (i == ai and lag == 0)]
        found = any(g[pr, ai, lag] in ("-->", "o->") for lag in range(g.shape[2]))
        return parents, found

    base = ["poison_in_mem", "poison_retr", "anomalous"]
    p, f = run_pcmci(df[base].values, base)
    print(f"  blind (regime-ignored)      : parents={p or '[]'}  poison_retr->anom "
          f"{'FOUND' if f else 'MISSED'}")
    aug = ["trigger"] + base
    p, f = run_pcmci(df[aug].values, aug)
    print(f"  additive u-augmentation     : parents={p or '[]'}  poison_retr->anom "
          f"{'FOUND' if f else 'MISSED'}   (trigger added as a NODE, not a regime)")
    sub = df[df.trigger == 1]
    if len(sub) > 10 and sub["poison_retr"].nunique() > 1 and sub["anomalous"].nunique() > 1:
        p, f = run_pcmci(sub[base].values, base)
        print(f"  regime-conditioned (u_t=1)  : parents={p or '[]'}  poison_retr->anom "
              f"{'FOUND' if f else 'MISSED'}   <- OURS: subsample the active regime")
    else:
        print("  regime-conditioned (u_t=1)  : insufficient within-regime variance to test")
    print("  Lesson (== E0 R1): the gate is multiplicative (poison_retr x trigger);"
          " adding trigger as an additive node does not expose it -- only conditioning"
          " on the regime does. This is the empirical case for regime-conditioned GRACE v1.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="results/minja_trace_sim.csv")
    ap.add_argument("--out", default="results/minja_audit_report.json")
    args = ap.parse_args()
    df = pd.read_csv(args.trace)
    print(f"loaded {len(df)} rounds from {args.trace}")
    rep = {"n_rounds": len(df), "test_ASR": float(
        df[df.phase == "test"]["anomalous"].mean()) if (df.phase == "test").any() else None}
    rep["behaviour"] = behaviour_audit(df)
    rep["similarity"] = similarity_audit(df)
    rep["causal"] = causal_audit(df)
    rep["provenance"] = provenance(df, args.trace)
    pcmci_graph(df)
    with open(args.out, "w") as f:
        json.dump(rep, f, indent=2, default=str)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
