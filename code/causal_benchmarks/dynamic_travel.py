"""Dynamic Travel: an intervention-and-propagation memory benchmark prototype.

Unlike MemoryArena's original travel task, a query changes one already-booked
itinerary state.  The evaluator expects every counterfactually changed downstream
cell to be updated.  Dependency rules are absent from the current query.
Completed transitions are visible only on the train split, allowing an impact
selector to learn repeated mechanisms without reading evaluator graph or
affected-node labels.

The prototype is deterministic and API-free.  T0 checks task admissibility; T1
separates impact selection from a shared deterministic value decoder and reports
effectiveness/efficiency across six frozen arms.  It is not yet an upstream
MemoryArena environment registration or an LLM end-to-end result.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from .common import (
        SCHEMA_VERSION,
        audit_predictions,
        changed_nodes,
        runtime_view,
        validate_episode,
    )
except ImportError:  # direct ``python code/causal_benchmarks/dynamic_travel.py``
    from common import (  # type: ignore
        SCHEMA_VERSION,
        audit_predictions,
        changed_nodes,
        runtime_view,
        validate_episode,
    )


DERIVED_NODES = {
    "transfer.end_hour",
    "attraction.status",
    "attraction.end_hour",
    "dinner.status",
    "dinner.end_hour",
    "hotel.checkin_status",
}

GRAPH = [
    {"source": "flight.arrival_hour", "target": "transfer.end_hour", "regime": "always"},
    {"source": "transfer.duration", "target": "transfer.end_hour", "regime": "always"},
    {"source": "attraction.available", "target": "attraction.status", "regime": "always"},
    {"source": "transfer.end_hour", "target": "attraction.status", "regime": "attraction.available"},
    {"source": "attraction.start_hour", "target": "attraction.status", "regime": "attraction.available"},
    {"source": "attraction.flexible", "target": "attraction.status", "regime": "attraction.available"},
    {"source": "attraction.duration", "target": "attraction.status", "regime": "attraction.available_and_flexible"},
    {"source": "attraction.status", "target": "attraction.end_hour", "regime": "always"},
    {"source": "attraction.start_hour", "target": "attraction.end_hour", "regime": "attraction_scheduled"},
    {"source": "attraction.duration", "target": "attraction.end_hour", "regime": "attraction_active"},
    {"source": "dinner.available", "target": "dinner.status", "regime": "always"},
    {"source": "transfer.end_hour", "target": "dinner.status", "regime": "dinner.available"},
    {"source": "attraction.end_hour", "target": "dinner.status", "regime": "dinner_available_and_attraction_active"},
    {"source": "dinner.start_hour", "target": "dinner.status", "regime": "dinner.available"},
    {"source": "dinner.flexible", "target": "dinner.status", "regime": "dinner.available"},
    {"source": "dinner.status", "target": "dinner.end_hour", "regime": "always"},
    {"source": "dinner.start_hour", "target": "dinner.end_hour", "regime": "dinner_scheduled"},
    {"source": "dinner.duration", "target": "dinner.end_hour", "regime": "dinner_active"},
    {"source": "transfer.end_hour", "target": "hotel.checkin_status", "regime": "always"},
    {"source": "dinner.end_hour", "target": "hotel.checkin_status", "regime": "dinner_active"},
    {"source": "hotel.deadline", "target": "hotel.checkin_status", "regime": "always"},
    {"source": "hotel.late_checkin", "target": "hotel.checkin_status", "regime": "after_deadline"},
]

EVENT_KINDS = (
    "flight_delay",
    "attraction_closure",
    "dinner_closure",
    "hotel_deadline_change",
    "independent_profile_update",
)

ENTITIES = {
    "train": (
        ("Alice", "Kyoto"),
        ("Bao", "Lisbon"),
        ("Camila", "Nairobi"),
        ("Dev", "Oslo"),
    ),
    "dev": (("Elena", "Quito"),),
    "test": (("Farid", "Seoul"), ("Grace", "Tallinn")),
}


def _recompute(state: dict[str, Any]) -> dict[str, Any]:
    """Apply the itinerary SCM to all derived state."""

    out = deepcopy(state)
    transfer_end = int(out["flight.arrival_hour"]) + int(out["transfer.duration"])
    out["transfer.end_hour"] = transfer_end

    if not out["attraction.available"]:
        attraction_status = "cancelled"
        attraction_end = None
    elif transfer_end <= int(out["attraction.start_hour"]) - 1:
        attraction_status = "scheduled"
        attraction_end = int(out["attraction.start_hour"]) + int(out["attraction.duration"])
    elif out["attraction.flexible"] and transfer_end + 1 + int(out["attraction.duration"]) <= 22:
        attraction_status = "rescheduled"
        attraction_end = transfer_end + 1 + int(out["attraction.duration"])
    else:
        attraction_status = "cancelled"
        attraction_end = None
    out["attraction.status"] = attraction_status
    out["attraction.end_hour"] = attraction_end

    ready_for_dinner = transfer_end
    if attraction_end is not None:
        ready_for_dinner = max(ready_for_dinner, attraction_end)
    if not out["dinner.available"]:
        dinner_status = "cancelled"
        dinner_end = None
    elif ready_for_dinner <= int(out["dinner.start_hour"]):
        dinner_status = "scheduled"
        dinner_end = int(out["dinner.start_hour"]) + int(out["dinner.duration"])
    elif out["dinner.flexible"] and ready_for_dinner + 1 + int(out["dinner.duration"]) <= 24:
        dinner_status = "rescheduled"
        dinner_end = ready_for_dinner + 1 + int(out["dinner.duration"])
    else:
        dinner_status = "cancelled"
        dinner_end = None
    out["dinner.status"] = dinner_status
    out["dinner.end_hour"] = dinner_end

    ready_for_hotel = max(transfer_end, dinner_end or transfer_end)
    deadline = int(out["hotel.deadline"])
    if ready_for_hotel <= deadline:
        hotel_status = "on_time"
    elif out["hotel.late_checkin"]:
        hotel_status = "late_allowed"
    else:
        hotel_status = "missed"
    out["hotel.checkin_status"] = hotel_status
    return out


def _active(edge: dict[str, str], state: dict[str, Any]) -> bool:
    regime = edge["regime"]
    if regime == "always":
        return True
    if regime == "attraction.available":
        return bool(state["attraction.available"])
    if regime == "attraction.available_and_flexible":
        return bool(state["attraction.available"] and state["attraction.flexible"])
    if regime == "attraction_scheduled":
        return state["attraction.status"] == "scheduled"
    if regime == "attraction_active":
        return state["attraction.status"] != "cancelled"
    if regime == "dinner.available":
        return bool(state["dinner.available"])
    if regime == "dinner_available_and_attraction_active":
        return bool(state["dinner.available"] and state["attraction.status"] != "cancelled")
    if regime == "dinner_scheduled":
        return state["dinner.status"] == "scheduled"
    if regime == "dinner_active":
        return state["dinner.status"] != "cancelled"
    if regime == "after_deadline":
        ready = max(
            int(state["transfer.end_hour"]),
            int(state["dinner.end_hour"] or state["transfer.end_hour"]),
        )
        return ready > int(state["hotel.deadline"])
    raise ValueError(f"unknown regime: {regime}")


def _base_state(rng: random.Random, split: str, index: int) -> dict[str, Any]:
    arrival = rng.randint(9, 12)
    transfer_duration = rng.randint(1, 2)
    transfer_end = arrival + transfer_duration
    attraction_start = max(rng.randint(14, 17), transfer_end + 1)
    attraction_duration = rng.choice((1, 2))
    dinner_start = max(rng.randint(18, 21), attraction_start + attraction_duration)
    state = {
        "flight.arrival_hour": arrival,
        "transfer.duration": transfer_duration,
        "attraction.available": True,
        "attraction.start_hour": attraction_start,
        "attraction.duration": attraction_duration,
        "attraction.flexible": rng.choice((True, False)),
        "dinner.available": True,
        "dinner.start_hour": dinner_start,
        "dinner.duration": 1,
        "dinner.flexible": rng.choice((True, False)),
        "hotel.deadline": max(rng.randint(22, 24), dinner_start + 1),
        "hotel.late_checkin": rng.choice((True, False)),
        "profile.emergency_contact": rng.choice(("Mina", "Noah", "Priya", "Theo")),
    }
    # Hold one compositional gate regime out of training.  Test blocks alternate
    # between this unseen all-fixed/no-late-check-in regime and ordinary regimes.
    if split == "train" and not any(
        (
            state["attraction.flexible"],
            state["dinner.flexible"],
            state["hotel.late_checkin"],
        )
    ):
        state["hotel.late_checkin"] = True
    if split == "test" and (index // len(EVENT_KINDS)) % 2 == 0:
        state["attraction.flexible"] = False
        state["dinner.flexible"] = False
        state["hotel.late_checkin"] = False
    return _recompute(state)


def _intervention(
    kind: str,
    state: dict[str, Any],
    rng: random.Random,
    split: str,
) -> tuple[str, Any, str]:
    if kind == "flight_delay":
        value = rng.choice(
            {"train": (18, 19, 20), "dev": (21,), "test": (22, 23)}[split]
        )
        wording = (
            f"The inbound service will not reach the gate before {value}:00. "
            "Reconcile all dependent bookings."
            if split == "test"
            else f"The airline now says the flight arrives at {value}:00. Update the itinerary."
        )
        return (
            "flight.arrival_hour",
            value,
            wording,
        )
    if kind == "attraction_closure":
        return (
            "attraction.available",
            False,
            "The booked attraction has closed for the day. Update the itinerary.",
        )
    if kind == "dinner_closure":
        return (
            "dinner.available",
            False,
            "The reserved restaurant has unexpectedly closed. Update the itinerary.",
        )
    if kind == "hotel_deadline_change":
        value = {"train": 17, "dev": 16, "test": 15}[split]
        return (
            "hotel.deadline",
            value,
            f"The hotel moved its check-in deadline to {value}:00. Update the itinerary.",
        )
    if kind == "independent_profile_update":
        choices = [name for name in ("Mina", "Noah", "Priya", "Theo")
                   if name != state["profile.emergency_contact"]]
        value = rng.choice(choices)
        return (
            "profile.emergency_contact",
            value,
            f"Change the emergency contact to {value}.",
        )
    raise ValueError(f"unknown event kind: {kind}")


def _required_reads(kind: str) -> list[str]:
    shared_schedule = [
        "transfer.duration",
        "attraction.available",
        "attraction.start_hour",
        "attraction.duration",
        "attraction.flexible",
        "dinner.available",
        "dinner.start_hour",
        "dinner.duration",
        "dinner.flexible",
        "hotel.deadline",
        "hotel.late_checkin",
    ]
    if kind == "flight_delay":
        return shared_schedule
    if kind == "attraction_closure":
        return [
            "transfer.end_hour",
            "attraction.start_hour",
            "attraction.duration",
            "attraction.flexible",
            "dinner.available",
            "dinner.start_hour",
            "dinner.duration",
            "dinner.flexible",
            "hotel.deadline",
            "hotel.late_checkin",
        ]
    if kind == "dinner_closure":
        return [
            "transfer.end_hour",
            "attraction.end_hour",
            "dinner.start_hour",
            "dinner.duration",
            "dinner.flexible",
            "hotel.deadline",
            "hotel.late_checkin",
        ]
    if kind == "hotel_deadline_change":
        return ["transfer.end_hour", "dinner.end_hour", "hotel.late_checkin"]
    return []


def _history(state: dict[str, Any], rng: random.Random, traveler: str, city: str) -> list[dict[str, Any]]:
    facts = [
        f"{traveler}'s flight to {city} is scheduled to arrive at {state['flight.arrival_hour']}:00.",
        f"Airport transfer takes {state['transfer.duration']} hour(s).",
        f"The attraction starts at {state['attraction.start_hour']}:00, lasts {state['attraction.duration']} hour(s), and is {'flexible' if state['attraction.flexible'] else 'fixed'}.",
        f"Dinner starts at {state['dinner.start_hour']}:00 and is {'flexible' if state['dinner.flexible'] else 'fixed'}.",
        f"Hotel check-in closes at {state['hotel.deadline']}:00; late check-in is {'allowed' if state['hotel.late_checkin'] else 'not allowed'}.",
        f"The emergency contact is {state['profile.emergency_contact']}.",
    ]
    distractors = [
        f"A different traveler saved museum note {rng.randint(100, 999)}.",
        f"A weather bulletin for another city was archived as item {rng.randint(100, 999)}.",
        f"An old restaurant search returned reference {rng.randint(100, 999)}.",
        f"A loyalty-program message has code {rng.randint(100, 999)}.",
    ]
    rows = [
        {"t": index, "kind": "memory_write", "text": text}
        for index, text in enumerate(facts + distractors)
    ]
    rng.shuffle(rows)
    for index, row in enumerate(rows):
        row["t"] = index
    return rows


def _split(index: int) -> str:
    # Split complete five-event blocks so every family appears in every split.
    bucket = (index // len(EVENT_KINDS)) % 10
    return "train" if bucket < 7 else "dev" if bucket == 7 else "test"


def generate_episode(index: int, rng: random.Random) -> dict[str, Any]:
    split = _split(index)
    traveler, city = rng.choice(ENTITIES[split])
    before = _base_state(rng, split, index)
    kind = EVENT_KINDS[index % len(EVENT_KINDS)]
    node, value, query_text = _intervention(kind, before, rng, split)
    intervened = deepcopy(before)
    intervened[node] = value
    after = _recompute(intervened)
    affected = changed_nodes(before, after)
    active_edges = [edge for edge in GRAPH if _active(edge, after)]
    episode = {
        "schema_version": SCHEMA_VERSION,
        "task": "dynamic_travel",
        "episode_id": f"dynamic-travel-{index:05d}",
        "split": split,
        "mechanism_id": "travel-itinerary-scm/v1",
        "entity": {"traveler": traveler, "day": 2, "city": city},
        "event_kind": kind,
        "history": _history(before, rng, traveler, city),
        "memory_state": before,
        "query": {
            "text": f"I am updating {traveler}'s day-2 trip to {city}. {query_text}",
            "intervention": {
                "node": node,
                "old_value": before[node],
                "new_value": value,
                "kind": kind,
            },
        },
        "gold": {
            "graph": GRAPH,
            "active_edges": active_edges,
            "affected_nodes": affected,
            "required_reads": _required_reads(kind),
            "post_state": after,
        },
        "generalization": {
            "entity_partition": split,
            "intervention_value_partition": split,
            "template_partition": "paraphrased" if split == "test" else "standard",
            "regime_signature": [
                before["attraction.flexible"],
                before["dinner.flexible"],
                before["hotel.late_checkin"],
            ],
        },
    }
    if split == "train":
        episode["observed_transition"] = {
            "pre_state": deepcopy(before),
            "intervention": deepcopy(episode["query"]["intervention"]),
            "post_state": deepcopy(after),
        }
    validate_episode(episode)
    return episode


def generate_dataset(episodes: int = 100, seed: int = 0) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    return [generate_episode(index, rng) for index in range(episodes)]


def exact_key_baseline(episode: dict[str, Any]) -> dict[str, Any]:
    """Apply only the query-explicit key/value and perform no propagation."""

    state = deepcopy(episode["memory_state"])
    intervention = episode["query"]["intervention"]
    state[intervention["node"]] = intervention["new_value"]
    return {"affected_nodes": [intervention["node"]], "post_state": state}


def oracle_propagation_baseline(episode: dict[str, Any]) -> dict[str, Any]:
    """Recompute the SCM; used only as a simulator and evaluation upper bound."""

    state = deepcopy(episode["memory_state"])
    intervention = episode["query"]["intervention"]
    state[intervention["node"]] = intervention["new_value"]
    state = _recompute(state)
    return {"affected_nodes": changed_nodes(episode["memory_state"], state), "post_state": state}


class LearnedImpactSelector:
    """Interventional reachability learned only from completed train transitions.

    The selector estimates a type-level impact graph rather than copying a gold
    adjacency matrix.  An edge ``source -> target`` is retained when at least one
    observed intervention on ``source`` changed ``target``.  This deliberately
    favors recall; regime-specific false positives remain visible in precision
    and efficiency, so the T1 cannot hide a missing gate model.
    """

    def __init__(self, effects: Mapping[str, Sequence[str]], transitions: int):
        self.effects = {source: set(targets) for source, targets in effects.items()}
        self.transitions = transitions

    @classmethod
    def fit(cls, train_views: Sequence[Mapping[str, Any]]) -> "LearnedImpactSelector":
        effects: dict[str, set[str]] = {}
        transitions = 0
        for view in train_views:
            if "gold" in view:
                raise ValueError("learner received evaluator gold")
            observed = view.get("observed_transition")
            if view.get("split") != "train" or not isinstance(observed, Mapping):
                raise ValueError("learner requires completed train transitions")
            source = str(observed["intervention"]["node"])
            effects.setdefault(source, set()).update(
                changed_nodes(observed["pre_state"], observed["post_state"])
            )
            transitions += 1
        return cls({key: sorted(value) for key, value in effects.items()}, transitions)

    def predict(self, view: Mapping[str, Any]) -> list[str]:
        if "gold" in view or "observed_transition" in view:
            raise ValueError("test selector received a forbidden outcome field")
        source = str(view["query"]["intervention"]["node"])
        return sorted(self.effects.get(source, {source}) | {source})

    def graph(self) -> list[dict[str, str]]:
        return [
            {"source": source, "target": target, "kind": "observed_interventional_impact"}
            for source in sorted(self.effects)
            for target in sorted(self.effects[source])
            if target != source
        ]


_TOKEN = re.compile(r"[a-z0-9]+")


def _lexical_selector(view: Mapping[str, Any], budget: int) -> list[str]:
    """Query-aware cell retrieval at exactly the learned selector's cell budget."""

    query_tokens = set(_TOKEN.findall(str(view["query"]["text"]).lower()))
    explicit = str(view["query"]["intervention"]["node"])
    ranked = []
    for key in view["memory_state"]:
        key_tokens = set(_TOKEN.findall(key.lower().replace("_", " ").replace(".", " ")))
        score = len(query_tokens & key_tokens) + (100 if key == explicit else 0)
        ranked.append((-score, key))
    return sorted(key for _, key in sorted(ranked)[: max(1, budget)])


