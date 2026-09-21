#!/usr/bin/env python3
"""Figures for the P2 block rebuilt in the P3 slide style (2026-09-03, second review):
one dominant diagram per slide, noun phrases and short labels inside the figure, the
explanation lives in one or two sentences below the figure (deck script: revise_p2_0903.py).

p2_problem.png       problem: past interactions -> memory (many cells) -> query -> agent; structure unknown
p2_pipeline.png      setting 1: trajectories -> GRACE -> learned slot graph -> selection -> MemoryArena plug-in
p2_cards.png         result 1: three comparison cards, frozen criterion line
p2_audit.png         analysis: the travel query already names the memory cell (lookup mask rate 1.0)
p2_hm3.png           setting 2: hidden dependency chain, history, exact repair, four environments
p2_hm3_results.png   result 2: four methods x four environments, fresh seeds

Sources: results/real/travel_learned_graph.json (slot graph), results/real/p2_compact_v3/
round_summary.json via docs/progress-report-2026-09-03.md section 4.2 (cards),
results/real/hm3/round2/det_test2.json (fresh seeds 20-22).
"""
import json
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIG = os.path.join(HERE, "figs_0830")
BLUE = "#2a78d6"
LIGHTBLUE = (0.88, 0.92, 0.99)
GRAY = "0.3"
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": "black", "axes.labelcolor": "black",
    "xtick.color": "black", "ytick.color": "black",
    "text.color": "black", "font.size": 10,
    "font.family": "serif", "font.serif": ["Georgia", "DejaVu Serif"],
    "axes.spines.top": False, "axes.spines.right": False,
})


def canvas(w, h):
    f, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    return f, ax


def box(ax, x, y, w, h, txt="", fc="white", lw=1.3, fs=9.6, ls="-", ec="black", pad=0.010, **kw):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad={pad}", fc=fc, ec=ec, lw=lw, ls=ls))
    if txt:
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=fs, **kw)


def arrow(ax, x1, y1, x2, y2, lw=1.4, color="black", ls="-", ms=13, rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=ms, lw=lw,
                                 color=color, ls=ls, connectionstyle=f"arc3,rad={rad}"))


def lab(ax, x, y, txt, fs=8.6, color=GRAY, **kw):
    kw.setdefault("ha", "center"); kw.setdefault("va", "center")
    ax.text(x, y, txt, fontsize=fs, color=color, style="italic", **kw)


def save(f, name):
    f.tight_layout(pad=0.2)
    p = os.path.join(FIG, name); f.savefig(p, dpi=200, bbox_inches="tight"); plt.close(f); return p


def mini_grid(ax, x, y, cw, ch, rows, cols, fills=None, lw=0.6):
    """rows x cols grid of small cells; fills: {(row, col): color}, row 0 at the top."""
    fills = fills or {}
    for r in range(rows):
        for c in range(cols):
            ax.add_patch(plt.Rectangle((x + c * cw, y + (rows - 1 - r) * ch), cw, ch,
                                       fc=fills.get((r, c), "white"), ec="0.35", lw=lw))


# ---------------------------------------------------------------------------------------------
def fig_problem():
    f, ax = canvas(9.2, 2.45)
    cy, ch = 0.60, 0.30
    box(ax, 0.01, cy, 0.175, ch, "past interactions\nrounds t−k … t−1")
    arrow(ax, 0.188, cy + ch / 2, 0.232, cy + ch / 2)
    lab(ax, 0.21, cy + ch + 0.05, "write")
    # the memory: top aligned with the row, extends downwards to hold the cell grid
    mx, mw = 0.235, 0.255
    box(ax, mx, cy - 0.22, mw, ch + 0.22, "", fc="white")
    ax.text(mx + mw / 2, cy + ch - 0.06, "agent memory", ha="center", va="center", fontsize=9.6)
    lab(ax, mx + mw / 2, cy + ch - 0.12, "persons × days × slots", fs=7.8)
    fills = {(0, 5): BLUE, (1, 5): LIGHTBLUE, (2, 0): LIGHTBLUE, (2, 1): LIGHTBLUE}
    mini_grid(ax, mx + 0.025, cy - 0.195, 0.029, 0.062, 3, 7, fills)
    arrow(ax, mx + mw + 0.004, cy + ch / 2, 0.545, cy + ch / 2)
    lab(ax, 0.518, cy + ch + 0.05, "select — which cells?")
    box(ax, 0.55, cy, 0.175, ch, "current query", fc=LIGHTBLUE)
    arrow(ax, 0.728, cy + ch / 2, 0.772, cy + ch / 2)
    lab(ax, 0.75, cy + ch + 0.05, "act")
    box(ax, 0.775, cy, 0.215, ch, "agent\n→ plan / answer")
    # the unknown dependency structure, feeding the selection step
    nx = [0.62, 0.70, 0.78]; ny = 0.15
    for x in nx:
        ax.add_patch(Circle((x, ny), 0.028, fc="white", ec="black", lw=1.1))
    for a, b in ((0, 1), (1, 2)):
        arrow(ax, nx[a] + 0.03, ny, nx[b] - 0.03, ny, lw=1.1, ls=(0, (3, 2)), ms=10)
    arrow(ax, nx[0] + 0.015, ny + 0.03, nx[2] - 0.015, ny + 0.03, lw=1.1, ls=(0, (3, 2)), ms=10, rad=-0.5)
    ax.text(nx[1], ny + 0.14, "?", ha="center", va="center", fontsize=14, color=BLUE, fontweight="bold")
    lab(ax, 0.70, ny - 0.10, "dependency structure among memory cells: unknown", fs=8.4)
    arrow(ax, 0.60, ny + 0.10, 0.52, cy + ch / 2 - 0.03, lw=1.5, color=BLUE, ls=(0, (4, 2)), rad=0.3)
    ax.text(0.25, 0.20, "P2: learned dependency structure\n→ memory selection", fontsize=9.4, color=BLUE,
            ha="center", va="center")
    return save(f, "p2_problem.png")


