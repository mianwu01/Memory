"""Aggregate results/e0v2/*.jsonl into summary tables, the frozen judgements, and
the gate heatmap.  Usage: python3 code/e0v2/report.py"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "e0v2"
sys.path.insert(0, str(ROOT / "code"))
from e0v2.scm import REGIMES  # noqa: E402

POOLED = ["pooled_ridge", "additive_u", "pcmci", "grace_official", "gates_pooled"]
ARM_ORDER = ["pooled_ridge", "additive_u", "pcmci", "grace_official", "gates_pooled",
             "interaction_u", "interaction_u_hc", "per_regime", "grace_per_regime",
             "regime_grace", "regime_grace_shared", "regime_grace_screen_pooled",
             "regime_grace_screen_union", "gates_pooled_mlp", "regime_grace_mlp",
             "per_regime@shuffle", "interaction_u_hc@shuffle", "regime_grace@shuffle"]


def load(name: str):
    p = RES / f"{name}.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def group(recs, keys):
    g = defaultdict(list)
    for r in recs:
        if "metrics" not in r:
            continue
        g[tuple(r["spec"][k] for k in keys)].append(r)
    return g


def stat(vals):
    v = np.asarray([x for x in vals if x is not None], float)
    if v.size == 0:
        return "–"
    return f"{v.mean():.3f} ± {v.std(ddof=0):.3f}" if v.size > 1 else f"{v[0]:.3f}"


def m(r, *path):
    x = r["metrics"]
    for p in path:
        x = x[p]
    return x


def arm_sort(a):
    return ARM_ORDER.index(a) if a in ARM_ORDER else 99


# --------------------------------------------------------------------------- #
def e0a_tables(recs, title, arms=None):
    out = [f"### {title}", "",
           "| arm | σ | seeds | edge F1 | cell F1 (all) | cell F1 (memory) | gate exact | read cells | write cells | hold cells | distractor cells | coef MAE (memory) | runtime s |",
           "|---|---|---:|---|---|---|---|---|---|---|---|---|---:|"]
    g = group(recs, ["arm", "sigma"])
    for (arm, sigma) in sorted(g, key=lambda k: (arm_sort(k[0]), k[1])):
        if arms and arm not in arms:
            continue
        rs = g[(arm, sigma)]
        out.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {:.0f} |".format(
            arm, sigma, len(rs),
            stat([m(r, "edge", "F1") for r in rs]), stat([m(r, "cell", "F1") for r in rs]),
            stat([m(r, "cell_mem", "F1") for r in rs]), stat([m(r, "gate_exact") for r in rs]),
            stat([m(r, "recall_cell_read") for r in rs]), stat([m(r, "recall_cell_write") for r in rs]),
            stat([m(r, "recall_cell_hold") for r in rs]), stat([m(r, "recall_cell_distractor") for r in rs]),
            stat([r["metrics"].get("coef_mae_true_cells_mem") for r in rs]),
            np.mean([r["info"].get("runtime_s", r["elapsed_s"]) for r in rs])))
    out.append("")
    return out


def e0a_judgement(recs):
    g = group(recs, ["arm", "sigma"])
    seeds_ok = {}
    lines = ["### Frozen judgement (docs/e0-v2-design-2026-09-03.md §5)", ""]
    # C1
    c1 = True
    for (arm, sigma), rs in g.items():
        if arm == "regime_grace":
            n_ok = sum(m(r, "cell_mem", "F1") >= 0.9 for r in rs)
            seeds_ok[sigma] = (n_ok, len(rs))
            if n_ok < 4:
                c1 = False
    lines.append(f"- C1 gate recovery (regime_grace cell_mem F1 ≥ 0.90 in ≥ 4/5 seeds at every σ): "
                 f"{'PASS' if c1 else 'FAIL'} — " + ", ".join(f"σ={s}: {a}/{b}" for s, (a, b) in sorted(seeds_ok.items())))
    # C2
    viol = []
    for (arm, sigma), rs in g.items():
        if arm in POOLED:
            for r in rs:
                if m(r, "cell_mem", "F1") >= 0.9:
                    viol.append((arm, sigma, r["spec"]["seed"]))
    lines.append(f"- C2 model class (no pooled arm reaches cell_mem F1 ≥ 0.90 in any seed): "
                 f"{'PASS' if not viol else 'FAIL ' + str(viol)}")
    # C3
    viol = []
    for (arm, sigma), rs in g.items():
        if arm.endswith("@shuffle"):
            for r in rs:
                if m(r, "cell_mem", "F1") >= 0.7 or m(r, "gate_exact") >= 0.5:
                    viol.append((arm, sigma, r["spec"]["seed"], m(r, "cell_mem", "F1"), m(r, "gate_exact")))
    lines.append(f"- C3 negative control (every @shuffle arm cell_mem F1 < 0.70 and gate_exact < 0.50): "
                 f"{'PASS' if not viol else 'FAIL ' + str(viol)}")
    # C4
    also = []
    for arm in ("interaction_u_hc", "per_regime", "grace_per_regime", "interaction_u"):
        ok = all(sum(m(r, "cell_mem", "F1") >= 0.9 for r in rs) >= 4
                 for (a, s), rs in g.items() if a == arm) and any(a == arm for (a, s) in g)
        if ok:
            also.append(arm)
    lines.append(f"- C4 honest baseline: arms that also satisfy the C1 bar: {also or 'none'}")
    lines.append(f"- E0a: **{'PASS' if c1 and not [1 for (a, s), rs in g.items() if a in POOLED for r in rs if m(r, 'cell_mem', 'F1') >= 0.9] and not [1 for (a, s), rs in g.items() if a.endswith('@shuffle') for r in rs if m(r, 'cell_mem', 'F1') >= 0.7 or m(r, 'gate_exact') >= 0.5] else 'FAIL'}**")
    lines.append("")
    return lines


def e0b_tables(recs):
    if not recs:
        return []
    out = ["### E0b — read rarity × sample size", ""]
    g = group(recs, ["preset", "arm", "T"])
    presets = sorted({k[0] for k in g}, key=lambda p: -float(p[1:]) if p != "default" else 0)
    arms = sorted({k[1] for k in g}, key=arm_sort)
    Ts = sorted({k[2] for k in g})
    # realised p_read
    pr = defaultdict(list)
    for r in recs:
        if "metrics" in r:
            pr[r["spec"]["preset"]].append(r["data"]["p_read"])
    out.append("Realised read fraction per preset: " + ", ".join(f"{p}: {np.mean(pr[p]):.3f}" for p in presets))
    out.append("")
    out.append("Smallest T at which the median (over seeds) memory-cell F1 is ≥ 0.90:")
    out.append("")
    out.append("| preset | " + " | ".join(arms) + " |")
    out.append("|---|" + "---|" * len(arms))
    for p in presets:
        row = [p]
        for a in arms:
            best = None
            for T in Ts:
                rs = g.get((p, a, T), [])
                if rs and np.median([m(r, "cell_mem", "F1") for r in rs]) >= 0.9:
                    best = T
                    break
            row.append(str(best) if best else "> 50k")
        out.append("| " + " | ".join(row) + " |")
    out.append("")
    out.append("Median memory-cell F1 (and read-cell recall) by T:")
    out.append("")
    out.append("| preset | arm | " + " | ".join(f"T={T}" for T in Ts) + " |")
    out.append("|---|---|" + "---|" * len(Ts))
    for p in presets:
        for a in arms:
            cells = []
            for T in Ts:
                rs = g.get((p, a, T), [])
                if rs:
                    cells.append(f"{np.median([m(r, 'cell_mem', 'F1') for r in rs]):.2f} ({np.median([m(r, 'recall_cell_read') for r in rs]):.2f})")
                else:
                    cells.append("–")
            out.append(f"| {p} | {a} | " + " | ".join(cells) + " |")
    out.append("")
    return out


def e0c_tables(recs, mlp=False):
    if not recs:
        return []
    out = [f"### {'E0c — MLP mechanisms (d = 32)' if mlp else 'E0c — scale (linear)'}", ""]
    g = group(recs, ["n_dist", "arm"])
    out.append("| d | arm | seeds | edge F1 | cell F1 (memory) | gate exact | read cells | write cells | distractor cells | " + ("" if mlp else "coef MAE (memory) | ") + "runtime s | notes |")
    out.append("|---:|---|---:|---|---|---|---|---|---|" + ("" if mlp else "---|") + "---:|---|")
    for (nd, arm) in sorted(g, key=lambda k: (k[0], arm_sort(k[1]))):
        rs = g[(nd, arm)]
        notes = []
        for r in rs:
            if r["info"].get("underdetermined"):
                notes.append("interaction underdetermined in regimes " + str(r["info"]["underdetermined"]))
                break
            if r["info"].get("screened_regimes"):
                notes.append("SIS screening in regimes " + str(r["info"]["screened_regimes"]))
                break
        cols = [str(nd + 12), arm, str(len(rs)), stat([m(r, "edge", "F1") for r in rs]),
                stat([m(r, "cell_mem", "F1") for r in rs]), stat([m(r, "gate_exact") for r in rs]),
                stat([m(r, "recall_cell_read") for r in rs]), stat([m(r, "recall_cell_write") for r in rs]),
                stat([m(r, "recall_cell_distractor") for r in rs])]
        if not mlp:
            cols.append(stat([r["metrics"].get("coef_mae_true_cells_mem") for r in rs]))
        cols += [f"{np.mean([r['info'].get('runtime_s', r['elapsed_s']) for r in rs]):.0f}", "; ".join(notes)]
        out.append("| " + " | ".join(cols) + " |")
    errs = [r for r in recs if "error" in r]
    if errs:
        out.append("")
        out.append("Errors: " + "; ".join(f"{r['spec']['arm']} d={r['spec']['n_dist'] + 12} seed={r['spec']['seed']}: {r['error'][:120]}" for r in errs))
    out.append("")
    return out


# --------------------------------------------------------------------------- #
def heatmap(recs, sigma=0.01, seed=0, arms=("regime_grace", "per_regime", "gates_pooled")):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    ramp = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
    cmap = LinearSegmentedColormap.from_list("seq_blue", ramp)
    pick = {}
    for r in recs:
        s = r["spec"]
        if "metrics" in r and s["sigma"] == sigma and s["seed"] == seed and s["arm"] in arms:
            pick[s["arm"]] = r
    if not pick:
        return None
    base = next(iter(pick.values()))
    rows = base["heatmap"]["rows"]
    labels = [f"{r['edge'].replace('@1', '')}" for r in rows]
    panels = [("ground truth", np.array([r["truth"] for r in rows]))]
    for a in arms:
        if a in pick:
            panels.append((a, np.array([r["est"] for r in pick[a]["heatmap"]["rows"]])))
    fig, axes = plt.subplots(1, len(panels), figsize=(3.1 * len(panels) + 1.2, 6.2), sharey=True)
    fig.patch.set_facecolor("#fcfcfb")
    for ax, (name, M) in zip(np.atleast_1d(axes), panels):
        ax.set_facecolor("#fcfcfb")
        ax.imshow(np.abs(M), cmap=cmap, vmin=0, vmax=1.05, aspect="auto")
        for i in range(M.shape[0]):
            for j in range(M.shape[1]):
                v = M[i, j]
                if abs(v) >= 0.05:
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7.5,
                            color="#ffffff" if abs(v) > 0.55 else "#0b0b0b")
        ax.set_xticks(range(M.shape[1]))
        ax.set_xticklabels([r.replace("_", " ") for r in REGIMES], rotation=45, ha="right", fontsize=8, color="#52514e")
        ax.set_title(name, fontsize=10, color="#0b0b0b")
        ax.tick_params(length=0)
        ax.tick_params(which="minor", length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_xticks(np.arange(-0.5, M.shape[1], 1), minor=True)
        ax.set_yticks(np.arange(-0.5, M.shape[0], 1), minor=True)
        ax.grid(which="minor", color="#fcfcfb", linewidth=2)
    axes[0].set_yticks(range(len(labels)))
    axes[0].set_yticklabels(labels, fontsize=8.5, color="#0b0b0b")
    for k, y in enumerate([3.5, 7.5]):
        for ax in np.atleast_1d(axes):
            ax.axhline(y, color="#52514e", linewidth=0.8)
    fig.suptitle(f"E0 v2 gate table — coefficient of each memory edge in each regime (σ_hold = {sigma}, seed {seed})",
                 fontsize=10.5, color="#0b0b0b")
    fig.text(0.01, 0.01, "rows: write edges (top), hold edges, read edges (bottom); a blank cell is an inactive gate",
             fontsize=8, color="#52514e")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    out = RES / "fig_gate_heatmap.png"
    fig.savefig(out, dpi=160, facecolor=fig.get_facecolor())
    fig.savefig(RES / "fig_gate_heatmap.svg", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def main():
    e0a = load("e0a")
    md = ["# E0 v2 summary (generated by code/e0v2/report.py)", ""]
    if e0a:
        md += e0a_judgement(e0a)
        md += e0a_tables(e0a, "E0a — identification, n = 32, T = 10,000, seeds 0–4")
    for tag, title in (("_lam025", "λ sensitivity: scale 0.25"), ("_lam100", "λ sensitivity: scale 1.0")):
        rs = load("e0a" + tag)
        if rs:
            md += e0a_tables(rs, title)
    lag2 = load("e0a_lag2")
    if lag2:
        md += e0a_tables(lag2, "max_lag = 2 (candidate lags 1 and 2; truth is lag 1)")
    md += e0b_tables(load("e0b"))
    md += e0c_tables(load("e0c_mlp"), mlp=True)
    md += e0c_tables(load("e0c"))
    errs = [r for r in e0a if "error" in r]
    if errs:
        md.append("E0a errors: " + "; ".join(f"{r['spec']['arm']} σ={r['spec']['sigma']} seed={r['spec']['seed']}: {r['error'][:100]}" for r in errs))
    fig = heatmap(e0a) if e0a else None
    if fig:
        md.append(f"Heatmap: `{fig.relative_to(ROOT)}`")
    (RES / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
