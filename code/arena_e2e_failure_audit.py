"""Explain MemoryArena PS failures using the official evaluator's slot checks.

PS is an all-slots person-level pass, whereas SPS averages only slots inferred as
query constraints.  This audit makes that denominator difference visible and
also checks submission coverage and parse completeness.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from arena_e2e_inherit import target_cells_from_query

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

REPO = Path(__file__).resolve().parents[1]
ARENA = REPO / "benchmarks" / "MemoryArena"
DEFAULT_E2E = ARENA / "results" / "travel_e2e"


def submission_for(arm_dir: Path, model: str) -> Path:
    preferred = arm_dir / "submission" / f"{model}_submission.jsonl"
    if preferred.is_file():
        return preferred
    found = sorted((arm_dir / "submission").glob("*_submission.jsonl"))
    if len(found) != 1:
        raise FileNotFoundError(f"expected one submission under {arm_dir}")
    return found[0]


def audit_arm(eval_mod, arm_dir: Path, model: str) -> dict:
    submission = submission_for(arm_dir, model)
    gt, base_plans, group_counts = eval_mod.load_ground_truth()
    submitted = eval_mod.load_submissions(str(submission))
    submitted_names = {}
    submitted_queries = {}
    for line in submission.read_text().splitlines():
        row = json.loads(line)
        for person in row.get("persons", []):
            key = (row["id"], person.get("person_idx"))
            submitted_names[key] = person.get("name")
            submitted_queries[key] = person.get("query") or ""
    group_ids = sorted({key[0] for key in submitted})
    expected_keys = {key for key in gt if key[0] in group_ids}

    failures = Counter()
    constrained_failures = Counter()
    nonconstraint_failures = Counter()
    explicit_target_failures = Counter()
    inherited_slot_failures = Counter()
    distribution = Counter()
    full_pass = 0
    unparseable = 0
    invalid_day_sets = 0
    only_constrained = 0
    only_nonconstraint = 0
    both = 0
    person_failure_details = []

    for key in sorted(expected_keys):
        plan = submitted.get(key)
        truth = gt.get(key)
        if not plan:
            unparseable += 1
        days = {day.get("day") or day.get("days") for day in (plan or [])}
        if days != {1, 2, 3}:
            invalid_day_sets += 1

        constrained_slots = eval_mod.find_constraint_slots(
            gt, base_plans, key[0], key[1])
        explicit_targets = target_cells_from_query(submitted_queries.get(key, ""))
        constrained_for_person = 0
        nonconstraint_for_person = 0
        n_failed = 0
        failed_slots = []
        for truth_day in truth or []:
            day_idx = truth_day.get("days") or truth_day.get("day")
            for slot in eval_mod.SLOTS:
                if eval_mod.check_slot_pass(truth, plan, day_idx, slot):
                    continue
                n_failed += 1
                failures[slot] += 1
                is_constraint = (day_idx, slot) in constrained_slots
                is_explicit_target = (day_idx, slot) in explicit_targets
                failed_slots.append({
                    "day": day_idx,
                    "slot": slot,
                    "query_constraint": is_constraint,
                    "query_explicit_target": is_explicit_target,
                })
                if is_explicit_target:
                    explicit_target_failures[slot] += 1
                else:
                    inherited_slot_failures[slot] += 1
                if is_constraint:
                    constrained_failures[slot] += 1
                    constrained_for_person += 1
                else:
                    nonconstraint_failures[slot] += 1
                    nonconstraint_for_person += 1
        distribution[n_failed] += 1
        if n_failed == 0:
            full_pass += 1
        elif constrained_for_person and nonconstraint_for_person:
            both += 1
        elif constrained_for_person:
            only_constrained += 1
        else:
            only_nonconstraint += 1
        person_failure_details.append({
            "data_idx": key[0],
            "person_idx": key[1],
            "name": submitted_names.get(key),
            "n_failed_slots": n_failed,
            "n_constraint_failures": constrained_for_person,
            "n_nonconstraint_failures": nonconstraint_for_person,
            "failed_slots": failed_slots,
        })

    person_failure_details.sort(
        key=lambda row: (row["n_failed_slots"], row["data_idx"], row["person_idx"]))

    return {
        "submission": str(submission),
        "episode_ids": group_ids,
        "expected_persons": sum(group_counts[i] for i in group_ids),
        "submitted_persons": len(submitted),
        "missing_persons": len(expected_keys - set(submitted)),
        "extra_persons": len(set(submitted) - expected_keys),
        "full_pass_persons": full_pass,
        "ps": 100 * full_pass / len(expected_keys) if expected_keys else 0.0,
        "unparseable_or_empty_plans": unparseable,
        "invalid_day_sets": invalid_day_sets,
        "persons_failing_only_query_constraints": only_constrained,
        "persons_failing_only_nonconstraint_slots": only_nonconstraint,
        "persons_failing_both": both,
        "failed_slot_count_distribution": {
            str(k): distribution[k] for k in sorted(distribution)},
        "closest_failed_persons": [
            row for row in person_failure_details if row["n_failed_slots"] > 0
        ][:5],
        "person_failure_details": person_failure_details,
        "failures_by_slot": dict(failures),
        "constrained_failures_by_slot": dict(constrained_failures),
        "nonconstraint_failures_by_slot": dict(nonconstraint_failures),
        "explicit_target_failures_by_slot": dict(explicit_target_failures),
        "inherited_slot_failures_by_slot": dict(inherited_slot_failures),
        "total_constrained_failures": sum(constrained_failures.values()),
        "total_nonconstraint_failures": sum(nonconstraint_failures.values()),
        "total_explicit_target_failures": sum(explicit_target_failures.values()),
        "total_inherited_slot_failures": sum(inherited_slot_failures.values()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", required=True)
    ap.add_argument("--e2e_dir", default=str(DEFAULT_E2E))
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--out", default="results/real/e2e_failure_audit.json")
    args = ap.parse_args()

    sys.path.insert(0, str(ARENA))
    cwd = Path.cwd()
    try:
        os.chdir(ARENA)
        from env.env_systems.travel_planner_env import eval as official_eval

        e2e_dir = Path(args.e2e_dir).resolve()
        report = {
            arm: audit_arm(official_eval, e2e_dir / arm, args.model)
            for arm in args.arms
        }
    finally:
        os.chdir(cwd)

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    for arm, row in report.items():
        print(
            f"{arm}: PS {row['full_pass_persons']}/{row['expected_persons']}; "
            f"constraint failures {row['total_constrained_failures']}; "
            f"nonconstraint failures {row['total_nonconstraint_failures']}; "
            f"explicit-target failures {row['total_explicit_target_failures']}; "
            f"inherited-slot failures {row['total_inherited_slot_failures']}; "
            f"unparseable {row['unparseable_or_empty_plans']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