# ---------------------------------------------------------------------------------------------
def fig_pipeline():
    f, ax = canvas(9.2, 3.2)
    ty, th = 0.75, 0.20
    xs = [0.01, 0.265, 0.52, 0.775]; bw = 0.215
    texts = ["interaction trajectories\n260 travel episodes", "GRACE\ntemporal causal discovery",
             "learned slot graph\n7 slots · lag ≤ 3", "memory selection\nancestors · last 3 writers"]
    fcs = ["white", LIGHTBLUE, "white", LIGHTBLUE]
    for x, t, fc in zip(xs, texts, fcs):
        box(ax, x, ty, bw, th, t, fc=fc, fs=9.4)
    for a, b in zip(xs[:-1], xs[1:]):
        arrow(ax, a + bw + 0.004, ty + th / 2, b - 0.004, ty + th / 2)
    lab(ax, xs[1] - 0.02, ty + th + 0.045, "in")
    lab(ax, xs[2] - 0.02, ty + th + 0.045, "out")
    # under the trajectories: three episodes as rows of cells over days
    for i in range(3):
        mini_grid(ax, 0.045, 0.59 - i * 0.075, 0.026, 0.06, 1, 5)
        ax.text(0.038, 0.62 - i * 0.075, f"ep {i + 1}", ha="right", va="center", fontsize=7.4, color=GRAY)
    lab(ax, 0.11, 0.695, "slots over days", fs=7.8)
    # under GRACE
    lab(ax, xs[1] + bw / 2, 0.60, "split by write / hold / read\nfit each regime\nkeep significant edges", fs=8.0)
    # under the slot graph: day d-1 -> day d
    gx0, gx1 = xs[2] + 0.045, xs[2] + 0.175
    names = ["breakfast", "lunch", "dinner", "hotel"]
    ys = [0.66, 0.595, 0.53, 0.465]
    lab(ax, gx0, 0.705, "day d−1", fs=7.6); lab(ax, gx1, 0.705, "day d", fs=7.6)
    for n, y in zip(names, ys):
        ax.text(gx0, y, n, ha="center", va="center", fontsize=7.8)
        ax.text(gx1, y, n, ha="center", va="center", fontsize=7.8)
        arrow(ax, gx0 + 0.032, y, gx1 - 0.032, y, lw=1.2, color=BLUE, ms=9)
    arrow(ax, gx0 + 0.032, ys[0] - 0.012, gx1 - 0.032, ys[1] + 0.012, lw=1.0, color=BLUE, ms=9)
    lab(ax, xs[2] + bw / 2, 0.415, "city · transport · attraction: constant", fs=7.4)
    # under memory selection: kept cells
    fills = {(0, 5): BLUE, (1, 5): LIGHTBLUE, (2, 5): LIGHTBLUE, (0, 0): LIGHTBLUE, (0, 1): LIGHTBLUE, (0, 3): LIGHTBLUE}
    mini_grid(ax, xs[3] + 0.02, 0.50, 0.025, 0.06, 3, 7, fills)
    lab(ax, xs[3] + 0.11, 0.695, "kept cells → compact text", fs=7.8)
    lab(ax, xs[3] + 0.11, 0.44, "query cell · its ancestors\n· one copy of constants", fs=7.4)
    # MemoryArena container
    cy0, ch0 = 0.0, 0.33
    box(ax, 0.01, cy0, 0.98, ch0, "", fc="white", lw=1.1, ls=(0, (5, 3)), ec="0.35", pad=0.006)
    ax.text(0.02, cy0 + ch0 - 0.035, "MemoryArena — existing agentic benchmark (travel), official scorer", fontsize=8.8,
            color="0.25", va="center", ha="left", fontweight="bold")
    iy, ih = cy0 + 0.09, 0.15
    box(ax, 0.06, iy, 0.26, ih, "memory system\n13 built-in + ours (plug-in)", fc=LIGHTBLUE, fs=9.0)
    box(ax, 0.40, iy, 0.22, ih, "ReAct agent\ndeepseek-v4-flash", fs=9.0)
    box(ax, 0.70, iy, 0.25, ih, "official scorer\nplan score PS · input tokens", fs=9.0)
    arrow(ax, 0.324, iy + ih / 2, 0.396, iy + ih / 2)
    arrow(ax, 0.624, iy + ih / 2, 0.696, iy + ih / 2)
    arrow(ax, 0.45, iy - 0.025, 0.20, iy - 0.025, lw=1.1, ms=10)
    lab(ax, 0.36, iy - 0.058, "writes each round (the only cross-round channel)", fs=7.6)
    # plug-in: elbow from the selection box, around the mini visuals, into the memory system
    sx, ey = xs[3] + bw + 0.004, 0.375
    ax.plot([sx, sx + 0.004], [ty + th / 2, ty + th / 2], color=BLUE, lw=1.6)
    ax.plot([sx + 0.004, sx + 0.004], [ty + th / 2, ey], color=BLUE, lw=1.6, ls=(0, (4, 2)))
    ax.plot([sx + 0.004, 0.19], [ey, ey], color=BLUE, lw=1.6, ls=(0, (4, 2)))
    arrow(ax, 0.19, ey, 0.19, iy + ih + 0.006, lw=1.6, color=BLUE, ls=(0, (4, 2)))
    ax.text(0.36, 0.40, "plug-in: registered at runtime", fontsize=8.6, color=BLUE, ha="center", va="center")
    return save(f, "p2_pipeline.png")


