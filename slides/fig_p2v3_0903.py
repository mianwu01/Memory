#!/usr/bin/env python3
"""Figures for the P2 round-2 (Hidden Mechanism v3) slides, deck style of 8-30.pptx.

fig_v3_task     the v3 task: intervention -> stale? -> reads -> minimal non-idempotent
                transactions -> post-state + receipt; why a superset fails
fig_v3_methods  executable exact success on fresh test seeds 20-22, per method group
fig_v3_api      paired bootstrap of graph/compact - full/verbose, both API rounds
All numbers from results/real/hm3/round2/*.json and results/real/hm3/*.json.
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIG = os.path.join(HERE, "figs_0830")
BLUE = "#2a78d6"
LIGHTBLUE = (0.88, 0.92, 0.99)
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": "black", "axes.labelcolor": "black",
    "xtick.color": "black", "ytick.color": "black",
    "text.color": "black", "font.size": 10,
    "font.family": "serif", "font.serif": ["Georgia", "DejaVu Serif"],
    "axes.spines.top": False, "axes.spines.right": False,
})


def fig_v3_task():
    f, ax = plt.subplots(figsize=(9.2, 2.9))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    def box(x, y, w, h, txt, fc="white", lw=1.3, fs=9.2):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.010", fc=fc, ec="black", lw=lw))
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=fs)

    def arrow(x1, y1, x2, y2, lw=1.4, color="black", ls="-"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=13,
                                     lw=lw, color=color, ls=ls))

    cy, ch = 0.66, 0.26
    box(0.01, cy, 0.17, ch, "intervention\n“flight F68 now\narrives 18:15”", fc=LIGHTBLUE)
    arrow(0.182, cy + ch / 2, 0.218, cy + ch / 2)
    box(0.22, cy, 0.19, ch, "which memories\nare stale?\n(hidden mechanism)")
    arrow(0.412, cy + ch / 2, 0.448, cy + ch / 2)
    box(0.45, cy, 0.17, ch, "read the\nwitnesses in\nthe history")
    arrow(0.622, cy + ch / 2, 0.658, cy + ch / 2)
    box(0.66, cy, 0.33, ch, "minimal repair transactions\n{op, object, expected_revision, payload}", lw=1.7)
    ax.text(0.825, cy - 0.055, "each write: revision +1 · token −1 · fee · price lock lost",
            ha="center", va="top", fontsize=8.2, style="italic", color="0.3")
    ax.text(0.315, cy - 0.055, "provider auto-rebooks? hotel enforces cutoff?\nrestaurant shifts or cancels? bundle linked?",
            ha="center", va="top", fontsize=8.2, style="italic", color="0.3")

    y2, h2 = 0.06, 0.30
    box(0.01, y2, 0.30, h2, "Executable Exact Success\nall legal ∧ post-state = oracle\n∧ receipt = oracle", fc=LIGHTBLUE, fs=9.0)
    box(0.35, y2, 0.30, h2, "conservative superset\nrewrites an unaffected value\n→ receipt differs → fail", fs=9.0)
    box(0.69, y2, 0.30, h2, "lookup / kNN\nwrite the auto-updated transfer\n→ stale revision → illegal", fs=9.0)
    f.tight_layout(pad=0.2)
    p = os.path.join(FIG, "v3_task.png"); f.savefig(p, dpi=200, bbox_inches="tight"); plt.close(f); return p


def fig_v3_methods():
    from collections import defaultdict
    r = json.load(open(os.path.join(ROOT, "results/real/hm3/round2/det_test2.json")))
    acc = defaultdict(lambda: defaultdict(list))
    for key, run_ in r["runs"].items():
        d = key.split("/")[0]
        for ln, res in run_["learners"].items():
            acc[d][ln].append(res["summary"]["ees"])
    doms = [("travel", "Travel"), ("shopping32", "Shopping v3.2"), ("search", "Search"), ("formal", "Formal")]
    groups = [("best lookup", lambda m: max(np.mean(m["exact_kv"]), np.mean(m["source_union"]), np.mean(m["source_regime"]))),
              ("kNN", lambda m: np.mean(m["knn"])), ("superset", lambda m: np.mean(m["superset"])),
              ("GNN + estimates", lambda m: np.mean(m["gnn_est"])),
              ("program learner", lambda m: np.mean(m["program_reg"])),
              ("learned graph", lambda m: np.mean(m["graph"])),
              ("history-only oracle", lambda m: np.mean(m["rh_oracle"]))]
    f, ax = plt.subplots(figsize=(9.2, 3.0))
    n, w = len(groups), 0.11
    xs = np.arange(len(doms))
    colors = ["0.80", "0.68", "0.56", "0.42", "#9fc3ee", BLUE, "black"]
    for gi, (gname, fn) in enumerate(groups):
        vals = [fn(acc[d]) for d, _ in doms]
        ax.bar(xs + (gi - (n - 1) / 2) * w, vals, w, label=gname, color=colors[gi], edgecolor="black", lw=0.5)
        if gname in ("learned graph", "program learner"):
            other = [np.mean(acc[d]["graph" if gname == "program learner" else "program_reg"]) for d, _ in doms]
            for x, v, o in zip(xs + (gi - (n - 1) / 2) * w, vals, other):
                # stagger the two labels when the bars are within 0.05 of each other
                lift = 0.06 if (abs(v - o) < 0.05 and gname == "learned graph") else 0.02
                ax.text(x, v + lift, f"{v:.2f}", ha="center", fontsize=7.6)
    ax.set_xticks(xs); ax.set_xticklabels([lab for _, lab in doms])
    ax.set_ylim(0, 1.12); ax.set_ylabel("executable exact success")
    ax.axhline(0.5, color="0.6", lw=0.8, ls=(0, (3, 3)))
    ax.text(-0.42, 0.515, "chance-level\ncopying", fontsize=7.6, color="0.4", ha="left", va="bottom")
    ax.legend(ncol=4, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.16))
    f.tight_layout(pad=0.3)
    p = os.path.join(FIG, "v3_methods.png"); f.savefig(p, dpi=200, bbox_inches="tight"); plt.close(f); return p


def fig_v3_api():
    bs = json.load(open(os.path.join(ROOT, "results/real/hm3/round2/paired_bootstrap.json")))
    r3p = os.path.join(ROOT, "results/real/hm3/round3/paired_analysis.json")
    r3 = json.load(open(r3p)) if os.path.exists(r3p) else None
    r1 = json.load(open(os.path.join(ROOT, "results/real/hm3/llm_summary.json")))["cells"]
    r2 = json.load(open(os.path.join(ROOT, "results/real/hm3/round2/llm_summary.json")))["cells"]
    f, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.3, 3.1), gridspec_kw={"width_ratios": [1.35, 1]})
    labels, means, los, his, ys = [], [], [], [], []
    y = 0
    for d in ("travel", "search"):
        for rnd in ("round1", "round2", "pooled"):
            e = bs[f"{d}|graph/compact-full/verbose|{rnd}"]
            labels.append(f"{d.capitalize()} · {rnd}"); means.append(e["mean"]); los.append(e["ci_lo"]); his.append(e["ci_hi"]); ys.append(y)
            y += 1
        if r3 and r3[d]["main_judgement"]["paired"]["n"]:
            e = r3[d]["main_judgement"]["paired"]
            labels.append(f"{d.capitalize()} · round3 (n={e['n']})"); means.append(e["mean"]); los.append(e["ci_lo"]); his.append(e["ci_hi"]); ys.append(y)
            y += 1
        r4p = os.path.join(ROOT, "results/real/hm3/round4/paired_analysis.json")
        if os.path.exists(r4p):
            e = json.load(open(r4p))[d]["graph_closed/compact - full/verbose(r3)"]
            if e["n"]:
                labels.append(f"{d.capitalize()} · round4, closed (n={e['n']})"); means.append(e["mean"]); los.append(e["ci_lo"]); his.append(e["ci_hi"]); ys.append(y)
                y += 1
        y += 0.6
    ys = np.array(ys)
    ax1.axvline(0, color="black", lw=1.0)
    ax1.axvspan(-0.10, 0.6, color=LIGHTBLUE, alpha=0.7, lw=0)
    ax1.errorbar(means, ys, xerr=[np.array(means) - np.array(los), np.array(his) - np.array(means)],
                 fmt="o", color=BLUE, ecolor="black", capsize=3, ms=6)
    ax1.set_yticks(ys); ax1.set_yticklabels(labels, fontsize=8.6); ax1.invert_yaxis()
    ax1.set_xlim(-0.55, 0.55); ax1.set_xlabel("EES: graph/compact − full/verbose (paired, 95% bootstrap)", fontsize=8.8)
    ax1.text(0.33, ys[2] + 0.55, "pre-registered\nnon-inferiority zone", fontsize=7.8, color="0.35", ha="center", va="center")
    ax1.set_title("selection effect, graph/compact − full/verbose", fontsize=9.5)
    cells = ["full/verbose", "full/compact", "graph/verbose", "graph/compact", "exact/compact"]
    x = np.arange(len(cells)); w = 0.2
    for i, (d, src, col) in enumerate([("travel", r1, "0.75"), ("travel", r2, BLUE), ("search", r1, "0.45"), ("search", r2, "black")]):
        vals = [src[f"{d}/{c}"]["input_tokens"] / 20 / 1000 for c in cells]
        ax2.bar(x + (i - 1.5) * w, vals, w, color=col, edgecolor="black", lw=0.4,
                label=f"{d} · round {'1' if src is r1 else '2'}")
    ax2.set_xticks(x); ax2.set_xticklabels(cells, rotation=25, ha="right", fontsize=8)
    ax2.set_ylabel("input tokens per episode (k)", fontsize=8.8)
    ax2.legend(fontsize=7.4, frameon=False)
    ax2.set_title("input: graph/compact is 68–80% below full/verbose", fontsize=9.5)
    f.tight_layout(pad=0.4)
    p = os.path.join(FIG, "v3_api.png"); f.savefig(p, dpi=200, bbox_inches="tight"); plt.close(f); return p


if __name__ == "__main__":
    for fn in (fig_v3_task, fig_v3_methods, fig_v3_api):
        print(fn())
