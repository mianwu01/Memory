"""Deterministic interventional formal-reasoning benchmark prototype.

The original MemoryArena math/physics tasks contain useful implicit symbol
dependencies, but do not expose interventional ground truth.  This module keeps
the sequential-notebook shape while making an upstream correction explicit and
using a deterministic simulator to recompute every downstream result.

Only the Python standard library is required.  Run the zero-LLM gate with::

    python3 code/causal_benchmarks/causal_formal.py t0 --count 120 --seed 17

or emit JSONL episodes with ``generate``.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

try:  # Package import under unittest/module execution.
    from .common import (
        SCHEMA_VERSION,
        audit_predictions,
        runtime_view as shared_runtime_view,
        validate_episode,
    )
except ImportError:  # Direct ``python code/.../causal_formal.py`` execution.
    from common import (  # type: ignore
        SCHEMA_VERSION,
        audit_predictions,
        runtime_view as shared_runtime_view,
        validate_episode,
    )


Value = int | bool
Evaluator = Callable[[Mapping[str, Value]], Value]


@dataclass(frozen=True)
class DerivedNode:
    """One deterministic notebook result in topological order."""

    name: str
    parents: tuple[str, ...]
    formula: str
    evaluate: Evaluator
    # A parent edge is active only when ``gate(state)`` is true.  The formula
    # must obey the same condition.  Other parent edges are always active.
    gated_parents: tuple[tuple[str, str, Callable[[Mapping[str, Value]], bool]], ...] = ()


@dataclass(frozen=True)
class FamilySpec:
    """A reusable formal notebook mechanism shared across episodes."""

    name: str
    task: str
    primitives: tuple[str, ...]
    derived: tuple[DerivedNode, ...]
    negative_controls: tuple[str, ...]


def _math_spec() -> FamilySpec:
    return FamilySpec(
        name="affine_recurrence",
        task="causal_formal_math",
        primitives=(
            "parameter.base",
            "definition.step",
            "axiom.twist_enabled",
            "definition.twist",
            "control.notation_scale",
        ),
        derived=(
            DerivedNode(
                "lemma.term_2",
                ("parameter.base", "definition.step"),
                "term_2 := base + step",
                lambda s: int(s["parameter.base"]) + int(s["definition.step"]),
            ),
            DerivedNode(
                "lemma.term_3",
                ("lemma.term_2", "definition.step"),
                "term_3 := term_2 + step",
                lambda s: int(s["lemma.term_2"]) + int(s["definition.step"]),
            ),
            DerivedNode(
                "theorem.core",
                ("lemma.term_3",),
                "core := 2 * term_3",
                lambda s: 2 * int(s["lemma.term_3"]),
            ),
            DerivedNode(
                "lemma.active_branch",
                (
                    "theorem.core",
                    "axiom.twist_enabled",
                    "definition.twist",
                ),
                "active_branch := core + twist if twist_enabled else core",
                lambda s: int(s["theorem.core"])
                + (
                    int(s["definition.twist"])
                    if bool(s["axiom.twist_enabled"])
                    else 0
                ),
                gated_parents=(
                    (
                        "definition.twist",
                        "axiom.twist_enabled == true",
                        lambda s: bool(s["axiom.twist_enabled"]),
                    ),
                ),
            ),
            DerivedNode(
                "theorem.final",
                ("lemma.active_branch", "parameter.base"),
                "final := active_branch - base",
                lambda s: int(s["lemma.active_branch"])
                - int(s["parameter.base"]),
            ),
            DerivedNode(
                "control.notation_invariant",
                ("control.notation_scale",),
                "notation_invariant := notation_scale ** 2",
                lambda s: int(s["control.notation_scale"]) ** 2,
            ),
        ),
        negative_controls=("control.notation_scale", "control.notation_invariant"),
    )


def _physics_spec() -> FamilySpec:
    return FamilySpec(
        name="gated_motion",
        task="causal_formal_phys",
        primitives=(
            "parameter.mass",
            "parameter.velocity",
            "definition.drag_coefficient",
            "axiom.field_enabled",
            "parameter.field_strength",
            "parameter.duration",
            "control.detector_bias",
        ),
        derived=(
            DerivedNode(
                "lemma.inertial_momentum",
                ("parameter.mass", "parameter.velocity"),
                "inertial_momentum := mass * velocity",
                lambda s: int(s["parameter.mass"]) * int(s["parameter.velocity"]),
            ),
            DerivedNode(
                "lemma.drag_loss",
                ("definition.drag_coefficient", "parameter.velocity"),
                "drag_loss := drag_coefficient * velocity",
                lambda s: int(s["definition.drag_coefficient"])
                * int(s["parameter.velocity"]),
            ),
            DerivedNode(
                "theorem.net_momentum",
                ("lemma.inertial_momentum", "lemma.drag_loss"),
                "net_momentum := inertial_momentum - drag_loss",
                lambda s: int(s["lemma.inertial_momentum"])
                - int(s["lemma.drag_loss"]),
            ),
            DerivedNode(
                "lemma.active_force",
                (
                    "theorem.net_momentum",
                    "axiom.field_enabled",
                    "parameter.field_strength",
                ),
                "active_force := net_momentum + field_strength if field_enabled else net_momentum",
                lambda s: int(s["theorem.net_momentum"])
                + (
                    int(s["parameter.field_strength"])
                    if bool(s["axiom.field_enabled"])
                    else 0
                ),
                gated_parents=(
                    (
                        "parameter.field_strength",
                        "axiom.field_enabled == true",
                        lambda s: bool(s["axiom.field_enabled"]),
                    ),
                ),
            ),
            DerivedNode(
                "theorem.displacement_score",
                ("lemma.active_force", "parameter.duration"),
                "displacement_score := active_force * duration",
                lambda s: int(s["lemma.active_force"]) * int(s["parameter.duration"]),
            ),
            DerivedNode(
                "control.calibration_checksum",
                ("control.detector_bias",),
                "calibration_checksum := detector_bias ** 2 + 1",
                lambda s: int(s["control.detector_bias"]) ** 2 + 1,
            ),
        ),
        negative_controls=("control.detector_bias", "control.calibration_checksum"),
    )


SPECS = {spec.task: spec for spec in (_math_spec(), _physics_spec())}


def _derived_by_name(spec: FamilySpec) -> dict[str, DerivedNode]:
    return {node.name: node for node in spec.derived}


def _materialize(spec: FamilySpec, primitive_state: Mapping[str, Value]) -> dict[str, Value]:
    """Evaluate a complete notebook from primitive values."""

    missing = sorted(set(spec.primitives) - set(primitive_state))
    if missing:
        raise ValueError(f"missing primitive state for {spec.task}: {missing}")
    state: dict[str, Value] = {key: primitive_state[key] for key in spec.primitives}
    for node in spec.derived:
        state[node.name] = node.evaluate(state)
    return state


def _edge_records(spec: FamilySpec) -> list[dict[str, str]]:
    graph = []
    for node in spec.derived:
        gates = {parent: condition for parent, condition, _ in node.gated_parents}
        for parent in node.parents:
            graph.append(
                {
                    "source": parent,
                    "target": node.name,
                    "condition": gates.get(parent, "always"),
                }
            )
    return graph


def _active_edges(spec: FamilySpec, state: Mapping[str, Value]) -> list[dict[str, str]]:
    active = []
    for node in spec.derived:
        gates = {parent: gate for parent, _, gate in node.gated_parents}
        conditions = {
            parent: condition for parent, condition, _ in node.gated_parents
        }
        for parent in node.parents:
            if parent not in gates or gates[parent](state):
                active.append(
                    {
                        "source": parent,
                        "target": node.name,
                        "condition": conditions.get(parent, "always"),
                    }
                )
    return active


def simulate(
    task: str,
    pre_state: Mapping[str, Value],
    intervention: Mapping[str, Any],
) -> dict[str, Value]:
    """Apply one primitive intervention and recompute the formal notebook.

    This function is the independent structural mechanism used by the oracle
    baseline.  It intentionally has no episode/gold argument.
    """

    spec = SPECS[task]
    target = str(intervention["node"])
    if target not in spec.primitives:
        raise ValueError(f"intervention target must be primitive: {target}")
    primitives = {key: pre_state[key] for key in spec.primitives}
    primitives[target] = intervention["new_value"]
    return _materialize(spec, primitives)


def _required_reads(
    spec: FamilySpec,
    affected_results: Sequence[str],
    post_state: Mapping[str, Value],
    intervention_target: str,
) -> list[str]:
    """Return non-intervened primitive values needed to recompute changed results."""

    active_parents: dict[str, list[str]] = {}
    for edge in _active_edges(spec, post_state):
        active_parents.setdefault(edge["target"], []).append(edge["source"])

    required: set[str] = set()
    frontier = list(affected_results)
    seen: set[str] = set()
    while frontier:
        node = frontier.pop()
        if node in seen:
            continue
        seen.add(node)
        for parent in active_parents.get(node, []):
            if parent in spec.primitives:
                if parent != intervention_target:
                    required.add(parent)
            else:
                frontier.append(parent)
    return sorted(required)


def _split_for(index: int) -> str:
    # Scenarios cycle every six local episodes.  Splitting by the repetition
    # index guarantees that, once each scenario has ten repetitions, every
    # intervention kind occurs in train, dev and test without state overlap.
    bucket = (index // 6) % 10
    if bucket < 7:
        return "train"
    if bucket < 8:
        return "dev"
    return "test"


def _math_primitive_state(
    rng: random.Random, scenario: int, split: str
) -> dict[str, Value]:
    ranges = {
        "train": ((2, 8), (2, 6), (1, 5), (6, 11)),
        "dev": ((12, 18), (9, 12), (8, 11), (15, 20)),
        "test": ((22, 30), (15, 20), (14, 19), (25, 31)),
    }
    base_range, step_range, twist_range, control_range = ranges[split]
    # Test parameter/definition corrections combine their source with an
    # inactive gate, a target-regime pairing never used for those sources in
    # train.  The topology itself remains shared and learnable.
    twist_enabled = scenario not in {3, 5}
    if split == "test" and scenario in {0, 1}:
        twist_enabled = False
    return {
        "parameter.base": rng.randint(*base_range),
        "definition.step": rng.randint(*step_range),
        "axiom.twist_enabled": twist_enabled,
        "definition.twist": rng.randint(*twist_range),
        "control.notation_scale": rng.randint(*control_range),
    }


def _physics_primitive_state(
    rng: random.Random, scenario: int, split: str
) -> dict[str, Value]:
    ranges = {
        "train": ((3, 9), (3, 8), (1, 2), (2, 7), (2, 5), (8, 13)),
        "dev": ((13, 19), (12, 17), (5, 6), (11, 16), (8, 11), (18, 23)),
        "test": ((23, 31), (21, 28), (9, 11), (20, 27), (14, 18), (28, 35)),
    }
    mass, velocity, drag, field, duration, control = ranges[split]
    field_enabled = scenario not in {3, 5}
    if split == "test" and scenario in {0, 1}:
        field_enabled = False
    return {
        "parameter.mass": rng.randint(*mass),
        "parameter.velocity": rng.randint(*velocity),
        "definition.drag_coefficient": rng.randint(*drag),
        "axiom.field_enabled": field_enabled,
        "parameter.field_strength": rng.randint(*field),
        "parameter.duration": rng.randint(*duration),
        "control.detector_bias": rng.randint(*control),
    }


def _intervention_for(
    spec: FamilySpec,
    state: Mapping[str, Value],
    scenario: int,
) -> dict[str, Any]:
    """Cycle through parameter, definition, axiom and gated interventions."""

    if spec.task == "causal_formal_math":
        choices = (
            ("parameter.base", int(state["parameter.base"]) + 2, "parameter_correction"),
            ("definition.step", int(state["definition.step"]) + 1, "definition_correction"),
            ("axiom.twist_enabled", False, "axiom_retraction"),
            ("axiom.twist_enabled", True, "axiom_activation"),
            ("definition.twist", int(state["definition.twist"]) + 3, "active_gate_update"),
            ("definition.twist", int(state["definition.twist"]) + 3, "inactive_gate_update"),
        )
    else:
        choices = (
            ("parameter.mass", int(state["parameter.mass"]) + 2, "parameter_correction"),
            (
                "definition.drag_coefficient",
                int(state["definition.drag_coefficient"]) + 1,
                "definition_correction",
            ),
            ("axiom.field_enabled", False, "axiom_retraction"),
            ("axiom.field_enabled", True, "axiom_activation"),
            (
                "parameter.field_strength",
                int(state["parameter.field_strength"]) + 3,
                "active_gate_update",
            ),
            (
                "parameter.field_strength",
                int(state["parameter.field_strength"]) + 3,
                "inactive_gate_update",
            ),
        )
    target, new_value, kind = choices[scenario % len(choices)]
    return {
        "node": target,
        "old_value": state[target],
        "new_value": new_value,
        "kind": kind,
    }


def _history(spec: FamilySpec, state: Mapping[str, Value]) -> list[dict[str, str]]:
    entries = []
    for position, primitive in enumerate(spec.primitives, start=1):
        entries.append(
            {
                "entry_id": f"primitive-{position}",
                "node": primitive,
                "text": f"Notebook primitive or assumption: {primitive} = {state[primitive]}.",
            }
        )
    for position, node in enumerate(spec.derived, start=1):
        entries.append(
            {
                "entry_id": f"derivation-{position}",
                "node": node.name,
                "text": f"Using {node.formula}, the recorded value is {state[node.name]}.",
            }
        )
    return entries


def _query_text(intervention: Mapping[str, Any], template_id: str) -> str:
    target = intervention["node"]
    value = str(intervention["new_value"]).lower()
    kind = intervention["kind"]
    if kind == "axiom_retraction":
        action = f"withdraw `{target}`; its corrected value is {value}"
    elif kind == "axiom_activation":
        action = f"activate `{target}`; its corrected value is {value}"
    else:
        action = f"correct `{target}` to {value}"
    templates = {
        "train_referee": "A referee asks us to {action}. Update the notebook conclusions.",
        "train_editor": "Editorial correction: {action}. Revise the notebook consistently.",
        "dev_erratum": "Apply this erratum: {action}. Reconcile the formal record.",
        "dev_revision": "During revision, {action}. Bring the notebook up to date.",
        "test_checker": "The proof checker received a patch: {action}. Repair the record.",
        "test_maintainer": "A maintainer reports that we must {action}. Refresh valid results.",
    }
    # Descendants are deliberately absent.  Generic words such as "results"
    # and "record" are not node identifiers.
    return templates[template_id].format(action=action)


def _template_for(split: str, index: int) -> str:
    templates = {
        "train": ("train_referee", "train_editor"),
        "dev": ("dev_erratum", "dev_revision"),
        "test": ("test_checker", "test_maintainer"),
    }
    return templates[split][(index // 6) % 2]


def make_episode(task: str, index: int, rng: random.Random, seed: int) -> dict[str, Any]:
    """Create one deterministic episode with evaluator-owned interventional gold."""

    spec = SPECS[task]
    scenario = index % 6
    split = _split_for(index)
    template_id = _template_for(split, index)
    primitives = (
        _math_primitive_state(rng, scenario, split)
        if task == "causal_formal_math"
        else _physics_primitive_state(rng, scenario, split)
    )
    pre_state = _materialize(spec, primitives)
    intervention = _intervention_for(spec, pre_state, scenario)
    post_state = simulate(task, pre_state, intervention)
    affected_nodes = sorted(
        key for key in pre_state if pre_state[key] != post_state[key]
    )
    derived_names = set(_derived_by_name(spec))
    affected_results = sorted(set(affected_nodes) & derived_names)
    unaffected_controls = sorted(
        node
        for node in spec.negative_controls
        if pre_state[node] == post_state[node]
    )
    episode = {
        "schema_version": SCHEMA_VERSION,
        "task": task,
        "episode_id": f"{task}-{seed}-{index:05d}",
        "split": split,
        "history": _history(spec, pre_state),
        "memory_state": pre_state,
        "query": {
            "text": _query_text(intervention, template_id),
            # This is an oracle semantic parse for propagation T0, not gold
            # descendants.  End-to-end work must score text parsing separately.
            "intervention": copy.deepcopy(intervention),
        },
        "metadata": {
            "family": spec.name,
            "scenario": intervention["kind"],
            "query_lists_descendants": False,
            "template_id": template_id,
            "value_partition": split,
            "heldout_regime_combination": split == "test" and scenario in {0, 1},
        },
        "gold": {
            "graph": _edge_records(spec),
            "active_edges": _active_edges(spec, post_state),
            "intervention": copy.deepcopy(intervention),
            "affected_nodes": affected_nodes,
            "affected_results": affected_results,
            "required_reads": _required_reads(
                spec,
                affected_results,
                post_state,
                str(intervention["node"]),
            ),
            "final_values": {name: post_state[name] for name in affected_results},
            "unaffected_controls": unaffected_controls,
            "post_state": post_state,
        },
    }
    if split == "train":
        # This is runtime-observed training evidence, not evaluator gold.  The
        # learner must infer changed cells by differencing the two states.
        episode["observed_transition"] = {
            "pre_state": copy.deepcopy(pre_state),
            "intervention": copy.deepcopy(intervention),
            "post_state": copy.deepcopy(post_state),
        }
    validate_episode(episode)
    return episode


def generate_episodes(
    count: int = 120,
    seed: int = 17,
    family: str = "both",
) -> list[dict[str, Any]]:
    """Generate math, physics, or alternating math+physics episodes."""

    if count < 1:
        raise ValueError("count must be positive")
    aliases = {
        "math": ("causal_formal_math",),
        "phys": ("causal_formal_phys",),
        "both": ("causal_formal_math", "causal_formal_phys"),
    }
    if family not in aliases:
        raise ValueError(f"unknown family: {family}")
    tasks = aliases[family]
    rng = random.Random(seed)
    family_indices = {task: 0 for task in tasks}
    episodes = []
    for global_index in range(count):
        task = tasks[global_index % len(tasks)]
        local_index = family_indices[task]
        family_indices[task] += 1
        episode = make_episode(task, local_index, rng, seed)
        episodes.append(episode)
    return episodes


def generate_dataset(episodes: int = 120, seed: int = 17) -> list[dict[str, Any]]:
    """Cross-task runner adapter; generate an alternating math/physics dataset."""

    return generate_episodes(count=episodes, seed=seed, family="both")


def predict_exact_key(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Strong structured baseline: update exactly the key named by the query."""

    state = copy.deepcopy(episode["memory_state"])
    intervention = episode["query"]["intervention"]
    target = intervention["node"]
    changed = state.get(target) != intervention["new_value"]
    state[target] = intervention["new_value"]
    return {
        "affected_nodes": [target] if changed else [],
        "post_state": state,
    }


