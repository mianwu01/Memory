"""Shared schema helpers for causal-memory benchmark prototypes.

The benchmark contract deliberately separates what a runtime may observe from
what the evaluator owns.  A method receives ``history``, ``memory_state`` and
``query``.  It must never receive ``gold``.  The gold section contains the
interventional graph and counterfactual post-state used only for evaluation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "causal-memory-benchmark/v1"
RUNTIME_FIELDS = {
    "schema_version",
    "task",
    "episode_id",
    "split",
    "history",
    "memory_state",
    "query",
    "mechanism_id",
    "entity",
    "event_kind",
    "metadata",
    "generalization",
}


def runtime_view(
    episode: Mapping[str, Any], *, training: bool = False
) -> dict[str, Any]:
    """Return the fields a method is allowed to inspect.

    ``gold`` is never copied.  A training method may additionally observe a
    completed transition, but only for episodes explicitly assigned to the
    train split.  Test-time callers therefore cannot accidentally receive the
    counterfactual outcome through the same object used by the evaluator.
    """

    validate_episode(episode)
    view = {
        key: deepcopy(value)
        for key, value in episode.items()
        if key in RUNTIME_FIELDS
    }
    if training and episode["split"] == "train" and "observed_transition" in episode:
        view["observed_transition"] = deepcopy(episode["observed_transition"])
    return view


def changed_nodes(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Return sorted state keys whose values changed under an intervention."""

    keys = set(before) | set(after)
    return sorted(key for key in keys if before.get(key) != after.get(key))


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def audit_predictions(
    episodes: Iterable[Mapping[str, Any]],
    predictions: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Score affected-node selection and state propagation.

    Predictions have two required fields: ``affected_nodes`` and ``post_state``.
    Metrics are macro-averaged by episode so a task with a large state vector
    cannot dominate another task merely through its number of cells.
    """

    episodes = list(episodes)
    predictions = list(predictions)
    if len(episodes) != len(predictions):
        raise ValueError("episodes and predictions must have the same length")

    per_episode = []
    for episode, prediction in zip(episodes, predictions):
        gold = episode["gold"]
        expected = set(gold["affected_nodes"])
        predicted = set(prediction.get("affected_nodes", []))
        post_state = gold["post_state"]
        proposed_state = prediction.get("post_state", {})

        tp = len(expected & predicted)
        affected_correct = sum(
            proposed_state.get(node) == post_state.get(node) for node in expected
        )
        all_correct = sum(
            proposed_state.get(node) == value for node, value in post_state.items()
        )
        per_episode.append(
            {
                "episode_id": episode["episode_id"],
                "affected_precision": _safe_ratio(tp, len(predicted)),
                "affected_recall": _safe_ratio(tp, len(expected)),
                "affected_state_accuracy": _safe_ratio(affected_correct, len(expected)),
                "full_state_accuracy": _safe_ratio(all_correct, len(post_state)),
                "propagation_required": len(expected) > 1,
            }
        )

    def mean(field: str) -> float:
        return sum(float(row[field]) for row in per_episode) / max(1, len(per_episode))

    return {
        "episodes": len(per_episode),
        "propagation_required_episodes": sum(
            int(row["propagation_required"]) for row in per_episode
        ),
        "affected_precision": mean("affected_precision"),
        "affected_recall": mean("affected_recall"),
        "affected_state_accuracy": mean("affected_state_accuracy"),
        "full_state_accuracy": mean("full_state_accuracy"),
        "per_episode": per_episode,
    }


def validate_episode(episode: Mapping[str, Any]) -> None:
    """Validate the small cross-task contract without external dependencies."""

    required = {
        "schema_version",
        "task",
        "episode_id",
        "split",
        "history",
        "memory_state",
        "query",
        "gold",
    }
    missing = sorted(required - set(episode))
    if missing:
        raise ValueError(f"episode missing fields: {missing}")
    if episode["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema: {episode['schema_version']}")
    if not isinstance(episode["history"], list):
        raise ValueError("history must be a list")
    if not isinstance(episode["memory_state"], dict):
        raise ValueError("memory_state must be a dict")
    query = episode["query"]
    if not isinstance(query, dict) or not {"text", "intervention"} <= set(query):
        raise ValueError("query must contain text and intervention")
    intervention = query["intervention"]
    intervention_fields = {"node", "old_value", "new_value", "kind"}
    if not isinstance(intervention, dict) or not intervention_fields <= set(intervention):
        raise ValueError(
            "query.intervention must contain node, old_value, new_value and kind"
        )
    node = intervention["node"]
    if node not in episode["memory_state"]:
        raise ValueError(f"intervention node is absent from memory_state: {node}")
    if episode["memory_state"][node] != intervention["old_value"]:
        raise ValueError("intervention old_value must equal the pre-intervention state")
    if intervention["old_value"] == intervention["new_value"]:
        raise ValueError("intervention must change its target value")
    observed = episode.get("observed_transition")
    if observed is not None:
        if episode["split"] != "train":
            raise ValueError("observed_transition is allowed only on the train split")
        observed_fields = {"pre_state", "intervention", "post_state"}
        if not isinstance(observed, dict) or not observed_fields <= set(observed):
            raise ValueError(
                "observed_transition must contain pre_state, intervention and post_state"
            )
        if observed["pre_state"] != episode["memory_state"]:
            raise ValueError("observed transition pre_state must equal memory_state")
        if observed["intervention"] != intervention:
            raise ValueError("observed transition intervention must equal query intervention")
        if not isinstance(observed["post_state"], dict):
            raise ValueError("observed transition post_state must be a dict")
    gold = episode["gold"]
    gold_required = {
        "graph",
        "active_edges",
        "affected_nodes",
        "required_reads",
        "post_state",
    }
    missing_gold = sorted(gold_required - set(gold))
    if missing_gold:
        raise ValueError(f"gold missing fields: {missing_gold}")
    actual_changed = changed_nodes(episode["memory_state"], gold["post_state"])
    if actual_changed != sorted(gold["affected_nodes"]):
        raise ValueError(
            "gold affected_nodes must equal the counterfactual state delta: "
            f"expected {actual_changed}, got {sorted(gold['affected_nodes'])}"
        )
