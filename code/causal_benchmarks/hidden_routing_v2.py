"""Fail-closed audit for the hidden-routing v2 microbenchmark.

The four nominal domains currently share one structural data-generating
process, which the suite-level pseudoreplication audit reports explicitly.
Every episode has fresh opaque node identifiers and a history-borne routing program.
History records expose endpoint pairs, route codes, and guarded checkpoints,
but the meanings of route direction and gate polarity are never exposed at
runtime.  A train-only learner identifies that small codebook from completed
train transitions and applies it to held-out route compositions.  A matching
train-enabled program receives the same information so the audit cannot claim
that a particular learned implementation is necessary when simple hypothesis
enumeration is sufficient.

This is an API-free admission layer.  It does not register an upstream
MemoryArena environment, alter the v1 six-arm protocol, or provide task-card
equations to a decoder.  The evaluator-owned graph is used only by the oracle
and by post-hoc mask scoring.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import random
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from .common import SCHEMA_VERSION, changed_nodes, runtime_view, validate_episode
except ImportError:  # pragma: no cover - direct module execution
    from common import (  # type: ignore
        SCHEMA_VERSION,
        changed_nodes,
        runtime_view,
        validate_episode,
    )


V2_TASKS = (
    "hidden_routing_v2_travel",
    "hidden_routing_v2_shopping",
    "hidden_routing_v2_search",
    "hidden_routing_v2_formal",
)

BASELINE_NAMES = (
    "exact_kv",
    "source_union",
    "source_regime_table",
    "matched_retrieval",
    "learned_graph",
    "consistent_codebook_program",
    "gold_free_program",
    "oracle_graph",
)

_DOMAIN = {
    "hidden_routing_v2_travel": {
        "noun": "itinerary ledger",
        "route_codes": {"saffron": True, "quartz": False},
        "gate_codes": {"harbor": True, "summit": False},
    },
    "hidden_routing_v2_shopping": {
        "noun": "order ledger",
        "route_codes": {"cobalt": True, "willow": False},
        "gate_codes": {"anchor": True, "meadow": False},
    },
    "hidden_routing_v2_search": {
        "noun": "evidence ledger",
        "route_codes": {"ember": True, "ivory": False},
        "gate_codes": {"orbit": True, "delta": False},
    },
    "hidden_routing_v2_formal": {
        "noun": "notebook ledger",
        "route_codes": {"violet": True, "timber": False},
        "gate_codes": {"cipher": True, "ripple": False},
    },
}

_TRAIN_COMPOSITIONS = ("chain_branch", "fork_branch", "staggered_gates")
_DEV_COMPOSITION = "bridged_fork"
_TEST_COMPOSITION = "woven_dual_gate"
_SHORTCUT_THRESHOLD = 0.95


def _opaque(seed: int, task: str, episode_index: int, label: str) -> str:
    payload = f"hidden-routing-v2|{seed}|{task}|{episode_index}|{label}"
    return "v_" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def _split(local_index: int, episodes_per_domain: int) -> str:
    train_end = episodes_per_domain // 2
    dev_end = train_end + max(2, episodes_per_domain // 6)
    return "train" if local_index < train_end else "dev" if local_index < dev_end else "test"


def _composition_edges(
    composition: str, local_index: int
) -> list[tuple[int, int, bool, bool]]:
    """Return ``source, target, gated, desired_active`` edge specifications."""

    alternate = local_index % 2 == 0
    if composition == "chain_branch":
        return [
            (6, 0, False, True),  # inbound, not a descendant of the intervention
            (0, 1, False, True),
            (1, 2, False, True),
            (2, 3, False, True),
            (1, 4, True, alternate),
            (4, 5, False, True),
            (7, 8, False, True),  # disconnected distractor component
        ]
    if composition == "fork_branch":
        return [
            (6, 0, False, True),
            (0, 1, False, True),
            (1, 2, False, True),
            (1, 3, False, True),
            (2, 4, True, alternate),
            (3, 5, True, not alternate),
            (7, 8, False, True),
        ]
    if composition == "staggered_gates":
        return [
            (6, 0, False, True),
            (0, 1, False, True),
            (1, 2, False, True),
            (2, 3, False, True),
            (1, 4, True, alternate),
            (4, 5, True, not alternate),
            (7, 8, False, True),
        ]
    if composition == "bridged_fork":
        return [
            (6, 0, False, True),
            (0, 1, False, True),
            (1, 2, False, True),
            (1, 3, False, True),
            (2, 4, True, alternate),
            (3, 4, True, not alternate),
            (4, 5, False, True),
            (7, 8, False, True),
        ]
    if composition == "woven_dual_gate":
        return [
            (7, 0, False, True),
            (0, 1, False, True),
            (1, 2, False, True),
            (1, 3, False, True),
            (2, 4, True, alternate),
            (3, 5, True, not alternate),
            (4, 6, False, True),
            (5, 6, False, True),
            (1, 9, True, False),  # guaranteed inactive decoy branch
            (8, 10, False, True),  # disconnected distractor component
        ]
    raise ValueError(f"unknown route composition: {composition}")


def _composition_for(split: str, local_index: int) -> str:
    if split == "train":
        return _TRAIN_COMPOSITIONS[local_index % len(_TRAIN_COMPOSITIONS)]
    if split == "dev":
        return _DEV_COMPOSITION
    return _TEST_COMPOSITION


def _children(edges: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    children: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        children[str(edge["source"])].add(str(edge["target"]))
    return children


def _reachability(
    source: str, edges: Iterable[Mapping[str, Any]]
) -> tuple[set[str], dict[str, int]]:
    children = _children(edges)
    reached = {source}
    distance = {source: 0}
    frontier = deque([source])
    while frontier:
        node = frontier.popleft()
        for child in sorted(children.get(node, ())):
            if child not in reached:
                reached.add(child)
                distance[child] = distance[node] + 1
                frontier.append(child)
    return reached, distance


def _encode_episode(
    task: str,
    local_index: int,
    episodes_per_domain: int,
    seed: int,
) -> dict[str, Any]:
    if task not in V2_TASKS:
        raise ValueError(task)
    split = _split(local_index, episodes_per_domain)
    composition = _composition_for(split, local_index)
    rng = random.Random((seed + 11) * 1_000_003 + V2_TASKS.index(task) * 100_003 + local_index)
    node_ids = [_opaque(seed, task, local_index, f"node-{index}") for index in range(11)]
    state: dict[str, Any] = {
        node: rng.randint(20, 90) for node in node_ids
    }
    route_codes = list(_DOMAIN[task]["route_codes"])
    gate_codes = list(_DOMAIN[task]["gate_codes"])
    history: list[dict[str, Any]] = []
    potential_edges: list[dict[str, Any]] = []
    active_edges: list[dict[str, Any]] = []

    for edge_index, (source_slot, target_slot, gated, desired_active) in enumerate(
        _composition_edges(composition, local_index)
    ):
        source = node_ids[source_slot]
        target = node_ids[target_slot]
        route_code = route_codes[(edge_index + local_index) % len(route_codes)]
        a_to_b = bool(_DOMAIN[task]["route_codes"][route_code])
        endpoint_a, endpoint_b = (source, target) if a_to_b else (target, source)
        gate_node: str | None = None
        gate_code: str | None = None
        active = True
        if gated:
            gate_node = _opaque(seed, task, local_index, f"gate-{edge_index}")
            gate_code = gate_codes[(edge_index + local_index) % len(gate_codes)]
            active_value = bool(_DOMAIN[task]["gate_codes"][gate_code])
            state[gate_node] = active_value if desired_active else not active_value
            active = desired_active
            history.append(
                {
                    "t": len(history),
                    "kind": "checkpoint_observation",
                    "node": gate_node,
                    "value": state[gate_node],
                    "text": f"Checkpoint {gate_node} currently records {str(state[gate_node]).lower()}.",
                }
            )
        edge = {
            "source": source,
            "target": target,
            "condition": "always" if not gated else f"hidden:{gate_code}",
        }
        potential_edges.append(edge)
        if active:
            active_edges.append(copy.deepcopy(edge))
        record = {
            "t": len(history),
            "kind": "route_observation",
            "record_id": _opaque(seed, task, local_index, f"record-{edge_index}"),
            "endpoint_a": endpoint_a,
            "endpoint_b": endpoint_b,
            "route_code": route_code,
            "gate_node": gate_node,
            "gate_code": gate_code,
            "text": (
                f"Trace {route_code} joins {endpoint_a} and {endpoint_b}."
                + (
                    f" Checkpoint {gate_node} is interpreted through code {gate_code}."
                    if gate_node is not None
                    else ""
                )
            ),
        }
        history.append(record)

    history.extend(
        {
            "t": len(history) + offset,
            "kind": "irrelevant_observation",
            "record_id": _opaque(seed, task, local_index, f"noise-{offset}"),
            "text": f"Archived unrelated note {rng.randrange(100_000, 999_999)}.",
        }
        for offset in range(3)
    )
    rng.shuffle(history)
    for t, record in enumerate(history):
        record["t"] = t

    intervention_node = node_ids[0]
    delta = 2 + V2_TASKS.index(task)
    intervention = {
        "node": intervention_node,
        "old_value": state[intervention_node],
        "new_value": state[intervention_node] + delta,
        "kind": "route_value_intervention",
    }
    reached, distances = _reachability(intervention_node, active_edges)
    post_state = copy.deepcopy(state)
    post_state[intervention_node] = intervention["new_value"]
    for node in sorted(reached - {intervention_node}):
        post_state[node] = int(state[node]) + delta * (distances[node] + 1)
    affected = changed_nodes(state, post_state)
    gate_reads = {
        str(record["gate_node"])
        for record in history
        if record.get("kind") == "route_observation" and record.get("gate_node")
    }
    query_text = (
        f"Update opaque record {intervention_node} in the {_DOMAIN[task]['noun']} "
        f"from {intervention['old_value']} to {intervention['new_value']}. Reconcile only "
        "consequences licensed by the pre-query trace history."
    )
    episode = {
        "schema_version": SCHEMA_VERSION,
        "task": task,
        "episode_id": f"{task}-s{seed}-e{local_index:05d}",
        "split": split,
        "history": history,
        "memory_state": state,
        "query": {"text": query_text, "intervention": intervention},
        "metadata": {"benchmark": "hidden-routing-v2"},
        "gold": {
            "graph": potential_edges,
            "active_edges": active_edges,
            "affected_nodes": affected,
            "required_reads": sorted(set(affected) | gate_reads),
            "post_state": post_state,
            "audit_annotations": {
                "route_composition": composition,
                "heldout_route_composition": split == "test",
                "max_active_hops": max(distances.values()),
            },
        },
    }
    if split == "train":
        episode["observed_transition"] = {
            "pre_state": copy.deepcopy(state),
            "intervention": copy.deepcopy(intervention),
            "post_state": copy.deepcopy(post_state),
        }
    validate_episode(episode)
    return episode


def generate_dataset(
    episodes_per_domain: int = 36, seed: int = 17
) -> list[dict[str, Any]]:
    """Generate a balanced deterministic four-domain dataset."""

    if episodes_per_domain < 16:
        raise ValueError("episodes_per_domain must be at least 16")
    return [
        _encode_episode(task, index, episodes_per_domain, seed)
        for task in V2_TASKS
        for index in range(episodes_per_domain)
    ]


def _training_views(views: Sequence[Mapping[str, Any]], task: str) -> None:
    if not views:
        raise ValueError("at least one train transition is required")
    for view in views:
        if "gold" in view:
            raise ValueError("training accepts runtime views, never evaluator gold")
        if view.get("task") != task or view.get("split") != "train":
            raise ValueError("training view has the wrong task or split")
        transition = view.get("observed_transition")
        if not isinstance(transition, Mapping):
            raise ValueError("training requires observed_transition")
        if set(transition) != {"pre_state", "intervention", "post_state"}:
            raise ValueError("observed_transition contains forbidden supervision")
        if transition["intervention"] != view["query"]["intervention"]:
            raise ValueError("training transition/query intervention mismatch")


def _inference_view(view: Mapping[str, Any], task: str) -> None:
    if "gold" in view or "observed_transition" in view:
        raise ValueError("inference requires an outcome-free runtime view")
    if view.get("task") != task or view.get("split") == "train":
        raise ValueError("inference view has the wrong task or split")
    required = {"episode_id", "history", "memory_state", "query", "task", "split"}
    if not required <= set(view):
        raise ValueError("inference view is incomplete")


def _route_records(history: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    records = [record for record in history if record.get("kind") == "route_observation"]
    for record in records:
        required = {"endpoint_a", "endpoint_b", "route_code", "gate_node", "gate_code"}
        if not required <= set(record):
            raise ValueError("malformed route observation")
    return records


def _decoded_edges(
    state: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    route_orientation: Mapping[str, bool],
    gate_active_value: Mapping[str, bool],
) -> list[dict[str, str]]:
    edges = []
    for record in _route_records(history):
        code = str(record["route_code"])
        if code not in route_orientation:
            continue
        a = str(record["endpoint_a"])
        b = str(record["endpoint_b"])
        source, target = (a, b) if route_orientation[code] else (b, a)
        gate_node = record.get("gate_node")
        gate_code = record.get("gate_code")
        if gate_node is not None:
            if str(gate_code) not in gate_active_value:
                continue
            if bool(state[str(gate_node)]) != gate_active_value[str(gate_code)]:
                continue
        edges.append({"source": source, "target": target})
    return edges


@dataclass
class HiddenRouteLearner:
    """Learn route-code direction and gate polarity from train deltas only."""

    task: str
    route_orientation: dict[str, bool] | None = None
    gate_active_value: dict[str, bool] | None = None
    fit_episode_ids: tuple[str, ...] = ()
    candidate_configurations: int = 0

    def fit(self, train_views: Sequence[Mapping[str, Any]]) -> "HiddenRouteLearner":
        views = list(train_views)
        _training_views(views, self.task)
        route_codes = sorted(
            {
                str(record["route_code"])
                for view in views
                for record in _route_records(view["history"])
            }
        )
        gate_codes = sorted(
            {
                str(record["gate_code"])
                for view in views
                for record in _route_records(view["history"])
                if record.get("gate_code") is not None
            }
        )
        if not route_codes or not gate_codes:
            raise ValueError("training trajectories do not identify route/gate alphabets")
        best_score: tuple[int, int, int, int] | None = None
        best_route: dict[str, bool] | None = None
        best_gate: dict[str, bool] | None = None
        bits = len(route_codes) + len(gate_codes)
        self.candidate_configurations = 2**bits
        for assignment in itertools.product((False, True), repeat=bits):
            route = dict(zip(route_codes, assignment[: len(route_codes)]))
            gate = dict(zip(gate_codes, assignment[len(route_codes) :]))
            exact = tp = fp = fn = 0
            for view in views:
                transition = view["observed_transition"]
                target = str(transition["intervention"]["node"])
                edges = _decoded_edges(transition["pre_state"], view["history"], route, gate)
                predicted, _ = _reachability(target, edges)
                expected = set(
                    changed_nodes(transition["pre_state"], transition["post_state"])
                )
                exact += int(predicted == expected)
                tp += len(predicted & expected)
                fp += len(predicted - expected)
                fn += len(expected - predicted)
            score = (exact, tp, -fp, -fn)
            if best_score is None or score > best_score:
                best_score = score
                best_route = route
                best_gate = gate
        assert best_route is not None and best_gate is not None
        self.route_orientation = best_route
        self.gate_active_value = best_gate
        self.fit_episode_ids = tuple(sorted(str(view["episode_id"]) for view in views))
        return self

    def predict_mask(self, view: Mapping[str, Any]) -> tuple[str, ...]:
        _inference_view(view, self.task)
        if self.route_orientation is None or self.gate_active_value is None:
            raise ValueError("learner must be fitted before prediction")
        target = str(view["query"]["intervention"]["node"])
        edges = _decoded_edges(
            view["memory_state"],
            view["history"],
            self.route_orientation,
            self.gate_active_value,
        )
        reached, _ = _reachability(target, edges)
        return tuple(sorted(reached & set(view["memory_state"])))

    def summary(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "route_codes": sorted((self.route_orientation or {}).keys()),
            "gate_codes": sorted((self.gate_active_value or {}).keys()),
            "fit_episode_ids": list(self.fit_episode_ids),
            "candidate_configurations": self.candidate_configurations,
            "stored_graphs": 0,
            "stored_post_states": 0,
        }


@dataclass
class ConsistentCodebookProgram:
    """Enumerate every codebook consistent with the shared train outcomes.

    This is deliberately a plain program rather than a learned-graph arm.  It
    receives exactly the same train runtime views as :class:`HiddenRouteLearner`.
    At inference it unions the reachable sets of all surviving hypotheses, so
    it remains recall-safe when the training evidence is ambiguous instead of
    resolving ties with evaluator or designer information.
    """

    task: str
    consistent_configurations: tuple[
        tuple[dict[str, bool], dict[str, bool]], ...
    ] = ()
    fit_episode_ids: tuple[str, ...] = ()
    candidate_configurations: int = 0

    def fit(
        self, train_views: Sequence[Mapping[str, Any]]
    ) -> "ConsistentCodebookProgram":
        views = list(train_views)
        _training_views(views, self.task)
        route_codes = sorted(
            {
                str(record["route_code"])
                for view in views
                for record in _route_records(view["history"])
            }
        )
        gate_codes = sorted(
            {
                str(record["gate_code"])
                for view in views
                for record in _route_records(view["history"])
                if record.get("gate_code") is not None
            }
        )
        if not route_codes or not gate_codes:
            raise ValueError("training trajectories do not identify route/gate alphabets")

        bits = len(route_codes) + len(gate_codes)
        self.candidate_configurations = 2**bits
        consistent: list[tuple[dict[str, bool], dict[str, bool]]] = []
        for assignment in itertools.product((False, True), repeat=bits):
            route = dict(zip(route_codes, assignment[: len(route_codes)]))
            gate = dict(zip(gate_codes, assignment[len(route_codes) :]))
            matches_every_transition = True
            for view in views:
                transition = view["observed_transition"]
                target = str(transition["intervention"]["node"])
                edges = _decoded_edges(
                    transition["pre_state"], view["history"], route, gate
                )
                predicted, _ = _reachability(target, edges)
                expected = set(
                    changed_nodes(transition["pre_state"], transition["post_state"])
                )
                if predicted != expected:
                    matches_every_transition = False
                    break
            if matches_every_transition:
                consistent.append((route, gate))
        if not consistent:
            raise ValueError("no codebook is consistent with all train transitions")
        self.consistent_configurations = tuple(consistent)
        self.fit_episode_ids = tuple(sorted(str(view["episode_id"]) for view in views))
        return self

    def predict_mask(self, view: Mapping[str, Any]) -> tuple[str, ...]:
        _inference_view(view, self.task)
        if not self.consistent_configurations:
            raise ValueError("program must be fitted before prediction")
        target = str(view["query"]["intervention"]["node"])
        possible = {target}
        for route, gate in self.consistent_configurations:
            edges = _decoded_edges(
                view["memory_state"], view["history"], route, gate
            )
            reached, _ = _reachability(target, edges)
            possible.update(reached)
        return tuple(sorted(possible & set(view["memory_state"])))

    def summary(self) -> dict[str, Any]:
        route_codes = {
            code
            for route, _ in self.consistent_configurations
            for code in route
        }
        gate_codes = {
            code
            for _, gate in self.consistent_configurations
            for code in gate
        }
        return {
            "task": self.task,
            "route_codes": sorted(route_codes),
            "gate_codes": sorted(gate_codes),
            "fit_episode_ids": list(self.fit_episode_ids),
            "candidate_configurations": self.candidate_configurations,
            "consistent_configurations": len(self.consistent_configurations),
            "prediction_rule": "union_reachability_over_consistent_codebooks",
            "stored_graphs": 0,
            "stored_post_states": 0,
        }


def _numeric_nodes(state: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            node
            for node, value in state.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        )
    )


def _delta_shape(intervention: Mapping[str, Any]) -> tuple[str, int]:
    old = intervention["old_value"]
    new = intervention["new_value"]
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return ("number", 1 if new > old else -1)
    return (type(new).__name__, int(bool(new)))


def _source_key(view: Mapping[str, Any]) -> tuple[Any, ...]:
    intervention = view["query"]["intervention"]
    return (str(view["task"]), str(intervention["kind"]), *_delta_shape(intervention))


def _regime_key(view: Mapping[str, Any]) -> tuple[Any, ...]:
    booleans = [value for value in view["memory_state"].values() if isinstance(value, bool)]
    return (*_source_key(view), sum(booleans), len(booleans) - sum(booleans))


@dataclass
class ShortcutImpactTables:
    """Identifier-free source and visible-regime impact unions."""

    task: str
    source_union: dict[tuple[Any, ...], tuple[str, ...]] | None = None
    regime_union: dict[tuple[Any, ...], tuple[str, ...]] | None = None
    fit_episode_ids: tuple[str, ...] = ()

    def fit(self, train_views: Sequence[Mapping[str, Any]]) -> "ShortcutImpactTables":
        views = list(train_views)
        _training_views(views, self.task)
        source: dict[tuple[Any, ...], set[str]] = defaultdict(set)
        regime: dict[tuple[Any, ...], set[str]] = defaultdict(set)
        for view in views:
            transition = view["observed_transition"]
            target = str(transition["intervention"]["node"])
            changed = set(changed_nodes(transition["pre_state"], transition["post_state"]))
            templates = {"$target"}
            if changed - {target}:
                templates.add("$all_numeric")
            source[_source_key(view)].update(templates)
            regime[_regime_key(view)].update(templates)
        self.source_union = {key: tuple(sorted(value)) for key, value in source.items()}
        self.regime_union = {key: tuple(sorted(value)) for key, value in regime.items()}
        self.fit_episode_ids = tuple(sorted(str(view["episode_id"]) for view in views))
        return self

    @staticmethod
    def _instantiate(view: Mapping[str, Any], templates: Iterable[str]) -> tuple[str, ...]:
        target = str(view["query"]["intervention"]["node"])
        nodes = {target}
        if "$all_numeric" in set(templates):
            nodes.update(_numeric_nodes(view["memory_state"]))
        return tuple(sorted(nodes & set(view["memory_state"])))

    def predict_masks(self, view: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        _inference_view(view, self.task)
        if self.source_union is None or self.regime_union is None:
            raise ValueError("impact tables must be fitted before prediction")
        source_key = _source_key(view)
        regime_key = _regime_key(view)
        source_seen = source_key in self.source_union
        source_templates = self.source_union.get(source_key, ("$target",))
        regime_seen = regime_key in self.regime_union
        regime_templates = self.regime_union.get(regime_key, source_templates)
        return {
            "source_union": {
                "predicted_write_nodes": self._instantiate(view, source_templates),
                "lookup_seen": source_seen,
                "backed_off_to_source": False,
            },
            "source_regime_table": {
                "predicted_write_nodes": self._instantiate(view, regime_templates),
                "lookup_seen": regime_seen,
                "backed_off_to_source": not regime_seen,
            },
        }

    def summary(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "source_signatures": len(self.source_union or {}),
            "regime_signatures": len(self.regime_union or {}),
            "fit_episode_ids": list(self.fit_episode_ids),
            "stored_graphs": 0,
            "stored_post_states": 0,
        }


def exact_kv_mask(view: Mapping[str, Any]) -> tuple[str, ...]:
    _inference_view(view, str(view["task"]))
    return (str(view["query"]["intervention"]["node"]),)


def matched_retrieval_mask(view: Mapping[str, Any], budget: int) -> tuple[str, ...]:
    """Query-aware node retrieval at exactly the learned mask's write budget."""

    _inference_view(view, str(view["task"]))
    target = str(view["query"]["intervention"]["node"])
    target_records = [
        json.dumps(record, sort_keys=True)
        for record in view["history"]
        if target in json.dumps(record, sort_keys=True)
    ]
    ranked = []
    for node in _numeric_nodes(view["memory_state"]):
        cooccurrence = sum(node in record for record in target_records)
        score = 10_000 * int(node == target) + 100 * cooccurrence
        ranked.append((-score, node))
    wanted = min(max(1, budget), len(ranked))
    return tuple(sorted(node for _, node in sorted(ranked)[:wanted]))


