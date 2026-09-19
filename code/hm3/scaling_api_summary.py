"""Summarise the history-scaling API shards: per-cell means and paired comparisons on
the episodes that every listed cell has completed within a condition.

Usage: python3 -m hm3.scaling_api_summary [--root results/real/hm3/scaling] [--domains travel shopping32]
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import numpy as np

CONDS = ["native", "100", "500"]
ANCHOR = ("full", "verbose")
PAIRS = [("graph_closed", "compact"), ("graph_closed", "verbose"), ("full", "compact"),
         ("bm25_k16", "compact"), ("recency_k16", "compact")]


def load(root, domain, cond):
    cells = {}
    for d in sorted(glob.glob(f"{root}/{domain}_{cond}/shards/*/")):
        lp = os.path.join(d, "llm_ledger.jsonl")
        if not os.path.exists(lp):
            continue
        for l in open(lp):
            r = json.loads(l)
            if r.get("event") == "cell" and not r.get("dry_run"):
                cells[r["cell"]] = r
    return list(cells.values())


def boot_ci(d, n_boot=4000, seed=0):
    d = np.asarray(d, dtype=float)
    if len(d) == 0:
        return None
    rng = np.random.default_rng(seed)
    b = [rng.choice(d, len(d)).mean() for _ in range(n_boot)]
    return float(d.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main(root, domains):
    out = []
    for D in domains:
        out.append(f"\n#### {D}\n")
        out.append("| condition | cell | n | EES | legal | affected F1 | input tok | output tok | est $/cell |")
        out.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        paired_rows = []
        for c in CONDS:
            rows = load(root, D, c)
            if not rows:
                continue
            by = {}
            for r in rows:
                by.setdefault((r["selection"], r["serialization"]), {})[r["episode"]] = r
            for k in sorted(by):
                v = list(by[k].values())
                n = len(v)
                out.append(f"| {c} | {k[0]}/{k[1]} | {n} | {np.mean([r['score']['ees'] for r in v]):.2f} | "
                           f"{np.mean([r['score']['legal'] for r in v]):.2f} | {np.mean([r['score']['affected_f1'] for r in v]):.2f} | "
                           f"{np.mean([r['input_tokens'] for r in v]):.0f} | {np.mean([r['output_tokens'] for r in v]):.0f} | "
                           f"{np.mean([r['cost'] for r in v]):.3f} |")
            anchor = by.get(ANCHOR, {})
            for k in PAIRS:
                if k not in by:
                    continue
                eps = sorted(set(anchor) & set(by[k]))
                if not eps:
                    continue
                d = [int(by[k][e]["score"]["ees"]) - int(anchor[e]["score"]["ees"]) for e in eps]
                ci = boot_ci(d)
                tok = np.mean([by[k][e]["input_tokens"] for e in eps]) / max(1e-9, np.mean([anchor[e]["input_tokens"] for e in eps]))
                w = sum(1 for x in d if x > 0); t = sum(1 for x in d if x == 0); l = sum(1 for x in d if x < 0)
                paired_rows.append(f"| {c} | {k[0]}/{k[1]} − full/verbose | {len(eps)} | {ci[0]:+.3f} [{ci[1]:+.3f}, {ci[2]:+.3f}] | {w}/{t}/{l} | {100 * (1 - tok):.0f}% |")
        out.append("")
        out.append("| condition | paired comparison (EES) | n episodes | mean [95% CI] | W/T/L | input reduction |")
        out.append("|---|---|---:|---|---|---:|")
        out.extend(paired_rows)
        # same-episode view across conditions for the two key cells
        common = None
        per = {}
        for c in CONDS:
            rows = load(root, D, c)
            per[c] = {(r["selection"], r["serialization"], r["episode"]): r for r in rows}
            eps = {r["episode"] for r in rows if (r["selection"], r["serialization"]) in (("graph_closed", "compact"), ANCHOR)}
            eps_both = {e for e in eps if ("graph_closed", "compact", e) in per[c] and (ANCHOR[0], ANCHOR[1], e) in per[c]}
            common = eps_both if common is None else common & eps_both
        if common:
            out.append("")
            out.append(f"Same {len(common)} episodes completed in all conditions (graph_closed/compact and full/verbose):")
            out.append("")
            out.append("| condition | graph_closed/compact EES | full/verbose EES | graph input tok | full input tok |")
            out.append("|---|---:|---:|---:|---:|")
            for c in CONDS:
                g = [per[c][("graph_closed", "compact", e)] for e in sorted(common)]
                f = [per[c][(ANCHOR[0], ANCHOR[1], e)] for e in sorted(common)]
                out.append(f"| {c} | {np.mean([r['score']['ees'] for r in g]):.2f} | {np.mean([r['score']['ees'] for r in f]):.2f} | "
                           f"{np.mean([r['input_tokens'] for r in g]):.0f} | {np.mean([r['input_tokens'] for r in f]):.0f} |")
    print("\n".join(out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="results/real/hm3/scaling")
    ap.add_argument("--domains", nargs="+", default=["travel", "shopping32"])
    a = ap.parse_args()
    main(a.root, a.domains)
