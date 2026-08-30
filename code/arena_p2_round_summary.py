"""Validate and summarize the frozen MemoryArena compact-v3 held-out matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METRICS = ("ps", "sps", "sr")


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def bootstrap_mean_ci(values: list[float], seed: int,
                      n_boot: int = 10000) -> list[float]:
    rng = random.Random(seed)
    n = len(values)
    samples = sorted(
        sum(rng.choice(values) for _ in range(n)) / n for _ in range(n_boot))
    return [samples[int(0.025 * (n_boot - 1))],
            samples[int(0.975 * (n_boot - 1))]]


def compare(left: dict, right: dict, seed_offset: int) -> dict:
    ids = sorted(set(left["per_episode"]) & set(right["per_episode"]), key=int)
    metrics = {}
    for metric_index, metric in enumerate(METRICS):
        deltas = [
            float(left["per_episode"][episode][metric])
            - float(right["per_episode"][episode][metric])
            for episode in ids
        ]
        metrics[metric] = {
            "episode_deltas": dict(zip(ids, deltas)),
            "episode_mean_delta_points": sum(deltas) / len(deltas),
            "episode_bootstrap_95": bootstrap_mean_ci(
                deltas, seed=4100 + seed_offset * 10 + metric_index),
            "wins": sum(value > 1e-12 for value in deltas),
            "ties": sum(abs(value) <= 1e-12 for value in deltas),
            "losses": sum(value < -1e-12 for value in deltas),
            "overall_delta_points": (
                float(left["metrics"][metric]) - float(right["metrics"][metric])),
        }
    return {"episode_ids": ids, "n_episodes": len(ids), "metrics": metrics}


def usage_projection(arm: dict) -> dict:
    call_usage = arm.get("call_usage") or {}
    upstream = arm.get("usage") or {}
    return {
        "source": call_usage.get("source"),
        "aggregation": call_usage.get("aggregation"),
        "calls": call_usage.get("calls"),
        "input_tokens": call_usage.get("total_input_tokens"),
        "output_tokens": call_usage.get("total_output_tokens"),
        "cost": call_usage.get("total_cost"),
        "api_duration_seconds": call_usage.get("api_duration_seconds"),
        "wall_duration_seconds": upstream.get("duration_seconds"),
        "thinking_modes": call_usage.get("thinking_modes"),
        "returned_models": call_usage.get("returned_models"),
        "repair_calls": call_usage.get("repair_calls"),
        "finish_reasons": call_usage.get("finish_reasons"),
        "covered_episode_ids": call_usage.get("covered_episode_ids"),
        "missing_completed_episode_ids": call_usage.get(
            "missing_completed_episode_ids"),
        "malformed_ledger_lines": call_usage.get("malformed_ledger_lines"),
        "selected_attempts": call_usage.get("selected_attempts"),
        "per_episode": call_usage.get("per_episode"),
    }


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--pure", required=True)
    parser.add_argument("--nog", required=True)
    parser.add_argument("--bm25", required=True)
    parser.add_argument("--long-context", dest="long_context", required=True)
    parser.add_argument("--expected-ids", type=int, nargs="+", required=True)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--configs", nargs=4, required=True)
    parser.add_argument("--protocol-document", required=True)
    parser.add_argument(
        "--frozen-protocol",
        default="results/real/p2_compact_v3/frozen_protocol.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    scores = json.loads((ROOT / args.input).read_text())
    frozen_protocol_path = (ROOT / args.frozen_protocol).resolve()
    frozen_protocol = json.loads(frozen_protocol_path.read_text())
    arm_names = {
        "pure": args.pure, "noG": args.nog, "bm25": args.bm25,
        "long_context": args.long_context,
    }
    expected = [str(value) for value in args.expected_ids]
    expected_set = set(expected)
    if [str(value) for value in frozen_protocol["heldout_episode_ids"]] != expected:
        raise ValueError("requested held-out IDs do not match the frozen protocol")
    if frozen_protocol["protocol_document"] != args.protocol_document:
        raise ValueError("protocol document path does not match the frozen protocol")
    protocol_document_path = (ROOT / args.protocol_document).resolve()
    if file_hash(protocol_document_path) != frozen_protocol[
            "protocol_document_sha256"]:
        raise ValueError("protocol document changed after the matrix was frozen")
    if frozen_protocol["arm_order"] != list(arm_names):
        raise ValueError("arm labels/order do not match the frozen protocol")
    for label, name in arm_names.items():
        if frozen_protocol["arms"][label]["arm"] != name:
            raise ValueError(f"{label} arm does not match the frozen protocol")
    matrix = {}
    for label, name in arm_names.items():
        if name not in scores or "metrics" not in scores[name]:
            raise ValueError(f"missing scored arm {name!r}")
        arm = scores[name]
        observed = set(str(value) for value in arm["episode_ids"])
        call_usage = arm.get("call_usage") or {}
        covered = set(str(value) for value in call_usage.get("covered_episode_ids", []))
        if observed != expected_set or covered != expected_set:
            raise ValueError(
                f"incomplete {name}: episodes={sorted(observed)} usage={sorted(covered)}")
        if call_usage.get("missing_completed_episode_ids"):
            raise ValueError(
                f"usage ledger reports missing completed episodes for {name}: "
                f"{call_usage['missing_completed_episode_ids']}")
        if int(call_usage.get("malformed_ledger_lines", -1)) != 0:
            raise ValueError(
                f"usage ledger has malformed lines for {name}: "
                f"{call_usage.get('malformed_ledger_lines')}")
        matrix[label] = {
            "arm": name, "metrics": arm["metrics"],
            "per_episode": arm["per_episode"], "usage": usage_projection(arm),
        }

    graph_path = (ROOT / args.graph).resolve()
    graph = json.loads(graph_path.read_text())
    graph_excluded = set(str(value) for value in graph.get("excluded_episode_ids", []))
    if not expected_set <= graph_excluded:
        raise ValueError("held-out IDs are not all excluded from graph/persistence learning")
    frozen_graph = frozen_protocol["graph_learning"]["plugin_graph"]
    if ((ROOT / frozen_graph["path"]).resolve() != graph_path
            or frozen_graph["sha256"] != file_hash(graph_path)):
        raise ValueError("graph artifact does not match the frozen protocol")
    frozen_typegraph = frozen_protocol["graph_learning"]["typegraph"]
    typegraph_path = (ROOT / frozen_typegraph["path"]).resolve()
    typegraph = json.loads(typegraph_path.read_text())
    if frozen_typegraph["sha256"] != file_hash(typegraph_path):
        raise ValueError("typegraph artifact does not match the frozen protocol")
    if (set(str(value) for value in typegraph.get("excluded_episode_ids", []))
            != expected_set):
        raise ValueError("typegraph exclusion set differs from held-out IDs")
    if int(typegraph.get("n_episodes", -1)) != int(
            frozen_protocol["graph_learning"]["n_episodes"]):
        raise ValueError("typegraph learning coverage differs from frozen protocol")

    configs = []
    fairness_rows = []
    for label, item in zip(arm_names, args.configs):
        path = (ROOT / item).resolve()
        cfg = json.loads(path.read_text())
        fairness = {
            "model": cfg["agent"]["model_name"],
            "decoder": cfg["task_specific"]["decoder"],
            "max_steps": cfg["task_specific"]["max_steps"],
            "llm_max_tokens": cfg["task_specific"].get("llm_max_tokens", 8192),
            "llm_thinking": cfg["task_specific"].get("llm_thinking", "default"),
            "env_name": cfg["env"]["env_name"],
            "env_config": cfg["env"].get("env_config", {}),
        }
        fairness_rows.append(fairness)
        config_sha256 = file_hash(path)
        frozen_arm = frozen_protocol["arms"][label]
        if ((ROOT / frozen_arm["config"]).resolve() != path
                or frozen_arm["config_sha256"] != config_sha256):
            raise ValueError(f"{label} config does not match the frozen protocol")
        configs.append({"path": str(path), "sha256": config_sha256, **fairness})
    if any(row != fairness_rows[0] for row in fairness_rows[1:]):
        raise ValueError(f"four-arm decoder/model/max-step/env mismatch: {fairness_rows}")
    frozen_runtime = frozen_protocol["shared_runtime"]
    for key in ("model", "decoder", "max_steps", "llm_max_tokens",
                "llm_thinking", "env_name"):
        if fairness_rows[0][key] != frozen_runtime[key]:
            raise ValueError(f"shared runtime {key} differs from frozen protocol")

    runtime_audit = {}
    expected_thinking = fairness_rows[0]["llm_thinking"]
    expected_model = fairness_rows[0]["model"]
    for label, arm in matrix.items():
        modes = arm["usage"].get("thinking_modes") or []
        returned = arm["usage"].get("returned_models") or []
        if modes != [expected_thinking]:
            raise ValueError(
                f"{label} actual thinking modes {modes} != {[expected_thinking]}")
        if returned != [expected_model]:
            raise ValueError(
                f"{label} returned models {returned} != {[expected_model]}")
        runtime_audit[label] = {
            "thinking_modes": modes,
            "returned_models": returned,
            "repair_calls": arm["usage"].get("repair_calls"),
            "finish_reasons": arm["usage"].get("finish_reasons"),
        }

    comparisons = {
        "pure_minus_noG": compare(scores[args.pure], scores[args.nog], 0),
        "pure_minus_bm25": compare(scores[args.pure], scores[args.bm25], 1),
        "pure_minus_long_context": compare(
            scores[args.pure], scores[args.long_context], 2),
    }
    pure_input = matrix["pure"]["usage"]["input_tokens"]
    nog_input = matrix["noG"]["usage"]["input_tokens"]
    input_reduction = 1.0 - float(pure_input) / float(nog_input)
    ps_delta = comparisons["pure_minus_noG"]["metrics"]["ps"][
        "episode_mean_delta_points"]
    decision = {
        "pure_minus_noG_episode_mean_ps_delta_points": ps_delta,
        "maximum_allowed_ps_loss_points": 5.0,
        "ps_loss_within_5_points": ps_delta >= -5.0,
        "pure_relative_noG_input_reduction_fraction": input_reduction,
        "minimum_required_input_reduction_fraction": 0.30,
        "input_reduction_at_least_30_percent": input_reduction >= 0.30,
    }
    decision["pass"] = bool(
        decision["ps_loss_within_5_points"]
        and decision["input_reduction_at_least_30_percent"])

    output = {
        "schema": "memoryarena-compact-v3-heldout-summary/v1",
        "protocol_document": args.protocol_document,
        "protocol_validation": {
            "frozen_protocol": str(frozen_protocol_path),
            "frozen_protocol_sha256": file_hash(frozen_protocol_path),
            "protocol_document_sha256": file_hash(protocol_document_path),
            "matrix_matches_frozen_protocol": True,
        },
        "scope": (
            "new LLM-e2e/graph-held-out boundary; not a pristine untouched "
            "benchmark split because the parser was previously audited on all groups"),
        "score_input": args.input,
        "expected_episode_ids": expected,
        "matrix_validation": {
            "arms": arm_names, "episodes_per_arm": len(expected),
            "complete_episode_and_usage_coverage": True,
            "shared_runtime": fairness_rows[0], "actual_runtime": runtime_audit,
            "configs": configs,
        },
        "graph_boundary": {
            "path": str(graph_path), "sha256": file_hash(graph_path),
            "typegraph_path": str(typegraph_path),
            "typegraph_sha256": file_hash(typegraph_path),
            "graph_learning_episodes": typegraph["n_episodes"],
            "excluded_episode_ids": sorted(graph_excluded, key=int),
            "heldout_ids_all_excluded": True,
        },
        "arms": matrix,
        "paired_comparisons": comparisons,
        "protocol_judgement": decision,
    }
    atomic_json(ROOT / args.out, output)
    print(f"pure-noG PS delta={ps_delta:.2f} points; input reduction="
          f"{input_reduction:.2%}; pass={decision['pass']}")
    print(f"wrote {ROOT / args.out}")


if __name__ == "__main__":
    main()