def _domain_impacted(view: Mapping[str, Any]) -> list[str]:
    before = view["memory_state"]
    state = deepcopy(before)
    intervention = view["query"]["intervention"]
    state[intervention["node"]] = intervention["new_value"]
    return changed_nodes(before, _recompute(state))


def _prediction_from_impacted(
    view: Mapping[str, Any], impacted: Sequence[str]
) -> dict[str, Any]:
    """Use one shared value oracle but write only selector-predicted impact cells."""

    before = view["memory_state"]
    intervention = view["query"]["intervention"]
    oracle_input = deepcopy(before)
    oracle_input[intervention["node"]] = intervention["new_value"]
    oracle_post = _recompute(oracle_input)
    predicted = sorted(set(impacted) | {str(intervention["node"])})
    post = deepcopy(before)
    for node in predicted:
        post[node] = deepcopy(oracle_post[node])
    return {
        "affected_nodes": predicted,
        "selected_nodes": predicted,
        "post_state": post,
    }


def _serialize_selection(
    view: Mapping[str, Any], selected: Sequence[str], style: str
) -> str:
    values = {key: view["memory_state"][key] for key in sorted(set(selected))}
    if style == "compact":
        return json.dumps(values, sort_keys=True, separators=(",", ":"))
    if style == "verbose":
        return "\n".join(
            f"The current itinerary state cell {key} stores the value {value!r}."
            for key, value in values.items()
        )
    raise ValueError(style)


