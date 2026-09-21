"""Paper figures from the actor panels: EES and input tokens against history length.

Usage (from code/):  PYTHONPATH=. python3 -m hm3.figures --out ../results/real/hm3/figures
Produces scaling_travel.{pdf,png}, scaling_shopping32.{pdf,png}, substrate_travel_arena.{pdf,png}
and a JSON with every plotted number.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from hm3.panel_summary import load

COND_ORDER = [("native", "native\n(≈13)"), ("100", "100"), ("c100", "100\nconflicting"), ("500", "500")]
CAP = 16384
COLORS = {"ours": "#0F7B7E", "full": "#B5651D", "bm25_k16": "#5B5FA6", "bm25": "#9A8FBF", "amem": "#7A7A7A", "closed": "#0F7B7E"}
STYLE = {"closed": {"ls": (0, (3, 2))}}
LABELS = {"ours": "structure (graph_seg)", "full": "full history", "bm25_k16": "BM25 top-16", "bm25": "BM25 top-3",
          "amem": "A-Mem", "closed": "structure, closed set"}


def boot_ci(vals, n=4000, seed=0):
    rng = np.random.default_rng(seed)
    a = np.asarray(vals, float)
    if len(a) == 0:
        return (np.nan, np.nan)
    b = [rng.choice(a, len(a)).mean() for _ in range(n)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def series(panels, prompt, arm, conds):
    """Return dict cond -> (mean EES, lo, hi, median input tokens, n) for one arm/prompt at the 16k cap."""
    out = {}
    for cond, _ in conds:
        cells = panels.get((cond, prompt, CAP), {}).get(arm)
        if not cells:
            continue
        ees = [float(c["score"]["ees"]) for c in cells.values()]
        toks = [c.get("input_tokens", 0) for c in cells.values()]
        lo, hi = boot_ci(ees)
        out[cond] = (float(np.mean(ees)), lo, hi, float(np.median(toks)), len(ees))
    return out


def draw(ax_e, ax_t, panels, prompt, arms, conds, title):
    xs = np.arange(len(conds))
    for key, arm in arms:
        s = series(panels, prompt, arm, conds)
        if not s:
            continue
        idx = [i for i, (c, _) in enumerate(conds) if c in s]
        m = [s[conds[i][0]][0] for i in idx]
        lo = [s[conds[i][0]][1] for i in idx]
        hi = [s[conds[i][0]][2] for i in idx]
        tk = [s[conds[i][0]][3] for i in idx]
        col = COLORS[key]
        kw = dict(color=col, lw=1.8, marker="o", ms=4.5, label=LABELS[key], **STYLE.get(key, {}))
        ax_e.plot(xs[idx], m, **kw)
        ax_e.fill_between(xs[idx], lo, hi, color=col, alpha=0.12, lw=0)
        ax_t.plot(xs[idx], tk, **kw)
        if key in ("ours", "full"):
            ax_e.annotate(f"{m[-1]:.2f}", (xs[idx][-1], m[-1]), xytext=(5, 0), textcoords="offset points", fontsize=7.5, color=col, va="center")
    for ax in (ax_e, ax_t):
        ax.set_xticks(xs)
        ax.set_xticklabels([l for _, l in conds], fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#DDDDDD", lw=0.6)
        ax.set_axisbelow(True)
        ax.set_xlim(-0.3, len(conds) - 0.4)
    ax_e.set_ylim(0, 0.8)
    ax_e.set_title(title, fontsize=10, loc="left")
    ax_t.set_yscale("log")
    ax_t.set_ylim(1e3, 4e5)
    ax_t.set_xlabel("history length (records)", fontsize=8.5)


def figure(panels, prompts, arms, conds, titles, ylabel_e, out, name):
    n = len(prompts)
    fig, axes = plt.subplots(2, n, figsize=(3.1 * n + 0.6, 5.2), sharey="row")
    axes = np.atleast_2d(axes) if n > 1 else np.array([[axes[0]], [axes[1]]])
    numbers = {}
    for j, prompt in enumerate(prompts):
        draw(axes[0, j], axes[1, j], panels, prompt, arms, conds, titles[j])
        numbers[prompt] = {"/".join(arm): {c: dict(zip(("ees", "lo", "hi", "med_input_tokens", "n"), v)) for c, v in series(panels, prompt, arm, conds).items()} for _, arm in arms}
    axes[0, 0].set_ylabel(ylabel_e, fontsize=9)
    axes[1, 0].set_ylabel("median input tokens (log)", fontsize=9)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=min(len(labels), 5), fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    for ext in ("pdf", "png"):
        fig.savefig(out / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    json.dump(numbers, open(out / f"{name}.json", "w"), indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../results/real/hm3/figures")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
    # Travel and Shopping: same-serialization panel, structure vs full history, both prompts, 16k cap.
    arms = [("ours", ("graph_seg", "verbose")), ("full", ("full", "verbose")), ("closed", ("graph_closed", "verbose"))]
    figure(load("travel"), ["v1", "v2"], arms, COND_ORDER,
           ["Travel, terminating prompt (v1)", "Travel, ledger-first prompt (v2)"], "EES (64 episodes, 95% bootstrap CI)", out, "scaling_travel")
    figure(load("shopping32"), ["v1", "v2"], arms, [c for c in COND_ORDER if c[0] != "c100"],
           ["Shopping, terminating prompt (v1)", "Shopping, ledger-first prompt (v2)"], "EES (64 episodes, 95% bootstrap CI)", out, "scaling_shopping32")
    # Substrate: MemoryArena entities and memory classes.
    arms = [("ours", ("causal", "verbose")), ("full", ("long_context", "verbose")), ("bm25_k16", ("bm25_k16", "verbose")),
            ("bm25", ("bm25", "verbose")), ("amem", ("amem", "verbose"))]
    LABELS["full"] = "long-context (MemoryArena)"
    figure(load("travel_arena"), ["v1", "v2"], arms, COND_ORDER,
           ["Real entities, prompt v1", "Real entities, prompt v2"], "EES (64 episodes, 95% bootstrap CI)", out, "substrate_travel_arena")
    print("written to", out)


if __name__ == "__main__":
    main()
