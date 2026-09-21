"""Figure: what the LLM's frontier and the executor's frontier are made of (record kind × object type), from the
majority-vote discovery sets on Travel seed 30.  Output: results/real/hm3/figures/frontier_composition.{pdf,png}"""
from __future__ import annotations
import json, glob, collections
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from .domains import get_domain
from .generate import generate_split
from .replay import record_features, reach_all

KINDS = [("intervention", "flight"), ("auto", "transfer"), ("txn", "transfer"), ("txn", "stay"), ("txn", "dinner"), ("txn", "activity"), ("txn", "bundle")]
LAB = {("intervention", "flight"): "flight\nintervention", ("auto", "transfer"): "transfer\nauto", ("txn", "transfer"): "transfer\ntxn",
       ("txn", "stay"): "stay\ntxn", ("txn", "dinner"): "dinner\ntxn", ("txn", "activity"): "activity\ntxn", ("txn", "bundle"): "bundle\ntxn"}


def main():
    d = get_domain("travel"); train = generate_split(d, 130, "train", 200); by = {ep.id: ep for ep in train}
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), sharey=True)
    for ax, P in zip(axes, ("v1", "v2")):
        rows = []
        for f in sorted(glob.glob(f"../results/real/hm3/replay_llm/travel_s30_{P}_k3_*/sets.jsonl")):
            rows += [json.loads(l) for l in open(f)]
        seen = set(); ok = []
        for r in rows:
            if r["full_ok"] and r["episode"] not in seen:
                seen.add(r["episode"]); ok.append(r)
        llm, ex = collections.Counter(), collections.Counter()
        for r in ok:
            ep = by[r["episode"]]; feats = record_features(d, ep, reach_all(ep))
            for rid in r["frontier"]: llm[(feats[rid]["kind"], feats[rid]["otype"])] += 1
            for rid in (r["executor_frontier"] or []): ex[(feats[rid]["kind"], feats[rid]["otype"])] += 1
        n = len(ok); x = np.arange(len(KINDS)); w = 0.38
        ax.bar(x - w / 2, [ex[k] / n for k in KINDS], w, color="#B5651D", label="executor frontier")
        ax.bar(x + w / 2, [llm[k] / n for k in KINDS], w, color="#0F7B7E", label=f"LLM frontier (prompt {P})")
        ax.set_xticks(x); ax.set_xticklabels([LAB[k] for k in KINDS], fontsize=7)
        ax.set_title(f"prompt {P}: {n} episodes, k = 3 votes", fontsize=9, loc="left")
        ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", color="#DDDDDD", lw=0.6); ax.set_axisbelow(True)
        ax.legend(fontsize=7, frameon=False)
    axes[0].set_ylabel("records per episode in the frontier", fontsize=8.5)
    fig.tight_layout()
    out = Path("../results/real/hm3/figures")
    for ext in ("pdf", "png"):
        fig.savefig(out / f"frontier_composition.{ext}", dpi=200, bbox_inches="tight")
    print("written")


if __name__ == "__main__":
    main()
