#!/usr/bin/env python3
"""Figure for the P3-B round-3 slide: attacks per arm per seed block, and the paired
touched-query effect of g1 / g2 against the no-op arm with bootstrap intervals."""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIG = os.path.join(HERE, "figs_0830")
BLUE = "#2a78d6"
plt.rcParams.update({"figure.facecolor": "white", "axes.facecolor": "white", "text.color": "black",
                     "font.size": 10, "font.family": "serif", "font.serif": ["Georgia", "DejaVu Serif"],
                     "axes.spines.top": False, "axes.spines.right": False})
s = json.load(open(os.path.join(ROOT, "results/real/p3b_round3/minja_r3_summary.json")))
seeds = s["per_seed"]; J = s["judgement"]
r4p = os.path.join(ROOT, "results/real/p3b_round3/round4/minja_r4_summary.json")
s4 = json.load(open(r4p)) if os.path.exists(r4p) else None
f, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.0), gridspec_kw={"width_ratios": [1.6, 1]})
# left: round-3 seeds (12 rounds each) followed by round-4 three-seed blocks (36 rounds each)
groups = [(f"s{b['seed']}", b["attacks"]) for b in seeds]
if s4:
    groups += [("r4 " + "-".join(str(x) for x in blk["seeds"]), blk["attacks"]) for blk in s4["blocks"]]
x = np.arange(len(groups)); w = 0.2
for i, (arm, col) in enumerate([("ungated", "0.75"), ("noop", "0.5"), ("g1", BLUE), ("g2", "black")]):
    ax1.bar(x + (i - 1.5) * w, [g[1][arm] for g in groups], w, color=col, edgecolor="black", lw=0.4, label=arm)
ax1.set_xticks(x); ax1.set_xticklabels([g[0] for g in groups], rotation=35 if s4 else 0, ha="right" if s4 else "center", fontsize=8)
ax1.set_ylabel("attacks per block"); ax1.set_ylim(0, max(3.4, 1.3 * max(v for g in groups for v in g[1].values())))
ax1.legend(ncol=4, fontsize=8, frameon=False, loc="upper left")
ax1.set_title("held-out attacks per block and arm (round 3 seeds; round 4 three-seed blocks)", fontsize=9.0)
labels, means, lo, hi = [], [], [], []
for rnd, JJ in (("r3", J),) + ((("r4", s4["judgement"]),) if s4 else ()):
    for arm in ("g1", "g2"):
        b = JJ[arm]["touched_paired_noop_minus_arm"]
        if b["n"]:
            labels.append(f"{rnd} {arm} · touched (n={b['n']})"); means.append(b["mean"]); lo.append(b["ci_lo"]); hi.append(b["ci_hi"])
ys = np.arange(len(labels))
ax2.axvline(0, color="black", lw=1)
ax2.errorbar(means, ys, xerr=[np.array(means) - np.array(lo), np.array(hi) - np.array(means)], fmt="o", color=BLUE, ecolor="black", capsize=3, ms=6)
ax2.set_yticks(ys); ax2.set_yticklabels(labels, fontsize=8.4); ax2.invert_yaxis()
ax2.set_xlabel("noop − gated attacks per query\n(paired, 95% bootstrap)", fontsize=8.4)
ax2.set_title("effect against the no-op control", fontsize=9.5)
f.tight_layout(pad=0.4)
p = os.path.join(FIG, "p3b_r3.png"); f.savefig(p, dpi=200, bbox_inches="tight"); print(p)