def _t1_arm_predictions(
    episode: Mapping[str, Any],
    view: Mapping[str, Any],
    learner: LearnedImpactSelector,
) -> dict[str, dict[str, Any]]:
    learned = learner.predict(view)
    explicit = [str(view["query"]["intervention"]["node"])]
    arms = {
        "exact_kv": explicit,
        "domain_solver": _domain_impacted(view),
        "matched_lexical": _lexical_selector(view, len(learned)),
        "learned_graph": learned,
        "oracle_graph": list(episode["gold"]["affected_nodes"]),
        "full_state": list(view["memory_state"]),
    }
    return {
        name: _prediction_from_impacted(view, impacted)
        for name, impacted in arms.items()
    }


def evaluate_t1(dataset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Run the frozen six-arm impact-selection and serialization experiment."""

    dataset = list(dataset)
    for episode in dataset:
        validate_episode(episode)
    train = [episode for episode in dataset if episode["split"] == "train"]
    test = [episode for episode in dataset if episode["split"] == "test"]
    train_views = [runtime_view(episode, training=True) for episode in train]
    test_views = [runtime_view(episode) for episode in test]
    if not train or not test:
        raise ValueError("T1 requires non-empty train and test splits")
    if any("gold" in view for view in train_views + test_views):
        raise ValueError("runtime projection leaked evaluator gold")
    if any("observed_transition" in view for view in test_views):
        raise ValueError("test runtime projection leaked an outcome")

    learner = LearnedImpactSelector.fit(train_views)
    per_episode = [
        _t1_arm_predictions(episode, view, learner)
        for episode, view in zip(test, test_views)
    ]
    arm_names = list(per_episode[0])
    metrics: dict[str, Any] = {}
    for arm in arm_names:
        predictions = [row[arm] for row in per_episode]
        scored = audit_predictions(test, predictions)
        scored.pop("per_episode", None)
        scored["task_success_rate"] = sum(
            prediction["post_state"] == episode["gold"]["post_state"]
            for episode, prediction in zip(test, predictions)
        ) / len(test)
        controls = [
            (episode, prediction)
            for episode, prediction in zip(test, predictions)
            if episode["event_kind"] == "independent_profile_update"
        ]
        scored["negative_control_specificity"] = sum(
            set(prediction["affected_nodes"])
            == {episode["query"]["intervention"]["node"]}
            for episode, prediction in controls
        ) / max(1, len(controls))
        scored["serialization"] = {}
        for style in ("compact", "verbose"):
            sizes = [
                len(_serialize_selection(view, prediction["selected_nodes"], style))
                for view, prediction in zip(test_views, predictions)
            ]
            cells = [len(prediction["selected_nodes"]) for prediction in predictions]
            scored["serialization"][style] = {
                "avg_selected_cells": sum(cells) / len(cells),
                "avg_context_chars": sum(sizes) / len(sizes),
                "avg_token_proxy": sum(math.ceil(size / 4) for size in sizes) / len(sizes),
            }
        metrics[arm] = scored

    train_entities = {(ep["entity"]["traveler"], ep["entity"]["city"]) for ep in train}
    test_entities = {(ep["entity"]["traveler"], ep["entity"]["city"]) for ep in test}
    train_values: dict[str, set[Any]] = {}
    test_values: dict[str, set[Any]] = {}
    for episodes, target in ((train, train_values), (test, test_values)):
        for episode in episodes:
            intervention = episode["query"]["intervention"]
            target.setdefault(intervention["node"], set()).add(intervention["new_value"])
    numeric_holdout = {
        node: sorted(test_values.get(node, set()) - train_values.get(node, set()))
        for node in ("flight.arrival_hour", "hotel.deadline")
    }
    train_regimes = {tuple(ep["generalization"]["regime_signature"]) for ep in train}
    test_regimes = {tuple(ep["generalization"]["regime_signature"]) for ep in test}
    learned = metrics["learned_graph"]
    lexical = metrics["matched_lexical"]
    domain = metrics["domain_solver"]
    learned_cost = learned["serialization"]["compact"]["avg_context_chars"]
    lexical_cost = lexical["serialization"]["compact"]["avg_context_chars"]
    domain_cost = domain["serialization"]["compact"]["avg_context_chars"]
    admission = {
        "train_test_runtime_isolated": True,
        "unseen_entities": not bool(train_entities & test_entities),
        "unseen_numeric_intervention_values": all(numeric_holdout.values()),
        "held_out_regime_combination": bool(test_regimes - train_regimes),
        "learned_beats_matched_retrieval_at_budget": (
            learned["affected_recall"] > lexical["affected_recall"]
            and learned_cost <= lexical_cost * 1.05
        ),
        "learned_preserves_negative_controls": (
            learned["negative_control_specificity"] == 1.0
        ),
        "learned_pareto_dominates_domain_solver": (
            learned["task_success_rate"] >= domain["task_success_rate"]
            and learned_cost < domain_cost
        ),
    }
    admission["causal_learning_claim_pass"] = all(admission.values())
    return {
        "schema": "causal-memory-t1-selection/v1",
        "task": "dynamic_travel",
        "train_episodes": len(train),
        "test_episodes": len(test),
        "learner": {
            "kind": "train-only interventional impact graph",
            "observed_transitions": learner.transitions,
            "graph": learner.graph(),
            "forbidden_inputs": ["gold.graph", "gold.affected_nodes", "test post_state"],
        },
        "generalization": {
            "train_test_entity_overlap": len(train_entities & test_entities),
            "held_out_numeric_values": numeric_holdout,
            "held_out_regime_signatures": [
                list(signature) for signature in sorted(test_regimes - train_regimes)
            ],
            "test_template": "paraphrased",
        },
        "value_decoder_boundary": (
            "All selection arms share the deterministic SCM value decoder, which writes "
            "only predicted impact cells. Task success isolates selection sufficiency; "
            "it is not an end-to-end language or equation-learning result."
        ),
        "arms": metrics,
        "admission": admission,
    }


def audit_dataset(dataset: list[dict[str, Any]]) -> dict[str, Any]:
    exact_predictions = [exact_key_baseline(ep) for ep in dataset]
    oracle_predictions = [oracle_propagation_baseline(ep) for ep in dataset]
    exact = audit_predictions(dataset, exact_predictions)
    oracle = audit_predictions(dataset, oracle_predictions)
    exact["episode_success_rate"] = sum(
        prediction["post_state"] == episode["gold"]["post_state"]
        for episode, prediction in zip(dataset, exact_predictions)
    ) / len(dataset)
    oracle["episode_success_rate"] = sum(
        prediction["post_state"] == episode["gold"]["post_state"]
        for episode, prediction in zip(dataset, oracle_predictions)
    ) / len(dataset)
    event_counts = Counter(ep["event_kind"] for ep in dataset)
    event_breakdown = {}
    for event_kind in sorted(event_counts):
        subset = [ep for ep in dataset if ep["event_kind"] == event_kind]
        subset_exact = audit_predictions(
            subset, [exact_key_baseline(ep) for ep in subset]
        )
        affected_sizes = [len(ep["gold"]["affected_nodes"]) for ep in subset]
        event_breakdown[event_kind] = {
            "episodes": len(subset),
            "affected_nodes_min": min(affected_sizes),
            "affected_nodes_mean": sum(affected_sizes) / len(affected_sizes),
            "affected_nodes_max": max(affected_sizes),
            "exact_kv_affected_recall": subset_exact["affected_recall"],
        }
    downstream_aliases = {
        "transfer.end_hour": "transfer end",
        "attraction.status": "attraction status",
        "attraction.end_hour": "attraction end",
        "dinner.status": "dinner status",
        "dinner.end_hour": "dinner end",
        "hotel.checkin_status": "checkin status",
    }
    leaked = 0
    downstream = 0
    for episode in dataset:
        query = episode["query"]["text"].lower()
        intervention = episode["query"]["intervention"]["node"]
        for node in episode["gold"]["affected_nodes"]:
            if node == intervention:
                continue
            downstream += 1
            leaked += int(downstream_aliases.get(node, node).lower() in query)

    propagation_fraction = exact["propagation_required_episodes"] / max(1, len(dataset))
    admission = {
        "propagation_fraction_at_least_half": propagation_fraction >= 0.5,
        "exact_kv_affected_recall_below_95_percent": exact["affected_recall"] < 0.95,
        "oracle_affected_state_accuracy_is_one": oracle["affected_state_accuracy"] == 1.0,
        "no_downstream_query_leakage": leaked == 0,
    }
    admission["pass"] = all(admission.values())
    return {
        "schema": "causal-memory-t0-audit/v1",
        "task": "dynamic_travel",
        "event_counts": dict(sorted(event_counts.items())),
        "event_breakdown": event_breakdown,
        "propagation_fraction": propagation_fraction,
        "downstream_query_leakage": {
            "leaked": leaked,
            "downstream_changed_nodes": downstream,
            "rate": leaked / max(1, downstream),
        },
        "exact_kv": {key: value for key, value in exact.items() if key != "per_episode"},
        "oracle": {key: value for key, value in oracle.items() if key != "per_episode"},
        "admission": admission,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--audit-out", type=Path)
    parser.add_argument("--t1-out", type=Path)
    args = parser.parse_args()

    dataset = generate_dataset(args.episodes, args.seed)
    audit = audit_dataset(dataset)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(dataset, indent=2, ensure_ascii=False))
    if args.audit_out:
        args.audit_out.parent.mkdir(parents=True, exist_ok=True)
        args.audit_out.write_text(json.dumps(audit, indent=2, ensure_ascii=False))
    t1 = evaluate_t1(dataset) if args.t1_out else None
    if args.t1_out and t1 is not None:
        args.t1_out.parent.mkdir(parents=True, exist_ok=True)
        args.t1_out.write_text(json.dumps(t1, indent=2, ensure_ascii=False))
    print(json.dumps(t1 or audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
