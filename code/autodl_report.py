"""Integrity-first official scoring for the registered AutoDL Travel campaign.

Repeats are averaged within each independent episode before paired bootstrap.
Incomplete scope produces a coverage and cost report, never a partial ranking.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import contextlib
import hashlib
import io
import json
from pathlib import Path
import statistics
import time

from faithful_memory import ROOT, environment
from faithful_report import events, usage


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def combine_usage(summaries):
    """Sum small usage records; never keep thousands of prompt logs in RAM."""
    total = usage([])
    for summary in summaries:
        for key, value in summary.items():
            if key == "phases":
                for phase, values in value.items():
                    target = total["phases"].setdefault(phase, {})
                    for metric, amount in values.items():
                        target[metric] = target.get(metric, 0) + amount
            else:
                total[key] = total.get(key, 0) + value
    return total


def checked_child(parent, relative):
    result = (parent / relative).resolve()
    if parent.resolve() not in result.parents:
        raise ValueError("Artifact path escapes its parent")
    return result


def registered_cases(protocol):
    """Reject missing, duplicate, or differently named registered cases."""
    ids = protocol["episode_ids"]
    repeats = protocol["repeats"]
    if len(ids) != len(set(ids)) or not ids or repeats < 1:
        raise ValueError("Invalid episode or repeat scope")
    expected = {}
    for variant, arms in protocol["variants"].items():
        if len(arms) != len(set(arms)):
            raise ValueError("Duplicate registered arm")
        for arm in arms:
            for ident in ids:
                for repeat in range(repeats):
                    key = f"{variant}/{arm}/{ident}/r{repeat}"
                    expected[key] = dict(key=key, variant=variant, arm=arm,
                                         id=ident, repeat=repeat)
    listed = protocol["cases"]
    if len(listed) != len(expected) or {c["key"] for c in listed} != set(expected):
        raise ValueError("Case list differs from the registered factorial scope")
    for case in listed:
        if any(case[k] != v for k, v in expected[case["key"]].items()):
            raise ValueError("Case metadata differs from its key")
    return listed


def select_attempt(base, case):
    folder = checked_child(base / "cases", case["key"])
    state_path = folder / "case_state.json"
    state = read_json(state_path) if state_path.exists() else {}
    selected = state.get("selected_attempt") or "attempt_0"
    attempt = checked_child(folder, selected)
    if attempt.parent != folder.resolve() or not attempt.name.startswith("attempt_"):
        raise ValueError("Invalid selected attempt")
    return folder, attempt, state


def validate_case(folder, case, protocol, expected_people, actor_hashes):
    status = read_json(folder / "status.json")
    if status.get("complete") is not True:
        raise ValueError("Incomplete method execution")
    if status.get("arm") != case["arm"] or status.get("id") != case["id"]:
        raise ValueError("Status case identity mismatch")
    prov = read_json(folder / "provenance.json")
    for name, sha in prov["source_hashes"].items():
        if protocol["source_hashes"].get(name) != sha:
            raise ValueError(f"Generation source differs from freeze: {name}")
    for key in ("model", "endpoint", "actor_thinking"):
        if prov[key] != protocol[key]:
            raise ValueError(f"Generation setting differs from freeze: {key}")
    for key in ("variant", "repeat"):
        if key in prov and prov[key] != case[key]:
            raise ValueError(f"Generation identity differs: {key}")
    if "graph_sha256" in prov and prov["graph_sha256"] != protocol["graph_sha256"]:
        raise ValueError("Generation graph differs from freeze")
    rows = events(folder / "events.jsonl")
    counts = Counter(row["event"] for row in rows)
    if dict(counts) != status["counts"] or counts.get("invalid", 0):
        raise ValueError("Event integrity failure")
    contract = [row for row in rows if row["event"] == "actor_contract"]
    if len(contract) != 1 or contract[0]["hashes"] != actor_hashes:
        raise ValueError("Original actor contract mismatch")
    if any(contract[0][key] for key in ("custom_decoder", "custom_prompt", "tool_filter")):
        raise ValueError("Custom actor behavior")
    if any(row["phase"] != "actor" and choice["finish_reason"] == "length"
           for row in rows if row["event"] == "llm" for choice in row["choices"]):
        raise ValueError("Incomplete memory operation")
    submissions = list((folder / "plans/submission").glob("*_submission.jsonl"))
    if len(submissions) != 1:
        raise ValueError("Ambiguous submission")
    records = [json.loads(line) for line in submissions[0].read_text().splitlines() if line.strip()]
    if len(records) != 1 or records[0]["id"] != case["id"]:
        raise ValueError("Submission episode mismatch")
    person_ids = [person["person_idx"] for person in records[0]["persons"]]
    if len(person_ids) != len(set(person_ids)) or set(person_ids) != expected_people:
        raise ValueError("Submission drops or duplicates people from official denominator")
    hashes = {str(path.relative_to(folder)): digest(path) for path in
              [folder / "status.json", folder / "provenance.json", folder / "events.jsonl", submissions[0]]}
    return records[0], rows, hashes


def episode_average(repeat_rows):
    """One statistical unit per episode, irrespective of repeat count."""
    id_sets = [set(row) for row in repeat_rows]
    if not id_sets or any(ids != id_sets[0] for ids in id_sets[1:]):
        raise ValueError("Repeat episode sets differ")
    return {ident: {metric: statistics.mean(row[ident][metric] for row in repeat_rows)
                    for metric in ("ps", "sps", "sr")}
            for ident in sorted(id_sets[0], key=int)}


def matched_coverage(cases, accepted, variants):
    result = {}
    for variant, arms in variants.items():
        grouped = defaultdict(set)
        wanted = defaultdict(set)
        for case in cases:
            if case["variant"] != variant:
                continue
            ident = str(case["id"])
            wanted[ident].add(case["key"])
            if case["key"] in accepted:
                grouped[ident].add(case["key"])
        result[variant] = {"complete_episode_blocks": sorted(
            (int(ident) for ident in wanted if grouped[ident] == wanted[ident])),
            "expected_episode_blocks": len(wanted), "arms": arms}
    return result


def collect(base):
    base = Path(base).resolve()
    protocol = read_json(base / "protocol.json")
    if protocol["schema"] != "autodl-travel-campaign/v1":
        raise ValueError("Unsupported campaign schema")
    cases = registered_cases(protocol)
    environment()
    from env.env_systems.travel_planner_env import eval as official
    from arena_e2e_score import bootstrap_mean_ci, per_episode_metrics
    gt, _, _ = official.load_ground_truth()
    expected_people = defaultdict(set)
    for ident, person in gt:
        expected_people[ident].add(person)
    actor_hashes = {str(path.relative_to(ROOT)): digest(path) for path in (
        ROOT / "benchmarks/MemoryArena/agent/travel_planner.py",
        ROOT / "benchmarks/MemoryArena/env/env_systems/travel_planner_env/prompts.py",
        ROOT / "benchmarks/MemoryArena/env/env_systems/travel_planner_env/tool_schemas.py")}
    graph = Path(protocol["graph_path"])
    if not graph.is_absolute():
        graph = ROOT / graph
    if digest(graph) != protocol["graph_sha256"]:
        raise ValueError("Graph artifact differs from freeze")
    expected_data = protocol["source_hashes"].get("dataset:MemoryArena")
    if expected_data:
        actual_data = hashlib.sha256(json.dumps(official.load_travel_data(), sort_keys=True,
                                                ensure_ascii=False).encode()).hexdigest()
        if actual_data != expected_data:
            raise ValueError("Official dataset differs from freeze")
    report = dict(schema="autodl-travel-report/v1", complete=False, created_at=time.time(),
                  protocol_sha256=digest(base / "protocol.json"), interpretation=protocol["interpretation"],
                  expected_cases=len(cases), accepted_cases=0, errors=[], cases={}, panels={},
                  statistical_unit="independent episode; average API repeats before paired bootstrap",
                  invoice_verified=False)
    accepted, all_attempt_usage, seen_instances = {}, [], set()
    for case in cases:
        key = case["key"]
        try:
            case_folder, attempt, state = select_attempt(base, case)
            # Charge every attempt, including failed and superseded attempts.
            for candidate in sorted(case_folder.glob("attempt_*")):
                path = candidate / "events.jsonl"
                if not path.exists():
                    continue
                attempt_rows = events(path, active=True)
                if attempt_rows:
                    instance = attempt_rows[0]["instance"]
                    if instance in seen_instances:
                        raise ValueError("Duplicate attempt instance; refusing double counting")
                    seen_instances.add(instance)
                    all_attempt_usage.append(usage(attempt_rows))
            report["cases"][key] = {"state": state.get("state", "unreported"),
                                    "selected_attempt": attempt.name}
            if state and state.get("state") != "complete":
                raise ValueError("Case state is not complete")
            record, rows, hashes = validate_case(attempt, case, protocol,
                                                expected_people[case["id"]], actor_hashes)
            accepted[key] = record
            report["cases"][key].update(accepted=True, artifact_sha256=hashes,
                usage=usage(rows), retrieved_text_characters=sum(len(row.get("text", ""))
                    for row in rows if row["event"] == "retrieve"))
        except (FileNotFoundError, KeyError, ValueError) as exc:
            report["errors"].append({"key": key, "error": str(exc)})
    report["accepted_cases"] = len(accepted)
    report["all_attempt_usage"] = combine_usage(all_attempt_usage)
    report["coverage"] = matched_coverage(cases, accepted, protocol["variants"])
    # This output is safe to refresh while workers are running.
    if len(accepted) != len(cases) or report["errors"]:
        report["scope_note"] = "Incomplete registered scope: coverage and accounting only; no partial ranking."
        (base / "progress_report.json").write_text(json.dumps(report, indent=2))
        return report
    analysis = base / "analysis"
    analysis.mkdir(exist_ok=True)
    for variant, arms in protocol["variants"].items():
        panel = {"arms": {}, "paired_comparisons": {}}
        for arm in arms:
            repeat_metrics, repeated_episodes = [], []
            consumption = []
            for repeat in range(protocol["repeats"]):
                keys = [f"{variant}/{arm}/{ident}/r{repeat}" for ident in protocol["episode_ids"]]
                records = [accepted[key] for key in keys]
                consumption.extend(report["cases"][key]["usage"] for key in keys)
                submission = analysis / f"{variant}_{arm}_r{repeat}_submission.jsonl"
                submission.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records))
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured):
                    repeat_metrics.append(official.evaluate(str(submission), model_name=protocol["model"], memory_system=arm))
                    repeated_episodes.append(per_episode_metrics(official, submission))
                (analysis / f"{variant}_{arm}_r{repeat}_evaluator.txt").write_text(captured.getvalue())
            per_episode = episode_average(repeated_episodes)
            panel["arms"][arm] = dict(
                official_metrics={metric: statistics.mean(row[metric] for row in repeat_metrics)
                                  for metric in ("ps", "sps", "sr")},
                per_repeat_official_metrics=repeat_metrics,
                per_episode_repeat_mean=per_episode, per_repeat_episode_metrics=repeated_episodes,
                episode_mean={metric: statistics.mean(row[metric] for row in per_episode.values())
                              for metric in ("ps", "sps", "sr")}, usage=combine_usage(consumption))
        if "ours" in arms:
            left = panel["arms"]["ours"]["per_episode_repeat_mean"]
            for baseline in (arm for arm in arms if arm != "ours"):
                right = panel["arms"][baseline]["per_episode_repeat_mean"]
                comparison = {}
                for metric in ("ps", "sps", "sr"):
                    differences = {ident: left[ident][metric] - right[ident][metric] for ident in left}
                    comparison[metric] = dict(episode_deltas=differences,
                        mean_delta_points=statistics.mean(differences.values()),
                        bootstrap_95=bootstrap_mean_ci(list(differences.values()), seed=20260918))
                panel["paired_comparisons"]["ours_minus_" + baseline] = comparison
        report["panels"][variant] = panel
    report.update(complete=True, analysis_sha256=digest(Path(__file__)))
    (base / "paired_results.json").write_text(json.dumps(report, indent=2))
    lines = ["# AutoDL Travel 配对结果", "", protocol["interpretation"], "",
             "PS/SPS/SR 采用官方评分；API 重复先在 episode 内平均，再按 episode 进行配对 bootstrap。", "",
             "| 条件 | 方法 | PS % | SPS % | SR % | 输入 tokens | 输出 tokens | 无报价调用 |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for variant, panel in report["panels"].items():
        for arm, result in panel["arms"].items():
            metrics, consumption = result["official_metrics"], result["usage"]
            lines.append(f"| {variant} | {arm} | {metrics['ps']:.2f} | {metrics['sps']:.2f} | {metrics['sr']:.2f} | "
                         f"{consumption['input_tokens']} | {consumption['output_tokens']} | {consumption['unpriced_calls']} |")
    lines += ["", "费用：仅保存 provider 明确返回的金额；未知单价不套用其他供应商价格。",
              "失败及被替代的尝试纳入 all_attempt_usage；表格中的 usage 属于选定有效尝试。"]
    (base / "results.md").write_text("\n".join(lines) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.base)
    print(json.dumps({key: report[key] for key in
                      ("complete", "expected_cases", "accepted_cases", "coverage", "all_attempt_usage")}, indent=2))
    if not report["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
