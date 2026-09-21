"""Case figure for the provenance section: one Travel incident (travel-s30-test-000, test seed 30)
drawn from docs/hm3-case-travel-s30-2026-09-19.md.  Three panels: the history as write events with the
required witnesses and the corrupted record marked; the mechanism path from the intervention to the
anomalous action with the hidden keys and the witnesses that reveal them; the backward trace ranking and
the clean-replacement test.  Colours: categorical slots 1-3 of the reference palette for record kinds,
status good/critical for the replacement outcomes (always with a text mark), text in ink tokens.

Usage: PYTHONPATH=<pylib>:. python3 -m hm3.case_figure --out ../results/real/hm3/provenance/figures/case_travel_s30_test000
"""
from __future__ import annotations

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK, INK2, MUTED, SURF, GRID = "#0b0b0b", "#52514e", "#8a8984", "#fcfcfb", "#e6e5e1"
KIND = {"intervention": "#2a78d6", "auto": "#eb6834", "txn": "#1baf7a"}   # categorical slots 1-3
GOOD, CRIT = "#0ca30c", "#d03b3b"

HISTORY = [  # rid, seg, kind, object, short delta
    ("h0", 0, "intervention", "F51", "arrival 825→1200"), ("h1", 0, "txn", "T27", "pickup 840→1225"),
    ("h2", 0, "txn", "S70", "checkin 890→1275"), ("h3", 0, "txn", "D84", "cancelled"), ("h4", 0, "txn", "B52", "rebooked"),
    ("h5", 1, "intervention", "F42", "arrival 615→1170"), ("h6", 1, "txn", "T55", "pickup 645→1195"),
    ("h7", 1, "txn", "S22", "checkin 685→1235, late 0→1"), ("h8", 1, "txn", "D55", "cancelled"), ("h9", 1, "txn", "B97", "rebooked"),
    ("h10", 2, "intervention", "F80", "arrival 900→990"), ("h11", 2, "auto", "T21", "pickup 965→1010"), ("h12", 2, "txn", "S57", "checkin 1015→1060"),
    ("h13", 3, "intervention", "F14", "arrival 1095→1215"), ("h14", 3, "auto", "T43", "pickup 1140→1235"),
    ("h15", 3, "txn", "S93", "checkin 1180→1275"), ("h16", 3, "txn", "D40", "cancelled"), ("h17", 3, "txn", "B62", "rebooked"),
    ("h18", 4, "intervention", "F70", "arrival 630→870"), ("h19", 4, "auto", "T24", "pickup 690→890"), ("h20", 4, "txn", "S90", "checkin 710→910"),
    ("h21", 5, "intervention", "F13", "arrival 1140→1080"), ("h22", 5, "auto", "T64", "pickup 1200→1105"), ("h23", 5, "txn", "S86", "checkin 1220→1125"),
    ("h24", 6, "intervention", "F80", "arrival 990→1290"), ("h25", 6, "auto", "T21", "pickup 1010→1310"),
    ("h26", 6, "txn", "S57", "checkin 1060→1360"), ("h27", 6, "txn", "D81", "cancelled"),
]
REQUIRED = {"h5", "h7", "h24", "h25"}
CORRUPTED = "h25"
RANKED = ["h25", "h24", "h7", "h5", "h27"]
BASELINES = [("recency", "h27, h26, h25", "3"), ("BM25 on anomaly", "h13, h14, h5", "—"), ("source heuristic", "h15, h14, h13", "—")]
REPLACE = [("top-1", "h25", True), ("top-3", "h25 h24 h7", True), ("random-1", "h27", False),
           ("random-3", "h13 h27 h5", False), ("similar non-ancestor", "h26", False), ("most recent", "h27", False)]


def box(ax, x, y, w, h, text, fc=SURF, ec=INK2, fs=7.2, bold=False, color=INK, lw=0.9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.012", fc=fc, ec=ec, lw=lw))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=color, fontweight="bold" if bold else "normal", linespacing=1.25)


def arrow(ax, p, q, color=INK2, ls="-", lw=1.1):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=9, color=color, lw=lw, linestyle=ls, shrinkA=2, shrinkB=2))


