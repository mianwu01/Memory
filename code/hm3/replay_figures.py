"""Figures for the read-intervention method: (a) replays and frontier size vs history length (E1b);
(b) replays to localise the causing record by candidate order (E3).
Usage (from code/): PYTHONPATH=. python3 -m hm3.replay_figures"""
from __future__ import annotations
import json, glob
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.ticker
import matplotlib.pyplot as plt
import numpy as np

OUT = Path("../results/real/hm3/figures")
C = {"travel": "#0F7B7E", "shopping32": "#B5651D"}
ORD = {"structural": "structural trace", "reads_then_history": "read set, then history", "bm25": "BM25 vs anomaly (= history order)"}


def fig_length():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.4, 2.7))
    for dom in ("travel", "shopping32"):
        d = json.load(open(f"../results/development/hm3/replay/length_{dom}.json"))
        xs = {"native": None, "100:abcd": 100, "500:abcd": 500}
        pts = {}
        for k, v in d.items():
            L = k.split("/")[1]
            n = v["n_records"] if L == "native" else xs[L]
            pts.setdefault(L, []).append((n, v["calls"], v["calls_p90"], v["frontier"]))
        Ls = ["native", "100:abcd", "500:abcd"]
        n = [np.mean([p[0] for p in pts[L]]) for L in Ls]
        calls = [np.mean([p[1] for p in pts[L]]) for L in Ls]
        p90 = [np.mean([p[2] for p in pts[L]]) for L in Ls]
        fr = [np.mean([p[3] for p in pts[L]]) for L in Ls]
        lab = "Travel" if dom == "travel" else "Shopping"
        a1.plot(n, calls, "o-", color=C[dom], lw=1.8, ms=4.5, label=f"{lab}, mean")
        a1.plot(n, p90, "o--", color=C[dom], lw=1.2, ms=3.5, label=f"{lab}, p90")
        a2.plot(n, fr, "o-", color=C[dom], lw=1.8, ms=4.5, label=lab)
    for ax in (a1, a2):
        ax.set_xscale("log"); ax.set_xlabel("history length n (records)", fontsize=8.5)
        ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", color="#DDDDDD", lw=0.6); ax.set_axisbelow(True)
        ax.set_xticks([18, 100, 500]); ax.set_xticklabels(["18", "100", "500"], fontsize=8)
        ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator()); ax.set_xlim(12, 800)
    a1.set_ylabel("replays per episode", fontsize=9); a1.set_ylim(0, 55); a1.legend(fontsize=7, frameon=False)
    a2.set_ylabel("frontier size (records)", fontsize=9); a2.set_ylim(0, 4); a2.legend(fontsize=7, frameon=False)
    a1.set_title("replays grow with log n", fontsize=9.5, loc="left"); a2.set_title("the frontier does not", fontsize=9.5, loc="left")
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"replay_length.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_localise():
    files = {"native": "../results/real/hm3/replay/localise_travel_native.json", "500": "../results/real/hm3/replay/localise_travel_500abcd.json"}
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.7), sharey=True)
    for ax, (cond, f) in zip(axes, files.items()):
        try:
            d = json.load(open(f))
        except FileNotFoundError:
            ax.set_title(f"{cond}: pending", fontsize=9.5, loc="left"); continue
        rows = [r for v in d.values() for r in v["rows"]]
        if not all(all(r[o]["hit"] for r in rows) for o in ("structural", "bm25")):
            pass
        bins = np.arange(0.5, 11.5, 1)
        for i, (o, lab) in enumerate(ORD.items()):
            calls = [min(r[o]["calls"], 10) for r in rows]
            h, _ = np.histogram(calls, bins=bins)
            ax.plot(np.arange(1, 11), h / len(rows), "o-", lw=1.6, ms=3.5, label=lab, color=["#0F7B7E", "#5B5FA6", "#B5651D", "#7A7A7A"][i])
        ax.set_title(f"{cond} history, {len(rows)} incidents", fontsize=9.5, loc="left")
        ax.set_xlabel("replays to localise the causing record", fontsize=8.5)
        ax.set_xticks(range(1, 11)); ax.set_xticklabels([str(i) if i < 10 else "10+" for i in range(1, 11)], fontsize=8)
        ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", color="#DDDDDD", lw=0.6); ax.set_axisbelow(True)
    axes[0].set_ylabel("fraction of incidents", fontsize=9); axes[0].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"replay_localise.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    fig_length(); fig_localise(); print("written", OUT)
