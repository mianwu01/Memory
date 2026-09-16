"""Run the train-only six-arm T1 experiment for all redesigned task families."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, Mapping


TASKS = {
    "dynamic_travel": ("causal_benchmarks.dynamic_travel", "evaluate_t1"),
    "dynamic_shopping": ("causal_benchmarks.dynamic_shopping", "run_t1_experiment"),
    "dynamic_search": ("causal_benchmarks.dynamic_search", "audit_t1"),
    "causal_formal": ("causal_benchmarks.causal_formal", "run_t1"),
}


def _without_episode_rows(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_episode_rows(item)
            for key, item in value.items()
            if key != "per_episode"
        }
    if isinstance(value, list):
        return [_without_episode_rows(item) for item in value]
    return value


def _search_chars(report: Mapping[str, Any], arm: str) -> float:
    row = next(
        row
        for row in report["selection_x_serialization"]
        if row["arm"] == arm and row["serialization"] == "compact"
    )
    return float(row["serialization_chars_mean"])


def _headline(task: str, report: Mapping[str, Any]) -> dict[str, Any]:
    if task == "dynamic_travel":
        learned = report["arms"]["learned_graph"]
        generic = report["arms"]["matched_lexical"]
        domain = report["arms"]["domain_solver"]
        full = report["arms"]["full_state"]
        chars = learned["serialization"]["compact"]["avg_context_chars"]
        full_chars = full["serialization"]["compact"]["avg_context_chars"]
        claim = report["admission"]["causal_learning_claim_pass"]
        novel = all(
            report["admission"][key]
            for key in (
                "unseen_entities",
                "unseen_numeric_intervention_values",
                "held_out_regime_combination",
            )
        )
        task_success = learned["task_success_rate"]
        domain_success = domain["task_success_rate"]
        generic_recall = generic["affected_recall"]
        learned_recall = learned["affected_recall"]
    elif task == "dynamic_shopping":
        learned = report["arms"]["learned_graph"]
        generic = report["arms"]["matched_retrieval"]
        domain = report["arms"]["domain_solver"]
        full = report["arms"]["full_state_history"]
        chars = learned["serialization"]["compact"]["characters"]
        full_chars = full["serialization"]["compact"]["characters"]
        claim = report["scientific_conclusion"]["causal_advantage_established"]
        novel = bool(
            report["novel_test"]["unseen_entity_episodes"]
            and report["novel_test"]["unseen_template_episodes"]
            and report["novel_test"]["unseen_value_episodes"]
            and report["novel_test"]["heldout_regime_combination_episodes"]
        )
        task_success = learned["task_success"]
        domain_success = domain["task_success"]
        generic_recall = generic["affected_recall"]
        learned_recall = learned["affected_recall"]
    elif task == "dynamic_search":
        learned = report["effects"]["learned_graph"]
        generic = report["effects"]["matched_lexical_structured"]
        domain = report["effects"]["provenance_domain"]
        chars = _search_chars(report, "learned_graph")
        full_chars = _search_chars(report, "full_history")
        claim = report["admission"]["supports_causal_learning_claim"]
        novel = report["novel_test"]["pass"]
        task_success = learned["final_answer_accuracy"]
        domain_success = domain["final_answer_accuracy"]
        generic_recall = generic["affected_recall"]
        learned_recall = learned["affected_recall"]
    elif task == "causal_formal":
        learned = report["arms"]["learned_graph"]["effectiveness"]
        generic = report["arms"]["matched_budget_retrieval"]["effectiveness"]
        domain = report["arms"]["program_dataflow"]["effectiveness"]
        chars = report["arms"]["learned_graph"]["serialization"]["compact"][
            "serialized_chars_mean"
        ]
        full_chars = report["arms"]["full_history"]["serialization"]["compact"][
            "serialized_chars_mean"
        ]
        claim = report["verdict"]["learned_graph_necessity_pass"]
        novel = not bool(report["leakage_audit"]["fit_eval_id_overlap"])
        task_success = learned["episode_success"]
        domain_success = domain["episode_success"]
        generic_recall = generic["affected_result_recall"]
        learned_recall = learned["affected_result_recall"]
    else:  # pragma: no cover
        raise ValueError(task)
    return {
        "novel_split_pass": bool(novel),
        "learned_affected_recall": learned_recall,
        "matched_retrieval_affected_recall": generic_recall,
        "learned_task_success": task_success,
        "domain_task_success": domain_success,
        "learned_compact_chars": chars,
        "full_compact_chars": full_chars,
        "efficiency_vs_full_fraction": chars / full_chars,
        "learned_beats_generic_retrieval": learned_recall > generic_recall,
        "learned_beats_domain_solver": task_success > domain_success,
        "causal_learning_claim_supported": bool(claim),
    }


def run_t1_suite(episodes: int = 120, seed: int = 17) -> dict[str, Any]:
    tasks: dict[str, Any] = {}
    for offset, (task, (module_name, evaluator_name)) in enumerate(TASKS.items()):
        module = importlib.import_module(module_name)
        dataset = module.generate_dataset(episodes=episodes, seed=seed + offset)
        report = getattr(module, evaluator_name)(dataset)
        tasks[task] = {
            "module": module_name,
            "headline": _headline(task, report),
            "report": _without_episode_rows(report),
        }
    return {
        "schema": "causal-memory-t1-suite/v1",
        "episodes_per_task": episodes,
        "seed": seed,
        "tasks": tasks,
        "all_novel_splits_pass": all(
            row["headline"]["novel_split_pass"] for row in tasks.values()
        ),
        "all_learned_beat_generic_retrieval": all(
            row["headline"]["learned_beats_generic_retrieval"]
            for row in tasks.values()
        ),
        "tasks_beating_domain_solver": [
            task
            for task, row in tasks.items()
            if row["headline"]["learned_beats_domain_solver"]
        ],
        "tasks_supporting_causal_learning_claim": [
            task
            for task, row in tasks.items()
            if row["headline"]["causal_learning_claim_supported"]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=120)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_t1_suite(episodes=args.episodes, seed=args.seed)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({task: row["headline"] for task, row in report["tasks"].items()}, indent=2))


if __name__ == "__main__":
    main()