def panel_history(ax):
    ax.set_title("A  History: write events as outcome records", loc="left", fontsize=9, color=INK, pad=6)
    n = len(HISTORY)
    for i, (rid, seg, kind, obj, delta) in enumerate(HISTORY):
        y = n - 1 - i
        if rid in REQUIRED:
            ax.add_patch(plt.Rectangle((-0.02, y - 0.45), 1.04, 0.9, fc="#f0efec", ec="none", zorder=0))
        ax.plot(0.03, y, marker="o", ms=5.5, color=KIND[kind], mec=SURF, mew=0.8, zorder=3)
        w = "bold" if rid in REQUIRED else "normal"
        ax.text(0.075, y, rid, fontsize=6.6, va="center", color=INK, fontweight=w)
        ax.text(0.17, y, f"seg {seg}", fontsize=6.2, va="center", color=MUTED)
        ax.text(0.30, y, obj, fontsize=6.6, va="center", color=INK, fontweight=w)
        ax.text(0.41, y, delta if rid != CORRUPTED else "pickup 1010→1310", fontsize=6.4, va="center", color=INK2)
        if rid == CORRUPTED:
            ax.text(0.82, y, "✕ corrupted: auto → txn", fontsize=6.4, va="center", ha="left", color=CRIT, fontweight="bold")
    ax.set_xlim(-0.02, 1.22)
    ax.set_ylim(-2.2, n - 0.3)
    ax.axis("off")
    for k, (kind, c) in enumerate(KIND.items()):
        ax.plot(0.03 + 0.40 * k, -1.0, marker="o", ms=5.5, color=c, mec=SURF, mew=0.8, clip_on=False)
        ax.text(0.075 + 0.40 * k, -1.0, {"intervention": "user intervention", "auto": "environment (auto)", "txn": "manual repair (txn)"}[kind], fontsize=6.4, va="center", color=INK2)
    ax.text(0.03, -1.9, "shaded rows: the witnesses the correct repair depends on", fontsize=6.4, ha="left", va="center", color=MUTED)


def panel_mechanism(ax):
    ax.set_title("B  Dependency path from the intervention to the repair", loc="left", fontsize=9, color=INK, pad=6)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    fs = 6.0
    # column 1: the object chain
    ax.text(0.16, 0.96, "objects", fontsize=6.4, ha="center", color=MUTED)
    box(ax, 0.02, 0.79, 0.28, 0.12, "F14  flight\narrival 1215 → 1410", fc="#e9f1fb", ec=KIND["intervention"], bold=True, fs=fs)
    box(ax, 0.02, 0.52, 0.28, 0.12, "T43  transfer\nprovider P51 · ride 40", ec=INK2, fs=fs)
    box(ax, 0.02, 0.25, 0.28, 0.12, "S93  stay\nhotel H82 · cutoff 1290", ec=INK2, fs=fs)
    box(ax, 0.02, 0.04, 0.28, 0.09, "D40 cancelled · A78 unchanged", ec=GRID, color=MUTED, fs=5.8)
    arrow(ax, (0.16, 0.79), (0.16, 0.64)); arrow(ax, (0.16, 0.52), (0.16, 0.37)); arrow(ax, (0.16, 0.25), (0.16, 0.13), color=MUTED, ls=":")
    # column 2: hidden keys and their witnesses
    ax.text(0.51, 0.96, "hidden policies (from history)", fontsize=6.4, ha="center", color=MUTED)
    box(ax, 0.37, 0.50, 0.28, 0.16, "auto_rebook[P51] = 1\nbuffer[P51] = 20\nwitnesses h24, h25", fc="#fdf0ea", ec=KIND["auto"], fs=fs)
    box(ax, 0.37, 0.25, 0.28, 0.12, "enforce_late[H82] = 1\nwitnesses h5, h7", fc="#e8f7f1", ec=KIND["txn"], fs=fs)
    arrow(ax, (0.37, 0.58), (0.30, 0.58), color=KIND["auto"]); arrow(ax, (0.37, 0.31), (0.30, 0.31), color=KIND["txn"])
    # column 3: outcomes
    ax.text(0.855, 0.96, "repair", fontsize=6.4, ha="center", color=MUTED)
    box(ax, 0.69, 0.50, 0.30, 0.16, "clean history\nT43 updates itself\ntxn S93: checkin 1470, late 1", fc="#eef8ee", ec=GOOD, fs=5.8)
    box(ax, 0.69, 0.19, 0.30, 0.21, "h25 read as txn\n→ auto_rebook[P51] = 0\n→ ✕ manual write to T43\n(stale revision, illegal)", fc="#fbeaea", ec=CRIT, fs=fs)
    arrow(ax, (0.65, 0.58), (0.69, 0.58), color=GOOD); arrow(ax, (0.65, 0.31), (0.69, 0.31), color=CRIT)
    ax.text(0.5, 0.0, "the auditor is given only the anomalous object T43", fontsize=6.4, ha="center", color=MUTED)


