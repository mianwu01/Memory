"""Render actual frozen read-gate results, including the first failure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

from .domains import get_domain
from .generate import generate_split


def main(args):
    data = json.loads(Path(args.input).read_text())
    c = data["config"]
    episodes = generate_split(get_domain(c["domain"]), c["seed"], c["split"], c["episodes"])
    # Fixed first test episode plus the first failure, not a best-case search.
    failure = next(i for i, r in enumerate(data["episodes"]) if not r["methods"]["grace_pcmci_g2"]["full_read_after_selection"])
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4))
    for ax, index in zip(axes, (0, failure)):
        row, ep = data["episodes"][index], episodes[index]
        m = row["methods"]["grace_pcmci_g2"]
        recovered = set(m["parents"])
        nodes = sorted(recovered | set(row["empirical_effect_parents"]), key=lambda g: int(g[1:]))
        ax.set(xlim=(0, 1), ylim=(0, 1))
        ax.axis("off")
        ax.set_title(row["episode"], fontsize=12, loc="left", pad=12)
        for j, gate in enumerate(nodes):
            y = .82-j*.58/max(1, len(nodes)-1)
            rid = row["gate_to_record"][gate]
            record = next(r for r in ep.H if r["rid"] == rid)
            found = gate in recovered
            color = "#176B9A" if found else "#A54E16"
            ax.text(.02, y, f"{rid}: {record['object_id']} / {record['kind']}\nflip frequency {row['heldout_flip_effects'][gate]:.3f}",
                    ha="left", va="center", fontsize=10,
                    bbox={"boxstyle": "round,pad=.35", "facecolor": "#F7F9FA", "edgecolor": color})
            ax.add_patch(FancyArrowPatch((.43, y), (.74, .53), arrowstyle="-|>",
                                        mutation_scale=15, color=color, linewidth=1.8,
                                        linestyle="-" if found else "--"))
        ax.text(.84, .53, "Replay\ncorrectness\nY(t+1)", ha="center", va="center", fontsize=11,
                bbox={"boxstyle": "round,pad=.5", "facecolor": "#E9F1F5", "edgecolor": "#466675"})
        status = "correct" if m["full_read_after_selection"] else "incorrect"
        ax.text(.02, .03, f"{len(m['parents'])}/{row['n_records']} records selected; replay {status}", fontsize=11)
    fig.suptitle("Randomized read gates G(t) → fixed-executor correctness", fontsize=15, y=.98)
    fig.text(.04, .10, "Solid: recovered outcome edge. Dashed: missed, nonzero held-out flip effect. PCMCI-G² and GRACE select identical sets.", fontsize=9)
    fig.text(.04, .055, "Outcome-parent subgraph only: other false-positive edges remain in raw results. Finite flip checks are not complete ground truth.", fontsize=9)
    fig.text(.04, .015, "Native synthetic HM3 episodes; per-episode fits on randomized replay trials. This is not a latent-thought or correct-output audit demo.", fontsize=9)
    fig.subplots_adjust(top=.84, bottom=.20, left=.04, right=.97, wspace=.15)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, metadata={"Date": None} if out.suffix == ".svg" else None, dpi=140)
    plt.close(fig)
    print(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="results/real/hm3/alignment/read_gate_tcd_s50.json")
    p.add_argument("--out", default="results/real/hm3/alignment/read_gate_structure.svg")
    main(p.parse_args())