# ---------------------------------------------------------------------------------------------
def fig_cards():
    f, ax = canvas(9.2, 2.55)
    cards = [("learned graph · compact memory", "93.94% PS", "434k input tokens", LIGHTBLUE, 1.9),
             ("same memory · no graph", "95.45% PS", "718k input tokens", "white", 1.3),
             ("BM25 retrieval", "72.73% PS", "1.46M input tokens", "white", 1.3)]
    xs = [0.02, 0.36, 0.70]; w = 0.28; y0, h = 0.30, 0.64
    for (title, ps, tok, fc, lw), x in zip(cards, xs):
        box(ax, x, y0, w, h, "", fc=fc, lw=lw)
        ax.text(x + w / 2, y0 + h - 0.11, title, ha="center", va="center", fontsize=9.6)
        ax.text(x + w / 2, y0 + h / 2 + 0.01, ps, ha="center", va="center", fontsize=19, fontweight="bold",
                color=BLUE if fc != "white" else "black")
        ax.text(x + w / 2, y0 + 0.11, tok, ha="center", va="center", fontsize=10.5)
    ax.text(0.5, 0.135, "−39.55% input for −1.43 PS points  →  PASS", ha="center", va="center", fontsize=15,
            fontweight="bold", color=BLUE)
    lab(ax, 0.5, 0.02, "frozen criterion vs the no-graph arm: PS loss ≤ 5 points and input reduction ≥ 30% · held-out IDs 111–120", fs=8.4)
    return save(f, "p2_cards.png")


