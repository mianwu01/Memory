"""Cost/transport audit and a figure from actual continuation artifacts."""
from collections import Counter
import json
from pathlib import Path

import numpy as np


def costs(base):
    paths = []
    for kind in ["real", "development"]:
        root = base / kind / "hm3/alignment"
        for directory in root.glob("continuation_*"):
            paths.extend(directory.rglob("ledger.jsonl"))
            paths.extend(directory.rglob("memory_calls.jsonl"))
    entries, requests, unreturned = [], 0, []
    for path in sorted(set(paths)):
        lines = [json.loads(x) for x in path.read_text().splitlines()]
        fresh = [r for r in lines if not r.get("reused_from")]
        good = [r for r in fresh if r["event"] == "result"]
        input_tokens = sum((r.get("usage") or {}).get("prompt_tokens", 0) for r in good)
        output_tokens = sum((r.get("usage") or {}).get("completion_tokens", 0) for r in good)
        entries.append(dict(path=str(path), fresh_responses=len(good), reused_rows=len(lines)-len(fresh),
                            failed=len(fresh)-len(good), input_tokens=input_tokens, output_tokens=output_tokens,
                            legacy_rate_scenario_usd=(input_tokens*2.5+output_tokens*10)/1e6,
                            provider_reported_cny=sum(r.get("provider_cost_cny") or 0 for r in good),
                            responses_with_provider_cost=sum(r.get("provider_cost_cny") is not None for r in good)))
        request_file = path.with_name("requests.jsonl")
        if request_file.exists():
            reqs = [json.loads(x) for x in request_file.read_text().splitlines()]
            done = {r["job_id"] for r in lines}
            requests += len(reqs)
            unreturned.extend(dict(path=str(request_file), job_id=r["job_id"])
                              for r in reqs if r["job_id"] not in done)
    total = {key: sum(r[key] for r in entries) for key in ["fresh_responses", "reused_rows", "failed", "input_tokens",
             "output_tokens", "legacy_rate_scenario_usd", "provider_reported_cny", "responses_with_provider_cost"]}
    return dict(totals=total, ledgers=entries, actor_request_intents=requests, unreturned_actor_requests=unreturned,
                scope="This continuation only. Legacy $2.5/$10 token-rate scenario is NOT DeepSeek Pro pricing or an invoice. "
                "Unreturned requests and failed upstream requests can incur unobserved charges. "
                "Reused rows excluded from fresh cost. Existing historical $27.35 not recomputed or merged.")


def figure(root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    report = json.loads((root / "report.json").read_text())
    data = report["episodes"]
    fig, axes = plt.subplots(2, 1, figsize=(11, 9), gridspec_kw={"height_ratios": [1, 1.2]})
    ax = axes[0]
    ax.set_axis_off()
    first = data[0]
    groups = first["groups"]
    fit = first["fit"]
    ax.set_title("Fixed first episode: randomized segment gates → actor correctness", loc="left", fontsize=12)
    for i, group in enumerate(groups):
        y = .8 - .6*i/max(1, len(groups)-1)
        color = "#b44438" if i == 0 else "#245e8c"
        label = f"segment {i} ({len(group)} records)"
        if i == 0:
            label += "\nexternally labeled disallowed"
        ax.text(.04, y, label, color=color, va="center", bbox=dict(boxstyle="round", fc="#f7f7f7", ec=color), transform=ax.transAxes)
        identified = bool(fit and i in fit["threshold_parents"])
        ax.annotate("", xy=(.77, .5), xytext=(.4, y), xycoords="axes fraction",
                    arrowprops=dict(arrowstyle="->", color=color if identified else "#aaaaaa",
                                    linestyle="-" if identified else ":", lw=2 if identified else 1))
        if fit:
            ax.text(.47, y, f"p={fit['p_values'][i]:.3g}", transform=ax.transAxes, fontsize=9)
    ax.text(.79, .5, "LLM exact\ntask success", va="center", bbox=dict(boxstyle="round", fc="#edf3ec", ec="#376c38"), transform=ax.transAxes)
    ax.text(.04, -.04, "Solid: threshold edge. Dotted: offered but not selected. Direction fixed by randomization; this is not a memory-state temporal graph.",
            transform=ax.transAxes, fontsize=8)
    ax = axes[1]
    arms = ["full", "learned_top2", "bm25_matched", "recency_matched", "source_blocked", "neutral_blocked", "source_changed"]
    values = np.array([[d["results"].get(a, {}).get("correct", 0)/3
                        if d["results"].get(a, {}).get("n") == 3 else np.nan for d in data] for a in arms])
    cmap = plt.get_cmap("Blues").copy()
    cmap.set_bad("#dddddd")
    ax.imshow(values, vmin=0, vmax=1, cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(data)), [d["episode"].replace("travel-", "") for d in data], rotation=25, ha="right")
    ax.set_yticks(range(len(arms)), arms)
    for i in range(len(arms)):
        for j in range(len(data)):
            x = values[i, j]
            ax.text(j, i, "missing" if np.isnan(x) else f"{round(x*3)}/3", ha="center", va="center",
                    color="white" if x > .6 else "black")
    ax.set_title("Every frozen case; independent validation calls (gray = incomplete)", loc="left", fontsize=12)
    fig.text(.02, .01, "Synthetic HM3 + actual LLM. Three repeats are a stability diagnostic. Source authorization is externally constructed.", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, 1), h_pad=3)
    fig.savefig(root / "structure_and_audit.svg")
    fig.savefig(root / "structure_and_audit.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    root = Path("results/real/hm3/alignment/continuation_pro_v2")
    audit = costs(Path("results"))
    (root / "cost_audit.json").write_text(json.dumps(audit, indent=2)+"\n")
    figure(root)
    print(json.dumps(audit["totals"]))
