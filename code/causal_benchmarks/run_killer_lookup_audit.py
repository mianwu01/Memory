"""Run the reproducible dev-only lookup-shortcut admission audit.

This runner never scores test episodes.  It fits source-union and query-signature
lookups from runtime-visible train transitions, freezes predictions on outcome-
free dev runtime views, and only then lets the admission scorer read dev gold.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any, Sequence

from .api_selection_plans import audit_killer_lookups_on_dev
from .common import runtime_view


SCHEMA = "causal-killer-lookup-dev-audit/v1"
DEFAULT_OUT = Path(
    "results/development/causal_benchmarks/killer_lookup_dev_audit.json"
)
TASKS = (
    ("dynamic_travel", "causal_benchmarks.dynamic_travel", 0),
    ("dynamic_shopping", "causal_benchmarks.dynamic_shopping", 1),
    ("dynamic_search", "causal_benchmarks.dynamic_search", 2),
    ("causal_formal", "causal_benchmarks.causal_formal", 3),
)


def _digest_ids(episode_ids: Sequence[str]) -> str:
    payload = json.dumps(sorted(episode_ids), separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _headline(report: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "lookup_coverage",
        "affected_precision",
        "affected_recall",
        "affected_f1",
        "affected_exact_match",
        "sufficient_mask_rate",
        "propagation_exact_match",
        "propagation_sufficient_mask_rate",
        "unaffected_specificity",
        "mean_write_nodes",
        "mean_write_fraction",
        "query_only_stop_rule_triggered",
    )
    return {
        arm: {field: values[field] for field in fields}
        for arm, values in report["arms"].items()
    }


def run_killer_lookup_audit(
    episodes: int = 120,
    seed: int = 17,
) -> dict[str, Any]:
    """Return the four-task train-fit/dev-score admission report."""

    if episodes <= 0:
        raise ValueError("episodes must be positive")
    tasks: dict[str, Any] = {}
    for task_family, module_name, seed_offset in TASKS:
        task_seed = seed + seed_offset
        module = importlib.import_module(module_name)
        dataset = module.generate_dataset(episodes=episodes, seed=task_seed)
        train_episodes = [row for row in dataset if row["split"] == "train"]
        dev_episodes = [row for row in dataset if row["split"] == "dev"]
        test_count = sum(row["split"] == "test" for row in dataset)
        if not train_episodes or not dev_episodes:
            raise ValueError(
                f"{task_family} requires non-empty train and dev splits; "
                f"got train={len(train_episodes)}, dev={len(dev_episodes)}"
            )
        train_views = [
            runtime_view(episode, training=True) for episode in train_episodes
        ]
        admission = audit_killer_lookups_on_dev(
            task_family, train_views, dev_episodes
        )
        tasks[task_family] = {
            "module": module_name,
            "generator_binding": {
                "episodes_requested": episodes,
                "base_seed": seed,
                "seed_offset": seed_offset,
                "task_seed": task_seed,
                "train_episodes": len(train_episodes),
                "dev_episodes": len(dev_episodes),
                "test_episodes_not_scored": test_count,
                "train_episode_ids_sha256": _digest_ids(
                    [str(row["episode_id"]) for row in train_episodes]
                ),
                "dev_episode_ids_sha256": _digest_ids(
                    [str(row["episode_id"]) for row in dev_episodes]
                ),
            },
            "evaluation_split": "dev_only",
            "admission_schema": admission["schema"],
            "prediction_boundary": admission["prediction_boundary"],
            "headline": _headline(admission),
            "hidden_dependency_admission_pass": admission[
                "hidden_dependency_admission_pass"
            ],
        }

    blocking_tasks = [
        task
        for task, row in tasks.items()
        if not row["hidden_dependency_admission_pass"]
    ]
    return {
        "schema": SCHEMA,
        "purpose": (
            "Offline admission audit for source-union/query-signature shortcuts; "
            "not a seventh API arm and not test performance."
        ),
        "episodes_generated_per_task": episodes,
        "base_seed": seed,
        "task_seed_rule": "task_seed = base_seed + fixed TASKS seed_offset",
        "scored_split": "dev_only",
        "stop_rule": (
            "A baseline blocks hidden-dependency necessity when its dev "
            "propagation_sufficient_mask_rate is at least 0.95."
        ),
        "tasks": tasks,
        "tasks_triggering_stop_rule": blocking_tasks,
        "overall_stop_rule_triggered": bool(blocking_tasks),
        "hidden_dependency_suite_admission_pass": not blocking_tasks,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=120)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    report = run_killer_lookup_audit(episodes=args.episodes, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "out": str(args.out),
                "overall_stop_rule_triggered": report[
                    "overall_stop_rule_triggered"
                ],
                "tasks_triggering_stop_rule": report[
                    "tasks_triggering_stop_rule"
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
