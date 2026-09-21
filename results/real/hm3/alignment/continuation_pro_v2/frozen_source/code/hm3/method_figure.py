"""Method schematic: the read-intervention loop (log -> masked replay -> minimal read set -> frontier model -> forward
read / backward localisation).  Output: results/real/hm3/figures/method_schematic.{pdf,png,svg}"""
from __future__ import annotations
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK, ACC, ACC2, MUT = "#1A2320", "#0F7B7E", "#B5651D", "#5C6862"


def box(ax, x, y, w, h, title, body, edge=INK, face="white", lw=1.2, dashed=False):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12", ec=edge, fc=face, lw=lw,
                       ls="--" if dashed else "-")
    ax.add_patch(p)
    ax.text(x + w / 2, y + h - 0.32, title, ha="center", va="center", fontsize=8.6, fontweight="bold", color=INK)
    for i, line in enumerate(body):
        ax.text(x + w / 2, y + h - 0.62 - 0.27 * i, line, ha="center", va="center", fontsize=6.6, color=MUT)


def arrow(ax, a, b, text=None, color=INK, dashed=False, rad=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=10, lw=1.2, color=color,
                                 ls="--" if dashed else "-", connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.16, text, ha="center", va="bottom", fontsize=6.8, color=color)


def main():
    fig, ax = plt.subplots(figsize=(10.2, 3.9))
    ax.set_xlim(0, 13.6); ax.set_ylim(0, 4.6); ax.axis("off")
    W, H = 2.75, 1.35
    box(ax, 0.2, 2.9, W, H, "episode log", ["state S₀, cue I", "history m₁ … mₙ", "decision Y = π(S₀, I, R)"])
    box(ax, 3.35, 2.9, W, H, "read intervention", ["replay π with R = S ⊆ H", "do(g = 1_S): reads set", "by the memory system"], edge=ACC, face="#E6F2F2")
    box(ax, 6.5, 2.9, W, H, "minimal read set", ["adaptive elimination", "O(|F| log n) replays", "F^π: what π needs"], edge=ACC, face="#E6F2F2")
    box(ax, 9.65, 2.9, W, H, "frontier model p_θ", ["typed path × regime features", "parser-free, no replays at test", "type-level edges E_θ"])
    box(ax, 6.5, 0.55, W, H, "forward: read", ["reach over E_θ; read p_θ ≥ τ", "flat in n, 3–6k tokens", "the actor sees the frontier"], edge=ACC2, face="#F7EEE4")
    box(ax, 9.65, 0.55, W, H, "backward: localise", ["order by the structural trace", "prefix search, clean-replacement", "replays; O(log n), median 1"], edge=ACC2, face="#F7EEE4")
    box(ax, 0.2, 0.55, W, H, "observational discovery", ["PCMCI+, GRACE, regression", "on the same logs", "prunes mediators (Prop. 1)"], edge=MUT, dashed=True)
    arrow(ax, (2.95, 3.57), (3.35, 3.57)); arrow(ax, (6.1, 3.57), (6.5, 3.57)); ax.text(6.3, 3.85, "c(π_S)", ha="center", fontsize=6.6, color=ACC)
    arrow(ax, (9.25, 3.57), (9.65, 3.57)); ax.text(9.45, 3.85, "train", ha="center", fontsize=6.6, color=INK)
    arrow(ax, (10.6, 2.9), (7.9, 1.9), color=ACC2, rad=0.15); arrow(ax, (11.2, 2.9), (11.2, 1.9), color=ACC2)
    arrow(ax, (2.95, 1.22), (6.5, 1.22), "same reach, different identification", color=MUT, dashed=True)
    ax.text(0.2, 4.45, "Reads are interventions the memory system performs on itself: the frontier is identified by replay, with no assumption on the write process.",
            fontsize=7.6, color=INK, va="center")
    fig.tight_layout()
    out = Path("../results/real/hm3/figures"); out.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png", "svg"):
        fig.savefig(out / f"method_schematic.{ext}", dpi=220, bbox_inches="tight")
    print("written", out / "method_schematic.png")


if __name__ == "__main__":
    main()