def gold_free_program_mask(view: Mapping[str, Any]) -> tuple[str, ...]:
    """Zero-shot conservative closure that deliberately ignores code semantics."""

    _inference_view(view, str(view["task"]))
    adjacency: dict[str, set[str]] = defaultdict(set)
    for record in _route_records(view["history"]):
        a = str(record["endpoint_a"])
        b = str(record["endpoint_b"])
        adjacency[a].add(b)
        adjacency[b].add(a)
    target = str(view["query"]["intervention"]["node"])
    reached = {target}
    frontier = deque([target])
    while frontier:
        node = frontier.popleft()
        for neighbor in sorted(adjacency.get(node, ())):
            if neighbor not in reached:
                reached.add(neighbor)
                frontier.append(neighbor)
    return tuple(sorted(reached & set(_numeric_nodes(view["memory_state"]))))


def oracle_graph_mask(episode: Mapping[str, Any]) -> tuple[str, ...]:
    """Evaluator-only active-graph reachability upper bound."""

    target = str(episode["query"]["intervention"]["node"])
    reached, _ = _reachability(target, episode["gold"]["active_edges"])
    return tuple(sorted(reached & set(episode["memory_state"])))


def _mask_metrics(
    episodes: Sequence[Mapping[str, Any]], masks: Sequence[Sequence[str]]
) -> dict[str, Any]:
    rows = []
    for episode, mask in zip(episodes, masks):
        expected = set(episode["gold"]["affected_nodes"])
        predicted = set(mask)
        state_nodes = set(episode["memory_state"])
        unaffected = state_nodes - expected
        tp = len(expected & predicted)
        precision = tp / len(predicted) if predicted else 1.0
        recall = tp / len(expected) if expected else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append(
            {
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "exact": predicted == expected,
                "sufficient": expected <= predicted,
                "specificity": (
                    len(unaffected - predicted) / len(unaffected) if unaffected else 1.0
                ),
                "write_nodes": len(predicted),
                "write_fraction": len(predicted) / len(state_nodes),
            }
        )

    def mean(field: str) -> float:
        return sum(float(row[field]) for row in rows) / max(1, len(rows))

    return {
        "episodes": len(rows),
        "affected_precision": mean("precision"),
        "affected_recall": mean("recall"),
        "affected_f1": mean("f1"),
        "exact_mask_rate": mean("exact"),
        "sufficient_mask_rate": mean("sufficient"),
        "unaffected_specificity": mean("specificity"),
        "avg_write_nodes": mean("write_nodes"),
        "avg_write_fraction": mean("write_fraction"),
    }