# ---------------------------------------------------------------------------------------------
def fig_audit():
    f, ax = canvas(9.2, 2.25)
    y0, h = 0.14, 0.72
    box(ax, 0.02, y0, 0.27, h, "", fc=LIGHTBLUE)
    ax.text(0.155, y0 + h - 0.11, "travel query, round t", ha="center", va="center", fontsize=9.6)
    ax.text(0.155, y0 + 0.30, "person = Alice\nday = 2\nslot = dinner\nnew value = …", ha="center", va="center", fontsize=10)
    arrow(ax, 0.30, y0 + h / 2, 0.40, y0 + h / 2, lw=2.4, ms=18)
    lab(ax, 0.35, y0 + h / 2 + 0.11, "lookup", fs=9.4)
    box(ax, 0.41, y0 + 0.18, 0.28, 0.36, "memory[Alice, day 2, dinner]", fs=10.4, lw=1.6)
    lab(ax, 0.55, y0 + 0.07, "the affected cell, read off the query", fs=8.4)
    ax.text(0.845, y0 + h / 2 + 0.12, "1.0", ha="center", va="center", fontsize=34, fontweight="bold", color=BLUE)
    ax.text(0.845, y0 + 0.12, "lookup sufficient-mask rate\n4 lookup baselines", ha="center", va="center", fontsize=9.4)
    return save(f, "p2_audit.png")


# ---------------------------------------------------------------------------------------------
def fig_hm3():
    f, ax = canvas(9.2, 3.05)
    box(ax, 0.01, 0.83, 0.33, 0.13, "query: “Flight F68 now arrives at 18:15”", fc=LIGHTBLUE, fs=9.4)
    cy, ch, bw = 0.55, 0.17, 0.135
    xs = [0.01, 0.205, 0.40, 0.595]
    names = ["Flight F68", "Transfer T3", "Stay H2", "Dinner"]
    for i, (x, n) in enumerate(zip(xs, names)):
        box(ax, x, cy, bw, ch, n, fc=LIGHTBLUE if i == 0 else "white")
    arrow(ax, 0.0775, 0.83, 0.0775, cy + ch + 0.006, lw=1.3, ms=11)
    qxs = []
    for a, b in zip(xs[:-1], xs[1:]):
        arrow(ax, a + bw + 0.004, cy + ch / 2, b - 0.004, cy + ch / 2, ls=(0, (3, 2)), lw=1.4)
        qx = (a + bw + b) / 2; qxs.append(qx)
        ax.add_patch(Circle((qx, cy - 0.075), 0.032, fc="white", ec=BLUE, lw=1.3))
        ax.text(qx, cy - 0.075, "?", ha="center", va="center", fontsize=11, color=BLUE, fontweight="bold")
    # affected memories -> exact repair
    box(ax, 0.79, cy, 0.20, ch, "affected memories", lw=1.3)
    arrow(ax, xs[3] + bw + 0.004, cy + ch / 2, 0.786, cy + ch / 2)
    box(ax, 0.79, 0.25, 0.20, ch, "exact repair", lw=1.8)
    arrow(ax, 0.89, cy - 0.004, 0.89, 0.25 + ch + 0.006)
    ax.text(0.79, 0.175, "×  miss one → fail", fontsize=8.8, va="center")
    ax.text(0.79, 0.115, "×  one extra write → fail", fontsize=8.8, va="center")
    # history feeds the hidden policies
    box(ax, 0.01, 0.09, 0.36, 0.25, "", fc="white")
    ax.text(0.19, 0.30, "history: earlier changes → outcomes", ha="center", va="center", fontsize=9.2)
    ax.text(0.19, 0.185, "Flight F21 delayed → transfer T1 rebooked\nStay H7 late → dinner shifted\n…", ha="center", va="center", fontsize=8.6)
    for qx in qxs:
        arrow(ax, 0.19, 0.345, qx, cy - 0.075 - 0.038, lw=1.3, color=BLUE, ls=(0, (4, 2)), ms=10)
    ax.text(0.55, 0.36, "recover the hidden policies", fontsize=9.2, color=BLUE, ha="center", va="center")
    lab(ax, 0.55, 0.29, "? = hidden policy: provider · hotel · restaurant", fs=8.2)
    # environments strip
    ax.add_patch(plt.Rectangle((0.0, -0.02), 1.0, 0.075, fc="0.94", ec="none"))
    for x, t in zip([0.125, 0.375, 0.625, 0.875], ["Travel · chain", "Shopping · compatibility", "Search · evidence", "Formal · proof DAG"]):
        ax.text(x, 0.0175, t, ha="center", va="center", fontsize=8.8)
    return save(f, "p2_hm3.png")


