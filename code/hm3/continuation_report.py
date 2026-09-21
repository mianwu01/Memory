"""Rebuild the continuation report from ledgers, including missingness and costs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np


def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def failure_kind(row):
    if row["event"] != "result":
        return "infrastructure"
    if row.get("correct"):
        return "correct"
    if not row.get("parse_ok") or row.get("score_error"):
        return "format_or_action_schema"
    score = row.get("score", {})
    if not score.get("legal"):
        return "illegal_transaction"
    if score.get("affected_f1", 0) < 1:
        return "wrong_affected_objects"
    if score.get("value_accuracy", 0) < 1:
        return "wrong_payload_values"
    return "other_exact_state_or_receipt_failure"


def interval(values, seeds):
    if not values:
        return None
    rng = np.random.default_rng(20260922)
    v = np.asarray(values)
    ids = [np.where(np.asarray(seeds) == seed)[0] for seed in sorted(set(seeds))]
    boots = np.concatenate([rng.choice(x, (10000, len(x))) for x in ids], axis=1)
    return [float(x) for x in np.quantile(v[boots].mean(axis=1), [.025, .975])]


def generate(root, native_root):
    import tiktoken
    encoder = tiktoken.get_encoding("cl100k_base")
    ledger = rows(root / "ledger.jsonl")
    overlay = rows(root / "transport_recovery/ledger.jsonl")
    merged = {r["job_id"]: r for r in ledger}
    for r in overlay:
        if r["job_id"] in merged and merged[r["job_id"]]["event"] == "result":
            raise ValueError("Recovery must not replace completed semantic results")
        merged[r["job_id"]] = r
    ledger = list(merged.values())
    episodes = json.loads((root / "episodes.json").read_text())
    manifests = {x["episode"]: x for x in json.loads((root / "manifests.json").read_text())}
    seeds = {x["id"]: x["seed"] for x in episodes}
    episode_ids = list(seeds)
    by = defaultdict(list)
    prompt_tokens = {}
    for row in ledger:
        by[row["episode"], row["stage"]].append(row)
        sha = row["prompt_sha256"]
        if sha not in prompt_tokens:
            path = root / "inputs" / f"{sha}.json"
            if not path.exists():
                path = root / "transport_recovery/inputs" / f"{sha}.json"
            msg = json.loads(path.read_text())
            prompt_tokens[sha] = sum(len(encoder.encode(m["content"])) for m in msg)
    arm_names = sorted({stage for _, stage in by if stage != "train"})
    means = {}
    table = {}
    for arm in arm_names:
        allrows = [x for ep in episode_ids for x in by[ep, arm]]
        good = [x for x in allrows if x["event"] == "result"]
        complete = {ep: by[ep, arm] for ep in episode_ids
                    if len(by[ep, arm]) == 3 and all(x["event"] == "result" for x in by[ep, arm])}
        means[arm] = {ep: np.mean([x["correct"] for x in rr]).item() for ep, rr in complete.items()}
        table[arm] = dict(completed_calls=len(good), expected_calls=18,
                          correct_calls=sum(x["correct"] for x in good), complete_episodes=len(complete),
                          episode_mean=float(np.mean(list(means[arm].values()))) if complete else None,
                          first_truncations=sum(x["finish_reason"] == "length" for x in good),
                          infrastructure_failures=len(allrows)-len(good),
                          mean_records=float(np.mean([len(x["reads"]["records"]) for x in good])) if good else None,
                          mean_input_proxy_tokens=float(np.mean([prompt_tokens[x["prompt_sha256"]] for x in good])) if good else None)
        table[arm]["failure_breakdown"] = dict(Counter(failure_kind(x) for x in allrows))
    comparisons = {}
    learned = means.get("learned_top2", {})
    for arm, values in means.items():
        ids = sorted(set(learned) & set(values))
        delta = [learned[x]-values[x] for x in ids]
        comparisons[arm] = dict(paired_episodes=len(ids),
                                delta=float(np.mean(delta)) if delta else None,
                                ci95=interval(delta, [seeds[x] for x in ids]))
    # Average random/permuted controls within episode, never count them as new tasks.
    for family in ["random", "wrong"]:
        names = [f"{family}_{s}" for s in [17, 29, 43]]
        ids = sorted(ep for ep in learned if all(ep in means.get(a, {}) for a in names))
        delta = [learned[ep]-float(np.mean([means[a][ep] for a in names])) for ep in ids]
        comparisons[family+"_within_episode_mean"] = dict(
            paired_episodes=len(ids), delta=float(np.mean(delta)) if delta else None,
            ci95=interval(delta, [seeds[x] for x in ids]))
    details = []
    for ep in episode_ids:
        fp = root / f"{ep}_fit.json"
        if not fp.exists():
            fp = root / "transport_recovery" / f"{ep}_fit.json"
        fit = json.loads(fp.read_text()) if fp.exists() else None
        mm = manifests[ep]
        alltrain = by[ep, "train"]
        complete_train = [r for r in alltrain if r["event"] == "result"]
        results = {arm: dict(n=len([r for r in by[ep, arm] if r["event"] == "result"]),
                            correct=sum(r.get("correct", False) for r in by[ep, arm])) for arm in arm_names}
        matched = {}
        ref = by[ep, "learned_top2"]
        if ref:
            refsha = ref[0]["prompt_sha256"]
            for arm in arm_names:
                rr = by[ep, arm]
                if rr:
                    matched[arm] = dict(same_input=rr[0]["prompt_sha256"] == refsha,
                                       record_residual=len(rr[0]["reads"]["records"])-len(ref[0]["reads"]["records"]),
                                       serialized_token_residual=prompt_tokens[rr[0]["prompt_sha256"]]-prompt_tokens[refsha])
        required = ["full", "source_blocked", "neutral_blocked", "source_changed"]
        audit_available = all(results.get(a, {}).get("n") == 3 for a in required)
        criterion = bool(audit_available and fit and 0 in fit["threshold_parents"]
                         and results["full"]["correct"] == 3 and results["neutral_blocked"]["correct"] == 3
                         and results["source_blocked"]["correct"] <= 1 and results["source_changed"]["correct"] <= 1)
        details.append(dict(episode=ep, seed=seeds[ep], groups=mm["groups"], fit=fit,
                            training_completed=len(complete_train), training_requested=len(alltrain),
                            train_unique_masks=len({tuple(x) for x in mm["masks"]}),
                            results=results, matching=matched, audit_available=audit_available,
                            source_audit_diagnostic_rule_passed=criterion))
    native = {}
    for system in ["mem0", "amem", "lightmem"]:
        cells = []
        for ep in episode_ids:
            directory = native_root / system / ep
            status_file = directory / "status.json"
            status = json.loads(status_file.read_text()) if status_file.exists() else {"status": "pending"}
            actor_variant = "actor_v2" if (native_root / "actor_interface_repair.json").exists() else "actor"
            actor = rows(directory / actor_variant / "ledger.jsonl")
            memory = rows(directory / "memory_calls.jsonl")
            good = [x for x in actor if x["event"] == "result"]
            cells.append(dict(episode=ep, status=status, actor_calls=len(good), actor_attempts=len(actor),
                              correct=sum(x["correct"] for x in good),
                              actor_truncated=sum(x["finish_reason"] == "length" for x in good),
                              memory_calls=len(memory),
                              memory_input_tokens=sum((x.get("usage") or {}).get("prompt_tokens", 0) for x in memory),
                              memory_output_tokens=sum((x.get("usage") or {}).get("completion_tokens", 0) for x in memory),
                              actor_input_tokens=sum((x.get("usage") or {}).get("prompt_tokens", 0) for x in good),
                              actor_output_tokens=sum((x.get("usage") or {}).get("completion_tokens", 0) for x in good)))
            cells[-1]["failure_breakdown"] = dict(Counter(failure_kind(x) for x in actor))
            cells[-1]["actor_variant"] = actor_variant
        native[system] = cells
    result = dict(status="diagnostic results; scientific acceptance evaluated separately",
                  actor_rows=len(ledger), expected_actor_rows=1020,
                  returned_models=dict(Counter(x.get("returned_model", "failure") for x in ledger)),
                  arms=table, paired_comparisons=comparisons, episodes=details, native_systems=native,
                  state_panels=json.loads((root / "state_panels.json").read_text()))
    result["discovery_cost"] = {
        "fresh_training_calls": sum(x["stage"] == "train" and x["event"] == "result" for x in ledger),
        "training_input_tokens": sum((x.get("usage") or {}).get("prompt_tokens", 0)
                                     for x in ledger if x["stage"] == "train"),
        "training_output_tokens": sum((x.get("usage") or {}).get("completion_tokens", 0)
                                      for x in ledger if x["stage"] == "train"),
        "interpretation": "Per-episode discovery calls count toward method cost; selected-input savings alone are not total efficiency gains."}
    (root / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    text = ["# 9/22 frozen stronger-actor continuation", "",
            "Synthetic HM3 Travel; actual LLM actor. This is a candidate randomized-read estimand, not recovery of the original memory-state temporal SCM or advisor approval for a pivot.", "",
            f"Actor: DeepSeek-V4-Pro; returned IDs: `{result['returned_models']}`. Six frozen episodes, 128 training calls each, 3 fresh calls per validation arm. Recorded job rows: {len(ledger)}/1020 (including failures).", "",
            "The 120-second transport attempt is archived. v2 reuses completed responses, including wrong ones; only failed or interrupted requests were recovered with a 300-second timeout. A final overlay allows one retry of newly failed infrastructure calls, never a semantic failure. Reused rows are not independent new calls; all attempts remain in cost accounting.", "",
            "## Independent actor checks", "",
            "| arm | correct / completed calls | complete episodes | episode accuracy | records | input proxy tokens | truncated |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    fmt = lambda x: "—" if x is None else f"{x:.3f}"
    for arm, t in table.items():
        text.append(f"| {arm} | {t['correct_calls']}/{t['completed_calls']} | {t['complete_episodes']}/6 | {fmt(t['episode_mean'])} | {fmt(t['mean_records'])} | {fmt(t['mean_input_proxy_tokens'])} | {t['first_truncations']} |")
    text += ["", "Full-read failure categories (computed from recorded scores, without new actor calls): `"
             + str(table.get("full", {}).get("failure_breakdown", {})) + "`. These are output error categories, not causal explanations of the model's internal reasoning."]
    text += ["", "## Learned top-2 minus each control", "",
             "Repeats are averaged within episode; intervals resample episodes within each of the three fixed seeds. Six episodes cannot support general claims about environments, models, or deployment.", "",
             "| control | paired episodes | delta | 95% conditional interval |", "|---|---:|---:|---|"]
    for arm, c in comparisons.items():
        text.append(f"| {arm} | {c['paired_episodes']} | {fmt(c['delta'])} | {c['ci95']} |")
    dc = result["discovery_cost"]
    text += ["", f"Discovery consumed {dc['fresh_training_calls']} completed training requests, "
             f"{dc['training_input_tokens']} input tokens and {dc['training_output_tokens']} output tokens. "
             "These costs belong to the learned method. The table's reduced selected input does not establish total cost savings; no cross-episode amortization is demonstrated."]
    text += ["", "## Frozen source audit: all cases", "",
             "The first segment is externally labeled disallowed; the final segment is a separate-source deletion control. These groups need not have equal record/token sizes. Source labels describe a constructed scenario, not a discovered real violation. The diagnostic rule additionally requires an inferred threshold edge from that source. Three repeats do not establish statistical significance.", "",
             "| episode | full | blocked source | neutral deletion | source changed | source edge | diagnostic rule |",
             "|---|---:|---:|---:|---:|---|---|"]
    for d in details:
        scores = [f"{d['results'].get(a, {}).get('correct', 0)}/{d['results'].get(a, {}).get('n', 0)}"
                  for a in ["full", "source_blocked", "neutral_blocked", "source_changed"]]
        edge = bool(d["fit"] and 0 in d["fit"]["threshold_parents"])
        text.append(f"| {d['episode']} | " + " | ".join(scores) + f" | {edge} | {d['source_audit_diagnostic_rule_passed']} |")
    text += ["", "The frozen +15-minute treatment translates both ends of historical time deltas. It can preserve difference-based policies such as pickup-minus-arrival, so an unchanged output under this treatment is not evidence of absent reliance. Full-read instability already prevents the intended normal-correct-output demonstration.", "",
             "There is no independent authorized retrieval tool in HM3. Blocking was executed as a read intervention; abstention is only a proposed fallback, not an implemented and independently validated safety controller. Relabeling identical content is not counted as an independently validated safe substitute.", "",
             "## Native memory-output variants", "",
             "Same tasks, actor, visible state, and output rules. The primary actor_v2 inputs restore exactly the shared state/query/system text after an insertion-order audit; cached native memories are unchanged, earlier actor outputs remain archived and excluded. Native top-8 entries are not equal records or tokens; A-Mem link expansion can include more entries. Native failures are separate from actor errors. This is not a strict matched-budget superiority comparison.", "",
             "| system | memory-completed episodes | complete actor episodes | correct / calls | write/read model calls | memory tokens in / out | actor tokens in / out |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for system, cells in native.items():
        text.append(f"| {system} | {sum(c['status']['status']=='completed' for c in cells)}/6 | {sum(c['actor_calls']==3 for c in cells)}/6 | {sum(c['correct'] for c in cells)}/{sum(c['actor_calls'] for c in cells)} | {sum(c['memory_calls'] for c in cells)} | {sum(c['memory_input_tokens'] for c in cells)} / {sum(c['memory_output_tokens'] for c in cells)} | {sum(c['actor_input_tokens'] for c in cells)} / {sum(c['actor_output_tokens'] for c in cells)} |")
    text += ["", "## Original-state representation and evidence limits", "",
             "| episode | segment transitions | numeric fields | changing fields |", "|---|---:|---:|---:|"]
    for s in result["state_panels"]:
        text.append(f"| {s['episode']} | {s['n_boundaries']-1} | {s['n_fields']} | {s['changing_fields']} |")
    text += ["", "These short trajectories do not provide enough independent transitions to justify estimating a full field-level SCM. Padding holds or pooling different object identities/regimes does not solve that problem. No new field-SCM recovery claim is made.", "",
             "Read-gate fitting uses oracle correctness labels for each episode and all 128 actor calls, with no amortized transfer. Gate directions are constrained by the known randomized experiment. Top-2 is a score ranking, including deterministic ties under constant outcomes; it is not a set of identified causal parents. G² asymptotic calibration may be poor in sparse conditional tables. API latency, mask coverage, coincident selections, and all failures remain in artifacts.", "",
             "A positive diagnostic is insufficient for Yujia's complete requirement: original temporal structure, independent memory utility, reliable correct-output auditing, and a representative real agent setting must connect under one defensible method.", ""]
    (root / "report.md").write_text("\n".join(text))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="results/real/hm3/alignment/continuation_pro_v2")
    p.add_argument("--native-root", default="results/real/hm3/alignment/continuation_memsys")
    args = p.parse_args()
    r = generate(Path(args.root), Path(args.native_root))
    print(json.dumps({"rows": r["actor_rows"], "arms": len(r["arms"])}))