def panel_trace(ax):
    ax.set_title("C  Backward trace through the same graph, then clean replacement", loc="left", fontsize=9, color=INK, pad=6)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.0, 0.93, "trace ranking (leave-one-record-out)", fontsize=7, color=INK2)
    for i, rid in enumerate(RANKED):
        y = 0.84 - i * 0.075
        c = CRIT if rid == CORRUPTED else INK2
        ax.text(0.02, y, f"{i + 1}", fontsize=7, color=MUTED, va="center")
        ax.text(0.08, y, rid, fontsize=7.2, color=c, fontweight="bold" if rid == CORRUPTED else "normal", va="center")
        if rid == CORRUPTED:
            ax.text(0.16, y, "← corrupted record", fontsize=6.6, color=CRIT, va="center")
    ax.text(0.0, 0.44, "baselines, rank of the corrupted record", fontsize=7, color=INK2)
    for i, (name, lst, rank) in enumerate(BASELINES):
        y = 0.36 - i * 0.07
        ax.text(0.02, y, name, fontsize=6.6, color=INK, va="center")
        ax.text(0.30, y, lst, fontsize=6.4, color=MUTED, va="center")
        ax.text(0.58, y, rank, fontsize=6.8, color=INK, va="center", ha="center")
    ax.text(0.62, 0.93, "replace with clean versions, re-run", fontsize=7, color=INK2)
    for i, (name, rids, ok) in enumerate(REPLACE):
        y = 0.84 - i * 0.075
        ax.text(0.63, y, name, fontsize=6.6, color=INK, va="center")
        ax.text(0.63, y - 0.032, rids, fontsize=5.8, color=MUTED, va="center")
        ax.text(1.0, y - 0.032, ("✓ restored" if ok else "✕ still wrong"), fontsize=6.6, color=(GOOD if ok else CRIT), va="center", ha="right", fontweight="bold")
    ax.plot([0.60, 0.60], [0.36, 0.96], color=GRID, lw=0.8)
    ax.text(0.62, 0.30, "across test seeds 30/31/32 (142 incidents):", fontsize=6.6, color=INK2)
    ax.text(0.62, 0.23, "corrupted record in top-3: 0.98–1.00", fontsize=6.6, color=INK)
    ax.text(0.62, 0.16, "top-3 replaced → execution restored: 0.98–1.00", fontsize=6.6, color=INK)
    ax.text(0.62, 0.09, "random-3 / most similar / most recent: 0.00", fontsize=6.6, color=INK)
    ax.text(0.62, 0.02, "same graph artifact as forward selection (SHA e1b6c6be)", fontsize=6.2, color=MUTED)


def main(out: str):
    plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": SURF, "axes.facecolor": SURF})
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.4), gridspec_kw={"width_ratios": [1.05, 1.25, 0.95], "wspace": 0.05})
    panel_history(axes[0]); panel_mechanism(axes[1]); panel_trace(axes[2])
    fig.suptitle("One incident: a flight moves, a corrupted witness flips a provider's policy, the same structure finds it and replacing it restores the repair",
                 fontsize=9.5, color=INK, x=0.01, ha="left", y=0.995)
    for ext in ("pdf", "svg", "png"):
        fig.savefig(f"{out}.{ext}", dpi=200, bbox_inches="tight", facecolor=SURF)
    print("wrote", out + ".{pdf,svg,png}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../results/real/hm3/provenance/figures/case_travel_s30_test000")
    main(ap.parse_args().out)