# ---------------------------------------------------------------------------------------------
def fig_hm3_results():
    r = json.load(open(os.path.join(ROOT, "results/real/hm3/round2/det_test2.json")))
    acc = defaultdict(lambda: defaultdict(list))
    for key, run_ in r["runs"].items():
        d = key.split("/")[0]
        for ln, res in run_["learners"].items():
            acc[d][ln].append(res["summary"]["ees"])
    doms = [("travel", "Travel"), ("shopping32", "Shopping v3.2"), ("search", "Search"), ("formal", "Formal")]
    black = ["flat", "flat_est", "gnn", "gnn_est"]
    best_black = {d: max((np.mean(acc[d][m]), m) for m in black) for d, _ in doms}
    print("best black box:", {d: (round(v, 3), m) for d, (v, m) in best_black.items()})
    groups = [("strongest black box", lambda m, d: best_black[d][0], "0.55"),
              ("program learner", lambda m, d: np.mean(m["program_reg"]), "#9fc3ee"),
              ("learned graph", lambda m, d: np.mean(m["graph"]), BLUE),
              ("oracle", lambda m, d: np.mean(m["rh_oracle"]), "black")]
    f, ax = plt.subplots(figsize=(9.2, 3.2))
    n, w = len(groups), 0.19
    xs = np.arange(len(doms))
    for gi, (gname, fn, col) in enumerate(groups):
        vals = [fn(acc[d], d) for d, _ in doms]
        pos = xs + (gi - (n - 1) / 2) * w
        ax.bar(pos, vals, w, label=gname, color=col, edgecolor="black", lw=0.5)
        for x, v in zip(pos, vals):
            ax.text(x, v + 0.02, f"{v:.2f}", ha="center", fontsize=8.6,
                    fontweight="bold" if gname == "learned graph" else "normal")
    ax.set_xticks(xs); ax.set_xticklabels([t for _, t in doms], fontsize=11)
    ax.set_xlim(-0.55, len(doms) - 0.45)
    ax.set_ylim(0, 1.12); ax.set_ylabel("executable exact success")
    ax.legend(ncol=4, fontsize=9.2, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.14), handlelength=1.4, columnspacing=2.0)
    f.tight_layout(pad=0.3)
    p = os.path.join(FIG, "p2_hm3_results.png"); f.savefig(p, dpi=200, bbox_inches="tight"); plt.close(f); return p


# ---------------------------------------------------------------------------------------------
def fig_llm_r34():
    """Appendix: API rounds 3-4 (about 64 episodes per cell), progress report section 4.9."""
    tasks = ["Travel", "Search"]
    full = [0.635, 0.597]
    g3, g4 = [0.219, 0.493], [0.444, 0.493]
    inp3, inp4 = ["−80.0%", "−59.4%"], ["−73.8%", "−69.5%"]
    diff3 = ["−0.41 [−0.54, −0.29]", "−0.10 [−0.25, +0.05]"]
    diff4 = ["−0.19 [−0.33, −0.05]", "−0.10 [−0.25, +0.05]"]
    f, ax = plt.subplots(figsize=(9.2, 2.9))
    xs = np.arange(len(tasks)); w = 0.22
    ax.bar(xs - w, full, w, color="black", label="full context / verbose")
    ax.bar(xs, g3, w, color="#9fc3ee", edgecolor="black", lw=0.5, label="graph selection / compact (round 3)")
    ax.bar(xs + w, g4, w, color=BLUE, edgecolor="black", lw=0.5, label="graph + witness closure / compact (round 4)")
    for x, v in zip(xs - w, full):
        ax.text(x, v + 0.02, f"{v:.2f}", ha="center", fontsize=8.8)
    for x, v, t in zip(xs, g3, inp3):
        ax.text(x, v + 0.02, f"{v:.2f}\n({t})", ha="center", fontsize=8.2)
    for x, v, t in zip(xs + w, g4, inp4):
        ax.text(x, v + 0.02, f"{v:.2f}\n({t})", ha="center", fontsize=8.2, fontweight="bold")
    for x, d3, d4 in zip(xs, diff3, diff4):
        ax.text(x, 0.90, f"paired vs full context · input change in ( )\nround 3 {d3}\nround 4 {d4}",
                ha="center", va="center", fontsize=7.6, color="0.3", style="italic")
    ax.set_xticks(xs); ax.set_xticklabels(tasks, fontsize=11)
    ax.set_xlim(-0.6, len(tasks) - 0.4); ax.set_ylim(0, 1.02)
    ax.set_ylabel("executable exact success\n(≈ 64 episodes per cell)")
    ax.legend(ncol=3, fontsize=8.6, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.16), handlelength=1.4, columnspacing=1.6)
    f.tight_layout(pad=0.3)
    p = os.path.join(FIG, "p2_llm_r34.png"); f.savefig(p, dpi=200, bbox_inches="tight"); plt.close(f); return p


if __name__ == "__main__":
    for fn in (fig_problem, fig_pipeline, fig_cards, fig_audit, fig_hm3, fig_hm3_results, fig_llm_r34):
        print(fn())