def _history_enumerates_potential_edges(episode: Mapping[str, Any]) -> bool:
    """Whether runtime route records expose every potential gold endpoint pair."""

    records = _route_records(episode["history"])
    history_pairs = [
        frozenset((str(record["endpoint_a"]), str(record["endpoint_b"])))
        for record in records
    ]
    gold_pairs = [
        frozenset((str(edge["source"]), str(edge["target"])))
        for edge in episode["gold"]["graph"]
    ]
    return len(history_pairs) == len(gold_pairs) and sorted(
        sorted(pair) for pair in history_pairs
    ) == sorted(sorted(pair) for pair in gold_pairs)


def _normalized_episode_structure(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Remove opaque IDs, code words, value scale, and domain surface labels.

    The generator inserts numeric state nodes in its latent slot order.  Using
    that order makes the audit independent of the opaque hashes while retaining
    directed/gated topology, active routing, the intervention position, and the
    normalized propagation response.
    """

    state = episode["memory_state"]
    numeric_nodes = [
        str(node)
        for node, value in state.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    slot = {node: index for index, node in enumerate(numeric_nodes)}
    graph = tuple(
        sorted(
            (
                slot[str(edge["source"])],
                slot[str(edge["target"])],
                str(edge.get("condition", "always")) != "always",
            )
            for edge in episode["gold"]["graph"]
        )
    )
    active_graph = tuple(
        sorted(
            (slot[str(edge["source"])], slot[str(edge["target"])])
            for edge in episode["gold"]["active_edges"]
        )
    )
    intervention = episode["query"]["intervention"]
    intervention_delta = intervention["new_value"] - intervention["old_value"]
    if not isinstance(intervention_delta, (int, float)) or intervention_delta == 0:
        raise ValueError("structural normalization requires a numeric intervention")
    normalized_changes = tuple(
        sorted(
            (
                slot[node],
                (episode["gold"]["post_state"][node] - state[node])
                / intervention_delta,
            )
            for node in numeric_nodes
            if episode["gold"]["post_state"][node] != state[node]
        )
    )
    return {
        "split": str(episode["split"]),
        "numeric_nodes": len(numeric_nodes),
        "gate_nodes": sum(isinstance(value, bool) for value in state.values()),
        "intervention_slot": slot[str(intervention["node"])],
        "intervention_direction": 1 if intervention_delta > 0 else -1,
        "potential_graph": graph,
        "active_graph": active_graph,
        "normalized_changes": normalized_changes,
    }


def _structural_replication_audit(
    episodes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    fingerprints: dict[str, str] = {}
    normalized_rows: dict[str, list[str]] = {}
    for task in V2_TASKS:
        rows = [
            json.dumps(
                _normalized_episode_structure(episode),
                sort_keys=True,
                separators=(",", ":"),
            )
            for episode in episodes
            if episode["task"] == task
        ]
        normalized_rows[task] = sorted(rows)
        fingerprints[task] = hashlib.sha256(
            json.dumps(normalized_rows[task], separators=(",", ":")).encode()
        ).hexdigest()
    groups: dict[str, list[str]] = defaultdict(list)
    for task, fingerprint in fingerprints.items():
        groups[fingerprint].append(task)
    duplicate_groups = [sorted(tasks) for tasks in groups.values() if len(tasks) > 1]
    independent = len(groups) == len(V2_TASKS)
    return {
        "normalization": (
            "opaque IDs, code words, domain nouns, raw values, and intervention "
            "magnitude removed; directed/gated topology and normalized response retained"
        ),
        "fingerprints": fingerprints,
        "unique_structural_fingerprints": len(groups),
        "duplicate_domain_groups": sorted(duplicate_groups),
        "all_domains_structurally_identical": len(groups) == 1,
        "structurally_independent_domains": independent,
        "pass": independent,
    }


def _domain_audit(
    task: str, episodes: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    train = [episode for episode in episodes if episode["split"] == "train"]
    test = [episode for episode in episodes if episode["split"] == "test"]
    if not train or not test:
        raise ValueError(f"{task} requires non-empty train and test splits")
    train_views = [runtime_view(episode, training=True) for episode in train]
    test_views = [runtime_view(episode, training=False) for episode in test]
    learner = HiddenRouteLearner(task).fit(train_views)
    consistent_program = ConsistentCodebookProgram(task).fit(train_views)
    shortcuts = ShortcutImpactTables(task).fit(train_views)

    # Freeze every non-oracle prediction before any evaluator outcome is scored.
    frozen: dict[str, list[tuple[str, ...]]] = {
        name: [] for name in BASELINE_NAMES if name != "oracle_graph"
    }
    shortcut_coverage = {"source_union": 0, "source_regime_table": 0}
    for view in test_views:
        learned = learner.predict_mask(view)
        lookup = shortcuts.predict_masks(view)
        frozen["exact_kv"].append(exact_kv_mask(view))
        frozen["source_union"].append(lookup["source_union"]["predicted_write_nodes"])
        frozen["source_regime_table"].append(
            lookup["source_regime_table"]["predicted_write_nodes"]
        )
        shortcut_coverage["source_union"] += int(lookup["source_union"]["lookup_seen"])
        shortcut_coverage["source_regime_table"] += int(
            lookup["source_regime_table"]["lookup_seen"]
        )
        frozen["matched_retrieval"].append(matched_retrieval_mask(view, len(learned)))
        frozen["learned_graph"].append(learned)
        frozen["consistent_codebook_program"].append(
            consistent_program.predict_mask(view)
        )
        frozen["gold_free_program"].append(gold_free_program_mask(view))

    oracle_masks = [oracle_graph_mask(episode) for episode in test]
    metrics = {name: _mask_metrics(test, masks) for name, masks in frozen.items()}
    metrics["oracle_graph"] = _mask_metrics(test, oracle_masks)
    for name in shortcut_coverage:
        metrics[name]["lookup_coverage"] = shortcut_coverage[name] / len(test)

    train_ids = {node for episode in train for node in episode["memory_state"]}
    test_ids = {node for episode in test for node in episode["memory_state"]}
    downstream_mentions = 0
    downstream_total = 0
    for episode in test:
        query = str(episode["query"]["text"])
        target = str(episode["query"]["intervention"]["node"])
        for node in episode["gold"]["affected_nodes"]:
            if node != target:
                downstream_total += 1
                downstream_mentions += int(str(node) in query)
    train_compositions = {
        episode["gold"]["audit_annotations"]["route_composition"] for episode in train
    }
    test_compositions = {
        episode["gold"]["audit_annotations"]["route_composition"] for episode in test
    }
    propagation_rate = sum(
        len(episode["gold"]["affected_nodes"]) > 1 for episode in test
    ) / len(test)
    multihop_rate = sum(
        episode["gold"]["audit_annotations"]["max_active_hops"] >= 2
        for episode in test
    ) / len(test)
    endpoint_exposure_rate = sum(
        _history_enumerates_potential_edges(episode) for episode in test
    ) / len(test)
    conservative_sufficient_baselines = [
        name
        for name in (
            "source_union",
            "source_regime_table",
            "matched_retrieval",
            "gold_free_program",
        )
        if metrics[name]["sufficient_mask_rate"] == 1.0
        and metrics[name]["exact_mask_rate"] < 1.0
    ]
    mask_only_task_solved_by_sufficient_superset = bool(
        conservative_sufficient_baselines
    )
    microbenchmark = {
        "runtime_outcomes_isolated": (
            all("gold" not in view for view in train_views + test_views)
            and all("observed_transition" in view for view in train_views)
            and all("observed_transition" not in view for view in test_views)
        ),
        "episode_ids_are_opaque_and_split_disjoint": not bool(train_ids & test_ids),
        "query_does_not_name_downstream_nodes": downstream_mentions == 0,
        "test_requires_propagation": propagation_rate == 1.0,
        "test_requires_multihop_propagation": multihop_rate == 1.0,
        "heldout_route_composition": bool(test_compositions - train_compositions),
        "learned_graph_recovers_heldout_routes": (
            metrics["learned_graph"]["exact_mask_rate"] == 1.0
        ),
        "consistent_program_recovers_heldout_routes": (
            metrics["consistent_codebook_program"]["exact_mask_rate"] == 1.0
        ),
        "oracle_graph_is_exact": metrics["oracle_graph"]["exact_mask_rate"] == 1.0,
    }
    microbenchmark["pass"] = all(microbenchmark.values())
    admission = {
        **{key: value for key, value in microbenchmark.items() if key != "pass"},
        "history_does_not_enumerate_potential_graph": (
            endpoint_exposure_rate < _SHORTCUT_THRESHOLD
        ),
        "exact_kv_leaves_headroom": metrics["exact_kv"]["affected_f1"] < _SHORTCUT_THRESHOLD,
        "source_union_leaves_headroom": (
            metrics["source_union"]["affected_f1"] < _SHORTCUT_THRESHOLD
            and metrics["source_union"]["exact_mask_rate"] < _SHORTCUT_THRESHOLD
        ),
        "source_regime_table_leaves_headroom": (
            metrics["source_regime_table"]["affected_f1"] < _SHORTCUT_THRESHOLD
            and metrics["source_regime_table"]["exact_mask_rate"] < _SHORTCUT_THRESHOLD
        ),
        "matched_retrieval_leaves_headroom": (
            metrics["matched_retrieval"]["affected_f1"]
            < metrics["learned_graph"]["affected_f1"]
        ),
        "consistent_codebook_program_leaves_headroom": (
            metrics["consistent_codebook_program"]["affected_f1"]
            < metrics["learned_graph"]["affected_f1"]
        ),
        "learned_beats_zero_shot_conservative_program": (
            metrics["learned_graph"]["affected_f1"]
            > metrics["gold_free_program"]["affected_f1"]
            and metrics["learned_graph"]["avg_write_nodes"]
            < metrics["gold_free_program"]["avg_write_nodes"]
        ),
        "gold_free_program_is_recall_safe": (
            metrics["gold_free_program"]["affected_recall"] == 1.0
        ),
        "correctness_necessity_supported": not (
            mask_only_task_solved_by_sufficient_superset
        ),
    }
    admission["pass"] = all(admission.values())
    verdict = (
        "PASS"
        if admission["pass"]
        else "PARTIAL"
        if microbenchmark["pass"]
        else "NO-GO"
    )
    return {
        "task": task,
        "splits": {
            split: sum(ep["split"] == split for ep in episodes)
            for split in ("train", "dev", "test")
        },
        "fit_audit": {
            "learned_graph": learner.summary(),
            "consistent_codebook_program": consistent_program.summary(),
            "shortcut_tables": shortcuts.summary(),
            "shared_non_oracle_training_access": {
                "policy": "all non-oracle baselines may use the same train observed_transition views",
                "eligible_baselines": [
                    name for name in BASELINE_NAMES if name != "oracle_graph"
                ],
                "train_episode_ids": sorted(
                    str(view["episode_id"]) for view in train_views
                ),
            },
            "forbidden_inputs": [
                "gold.graph",
                "gold.active_edges",
                "gold.affected_nodes",
                "designer codebooks",
                "task-card equations",
                "test post_state",
            ],
        },
        "generalization": {
            "train_test_node_id_overlap": len(train_ids & test_ids),
            "train_route_compositions": sorted(train_compositions),
            "test_route_compositions": sorted(test_compositions),
            "downstream_query_mentions": downstream_mentions,
            "downstream_nodes": downstream_total,
        },
        "diagnostics": {
            "propagation_rate": propagation_rate,
            "multihop_rate": multihop_rate,
            "history_potential_edge_exposure_rate": endpoint_exposure_rate,
            "conservative_sufficient_baselines": conservative_sufficient_baselines,
            "mask_only_task_solved_by_sufficient_superset": (
                mask_only_task_solved_by_sufficient_superset
            ),
        },
        "baselines": metrics,
        "microbenchmark": microbenchmark,
        "admission": admission,
        "verdict": verdict,
    }


def audit_dataset(dataset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Run a fail-closed T0/T1-mask audit without APIs or v1 artifacts."""

    episodes = list(dataset)
    for episode in episodes:
        validate_episode(episode)
    unknown = sorted({str(ep["task"]) for ep in episodes} - set(V2_TASKS))
    if unknown:
        raise ValueError(f"unknown hidden-routing tasks: {unknown}")
    domains = {
        task: _domain_audit(task, [ep for ep in episodes if ep["task"] == task])
        for task in V2_TASKS
    }
    structural_replication = _structural_replication_audit(episodes)
    per_domain_microbenchmark_pass = all(
        report["microbenchmark"]["pass"] for report in domains.values()
    )
    per_domain_confirmatory_pass = all(
        report["admission"]["pass"] for report in domains.values()
    )
    correctness_necessity_supported = all(
        report["admission"]["correctness_necessity_supported"]
        for report in domains.values()
    )
    confirmatory_pass = (
        per_domain_confirmatory_pass
        and structural_replication["pass"]
        and correctness_necessity_supported
    )
    verdict = (
        "PASS"
        if confirmatory_pass
        else "PARTIAL"
        if per_domain_microbenchmark_pass
        else "NO-GO"
    )
    return {
        "schema": "hidden-routing-v2-admission/v2",
        "tasks": list(V2_TASKS),
        "episodes": len(episodes),
        "baselines": list(BASELINE_NAMES),
        "domains": domains,
        "structural_replication_audit": structural_replication,
        "access_boundary": {
            "non_oracle_inputs": [
                "train runtime observed_transition",
                "eval pre-query history",
                "eval pre-state",
                "eval structured single intervention",
            ],
            "non_oracle_forbidden": [
                "evaluator graph",
                "affected-node labels",
                "designer codebook",
                "task-card equations",
                "eval post-state",
            ],
            "oracle_inputs": ["evaluator active graph structure"],
            "baseline_training_access": {
                name: "same train runtime observed_transition views permitted"
                for name in BASELINE_NAMES
                if name != "oracle_graph"
            },
            "scoring_order": "freeze all non-oracle masks before post-hoc gold scoring",
        },
        "admission": {
            "claim": "learned hidden causal structure is necessary for correctness",
            "per_domain_microbenchmark_pass": per_domain_microbenchmark_pass,
            "per_domain_confirmatory_pass": per_domain_confirmatory_pass,
            "structurally_independent_domains": structural_replication["pass"],
            "correctness_necessity_supported": correctness_necessity_supported,
            "all_domains_pass": confirmatory_pass,
            "passing_domains": [
                task for task, report in domains.items() if report["admission"]["pass"]
            ],
            "verdict": verdict,
            "supported_scope": (
                "latent codebook decoding and exact sparse impact-mask recovery"
                if per_domain_microbenchmark_pass
                else "no supported benchmark claim"
            ),
            "unsupported_scope": (
                "correctness necessity or independent four-domain replication"
            ),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes-per-domain", type=int, default=36)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    dataset = generate_dataset(args.episodes_per_domain, args.seed)
    report = audit_dataset(dataset)
    payload = {"dataset": dataset, "audit": report}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
