"""Run the zero-LLM admission suite for all redesigned task prototypes."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any

try:
    from .common import SCHEMA_VERSION, validate_episode
except ImportError:
    from common import SCHEMA_VERSION, validate_episode  # type: ignore


TASK_MODULES = {
    "dynamic_travel": "causal_benchmarks.dynamic_travel",
    "dynamic_shopping": "causal_benchmarks.dynamic_shopping",
    "dynamic_search": "causal_benchmarks.dynamic_search",
    "causal_formal": "causal_benchmarks.causal_formal",
}


def _without_per_episode(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_per_episode(item)
            for key, item in value.items()
            if key != "per_episode"
        }
    if isinstance(value, list):
        return [_without_per_episode(item) for item in value]
    return value


def _headline(label: str, audit: dict[str, Any]) -> dict[str, Any]:
    if label == "dynamic_travel":
        exact, oracle = audit["exact_kv"], audit["oracle"]
        propagation = audit["propagation_fraction"]
        leakage = audit["downstream_query_leakage"]["rate"]
        task_success = exact["episode_success_rate"]
    elif label == "dynamic_shopping":
        exact, oracle = audit["exact_key"], audit["oracle_propagation"]
        propagation = exact["propagation_required_episodes"] / audit["episodes"]
        leakage = 1.0 - audit["diagnostics"]["hidden_downstream_rate"]
        task_success = exact["episode_success_rate"]
    elif label == "dynamic_search":
        exact = audit["baselines"]["exact_key"]
        oracle = audit["baselines"]["oracle_propagation"]
        propagation = audit["diagnostics"]["propagation_required_fraction"]
        leakage = audit["diagnostics"]["query_downstream_id_leakage"]
        task_success = exact["final_answer_accuracy"]
    elif label == "causal_formal":
        exact, oracle = audit["exact_key"], audit["oracle_propagation"]
        propagation = audit["propagation_required_rate"]
        leakage = audit["downstream_query_leakage"]["leaked"] / audit["episodes"]
        task_success = exact["episode_success"]
    else:  # pragma: no cover - TASK_MODULES is fixed above.
        raise ValueError(label)
    return {
        "propagation_required_fraction": propagation,
        "query_downstream_leakage": leakage,
        "exact_key_affected_recall": exact["affected_recall"],
        "exact_key_affected_state_accuracy": exact["affected_state_accuracy"],
        "exact_key_task_success": task_success,
        "oracle_affected_recall": oracle["affected_recall"],
        "oracle_affected_state_accuracy": oracle["affected_state_accuracy"],
    }


def run_suite(episodes: int = 120, seed: int = 17) -> dict[str, Any]:
    results = {}
    for offset, (label, module_name) in enumerate(TASK_MODULES.items()):
        module = importlib.import_module(module_name)
        dataset = module.generate_dataset(episodes=episodes, seed=seed + offset)
        for episode in dataset:
            validate_episode(episode)
        audit = module.audit_dataset(dataset)
        admission = audit.get("admission", {})
        results[label] = {
            "module": module_name,
            "episodes": len(dataset),
            "schema_valid": True,
            "admission_pass": bool(admission.get("pass", False)),
            "headline": _headline(label, audit),
            "audit": _without_per_episode(audit),
        }
    return {
        "schema": "causal-memory-redesign-suite/v1",
        "episode_schema": SCHEMA_VERSION,
        "episodes_per_task": episodes,
        "seed": seed,
        "all_schema_valid": all(row["schema_valid"] for row in results.values()),
        "all_admission_pass": all(row["admission_pass"] for row in results.values()),
        "tasks": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=120)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_suite(args.episodes, args.seed)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
