"""Summarize paired alignment evidence without silently pooling protocols."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np


def paired(differences, seed=721):
    """Episode-paired bootstrap, stratified by seed; CI conditional on these seeds."""
    groups = [np.asarray(v, float) for _, v in sorted(differences.items()) if v]
    if not groups:
        return {"n": 0, "difference": None, "ci95": None}
    rng = np.random.default_rng(seed)
    n = sum(map(len, groups))
    boot = sum(g[rng.integers(len(g), size=(4000, len(g)))].sum(axis=1) for g in groups) / n
    return {"n": n, "difference": float(np.concatenate(groups).mean()),
            "ci95": np.quantile(boot, [.025, .975]).tolist()}


def read_gate_summary(paths):
    """Average random controls within each episode before uncertainty estimation."""
    episodes = []
    seen = set()
    for path in paths:
        data = json.loads(Path(path).read_text())
        for row in data["episodes"]:
            if row["episode"] in seen:
                raise ValueError(f"duplicate read-gate episode: {row['episode']}")
            seen.add(row["episode"])
            episodes.append((data["config"]["seed"], row))
    if not episodes:
        return {}
    result = {"n": len(episodes), "mean_history_records": float(np.mean([r["n_records"] for _, r in episodes])),
              "unique_executor_replay_contexts": sum(r["unique_replay_contexts"] for _, r in episodes),
              "summed_episode_seconds": sum(r["seconds"] for _, r in episodes), "methods": {}}
    for method in episodes[0][1]["methods"]:
        rows = [r["methods"][method] for _, r in episodes]
        controls = [c for r in rows for c in r["matched_random"].values()]
        diffs = defaultdict(list)
        for seed, r in episodes:
            a = r["methods"][method]
            diffs[seed].append(int(a["full_read_after_selection"])-np.mean([c["correct"] for c in a["matched_random"].values()]))
        result["methods"][method] = {
            "correct": sum(r["full_read_after_selection"] for r in rows), "n": len(rows),
            "mean_selected_records": float(np.mean([len(r["parents"]) for r in rows])),
            "macro_empirical_flip_precision": float(np.mean([r["empirical_flip_precision"] for r in rows if r["empirical_flip_precision"] is not None])),
            "macro_empirical_flip_recall": float(np.mean([r["empirical_flip_recall"] for r in rows if r["empirical_flip_recall"] is not None])),
            "random_correct": sum(c["correct"] for c in controls), "random_n": len(controls),
            "paired_vs_within_episode_random_mean": paired(diffs),
            "exact_proxy_token_matches": sum(c["token_residual"] == 0 for c in controls),
            "max_abs_proxy_token_residual": max(abs(c["token_residual"]) for c in controls),
            "max_relative_proxy_token_residual": max(abs(c["token_residual"])/max(1, c["target_history_proxy_tokens"]) for c in controls),
            "controls_identical_to_selected": sum(set(c["records"]) == set(r["selected_records"]) for r in rows for c in r["matched_random"].values()),
            "failed_episodes": [r["episode"] for _, r in episodes if not r["methods"][method]["full_read_after_selection"]],
            # Gates are externally independent by construction. These are false edges,
            # irrespective of the finite-context effect reference for the outcome.
            "spurious_lagged_edges_targeting_randomized_gates": sum(
                not edge.split("->")[1].startswith("decision_correct@")
                for _, r in episodes for edge in r["fits"][method]["edges"]),
        }
    return result


def main(args):
    report = {"ci_scope": "episode-paired, stratified by seed; conditional on evaluated seeds", "controls": {}, "reader": {}, "actor": {}}
    lines = ["# Structure alignment: reproducible results", "",
             "This report separates discovery controls, parser-free retrieval, and actual LLM calls.",
             "Complete adjacency means no learned type filtering; given instance links remain.", ""]
    control_path = Path(args.controls)
    if control_path.exists():
        data = json.loads(control_path.read_text())
        report["controls_completion"] = {"complete": data.get("complete", False), "cells": len(data["runs"]),
                                         "requested_episode_conditions": sum(c["n_requested"] for c in data["runs"].values()),
                                         "evaluated_episode_conditions": sum(c["n"] for c in data["runs"].values())}
        buckets = defaultdict(lambda: defaultdict(list))
        for key, cell in data["runs"].items():
            name, _, condition = key.split("/")
            for arm, a in cell["arms"].items():
                buckets[(name, condition)][arm].extend(a["rows"])
        lines += ["## Fixed-task discovery controls", "", "| domain / history | arm | n | executor EES | records | same complete input |", "|---|---|---:|---:|---:|---:|"]
        for (name, condition), arms in sorted(buckets.items()):
            result = {}
            for arm, rows in arms.items():
                result[arm] = {"n": len(rows), "ees": float(np.mean([r["ees"] for r in rows])),
                               "records": float(np.mean([r["n_records"] for r in rows])),
                               "same_complete_prompt_count": sum(r["same_prompt_as_complete"] for r in rows),
                               "max_abs_token_residual": max(abs(r.get("token_residual", 0)) for r in rows),
                               "exact_proxy_token_match_count": sum(r.get("token_residual") == 0 for r in rows)}
                if arm in ("complete/parser", "grace_open/parser", "grace_open_x3/parser", "query_only/parser", "permuted_17/matched", "random_17/matched"):
                    r = result[arm]
                    lines.append(f"| {name}/{condition} | {arm} | {r['n']} | {r['ees']:.3f} | {r['records']:.1f} | {r['same_complete_prompt_count']}/{r['n']} |")
            report["controls"][f"{name}/{condition}"] = result
        lines += ["", "Matching uses cl100k_base as a token proxy, not the provider's tokenizer. Residuals and all three wrong-graph permutations are in the JSON. Executor comparisons share the full state for value computation; actor comparisons actually restrict visible object context.", ""]
    reader_path = Path(args.reader)
    if reader_path.exists():
        data = json.loads(reader_path.read_text())
        buckets = defaultdict(list)
        for key, cell in data["runs"].items():
            name, seed, condition = key.split("/")
            buckets[(name, condition)].extend((seed, row) for row in cell["rows"])
        lines += ["## Fresh-seed parser-free retrieval", "", "This rule uses supplied component membership and temporal evidence; it is not a discovery algorithm.", "", "| domain / history | n | key2 | response2 | component2 | component2 − key2 [95% CI] | records key2 → component2 |", "|---|---:|---:|---:|---:|---|---|"]
        for (name, condition), rows in sorted(buckets.items()):
            means = {arm: {m: float(np.mean([r["arms"][arm][m] for _, r in rows])) for m in ("ees", "n_records")}
                     for arm in ("key2", "response2", "component2")}
            differences = defaultdict(list)
            for seed, r in rows:
                differences[seed].append(int(r["arms"]["component2"]["ees"])-int(r["arms"]["key2"]["ees"]))
            delta = paired(differences)
            report["reader"][f"{name}/{condition}"] = {"means": means, "paired": delta}
            a, b, c = (means[x] for x in ("key2", "response2", "component2"))
            lo, hi = delta["ci95"]
            lines.append(f"| {name}/{condition} | {len(rows)} | {a['ees']:.3f} | {b['ees']:.3f} | {c['ees']:.3f} | {delta['difference']:+.3f} [{lo:+.3f}, {hi:+.3f}] | {a['n_records']:.1f} → {c['n_records']:.1f} |")
        lines += ["", "Intervals condition on the three frozen seeds; they do not estimate uncertainty over arbitrary new environments. Component preference can benefit from HM3's disconnected foreign-component augmentation.", ""]
    actor_path = Path(args.actor) / "ledger.jsonl"
    if actor_path.exists():
        all_records = [json.loads(line) for line in actor_path.read_text().splitlines()]
        latest = {r["job_id"]: r for r in all_records if r["event"] == "result"}
        by_cell = defaultdict(lambda: defaultdict(dict))
        for r in latest.values():
            for arm in r["arms"]:
                by_cell[(r["domain"], r["condition"])][arm["name"]][r["episode"]] = r
        lines += ["## LLM diagnostic (v1, verbose, 16k output cap)", "", "Exact duplicate inputs within an episode share one call. Every pair uses the intersection of completed episodes, never mismatched denominators.", "", "| domain / history | arm | completed | EES | first-call truncations | Δ vs no-type-filter [95% CI] |", "|---|---|---:|---:|---:|---|"]
        for (name, condition), arms in sorted(by_cell.items()):
            ref = arms.get("complete/parser", {})
            info = {}
            for arm, rows in sorted(arms.items()):
                diffs = defaultdict(list)
                for ep in rows.keys() & ref.keys():
                    r, c = rows[ep], ref[ep]
                    diffs[r["seed"]].append(int(r["score"]["ees"])-int(c["score"]["ees"]))
                delta = paired(diffs)
                ees = float(np.mean([r["score"]["ees"] for r in rows.values()]))
                trunc = sum(r["truncated_first"] for r in rows.values())
                info[arm] = {"n": len(rows), "ees": ees, "truncated_first": trunc, "paired_vs_complete": delta}
                ci = "pending" if delta["ci95"] is None else f"{delta['difference']:+.3f} [{delta['ci95'][0]:+.3f}, {delta['ci95'][1]:+.3f}], n={delta['n']}"
                lines.append(f"| {name}/{condition} | {arm} | {len(rows)} | {ees:.3f} | {trunc} | {ci} |")
            report["actor"][f"{name}/{condition}"] = info
            comparisons = {}
            for reference in ("complete/key2", "full"):
                diffs = defaultdict(list)
                for ep in arms.get("component2", {}).keys() & arms.get(reference, {}).keys():
                    r, c = arms["component2"][ep], arms[reference][ep]
                    diffs[r["seed"]].append(int(r["score"]["ees"])-int(c["score"]["ees"]))
                comparisons[reference] = paired(diffs)
            report.setdefault("actor_component_comparisons", {})[f"{name}/{condition}"] = comparisons
        total_cost = sum(r.get("cost", 0) for r in all_records)
        lines += ["", f"Recorded accounting cost: ${total_cost:.4f}. Unique completed inputs: {len(latest)}. Infrastructure failures: {sum(r['event'] == 'infrastructure_failure' for r in all_records)}.", ""]
        report["actor_accounting"] = {"cost": total_cost, "unique_completed": len(latest), "infrastructure_failures": sum(r["event"] == "infrastructure_failure" for r in all_records)}
    gate = read_gate_summary(args.read_gate)
    if gate:
        report["read_gate"] = gate
        lines += ["## Established discovery on randomized read gates: candidate redesign", "",
                  "12 fresh native Travel episodes (seeds 50/51/52), independently fitted per episode; fixed deterministic executor only. 512 randomized training masks and 64 independent flip-effect contexts per gate. The lag is trial input → next-row outcome, not the original agent's evolving write timeline. No claim of amortized deployment, LLM transfer, or latent-state recovery.", "",
                  "| estimator | selected-read correct | mean selected records | matched random correct | paired Δ vs per-episode random mean [95% CI] | empirical flip P / R (macro) |",
                  "|---|---:|---:|---:|---|---|"]
        for name, r in gate["methods"].items():
            d = r["paired_vs_within_episode_random_mean"]
            lines.append(f"| {name} | {r['correct']}/{r['n']} | {r['mean_selected_records']:.2f} | {r['random_correct']}/{r['random_n']} | {d['difference']:+.3f} [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}] | {r['macro_empirical_flip_precision']:.3f} / {r['macro_empirical_flip_recall']:.3f} |")
        lines += ["", "Random controls are averaged within each episode: 36 sets are NOT 36 independent episodes. Matching preserves record count and object context; token lengths are approximate cl100k_base matches. Coincident learned/random sets remain in the analysis. Finite flip sensitivity is not a complete causal ground truth; omitted rare dependencies can still matter.",
                  f"Mean raw history: {gate['mean_history_records']:.2f} records. Total unique executor contexts (training + diagnostics + controls): {gate['unique_executor_replay_contexts']}; summed episode runtime: {gate['summed_episode_seconds']:.1f}s (excluding the post-hoc skeleton audit).", ""]
        for name, r in gate["methods"].items():
            lines.append(f"- {name}: {r['exact_proxy_token_matches']}/{r['random_n']} exact proxy-token matches; max absolute residual {r['max_abs_proxy_token_residual']} tokens; {r['controls_identical_to_selected']} coincident controls. Failed episodes: {', '.join(r['failed_episodes'])}. Spurious lagged edges into randomized gates across fits: {r['spurious_lagged_edges_targeting_randomized_gates']}.")
        lines += ["", "Only incoming outcome edges are used by the selector. The other inferred edges are not hidden from the artifacts; the spurious gate-target edges explicitly rule out claiming accurate full-graph recovery.", ""]
        attribution_path = Path(args.attribution)
        if attribution_path.exists():
            attribution = json.loads(attribution_path.read_text())
            rows = attribution["episodes"]
            summary = {"n": len(rows), "correct": sum(r["correct"] for r in rows),
                       "full_read_correct": sum(r["full_read_correct"] for r in rows),
                       "empty_read_correct": sum(r["empty_read_correct"] for r in rows),
                       "same_parents_as_grace": sum(r["same_parents_as_grace"] for r in rows),
                       "all_skeleton_counts_reproduced": all(r["same_skeleton_edge_count_as_original"] for r in rows)}
            report["read_gate_attribution"] = summary
            lines += [f"Post-hoc attribution check (same inputs/settings; no GRACE refit): PCMCI-G² alone is correct {summary['correct']}/{summary['n']}, and returns exactly the same outcome-parent sets as GRACE on {summary['same_parents_as_grace']}/{summary['n']} episodes. Full read: {summary['full_read_correct']}/{summary['n']}; empty read: {summary['empty_read_correct']}/{summary['n']}. **There is no demonstrated incremental benefit of the GRACE refinement.** The ParCorr vs GRACE+G² comparison also changes the CI test and alpha, so it is not a neural-refinement ablation.", ""]
    root = Path(args.actor).parent
    report["audit_validation"] = {}
    for directory, conclusion in (
        ("source_reliance_demo", "Failed to establish LLM source dependence: baseline and all three interventions were correct 3/3."),
        ("actor_source_audit", "Failed independent validation: full context was correct 0/3, subset 2/3, and blocked source 1/3. No stable normal-correct-output audit demonstrated."),
    ):
        path = root / directory / "summary.json"
        if path.exists():
            report["audit_validation"][directory] = {"passed": False, "conclusion": conclusion, "raw_summary": json.loads(path.read_text())}
    if report["audit_validation"]:
        lines += ["## Correct-output source audit: not established", ""]
        for directory, r in report["audit_validation"].items():
            lines += [f"- {directory}: {r['conclusion']}"]
        lines += ["", "Source authorization was externally supplied in a controlled scenario. Neither experiment supports hidden-thought recovery or deception detection. No replacement case was sought after the frozen independent validation failed.", ""]
    accounting = {}
    for ledger in sorted(root.glob("*/ledger.jsonl")):
        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        accounting[ledger.parent.name] = {"ledger_rows": len(rows), "accounting_dollars": sum(r.get("cost", r.get("cost_upper_accounting", 0)) for r in rows)}
    report["all_recorded_accounting"] = accounting
    lines += ["## Recorded cost and remaining evidence gaps", "",
              "Accounting uses legacy configured token rates, not provider billing. The interrupted interface pilot is preserved separately; in-flight unlogged calls and connectivity checks may add cost.", ""]
    for name, r in accounting.items():
        lines.append(f"- {name}: {r['ledger_rows']} recorded rows, ${r['accounting_dollars']:.4f}.")
    lines += ["", "The new actor diagnostic covers BM25, recency, query-only, complete/discovered type filters and matched controls, not fresh Mem0/A-Mem/LightMem runs. Those named-system comparisons, a stable LLM auditing demonstration, and advisor agreement on the read-gate estimand remain open. These artifacts do not establish a submission-ready causal-memory claim.", ""]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2))
    out.with_suffix(".md").write_text("\n".join(lines)+"\n")
    print(json.dumps({"controls_cells": len(report["controls"]), "reader_cells": len(report["reader"]),
                      "actor_cells": len(report["actor"]), "report": str(out.with_suffix('.md'))}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--controls", default="results/real/hm3/alignment/controls_complete.json")
    p.add_argument("--reader", default="results/real/hm3/alignment/reader_fresh.json")
    p.add_argument("--actor", default="results/real/hm3/alignment/actor_v1_closed")
    p.add_argument("--read-gate", nargs="*", default=[f"results/real/hm3/alignment/read_gate_tcd_s{s}.json" for s in (50, 51, 52)])
    p.add_argument("--attribution", default="results/real/hm3/alignment/read_gate_attribution.json")
    p.add_argument("--out", default="results/real/hm3/alignment/report")
    main(p.parse_args())
