"""P3 — when does the pooled audit go blind? A trigger-prevalence sweep.

Motivation (honest negative from the first run): on a trace where 'food' rounds
are ~2/3 of traffic, REGIME-BLIND discovery already finds poison_retr->anomalous.
E0's blindness result does NOT automatically transfer. But the realistic sleeper
threat model is precisely the RARE-trigger one: the attacker wants the trigger to
fire seldom so the behaviour looks clean. So the question is empirical:

    as the trigger becomes rare, at what prevalence does regime-blind discovery
    lose the edge, and does regime-conditioned discovery still recover it?

We sweep benign (non-trigger) filler against a fixed injection budget, over
several seeds, and score four estimators per trace:
  pooled_rd     : risk difference P(anom|poison_retr) - P(anom|~poison_retr)
  pooled_logit  : logistic coef on poison_retr, trigger/note/held (regime as a NODE)
  regime_rd     : same risk difference computed WITHIN the trigger=1 subsample
  pcmci_blind / pcmci_regime : PCMCI+ edge presence, pooled vs regime-subsampled

"Detected" = the estimator both (a) puts poison_retr above threshold and (b) does
not attribute the effect solely to the trigger. Everything is CPU-only, no API.

Usage: python3 code/minja_dilution_sweep.py
"""
from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

from minja_causal_audit import run as run_trace
from minja_causal_analysis import logreg_coef, risk_diff


class Args:
    """Plain arg holder matching minja_causal_audit.run()'s expectations."""
    def __init__(self, **kw):
        self.backend = "sim"
        self.model = "gpt-4o"
        self.minja_qa_dir = kw.pop("minja_qa_dir")
        self.file_name = "nutrition_test"
        self.num_templates = 8
        self.num_test = 12
        self.num_pre = 12
        self.num_benign = 30
        self.extra_benign_subjects = 0
        self.n_shots = 3
        self.seed = 42
        self.out = "results/_sweep_tmp.csv"
        self.verbose = False
        self.max_tokens = 6000
        self.__dict__.update(kw)


def pcmci_edge(df, cols=("poison_in_mem", "poison_retr", "anomalous"), alpha=0.05):
    try:
        from tigramite import data_processing as pp
        from tigramite.pcmci import PCMCI
        from tigramite.independence_tests.parcorr import ParCorr
    except Exception:
        return None
    cols = list(cols)
    sub = df[cols].astype(float)
    if any(sub[c].nunique() < 2 for c in cols):
        return False
    dataframe = pp.DataFrame(sub.values, var_names=cols)
    pcmci = PCMCI(dataframe=dataframe, cond_ind_test=ParCorr(), verbosity=0)
    with redirect_stdout(io.StringIO()):
        res = pcmci.run_pcmciplus(tau_min=0, tau_max=2, pc_alpha=alpha)
    g = res["graph"]
    ai, pr = cols.index("anomalous"), cols.index("poison_retr")
    return bool(any(g[pr, ai, lag] in ("-->", "o->") for lag in range(g.shape[2])))


def score_trace(df):
    out = {}
    out["n"] = len(df)
    out["trigger_prev"] = float(df["trigger"].mean())
    _, _, out["pooled_rd"] = risk_diff(df, "poison_retr")
    feats = ["trigger", "note_present", "poison_retr", "poison_in_mem"]
    w = logreg_coef(df[feats].values, df["anomalous"].values)
    out["pooled_logit_poison"] = float(w[1 + feats.index("poison_retr")])
    out["pooled_logit_trigger"] = float(w[1 + feats.index("trigger")])
    sub = df[df.trigger == 1]
    if len(sub) > 5 and sub["poison_retr"].nunique() > 1:
        _, _, out["regime_rd"] = risk_diff(sub, "poison_retr")
    else:
        out["regime_rd"] = float("nan")
    out["pcmci_blind"] = pcmci_edge(df)
    out["pcmci_regime"] = pcmci_edge(sub) if len(sub) > 15 else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minja_qa_dir", default=None)
    ap.add_argument("--benign", type=int, nargs="+",
                    default=[10, 30, 80, 150, 300, 600, 1200])
    ap.add_argument("--extra_benign_subjects", type=int, default=40,
                    help="widen benign pool so low trigger prevalence is reachable")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--out", default="results/minja_dilution_sweep.csv")
    a = ap.parse_args()
    kw = {}
    if a.minja_qa_dir:
        kw["minja_qa_dir"] = a.minja_qa_dir
    else:
        from minja_causal_audit import DEFAULT_QA_DIR
        kw["minja_qa_dir"] = DEFAULT_QA_DIR

    rows = []
    for nb in a.benign:
        for s in a.seeds:
            args = Args(num_benign=nb, seed=s,
                        extra_benign_subjects=a.extra_benign_subjects, **kw)
            with redirect_stdout(io.StringIO()):
                log = run_trace(args)
            df = pd.DataFrame(log)
            r = {"num_benign": nb, "seed": s, **score_trace(df)}
            rows.append(r)
        sel = [r for r in rows if r["num_benign"] == nb]
        print(f"benign={nb:4d}  trig_prev={np.mean([r['trigger_prev'] for r in sel]):.2f}  "
              f"pooled_rd={np.mean([r['pooled_rd'] for r in sel]):+.2f}  "
              f"regime_rd={np.nanmean([r['regime_rd'] for r in sel]):+.2f}  "
              f"logit_poison={np.mean([r['pooled_logit_poison'] for r in sel]):+.2f}  "
              f"pcmci_blind={np.mean([bool(r['pcmci_blind']) for r in sel]):.1f}  "
              f"pcmci_regime={np.mean([bool(r['pcmci_regime']) for r in sel]):.1f}")

    out = pd.DataFrame(rows)
    out.to_csv(a.out, index=False)
    print(f"\nwrote {a.out}")

    print("\n=== summary: detection vs trigger prevalence ===")
    g = out.groupby("num_benign").agg(
        trigger_prev=("trigger_prev", "mean"),
        pooled_rd=("pooled_rd", "mean"),
        regime_rd=("regime_rd", "mean"),
        pcmci_blind=("pcmci_blind", lambda s: float(np.mean([bool(x) for x in s]))),
        pcmci_regime=("pcmci_regime", lambda s: float(np.mean([bool(x) for x in s]))),
    )
    print(g.round(3).to_string())


if __name__ == "__main__":
    main()
