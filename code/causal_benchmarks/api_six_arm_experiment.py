"""Frozen six-arm real-API test for causal-memory selection and value update.

Unlike the decoder admission gate, this experiment never calls the oracle
``_task_packet`` to construct non-oracle masks.  Train-only learners and
runtime baselines first emit value-free :class:`SelectionPlan` objects.  The
prompt builder then looks up only pre-intervention values named by each plan.
Evaluator gold is accessed after API generation for scoring; the oracle arm is
isolated and may access graph structure, but never gold post-state values.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

from .api_decoder_experiment import (
    APIConfig,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    FAILURE_POLICY_REVISION,
    FORMAL_CARD,
    SEARCH_CARD,
    SHOPPING_RULES,
    SYSTEM_PROMPT,
    TASKS,
    TRAVEL_CARD,
    _atomic_json,
    _canonical,
    _digest,
    _read_jsonl,
    _run_cases,
    _shopping_runtime_resources,
    audit_and_rescore,
)
from .api_selection_plans import (
    ARM_NAMES,
    SelectionPlan,
    build_six_arm_plans,
    fit_learned_selector,
    validate_plan,
)
from .common import runtime_view


PROTOCOL_SCHEMA = "causal-api-six-arm-protocol/v1"
SUMMARY_SCHEMA = "causal-api-six-arm-summary/v1"
TASK_CARDS = {
    "dynamic_travel": TRAVEL_CARD,
    "dynamic_shopping": SHOPPING_RULES,
    "dynamic_search": SEARCH_CARD,
    "causal_formal": FORMAL_CARD,
}


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _plan_payload(
    task_family: str,
    view: Mapping[str, Any],
    plan: SelectionPlan,
) -> dict[str, Any]:
    if "gold" in view or "observed_transition" in view:
        raise ValueError("prompt construction requires an outcome-free inference view")
    validate_plan(plan, view, oracle_allowed=plan.arm == "oracle_graph")
    state = view["memory_state"]
    return {
        "episode_id": str(view["episode_id"]),
        "task": str(view["task"]),
        "task_rules": TASK_CARDS[task_family],
        "query": view["query"]["text"],
        "intervention": copy.deepcopy(view["query"]["intervention"]),
        "allowed_write_nodes": list(plan.predicted_write_nodes),
        "current_context_state": {
            node: copy.deepcopy(state[node]) for node in plan.selected_context_nodes
        },
        "selected_memory_records": [
            copy.deepcopy(view["history"][index])
            for index in plan.selected_history_ids
        ],
        "selected_dependency_edges": [
            {"source": edge.source, "target": edge.target, "label": edge.label}
            for edge in plan.selected_edges
        ],
        "runtime_resources": (
            _shopping_runtime_resources(view)
            if task_family == "dynamic_shopping"
            else None
        ),
    }


def validate_test_scope(
    cases: Sequence[Mapping[str, Any]], *, limit_per_task: int
) -> dict[str, Any]:
    """Require the exact pre-registered 4 x 12 x 6 novel-test matrix."""

    if limit_per_task != 12:
        raise ValueError("frozen test requires exactly 12 episodes per task family")
    expected_count = len(TASKS) * 12 * len(ARM_NAMES)
    if len(cases) != expected_count:
        raise ValueError(f"frozen test requires {expected_count} cases")
    request_ids = [str(case["request_id"]) for case in cases]
    if len(set(request_ids)) != len(request_ids):
        raise ValueError("test request ids are not unique")
    episode_seeds: dict[str, set[int]] = {}
    all_episode_seed_pairs: set[tuple[str, int]] = set()
    for task_family, _, _ in TASKS:
        task_cases = [case for case in cases if case["task_family"] == task_family]
        episode_ids = {str(case["episode_id"]) for case in task_cases}
        if len(episode_ids) != 12:
            raise ValueError(f"{task_family} does not have exactly 12 test episodes")
        for episode_id in episode_ids:
            episode_cases = [
                case for case in task_cases if str(case["episode_id"]) == episode_id
            ]
            if {str(case["arm"]) for case in episode_cases} != set(ARM_NAMES):
                raise ValueError(f"{episode_id} does not have exactly the six frozen arms")
            if len(episode_cases) != len(ARM_NAMES):
                raise ValueError(f"{episode_id} has duplicate arm cases")
            seeds = {int(case["decoder_seed"]) for case in episode_cases}
            if len(seeds) != 1:
                raise ValueError(f"{episode_id} arms do not share one decoder seed")
            episode_seeds[episode_id] = seeds
            all_episode_seed_pairs.add((episode_id, next(iter(seeds))))
    seeds_only = [seed for _, seed in all_episode_seed_pairs]
    if len(set(seeds_only)) != len(seeds_only):
        raise ValueError("decoder seeds collide across test episodes")
    return {
        "complete": True,
        "cases": len(cases),
        "task_families": len(TASKS),
        "episodes_per_task": 12,
        "arms_per_episode": len(ARM_NAMES),
        "unique_request_ids": len(set(request_ids)),
        "unique_episode_seeds": len(set(seeds_only)),
    }


def build_test_cases(
    *,
    episodes: int = 150,
    seed: int = 17,
    limit_per_task: int = 12,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Mapping[str, Any]],
    dict[str, dict[str, Any]],
]:
    """Fit on train transitions and build the frozen novel-test six-arm matrix."""

    cases: list[dict[str, Any]] = []
    evaluator_episodes: dict[str, Mapping[str, Any]] = {}
    learner_audit: dict[str, dict[str, Any]] = {}
    for task_family, module, offset in TASKS:
        dataset = module.generate_dataset(episodes=episodes, seed=seed + offset)
        train_views = [
            runtime_view(episode, training=True)
            for episode in dataset
            if episode["split"] == "train"
        ]
        if not train_views or any("observed_transition" not in view for view in train_views):
            raise ValueError(f"{task_family} has incomplete train transitions")
        learner = fit_learned_selector(task_family, train_views)
        test_episodes = [
            episode for episode in dataset if episode["split"] == "test"
        ][:limit_per_task]
        if len(test_episodes) < limit_per_task:
            raise ValueError(
                f"{task_family} has only {len(test_episodes)} test episodes; "
                f"requested {limit_per_task}"
            )
        learner_audit[task_family] = {
            "train_views": len(train_views),
            "train_episode_ids_sha256": _digest(
                sorted(str(view["episode_id"]) for view in train_views)
            ),
            "training_inputs": "runtime_view(training=True) observed transitions; no gold",
        }
        for episode_index, episode in enumerate(test_episodes):
            view = runtime_view(episode, training=False)
            if "gold" in view or "observed_transition" in view:
                raise AssertionError("test runtime projection leaked an outcome")
            plans = build_six_arm_plans(
                task_family,
                view,
                learner,
                oracle_episode=episode,
            )
            evaluator_episodes[str(episode["episode_id"])] = episode
            paired_seed = seed * 100_000 + offset * 1_000 + episode_index
            for arm in ARM_NAMES:
                plan = plans[arm]
                payload = _plan_payload(task_family, view, plan)
                request_id = f"{task_family}:{episode['episode_id']}:{arm}"
                # Normalize tuples to their on-disk JSON representation before
                # protocol equality checks; otherwise a freshly generated plan
                # compares unequal to the identical list-valued frozen JSON.
                plan_dict = json.loads(_canonical(plan.to_dict()))
                cases.append(
                    {
                        "request_id": request_id,
                        "task_family": task_family,
                        "task": str(view["task"]),
                        "episode_id": str(episode["episode_id"]),
                        "arm": arm,
                        "decoder_seed": paired_seed,
                        "write_nodes": list(plan.predicted_write_nodes),
                        "context_nodes": list(plan.selected_context_nodes),
                        "plan": plan_dict,
                        "plan_sha256": _digest(plan_dict),
                        "payload": payload,
                        "prompt_sha256": _digest(
                            {"system": SYSTEM_PROMPT, "user": _canonical(payload)}
                        ),
                    }
                )
    return cases, evaluator_episodes, learner_audit


def protocol_manifest(
    cases: Sequence[Mapping[str, Any]],
    learner_audit: Mapping[str, Any],
    dev_gate_summary: Mapping[str, Any],
    *,
    episodes: int,
    seed: int,
    limit: int,
    model: str,
    temperature: float,
    max_tokens: int,
    api_retries: int,
    base_url: str,
    timeout_seconds: float,
    workers: int,
    uncached_input_usd_per_million: float,
    cached_input_usd_per_million: float,
    output_usd_per_million: float,
) -> dict[str, Any]:
    scope_audit = validate_test_scope(cases, limit_per_task=limit)
    public_cases = [
        {
            key: copy.deepcopy(case[key])
            for key in (
                "request_id",
                "task_family",
                "task",
                "episode_id",
                "arm",
                "decoder_seed",
                "write_nodes",
                "context_nodes",
                "plan",
                "plan_sha256",
                "prompt_sha256",
            )
        }
        for case in cases
    ]
    shuffle_seed = seed + 1771
    execution_order = [str(case["request_id"]) for case in cases]
    random.Random(shuffle_seed).shuffle(execution_order)
    return {
        "schema": PROTOCOL_SCHEMA,
        "phase": "frozen_novel_test",
        "frozen_date": "2026-08-31",
        "failure_policy_revision": FAILURE_POLICY_REVISION,
        "experiment": "end_to_end_selection_plan_plus_api_value_decoder",
        "episodes_generated_per_task": episodes,
        "dataset_seed": seed,
        "test_episodes_per_task": limit,
        "task_families": sorted({str(case["task_family"]) for case in cases}),
        "arms": list(ARM_NAMES),
        "serialization": "compact_selected_state_records_edges/v1",
        "runtime": {
            "model": model,
            "base_url": base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "api_retries": api_retries,
            "timeout_seconds": timeout_seconds,
            "top_p": 1,
            "sdk_retries": 0,
            "workers": workers,
            "response_format": "json_object",
            "pricing_usd_per_million": {
                "uncached_input": uncached_input_usd_per_million,
                "cached_input": cached_input_usd_per_million,
                "output": output_usd_per_million,
            },
            "retry_backoff": (
                "1,2 seconds; total attempt budget shared by transport, empty, "
                "truncated, JSON-syntax, and type-level schema failures"
            ),
            "shuffle_seed": shuffle_seed,
            "execution_order_sha256": _digest(execution_order),
            "system_prompt_sha256": _digest(SYSTEM_PROMPT),
            "task_card_sha256": {
                task: _digest(card) for task, card in sorted(TASK_CARDS.items())
            },
        },
        "full_scope_audit": scope_audit,
        "dev_gate_prerequisite": {
            "protocol_case_manifest_sha256": dev_gate_summary.get(
                "protocol_case_manifest_sha256"
            ),
            "summary_sha256": _digest(dev_gate_summary),
            "all_task_decoder_gates_pass": dev_gate_summary.get(
                "all_task_decoder_gates_pass"
            ),
        },
        "learner_audit": copy.deepcopy(dict(learner_audit)),
        "selection_boundary": (
            "Non-oracle plans consume gold-free test runtime views and contain identifiers "
            "only. Oracle consumes evaluator potential-graph structure but no outcome "
            "values. Matched retrieval ranks nodes, history, and edges query-aware under "
            "separately matched learned-arm budgets."
        ),
        "gold_access": (
            "Oracle graph structure during oracle-plan construction; all outcome fields "
            "only after API generation for scoring."
        ),
        "invalid_response_policy": (
            "Transport, empty, truncated, JSON-syntax, and type-level schema failures "
            "receive at most the frozen retry budget with identical prompt and seed. "
            "Identity/node-set contract violations in structurally valid JSON are terminal "
            "semantic endpoint failures and are never retried. Unresolved engineering "
            "failures reduce coverage and are not semantic zeroes."
        ),
        "cases": public_cases,
        "case_manifest_sha256": _digest(public_cases),
    }


def _macro_selection(expected: set[str], predicted: set[str]) -> dict[str, float]:
    overlap = len(expected & predicted)
    precision = _safe_ratio(overlap, len(predicted))
    recall = _safe_ratio(overlap, len(expected))
    return {
        "precision": precision,
        "recall": recall,
        "f1": _safe_ratio(2 * precision * recall, precision + recall),
    }


def summarize_test(
    rows: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    evaluator_episodes: Mapping[str, Mapping[str, Any]],
    protocol: Mapping[str, Any],
    integrity_audit: Mapping[str, Any],
) -> dict[str, Any]:
    case_by_id = {str(case["request_id"]): case for case in cases}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        case = case_by_id[str(row["request_id"])]
        episode = evaluator_episodes[str(row["episode_id"])]
        expected = set(episode["gold"]["affected_nodes"])
        predicted = set(case["write_nodes"])
        selection = _macro_selection(expected, predicted)
        required_reads = set(episode["gold"].get("required_reads", []))
        context = set(case["context_nodes"])
        disclosed = set(context)
        resources = case["payload"].get("runtime_resources") or {}
        disclosed.update(
            f"availability.{item_id}"
            for item_id in resources.get("availability", {})
        )
        memory_context_recall = _safe_ratio(
            len(required_reads & context), len(required_reads)
        )
        context_recall = _safe_ratio(
            len(required_reads & disclosed), len(required_reads)
        )
        post = copy.deepcopy(episode["memory_state"])
        if row["semantic_scored"]:
            post.update(
                {
                    node: value
                    for node, value in row["updates"].items()
                    if node in post
                }
            )
        semantic_contract_failure = bool(
            row.get("semantic_contract_failure") is True
            or row.get("failure_class") == "semantic_contract"
            or row.get("semantic_contract_valid") is False
        )
        false_positive_overwrites = sum(
            node not in expected
            and node in row.get("updates", {})
            and row["updates"][node] != episode["memory_state"][node]
            for node in predicted
        ) if row["semantic_scored"] else 0
        item = {
            "row": row,
            "selection": selection,
            "memory_context_recall": memory_context_recall,
            "context_recall": context_recall,
            "selector_miss": bool(expected - predicted),
            "context_miss": bool(required_reads - disclosed),
            "value_error": bool(
                row["semantic_scored"]
                and (
                    semantic_contract_failure
                    or any(
                        node not in row["updates"]
                        or row["updates"][node]
                        != episode["gold"]["post_state"][node]
                        for node in predicted
                    )
                )
            ),
            "false_positive_overwrites": false_positive_overwrites,
            "semantic_contract_failure": semantic_contract_failure,
            "endpoint_success": bool(
                row["semantic_scored"]
                and not semantic_contract_failure
                and post == episode["gold"]["post_state"]
            ),
            "case": case,
        }
        groups.setdefault((str(row["task_family"]), str(row["arm"])), []).append(item)

    expected_case_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for case in cases:
        expected_case_groups.setdefault(
            (str(case["task_family"]), str(case["arm"])), []
        ).append(case)

    matrix: dict[str, dict[str, Any]] = {}
    for (task, arm), group_cases in sorted(expected_case_groups.items()):
        items = groups.get((task, arm), [])
        valid = [item for item in items if item["row"]["semantic_scored"]]
        expected_count = len(group_cases)
        received_ids = {str(item["row"]["request_id"]) for item in items}
        missing_request_ids = sorted(
            str(case["request_id"])
            for case in group_cases
            if str(case["request_id"]) not in received_ids
        )
        unresolved_engineering = [
            item for item in items if not bool(item["row"].get("semantic_scored"))
        ]
        semantic_contract_failures = [
            item for item in valid if item["semantic_contract_failure"]
        ]

        protocol_selection: list[dict[str, Any]] = []
        for case in group_cases:
            episode = evaluator_episodes[str(case["episode_id"])]
            expected = set(episode["gold"]["affected_nodes"])
            predicted = set(case["write_nodes"])
            required_reads = set(episode["gold"].get("required_reads", []))
            context = set(case["context_nodes"])
            disclosed = set(context)
            resources = case["payload"].get("runtime_resources") or {}
            disclosed.update(
                f"availability.{item_id}"
                for item_id in resources.get("availability", {})
            )
            protocol_selection.append(
                {
                    "selection": _macro_selection(expected, predicted),
                    "memory_context_recall": _safe_ratio(
                        len(required_reads & context), len(required_reads)
                    ),
                    "context_recall": _safe_ratio(
                        len(required_reads & disclosed), len(required_reads)
                    ),
                    "selector_miss": bool(expected - predicted),
                    "context_miss": bool(required_reads - disclosed),
                }
            )
        matrix.setdefault(task, {})[arm] = {
            "calls_expected": expected_count,
            "calls_received": len(items),
            "calls_missing": len(missing_request_ids),
            "missing_request_ids": missing_request_ids,
            "received_coverage": (
                len(items) / expected_count if expected_count else None
            ),
            "semantic_rows": len(valid),
            "semantic_coverage": (
                len(valid) / expected_count if expected_count else None
            ),
            "unresolved_engineering_rows": sorted(
                str(item["row"]["request_id"])
                for item in unresolved_engineering
            ),
            "unresolved_engineering_failures": len(unresolved_engineering),
            "semantic_contract_failure_rows": sorted(
                str(item["row"]["request_id"])
                for item in semantic_contract_failures
            ),
            "semantic_contract_failures": len(semantic_contract_failures),
            "selection_precision": _mean(
                [item["selection"]["precision"] for item in protocol_selection]
            ),
            "selection_recall": _mean(
                [item["selection"]["recall"] for item in protocol_selection]
            ),
            "selection_f1": _mean(
                [item["selection"]["f1"] for item in protocol_selection]
            ),
            "required_read_recall": _mean(
                [item["context_recall"] for item in protocol_selection]
            ),
            "memory_only_required_read_recall": _mean(
                [item["memory_context_recall"] for item in protocol_selection]
            ),
            "write_value_accuracy_valid_only": _mean(
                [
                    float(item["row"]["write_value_accuracy"])
                    for item in valid
                    if item["row"].get("write_value_accuracy") is not None
                ]
            ),
            "endpoint_success_valid_only": _mean(
                [float(item["endpoint_success"]) for item in valid]
            ),
            "selector_miss_episodes": sum(
                item["selector_miss"] for item in protocol_selection
            ),
            "context_miss_episodes": sum(
                item["context_miss"] for item in protocol_selection
            ),
            "value_error_episodes": sum(item["value_error"] for item in valid),
            "false_positive_overwrites": sum(
                item["false_positive_overwrites"] for item in valid
            ),
            "mean_write_nodes": _mean(
                [float(case["plan"]["write_budget"]) for case in group_cases]
            ),
            "mean_context_nodes": _mean(
                [float(case["plan"]["context_budget"]) for case in group_cases]
            ),
            "mean_history_records": _mean(
                [
                    float(len(case["plan"]["selected_history_ids"]))
                    for case in group_cases
                ]
            ),
            "mean_edges": _mean(
                [float(case["plan"]["edge_budget"]) for case in group_cases]
            ),
            "input_tokens": sum(
                int(item["row"].get("usage", {}).get("input_tokens", 0))
                for item in items
            ),
            "output_tokens": sum(
                int(item["row"].get("usage", {}).get("output_tokens", 0))
                for item in items
            ),
            "estimated_cost_usd": sum(
                float(item["row"].get("usage", {}).get("estimated_cost_usd", 0.0))
                for item in items
            ),
            "api_duration_seconds": sum(
                float(item["row"].get("api_duration_seconds", 0.0)) for item in items
            ),
        }

    expected_groups = {
        (task, arm)
        for task, _, _ in TASKS
        for arm in ARM_NAMES
    }
    received_groups = {
        (task, arm) for task, arms in matrix.items() for arm in arms
    }
    full_scope = (
        int(protocol["test_episodes_per_task"]) == 12
        and protocol.get("full_scope_audit", {}).get("complete") is True
        and len(cases)
        == len(TASKS) * len(ARM_NAMES) * int(protocol["test_episodes_per_task"])
        and received_groups == expected_groups
        and all(
            values["calls_received"] == values["calls_expected"]
            for arms in matrix.values()
            for values in arms.values()
        )
    )
    experiment_complete = bool(
        full_scope
        and integrity_audit.get("complete")
        and all(
            values["semantic_coverage"] == 1.0
            for arms in matrix.values()
            for values in arms.values()
        )
    )
    expected_request_ids = {str(case["request_id"]) for case in cases}
    received_request_ids = [str(row["request_id"]) for row in rows]
    received_request_id_set = set(received_request_ids)
    missing_request_ids = sorted(expected_request_ids - received_request_id_set)
    unexpected_request_ids = sorted(received_request_id_set - expected_request_ids)
    duplicate_request_ids = sorted(
        request_id
        for request_id in received_request_id_set
        if received_request_ids.count(request_id) > 1
    )
    expected_rows = [
        row for row in rows if str(row["request_id"]) in expected_request_ids
    ]
    semantic_rows = [row for row in expected_rows if row.get("semantic_scored")]
    unresolved_engineering_ids = sorted(
        str(row["request_id"])
        for row in expected_rows
        if not bool(row.get("semantic_scored"))
    )
    semantic_contract_failure_ids = sorted(
        str(row["request_id"])
        for row in semantic_rows
        if row.get("semantic_contract_failure") is True
        or row.get("failure_class") == "semantic_contract"
        or row.get("semantic_contract_valid") is False
    )
    return {
        "schema": SUMMARY_SCHEMA,
        "failure_policy_revision": FAILURE_POLICY_REVISION,
        "protocol_case_manifest_sha256": protocol["case_manifest_sha256"],
        "matrix": matrix,
        "manifest_audit": {
            "complete": not (
                missing_request_ids
                or unexpected_request_ids
                or duplicate_request_ids
            ),
            "calls_expected": len(expected_request_ids),
            "calls_received_unique": len(received_request_id_set & expected_request_ids),
            "missing_request_ids": missing_request_ids,
            "unexpected_request_ids": unexpected_request_ids,
            "duplicate_request_ids": duplicate_request_ids,
        },
        "coverage": {
            "calls_expected": len(expected_request_ids),
            "calls_received": len(expected_rows),
            "calls_missing": len(missing_request_ids),
            "received_coverage": (
                len(expected_rows) / len(expected_request_ids)
                if expected_request_ids
                else None
            ),
            "semantic_rows": len(semantic_rows),
            "semantic_coverage": (
                len(semantic_rows) / len(expected_request_ids)
                if expected_request_ids
                else None
            ),
        },
        "failure_classification": {
            "missing_request_ids": missing_request_ids,
            "unresolved_engineering_request_ids": unresolved_engineering_ids,
            "semantic_contract_failure_request_ids": semantic_contract_failure_ids,
            "unresolved_engineering_rows": len(unresolved_engineering_ids),
            "semantic_contract_failures": len(semantic_contract_failure_ids),
        },
        "integrity_audit": copy.deepcopy(dict(integrity_audit)),
        "full_scope_complete": full_scope,
        "experiment_complete": experiment_complete,
        "claim_boundary": (
            "This test measures value-free selection plans plus a real API decoder. "
            "Oracle is an evaluator upper bound; domain_solver is conservative potential "
            "reachability, not learned causal discovery. Valid semantic errors remain in "
            "endpoint metrics; unresolved engineering errors only reduce coverage."
        ),
        "failure_accounting": (
            "Only transport, empty, truncated, JSON-syntax, and type-level schema "
            "failures are retried. Missing and unresolved engineering rows are reported "
            "as coverage loss, never zero-filled. Structurally valid JSON contract "
            "violations are terminal semantic endpoint failures."
        ),
    }


def _load_dev_gate(path: Path, *, model: str, base_url: str) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("schema") != "causal-api-decoder-summary/v1":
        raise ValueError("wrong decoder dev-gate summary schema")
    if payload.get("failure_policy_revision") not in {
        None,
        FAILURE_POLICY_REVISION,
    }:
        raise ValueError("decoder dev-gate failure policy revision is incompatible")
    if not payload.get("all_task_decoder_gates_pass"):
        raise ValueError("the frozen four-task decoder dev gate did not pass")
    if not payload.get("integrity_audit", {}).get("complete"):
        raise ValueError("decoder dev-gate integrity audit is incomplete")
    if not payload.get("full_gate_scope_audit", {}).get("complete"):
        raise ValueError("decoder dev-gate scope audit is incomplete")
    if payload.get("integrity_audit", {}).get("protocol_cases") != 96:
        raise ValueError("decoder dev gate did not audit exactly 96 cases")
    manifest = payload.get("protocol_case_manifest_sha256")
    if not isinstance(manifest, str) or len(manifest) != 64:
        raise ValueError("decoder dev-gate manifest hash is invalid")
    if payload.get("model_requested") != model:
        raise ValueError("decoder dev-gate model differs from frozen test model")
    if payload.get("base_url") != base_url:
        raise ValueError("decoder dev-gate endpoint differs from frozen test endpoint")
    return payload


def _first_protocol_difference(left: Any, right: Any, path: str = "$") -> str:
    """Return one bounded, credential-free protocol mismatch diagnostic."""

    if type(left) is not type(right):
        return f"{path}: type {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                return f"{path}.{key}: key presence differs"
            difference = _first_protocol_difference(left[key], right[key], f"{path}.{key}")
            if difference:
                return difference
        return ""
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length {len(left)} != {len(right)}"
        for index, (first, second) in enumerate(zip(left, right)):
            difference = _first_protocol_difference(first, second, f"{path}[{index}]")
            if difference:
                return difference
        return ""
    if left != right:
        return f"{path}: {str(left)[:120]!r} != {str(right)[:120]!r}"
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=150)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--limit-per-task", type=int, default=12)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--api-retries", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--dev-gate-summary", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--results-jsonl", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    dev_gate = _load_dev_gate(
        args.dev_gate_summary, model=args.model, base_url=args.base_url
    )
    cases, evaluator_episodes, learner_audit = build_test_cases(
        episodes=args.episodes,
        seed=args.seed,
        limit_per_task=args.limit_per_task,
    )
    generated_protocol = protocol_manifest(
        cases,
        learner_audit,
        dev_gate,
        episodes=args.episodes,
        seed=args.seed,
        limit=args.limit_per_task,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        api_retries=args.api_retries,
        base_url=args.base_url,
        timeout_seconds=120.0,
        workers=args.workers,
        uncached_input_usd_per_million=2.5,
        cached_input_usd_per_million=0.25,
        output_usd_per_million=10.0,
    )
    if args.prepare_only:
        if args.protocol.exists():
            existing = json.loads(args.protocol.read_text())
            if existing != generated_protocol:
                raise SystemExit("refusing to overwrite a different frozen test protocol")
        else:
            _atomic_json(args.protocol, generated_protocol)
        print(json.dumps({
            "protocol": str(args.protocol),
            "cases": len(cases),
            "case_manifest_sha256": generated_protocol["case_manifest_sha256"],
        }, indent=2))
        return

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not configured")
    if not args.protocol.is_file():
        raise SystemExit("frozen --protocol is required before API execution")
    frozen = json.loads(args.protocol.read_text())
    if frozen != generated_protocol:
        raise SystemExit(
            "runtime test cases do not match frozen protocol; "
            + _first_protocol_difference(frozen, generated_protocol)
        )
    for required in (args.results_jsonl, args.ledger, args.summary):
        if required is None:
            raise SystemExit("--results-jsonl, --ledger and --summary are required")
    config = APIConfig(
        model=args.model,
        base_url=args.base_url,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_seconds=120.0,
        retries=args.api_retries,
        uncached_input_usd_per_million=2.5,
        cached_input_usd_per_million=0.25,
        output_usd_per_million=10.0,
    )
    order = list(cases)
    random.Random(args.seed + 1771).shuffle(order)
    rows = _run_cases(
        order,
        evaluator_episodes,
        config=config,
        ledger=args.ledger,
        results_jsonl=args.results_jsonl,
        workers=args.workers,
    )
    rescored, integrity = audit_and_rescore(
        rows,
        order,
        evaluator_episodes,
        _read_jsonl(args.ledger),
        config,
    )
    report = summarize_test(
        rescored,
        order,
        evaluator_episodes,
        frozen,
        integrity,
    )
    _atomic_json(args.summary, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