def predict_oracle_propagation(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Simulator/oracle graph upper bound without reading ``episode['gold']``."""

    pre_state = episode["memory_state"]
    post_state = simulate(
        str(episode["task"]), pre_state, episode["query"]["intervention"]
    )
    affected = sorted(key for key in pre_state if pre_state[key] != post_state[key])
    return {"affected_nodes": affected, "post_state": post_state}


# Consistent names used by the other isolated benchmark prototypes.
exact_key_baseline = predict_exact_key
oracle_propagation_baseline = predict_oracle_propagation


def formal_runtime_view(
    episode: Mapping[str, Any], training: bool = False
) -> dict[str, Any]:
    """Return the Formal runtime contract with evaluator gold removed.

    Training views expose a completed observed transition, while inference views
    never expose an outcome.  Keeping this adapter local avoids coupling the
    prototype to an evaluator implementation.
    """

    if training and episode.get("split") != "train":
        raise ValueError("training runtime views require split=train")
    view = shared_runtime_view(episode, training=training)
    if training and "observed_transition" not in view:
        raise ValueError("training episode is missing observed_transition")
    return view


def _regime_signature(state: Mapping[str, Value]) -> tuple[tuple[str, bool], ...]:
    return tuple(
        sorted((key, bool(value)) for key, value in state.items() if isinstance(value, bool))
    )


class LearnedImpactSelector:
    """Learn intervention-to-impact sets only from observed train deltas.

    This is deliberately a transparent train-only impact learner, not GRACE.
    It learns transitive impact relations rather than pretending to identify
    unique direct causal edges from a small deterministic notebook.
    """

    def __init__(self) -> None:
        self._conditional: dict[
            tuple[str, str, tuple[tuple[str, bool], ...]], Counter[tuple[str, ...]]
        ] = defaultdict(Counter)
        self._fallback: dict[tuple[str, str], Counter[tuple[str, ...]]] = defaultdict(
            Counter
        )
        self.fit_episode_ids: tuple[str, ...] = ()
        self.transitions_seen = 0

    def fit(self, train_views: Sequence[Mapping[str, Any]]) -> "LearnedImpactSelector":
        if not train_views:
            raise ValueError("at least one train transition is required")
        ids = []
        for view in train_views:
            if "gold" in view:
                raise ValueError("fit accepts runtime views only; evaluator gold was present")
            if view.get("split") != "train":
                raise ValueError("fit accepts train split only")
            transition = view.get("observed_transition")
            if not isinstance(transition, Mapping):
                raise ValueError("fit requires runtime-visible observed_transition")
            pre = transition["pre_state"]
            post = transition["post_state"]
            intervention = transition["intervention"]
            target = str(intervention["node"])
            impacts = tuple(
                sorted(
                    key
                    for key in set(pre) | set(post)
                    if key != target and pre.get(key) != post.get(key)
                )
            )
            task = str(view["task"])
            signature = _regime_signature(post)
            self._conditional[(task, target, signature)][impacts] += 1
            self._fallback[(task, target)][impacts] += 1
            ids.append(str(view["episode_id"]))
        self.fit_episode_ids = tuple(sorted(ids))
        self.transitions_seen = len(ids)
        return self

    @staticmethod
    def _mode(counter: Counter[tuple[str, ...]]) -> tuple[str, ...]:
        if not counter:
            return ()
        # Deterministic tie break: larger support, then lexical tuple.
        return sorted(counter, key=lambda value: (-counter[value], value))[0]

    def select(self, inference_view: Mapping[str, Any]) -> list[str]:
        if "gold" in inference_view or "observed_transition" in inference_view:
            raise ValueError("predict accepts outcome-free inference runtime views only")
        intervention = inference_view["query"]["intervention"]
        target = str(intervention["node"])
        task = str(inference_view["task"])
        hypothetical = dict(inference_view["memory_state"])
        hypothetical[target] = intervention["new_value"]
        signature = _regime_signature(hypothetical)
        counter = self._conditional.get((task, target, signature))
        impacts = self._mode(counter) if counter else self._mode(self._fallback[(task, target)])
        return sorted({target, *impacts})

    def summary(self) -> dict[str, Any]:
        relations = []
        for (task, source), counter in sorted(self._fallback.items()):
            impacts = self._mode(counter)
            for target in impacts:
                relations.append(
                    {
                        "task": task,
                        "source": source,
                        "impacted_result": target,
                        "transition_support": sum(counter.values()),
                    }
                )
        return {
            "learner": "train-delta-modal-impact-v1",
            "transitions_seen": self.transitions_seen,
            "fit_episode_ids": list(self.fit_episode_ids),
            "impact_relations": relations,
        }


def _descendant_selection(
    task: str, post_state: Mapping[str, Value], source: str
) -> list[str]:
    spec = SPECS[task]
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in _active_edges(spec, post_state):
        adjacency[edge["source"]].append(edge["target"])
    selected = {source}
    frontier = [source]
    while frontier:
        node = frontier.pop()
        for child in adjacency.get(node, []):
            if child not in selected:
                selected.add(child)
                frontier.append(child)
    return sorted(selected)


def _execution_context(
    task: str,
    post_state: Mapping[str, Value],
    selected_updates: Sequence[str],
) -> list[str]:
    """Ancestors read by the shared executable-value decoder."""

    spec = SPECS[task]
    parents: dict[str, list[str]] = defaultdict(list)
    for edge in _active_edges(spec, post_state):
        parents[edge["target"]].append(edge["source"])
    context = set(selected_updates)
    frontier = list(selected_updates)
    while frontier:
        node = frontier.pop()
        for parent in parents.get(node, []):
            if parent not in context:
                context.add(parent)
                frontier.append(parent)
    return sorted(context)


def _history_chars(view: Mapping[str, Any]) -> int:
    return sum(len(str(entry.get("text", ""))) for entry in view["history"])


def _prediction_from_selection(
    view: Mapping[str, Any],
    selected_updates: Sequence[str],
    *,
    affected_prediction: Sequence[str] | None = None,
    scan_full_history: bool = False,
    context_override: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Use shared executable semantics so T1 isolates impact selection."""

    task = str(view["task"])
    pre_state = view["memory_state"]
    counterfactual = simulate(task, pre_state, view["query"]["intervention"])
    proposed = copy.deepcopy(pre_state)
    for node in selected_updates:
        if node in counterfactual:
            proposed[node] = counterfactual[node]
    context = (
        sorted(context_override)
        if context_override is not None
        else _execution_context(task, counterfactual, selected_updates)
    )
    return {
        "affected_nodes": sorted(
            affected_prediction if affected_prediction is not None else selected_updates
        ),
        "post_state": proposed,
        "selected_update_nodes": sorted(set(selected_updates)),
        "selected_context_nodes": context,
        "history_scan_chars": _history_chars(view) if scan_full_history else 0,
    }


def program_dataflow_baseline(view: Mapping[str, Any]) -> dict[str, Any]:
    """Strong domain solver using the executable notebook dependency program."""

    intervention = view["query"]["intervention"]
    counterfactual = simulate(str(view["task"]), view["memory_state"], intervention)
    selected = _descendant_selection(
        str(view["task"]), counterfactual, str(intervention["node"])
    )
    return _prediction_from_selection(view, selected)


def learned_graph_baseline(
    view: Mapping[str, Any], selector: LearnedImpactSelector
) -> dict[str, Any]:
    return _prediction_from_selection(view, selector.select(view))


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def matched_budget_retrieval_baseline(
    view: Mapping[str, Any], update_budget: int
) -> dict[str, Any]:
    """Lexical history retrieval with the learned arm's update-cell budget."""

    intervention = view["query"]["intervention"]
    target = str(intervention["node"])
    query_tokens = _tokens(str(view["query"]["text"]) + " " + target.replace(".", " "))
    entry_by_node = {str(entry["node"]): entry for entry in view["history"]}
    ranked = []
    for node in view["memory_state"]:
        if node == target:
            continue
        text = str(entry_by_node.get(node, {}).get("text", ""))
        overlap = len(query_tokens & _tokens(node.replace(".", " ") + " " + text))
        ranked.append((-overlap, node))
    ranked.sort()
    selected = [target] + [node for _, node in ranked[: max(0, update_budget - 1)]]
    return _prediction_from_selection(view, selected, scan_full_history=True)


def oracle_graph_baseline(view: Mapping[str, Any]) -> dict[str, Any]:
    """Independent simulator upper bound; no episode gold is required."""

    pre = view["memory_state"]
    post = simulate(str(view["task"]), pre, view["query"]["intervention"])
    changed = sorted(key for key in pre if pre[key] != post[key])
    return _prediction_from_selection(view, changed)


def full_history_baseline(view: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute the whole notebook while exposing every history/state cell."""

    pre = view["memory_state"]
    post = simulate(str(view["task"]), pre, view["query"]["intervention"])
    changed = sorted(key for key in pre if pre[key] != post[key])
    return _prediction_from_selection(
        view,
        list(pre),
        affected_prediction=changed,
        context_override=list(pre),
    )


def exact_key_t1_baseline(view: Mapping[str, Any]) -> dict[str, Any]:
    intervention = view["query"]["intervention"]
    return _prediction_from_selection(view, [str(intervention["node"])])


def _episode_success(
    episodes: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]]
) -> float:
    correct = sum(
        prediction.get("post_state") == episode["gold"]["post_state"]
        and sorted(prediction.get("affected_nodes", []))
        == sorted(episode["gold"]["affected_nodes"])
        for episode, prediction in zip(episodes, predictions)
    )
    return correct / len(episodes) if episodes else 1.0


def _result_recall(
    episodes: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]]
) -> float:
    recalls = []
    for episode, prediction in zip(episodes, predictions):
        gold = set(episode["gold"]["affected_results"])
        if not gold:
            continue
        predicted = set(prediction.get("affected_nodes", []))
        recalls.append(len(gold & predicted) / len(gold))
    return sum(recalls) / len(recalls) if recalls else 1.0


def run_t0(episodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Run the exact-key falsification gate and oracle upper bound."""

    exact_predictions = [predict_exact_key(episode) for episode in episodes]
    oracle_predictions = [predict_oracle_propagation(episode) for episode in episodes]
    exact = audit_predictions(episodes, exact_predictions)
    oracle = audit_predictions(episodes, oracle_predictions)
    propagation = sum(bool(ep["gold"]["affected_results"]) for ep in episodes)
    inactive_gate = sum(
        ep["metadata"]["scenario"] == "inactive_gate_update" for ep in episodes
    )
    leaked_episodes = [
        ep["episode_id"]
        for ep in episodes
        if any(
            result in ep["query"]["text"]
            for result in ep["gold"]["affected_results"]
        )
    ]
    exact_success = _episode_success(episodes, exact_predictions)
    result_recall = _result_recall(episodes, exact_predictions)
    report = {
        "episodes": len(episodes),
        "families": {
            task: sum(ep["task"] == task for ep in episodes) for task in sorted(SPECS)
        },
        "propagation_required": propagation,
        "propagation_required_rate": propagation / len(episodes),
        "inactive_gate_negative_controls": inactive_gate,
        "downstream_query_leakage": {
            "leaked": len(leaked_episodes),
            "episode_ids": leaked_episodes,
        },
        "exact_key": {
            "affected_precision": exact["affected_precision"],
            "affected_recall": exact["affected_recall"],
            "affected_state_accuracy": exact["affected_state_accuracy"],
            "full_state_accuracy": exact["full_state_accuracy"],
            "affected_result_recall": result_recall,
            "episode_success": exact_success,
        },
        "oracle_propagation": {
            "affected_precision": oracle["affected_precision"],
            "affected_recall": oracle["affected_recall"],
            "affected_state_accuracy": oracle["affected_state_accuracy"],
            "full_state_accuracy": oracle["full_state_accuracy"],
            "affected_result_recall": _result_recall(episodes, oracle_predictions),
            "episode_success": _episode_success(episodes, oracle_predictions),
        },
        "headroom": {
            "affected_recall": oracle["affected_recall"] - exact["affected_recall"],
            "affected_result_recall": _result_recall(episodes, oracle_predictions)
            - _result_recall(episodes, exact_predictions),
            "episode_success": _episode_success(episodes, oracle_predictions)
            - _episode_success(episodes, exact_predictions),
        },
    }
    report["admission"] = {
        "pass": (
            propagation / len(episodes) >= 0.5
            and exact_success < 0.95
            and result_recall < 0.95
            and not leaked_episodes
        ),
        "rule": (
            "propagation_required_rate >= 0.5; exact-key episode success and "
            "affected-result recall < 0.95; zero downstream query leakage"
        ),
    }
    return report


def audit_dataset(dataset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Cross-task runner adapter for the deterministic T0 audit."""

    return run_t0(dataset)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 1.0


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _arm_effectiveness(
    episodes: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]]
) -> dict[str, float]:
    common = audit_predictions(episodes, predictions)
    result_precision = []
    result_recall = []
    negative_preservation = []
    negative_selection = []
    unaffected_accuracy = []
    required_read_recall = []
    for episode, prediction in zip(episodes, predictions):
        derived = set(_derived_by_name(SPECS[str(episode["task"])]))
        gold_results = set(episode["gold"]["affected_results"])
        predicted_results = set(prediction["affected_nodes"]) & derived
        tp = len(gold_results & predicted_results)
        if gold_results or predicted_results:
            result_precision.append(
                tp / len(predicted_results) if predicted_results else 0.0
            )
        if gold_results:
            result_recall.append(tp / len(gold_results))

        controls = set(SPECS[str(episode["task"])].negative_controls)
        proposed = prediction["post_state"]
        gold_post = episode["gold"]["post_state"]
        negative_preservation.append(
            _safe_ratio(
                sum(proposed.get(node) == gold_post[node] for node in controls),
                len(controls),
            )
        )
        selected_updates = set(prediction.get("selected_update_nodes", []))
        negative_selection.append(bool(selected_updates & controls))

        unaffected = set(gold_post) - set(episode["gold"]["affected_nodes"])
        unaffected_accuracy.append(
            _safe_ratio(
                sum(proposed.get(node) == gold_post[node] for node in unaffected),
                len(unaffected),
            )
        )
        required = set(episode["gold"]["required_reads"])
        context = set(prediction.get("selected_context_nodes", []))
        required_read_recall.append(_safe_ratio(len(required & context), len(required)))

    precision = _mean(result_precision)
    recall = _mean(result_recall)
    result_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "affected_node_precision": common["affected_precision"],
        "affected_node_recall": common["affected_recall"],
        "affected_state_accuracy": common["affected_state_accuracy"],
        "full_state_accuracy": common["full_state_accuracy"],
        "affected_result_precision": precision,
        "affected_result_recall": recall,
        "affected_result_f1": result_f1,
        "episode_success": _episode_success(episodes, predictions),
        "unaffected_state_accuracy": _mean(unaffected_accuracy),
        "negative_control_preservation": _mean(negative_preservation),
        "negative_control_selection_episode_rate": _mean(
            [float(value) for value in negative_selection]
        ),
        "required_read_recall": _mean(required_read_recall),
    }


def _serialize_prediction_context(
    view: Mapping[str, Any], prediction: Mapping[str, Any], mode: str
) -> str:
    context = set(prediction.get("selected_context_nodes", []))
    query = str(view["query"]["text"])
    if mode == "verbose":
        entries = [
            str(entry["text"])
            for entry in view["history"]
            if str(entry.get("node")) in context
        ]
        return query + "\n" + "\n".join(entries)
    if mode == "compact":
        cells = "; ".join(
            f"{node}={view['memory_state'][node]}" for node in sorted(context)
        )
        return query + "\nSTATE " + cells
    raise ValueError(f"unknown serialization: {mode}")


def _arm_efficiency(
    views: Sequence[Mapping[str, Any]],
    predictions: Sequence[Mapping[str, Any]],
    mode: str,
) -> dict[str, float]:
    serialized = [
        _serialize_prediction_context(view, prediction, mode)
        for view, prediction in zip(views, predictions)
    ]
    return {
        "selected_update_nodes_mean": _mean(
            [float(len(prediction.get("selected_update_nodes", []))) for prediction in predictions]
        ),
        "selected_context_nodes_mean": _mean(
            [float(len(prediction.get("selected_context_nodes", []))) for prediction in predictions]
        ),
        "selected_context_fraction_mean": _mean(
            [
                len(prediction.get("selected_context_nodes", []))
                / len(view["memory_state"])
                for view, prediction in zip(views, predictions)
            ]
        ),
        "serialized_chars_mean": _mean([float(len(text)) for text in serialized]),
        "serialized_token_proxy_mean": _mean(
            [float((len(text) + 3) // 4) for text in serialized]
        ),
        "history_scan_chars_mean": _mean(
            [float(prediction.get("history_scan_chars", 0)) for prediction in predictions]
        ),
    }


def _split_diagnostics(dataset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    train = [episode for episode in dataset if episode["split"] == "train"]
    dev_test = [episode for episode in dataset if episode["split"] in {"dev", "test"}]
    train_templates = {episode["metadata"]["template_id"] for episode in train}
    heldout_templates = {episode["metadata"]["template_id"] for episode in dev_test}
    value_overlaps = []
    for task, spec in SPECS.items():
        task_train = [episode for episode in train if episode["task"] == task]
        task_eval = [episode for episode in dev_test if episode["task"] == task]
        for node in spec.primitives:
            train_values = {
                episode["memory_state"][node]
                for episode in task_train
                if not isinstance(episode["memory_state"][node], bool)
            }
            eval_values = {
                episode["memory_state"][node]
                for episode in task_eval
                if not isinstance(episode["memory_state"][node], bool)
            }
            overlap = sorted(train_values & eval_values)
            if overlap:
                value_overlaps.append({"task": task, "node": node, "values": overlap})
    return {
        "train_episodes": len(train),
        "dev_episodes": sum(episode["split"] == "dev" for episode in dataset),
        "test_episodes": sum(episode["split"] == "test" for episode in dataset),
        "train_observed_transitions": sum("observed_transition" in ep for ep in train),
        "dev_test_outcome_leaks": sum("observed_transition" in ep for ep in dev_test),
        "train_templates": sorted(train_templates),
        "heldout_templates": sorted(heldout_templates),
        "template_overlap": sorted(train_templates & heldout_templates),
        "numeric_primitive_value_overlaps": value_overlaps,
        "heldout_target_regime_combinations": sum(
            bool(ep["metadata"]["heldout_regime_combination"])
            for ep in dev_test
        ),
        "heldout_long_impact_episodes": sum(
            len(ep["gold"]["affected_results"]) >= 4 for ep in dev_test
        ),
    }


def run_t1(
    dataset: Sequence[Mapping[str, Any]], eval_split: str = "test"
) -> dict[str, Any]:
    """Run the train-only six-arm deterministic selector experiment."""

    if eval_split not in {"dev", "test"}:
        raise ValueError("eval_split must be dev or test")
    train_episodes = [episode for episode in dataset if episode["split"] == "train"]
    eval_episodes = [episode for episode in dataset if episode["split"] == eval_split]
    if not train_episodes or not eval_episodes:
        raise ValueError("T1 requires non-empty train and evaluation splits")

    train_views = [formal_runtime_view(episode, training=True) for episode in train_episodes]
    eval_views = [formal_runtime_view(episode, training=False) for episode in eval_episodes]
    selector = LearnedImpactSelector().fit(train_views)

    predictions: dict[str, list[dict[str, Any]]] = {
        "exact_kv": [exact_key_t1_baseline(view) for view in eval_views],
        "program_dataflow": [program_dataflow_baseline(view) for view in eval_views],
        "learned_graph": [learned_graph_baseline(view, selector) for view in eval_views],
        "oracle_graph": [oracle_graph_baseline(view) for view in eval_views],
        "full_history": [full_history_baseline(view) for view in eval_views],
    }
    predictions["matched_budget_retrieval"] = [
        matched_budget_retrieval_baseline(
            view, len(learned_prediction["selected_update_nodes"])
        )
        for view, learned_prediction in zip(eval_views, predictions["learned_graph"])
    ]

    arms = {}
    cross = {}
    for name in (
        "exact_kv",
        "program_dataflow",
        "matched_budget_retrieval",
        "learned_graph",
        "oracle_graph",
        "full_history",
    ):
        effectiveness = _arm_effectiveness(eval_episodes, predictions[name])
        serializations = {
            mode: _arm_efficiency(eval_views, predictions[name], mode)
            for mode in ("verbose", "compact")
        }
        arms[name] = {
            "effectiveness": effectiveness,
            "serialization": serializations,
        }
        cross[name] = {
            mode: {
                "episode_success": effectiveness["episode_success"],
                "affected_result_f1": effectiveness["affected_result_f1"],
                **serializations[mode],
            }
            for mode in ("verbose", "compact")
        }

    diagnostics = _split_diagnostics(dataset)
    eval_ids = {str(episode["episode_id"]) for episode in eval_episodes}
    fit_ids = set(selector.fit_episode_ids)
    leakage = {
        "fit_received_gold": False,
        "fit_eval_id_overlap": sorted(fit_ids & eval_ids),
        "eval_observed_transition_leaks": sum(
            "observed_transition" in view for view in eval_views
        ),
        "query_descendant_leaks": sum(
            any(
                result in episode["query"]["text"]
                for result in episode["gold"]["affected_results"]
            )
            for episode in eval_episodes
        ),
    }
    learned = arms["learned_graph"]["effectiveness"]
    exact = arms["exact_kv"]["effectiveness"]
    program = arms["program_dataflow"]["effectiveness"]
    full_compact = arms["full_history"]["serialization"]["compact"]
    learned_compact = arms["learned_graph"]["serialization"]["compact"]
    pipeline_pass = (
        not leakage["fit_eval_id_overlap"]
        and leakage["eval_observed_transition_leaks"] == 0
        and leakage["query_descendant_leaks"] == 0
        and diagnostics["dev_test_outcome_leaks"] == 0
        and not diagnostics["template_overlap"]
        and not diagnostics["numeric_primitive_value_overlaps"]
        and learned["episode_success"] > exact["episode_success"]
    )
    return {
        "schema": "causal-formal-t1/v1",
        "eval_split": eval_split,
        "train_episodes": len(train_episodes),
        "eval_episodes": len(eval_episodes),
        "learner": selector.summary(),
        "split_diagnostics": diagnostics,
        "leakage_audit": leakage,
        "arms": arms,
        "selection_x_serialization": cross,
        "orthogonality": {
            "effectiveness_invariant_by_construction": True,
            "learned_compact_vs_verbose_char_reduction": 1.0
            - arms["learned_graph"]["serialization"]["compact"]["serialized_chars_mean"]
            / arms["learned_graph"]["serialization"]["verbose"]["serialized_chars_mean"],
        },
        "verdict": {
            "train_only_pipeline_pass": pipeline_pass,
            "effectiveness_replication_pass": learned["episode_success"]
            > exact["episode_success"],
            "efficiency_replication_pass": (
                learned["episode_success"] >= arms["full_history"]["effectiveness"]["episode_success"]
                and learned_compact["serialized_chars_mean"]
                < full_compact["serialized_chars_mean"]
            ),
            # Formal executable equations make this the decisive killer check.
            "learned_graph_necessity_pass": learned["episode_success"]
            > program["episode_success"],
            "claim_boundary": (
                "mutable-formal-artifact interventional dataflow; not empirical "
                "causal discovery or agent safety"
            ),
        },
    }


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("generate", "t0", "t1", "example"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--count", type=int, default=120)
        sub.add_argument("--seed", type=int, default=17)
        sub.add_argument("--family", choices=("math", "phys", "both"), default="both")
        if name == "generate":
            sub.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    episodes = generate_episodes(args.count, args.seed, args.family)
    if args.command == "generate":
        if args.output:
            _write_jsonl(args.output, episodes)
            print(json.dumps({"episodes": len(episodes), "output": str(args.output)}))
        else:
            for episode in episodes:
                print(json.dumps(episode, ensure_ascii=False, sort_keys=True))
    elif args.command == "example":
        print(json.dumps(episodes[0], ensure_ascii=False, indent=2, sort_keys=True))
    elif args.command == "t1":
        print(json.dumps(run_t1(episodes), indent=2, sort_keys=True))
    else:
        print(json.dumps(run_t0(episodes), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
