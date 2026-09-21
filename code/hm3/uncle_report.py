"""Report the fixed-budget official-UnCLe extension separately from prior pilots."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np

from .alignment_report import paired
from .domains import get_domain
from .generate import generate_split
from .replay import ExecutorOracle


def main(args):
    rows = []
    inputs = []
    for path in args.inputs:
        data = json.loads(Path(path).read_text())
        if len(data["episodes"]) != data["config"]["episodes"]:
            raise ValueError(f"incomplete result: {path}")
        if (data["config"]["reconstruction_epochs"], data["config"]["joint_epochs"]) != (1000, 2000):
            raise ValueError("Do not pool a smoke/short run with the frozen paper configuration")
        inputs.append({"path": path, "config": data["config"], "source_commit": data["source_commit"]})
        rows.extend((data["config"]["seed"], r) for r in data["episodes"])
    if len({r["episode"] for _, r in rows}) != len(rows):
        raise ValueError("duplicate episodes")
    report = {"inputs": inputs, "n": len(rows), "methods": {},
              "mean_history_records": float(np.mean([r["n_records"] for _, r in rows])),
              "summed_episode_seconds": sum(r["seconds"] for _, r in rows),
              "pcmci_g2": {"correct": sum(r["pcmci_g2"]["correct"] for _, r in rows),
                           "mean_records": float(np.mean([len(r["pcmci_g2"]["records"]) for _, r in rows]))}}
    # Read-only post-hoc ceiling/floor check; does not change fits or selections.
    reference_rows = []
    domain = get_domain("travel")
    for item in inputs:
        config = item["config"]
        for ep in generate_split(domain, config["seed"], config["split"], config["episodes"]):
            oracle = ExecutorOracle(domain, ep)
            reference_rows.append({"episode": ep.id, "full": bool(oracle([r["rid"] for r in ep.H])), "empty": bool(oracle([]))})
    report["posthoc_reference_check"] = reference_rows
    lines = ["# Official UnCLe extension: frozen-config results", "",
             "NeurIPS 2025 official implementation, fixed NC8 settings: 1,000 reconstruction + 2,000 joint epochs. Each episode is separately fitted on 512 randomized-read trials. New Travel seeds 60/61/62, first four episodes each. No LLM calls or cross-episode amortization.", "",
             "The output is a model-based summary dependency score, not a proven causal graph. Fixed top-k curves are not identification of causal parents. AP uses the finite held-out flip reference (64 contexts per gate), not population graph truth.", "",
             "| score | k | correct / episodes | matched random correct / sets | paired Δ [95% CI] | macro AP |",
             "|---|---:|---:|---:|---|---:|"]
    for name in ("uncle_permutation", "uncle_parameter"):
        info = {"macro_AP": float(np.mean([r["methods"][name]["empirical_effect_AP"] for _, r in rows])), "topk": {}}
        for k in ("2", "4", "8"):
            chosen = [r["methods"][name]["topk"][k] for _, r in rows]
            controls = [c for r in chosen for c in r["matched_random"].values()]
            diffs = defaultdict(list)
            per_seed = defaultdict(list)
            for seed, r in rows:
                a = r["methods"][name]["topk"][k]
                diffs[seed].append(int(a["correct"])-np.mean([c["correct"] for c in a["matched_random"].values()]))
                per_seed[seed].append(int(a["correct"]))
            d = paired(diffs)
            a = {"n": len(chosen), "correct": sum(r["correct"] for r in chosen),
                 "random_correct": sum(c["correct"] for c in controls), "random_n": len(controls),
                 "paired": d, "correct_by_seed": {s: sum(v) for s, v in per_seed.items()},
                 "max_abs_proxy_token_residual": max(abs(c["token_residual"]) for c in controls),
                 "exact_proxy_token_matches": sum(c["token_residual"] == 0 for c in controls),
                 "coincident_controls": sum(set(c["records"]) == set(r["records"]) for r in chosen for c in r["matched_random"].values())}
            info["topk"][k] = a
            lines.append(f"| {name} | {k} | {a['correct']}/{a['n']} | {a['random_correct']}/{a['random_n']} | {d['difference']:+.3f} [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}] | {info['macro_AP']:.3f} |")
        report["methods"][name] = info
    lines += ["", f"PCMCI-G² reference on these same inputs: {report['pcmci_g2']['correct']}/{len(rows)} correct, mean {report['pcmci_g2']['mean_records']:.2f} selected records. This is not fixed-k and is not an equal-budget superiority comparison.", "",
              f"Post-hoc executor references: full read {sum(r['full'] for r in reference_rows)}/{len(rows)} correct; empty read {sum(r['empty'] for r in reference_rows)}/{len(rows)}.", "",
              f"Raw history averages {report['mean_history_records']:.2f} records. Summed per-episode runtime (includes diagnostics/controls) is {report['summed_episode_seconds']:.1f}s; concurrent jobs mean this is not elapsed wall time.", "",
              "Three random controls are averaged within each episode before bootstrap. Intervals condition on the evaluated seeds. Matching uses cl100k_base as a proxy and may have residuals; the JSON records residuals and coincident controls. No best-k or best-method selection replaces the full table.", "",
              "LCM (2026) was source-checked but not run on this panel: public checkpoints support only 12 variables. TGES (2025) was not run because its stated Gaussian-data guarantees do not apply directly. These exclusions are not negative experimental results.", ""]
    budget_path = Path(args.budget_check)
    if budget_path.exists():
        audit = json.loads(budget_path.read_text())
        if {r["episode"] for r in audit["episodes"]} != {r["episode"] for _, r in rows}:
            raise ValueError("budget attribution and UnCLe results have different episode sets")
        report["posthoc_equal_record_budget"] = audit["summary"]
        lines += ["## Post-hoc equal-record-budget attribution", "",
                  "PCMCI-G² score ranking uses ascending MCI p values, descending test statistic, then stable record order. All methods use the same records and full object context. This matches record count, not exact token count; it is a score selector, not a threshold-identified graph.", "",
                  "| records read | PCMCI-G² ranking | UnCLe permutation | UnCLe parameter |",
                  "|---:|---:|---:|---:|"]
        for k, row in audit["summary"].items():
            lines.append(f"| {k} | {row['pcmci_rank_correct']}/{row['n']} | {report['methods']['uncle_permutation']['topk'][k]['correct']}/{len(rows)} | {report['methods']['uncle_parameter']['topk'][k]['correct']}/{len(rows)} |")
        lines += ["", "At 8 records, PCMCI-G² ranking and UnCLe permutation are both correct 11/12 with identical success/failure indicators. There is no demonstrated incremental utility of UnCLe over this same-budget statistical ranking. A useful dependence-informed ranking result is not evidence for choosing the neural estimator as the paper's main contribution.", ""]
    out = Path(args.out)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2)+"\n")
    out.with_suffix(".md").write_text("\n".join(lines)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inputs", nargs="+", default=[f"results/real/hm3/alignment/uncle_s{s}.json" for s in (60, 61, 62)])
    p.add_argument("--out", default="results/real/hm3/alignment/uncle_report")
    p.add_argument("--budget-check", default="results/real/hm3/alignment/uncle_budget_check.json")
    main(p.parse_args())
