"""Gold-isolated selection plans for the six-arm test API experiment.

The deterministic T1 prototypes often attach a shared decoder ``post_state`` to
their predictions.  That is convenient for selection-only evaluation, but it is
not a safe object to pass to a real value decoder.  This module therefore builds
fresh plans containing *identifiers only*: writable state nodes, readable state
nodes, history-record indices, and graph edges.  A later prompt builder may look
up pre-intervention values from a gold-free runtime view.

Non-oracle builders accept only inference ``runtime_view`` objects.  The oracle
adapter is deliberately separate and uses only evaluator graph structure; it
does not read gold affected nodes, required reads, or post-state values.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

from . import causal_formal, dynamic_search, dynamic_shopping, dynamic_travel
from .common import runtime_view


SCHEMA_VERSION = "causal-api-selection-plan/v1"
ARM_NAMES = (
    "exact_kv",
    "domain_solver",
    "matched_retrieval",
    "learned_graph",
    "oracle_graph",
    "full_state_history",
)
TASK_FAMILIES = (
    "dynamic_travel",
    "dynamic_shopping",
    "dynamic_search",
    "causal_formal",
)
NON_ORACLE_ARMS = tuple(arm for arm in ARM_NAMES if arm != "oracle_graph")
_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, order=True)
class EdgeRef:
    """A value-free dependency edge suitable for a prompt manifest."""

    source: str
    target: str
    label: str


@dataclass(frozen=True)
class SelectionPlan:
    """Frozen output of one selection arm.

    The plan intentionally has no arbitrary metadata/value mapping.  This keeps
    downstream code from smuggling a simulator post-state into a prompt under a
    less obvious field name.
    """

    schema_version: str
    episode_id: str
    task_family: str
    arm: str
    predicted_write_nodes: tuple[str, ...]
    selected_context_nodes: tuple[str, ...]
    selected_history_ids: tuple[int, ...]
    selected_edges: tuple[EdgeRef, ...]
    provenance: str
    write_budget: int
    context_budget: int
    edge_budget: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KillerLookup:
    """Train-only lookup baselines used by the offline admission audit.

    These deliberately simple baselines test whether a stable intervention key
    or query-visible signature can recover the write mask without retrieving a
    dependency graph.  Templates contain node identifiers only; ``$target`` is
    instantiated with the current intervention node at prediction time.
    """

    task_family: str
    source_unions: Mapping[str, tuple[str, ...]]
    query_signature_unions: Mapping[str, tuple[str, ...]]
    fit_episode_ids: tuple[str, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "task_family": self.task_family,
            "source_unions": {
                key: list(value) for key, value in sorted(self.source_unions.items())
            },
            "query_signature_unions": {
                key: list(value)
                for key, value in sorted(self.query_signature_unions.items())
            },
            "fit_episode_ids": list(self.fit_episode_ids),
        }


def _inference_view(view: Mapping[str, Any]) -> None:
    if "gold" in view or "observed_transition" in view:
        raise ValueError("non-oracle planning requires an outcome-free runtime_view")
    required = {"episode_id", "split", "history", "memory_state", "query", "task"}
    missing = sorted(required - set(view))
    if missing:
        raise ValueError(f"runtime_view is missing fields: {missing}")
    if view["split"] == "train":
        raise ValueError("test-time planning does not accept split=train")


def _training_views(views: Sequence[Mapping[str, Any]]) -> None:
    if not views:
        raise ValueError("at least one training runtime_view is required")
    for view in views:
        if "gold" in view:
            raise ValueError("learner fitting accepts runtime_view objects, never gold")
        if view.get("split") != "train" or "observed_transition" not in view:
            raise ValueError("learner fitting requires train observed_transition records")


def _canonical_nodes(nodes: Iterable[str], state: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(sorted({str(node) for node in nodes if str(node) in state}))


def _edge_label(edge: Mapping[str, Any]) -> str:
    for key in ("relation", "regime", "condition", "kind"):
        if key in edge:
            return str(edge[key])
    return "dependency"


def _edge_refs(edges: Iterable[Mapping[str, Any]]) -> tuple[EdgeRef, ...]:
    refs = {
        EdgeRef(str(edge["source"]), str(edge["target"]), _edge_label(edge))
        for edge in edges
        if "source" in edge and "target" in edge
    }
    return tuple(sorted(refs))


def _runtime_edges(task_family: str, view: Mapping[str, Any]) -> tuple[EdgeRef, ...]:
    state = view["memory_state"]
    if task_family == "dynamic_travel":
        edges: Iterable[Mapping[str, Any]] = dynamic_travel.GRAPH
    elif task_family == "dynamic_shopping":
        edges = dynamic_shopping.dependency_graph(state)["edges"]
    elif task_family == "dynamic_search":
        edges = dynamic_search.parse_runtime_graph(view["history"], state)
    elif task_family == "causal_formal":
        edges = causal_formal._edge_records(causal_formal.SPECS[str(view["task"])])
    else:
        raise ValueError(f"unknown task family: {task_family}")
    return tuple(
        edge
        for edge in _edge_refs(edges)
        if edge.source in state and edge.target in state
    )


def _descendants(source: str, edges: Sequence[EdgeRef], state: Mapping[str, Any]) -> tuple[str, ...]:
    children: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        children[edge.source].add(edge.target)
    reached = {source}
    frontier = deque([source])
    while frontier:
        node = frontier.popleft()
        for child in sorted(children.get(node, ())):
            if child not in reached:
                reached.add(child)
                frontier.append(child)
    return _canonical_nodes(reached, state)


def _parent_closure(nodes: Iterable[str], edges: Sequence[EdgeRef], state: Mapping[str, Any]) -> tuple[str, ...]:
    parents: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        parents[edge.target].add(edge.source)
    reached = set(_canonical_nodes(nodes, state))
    frontier = deque(sorted(reached))
    while frontier:
        node = frontier.popleft()
        for parent in sorted(parents.get(node, ())):
            if parent in state and parent not in reached:
                reached.add(parent)
                frontier.append(parent)
    return tuple(sorted(reached))


def _edges_within(edges: Sequence[EdgeRef], nodes: Iterable[str]) -> tuple[EdgeRef, ...]:
    selected = set(nodes)
    return tuple(edge for edge in edges if edge.source in selected and edge.target in selected)


def _history_ids_for_nodes(view: Mapping[str, Any], nodes: Iterable[str]) -> tuple[int, ...]:
    needles = tuple(sorted(set(nodes)))
    selected = []
    for index, record in enumerate(view["history"]):
        text = json.dumps(record, ensure_ascii=False, sort_keys=True)
        selected_slots = {
            node.split(".", 1)[1]
            for node in needles
            if node.startswith(("cart.", "price."))
        }
        constraint_needed = any(
            node.startswith(("policy.", "constraint.", "ledger."))
            for node in needles
        )
        if (
            any(node in text for node in needles)
            or str(record.get("slot", "")) in selected_slots
            or (constraint_needed and record.get("event") == "constraints_saved")
        ):
            selected.append(index)
    return tuple(selected)


def _tokens(value: Any) -> set[str]:
    return set(_TOKEN.findall(str(value).lower()))


def _source_lookup_key(task_family: str, view: Mapping[str, Any]) -> str:
    """Abstract the intervention source without reading history or a graph."""

    intervention = view["query"]["intervention"]
    node = str(intervention["node"])
    if task_family == "dynamic_travel":
        parts: list[Any] = [task_family, node]
    elif task_family == "dynamic_shopping":
        namespace, _, entity = node.partition(".")
        if namespace == "availability":
            item = dynamic_shopping.CATALOG.get(entity, {})
            parts = [task_family, namespace, str(item.get("slot", "unknown"))]
        elif namespace in {"price", "cart", "policy"}:
            parts = [task_family, namespace, entity]
        else:
            parts = [task_family, "node", node]
    elif task_family == "dynamic_search":
        old_value = intervention.get("old_value")
        old = old_value if isinstance(old_value, Mapping) else {}
        parts = [task_family, str(old.get("kind", "unknown"))]
    elif task_family == "causal_formal":
        parts = [str(view["task"]), node]
    else:
        raise ValueError(f"unknown task family: {task_family}")
    return json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _query_signature_key(task_family: str, view: Mapping[str, Any]) -> str:
    """Return a query-visible signature for the offline shortcut audit.

    The signature intentionally excludes ``memory_state`` and history.  It may
    use the supplied semantic intervention parse because every frozen arm sees
    that parse.  Shopping additionally uses the public catalog ontology to map
    an entity identifier to its query-visible product slot.
    """

    intervention = view["query"]["intervention"]
    kind = str(intervention["kind"])
    parts: list[Any] = [_source_lookup_key(task_family, view), kind]
    if task_family == "dynamic_search":
        old_value = intervention.get("old_value")
        new_value = intervention.get("new_value")
        old = old_value if isinstance(old_value, Mapping) else {}
        new = new_value if isinstance(new_value, Mapping) else {}
        # Only categorical query fields are retained.  Episode-specific IDs and
        # numeric versions would turn the lookup into an ID memorizer rather
        # than a serious surface-signature baseline.
        for key in ("trust", "active", "stance", "independent"):
            if key in old or key in new:
                parts.append((key, old.get(key), new.get(key)))
    return json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _impact_templates(
    task_family: str,
    pre: Mapping[str, Any],
    post: Mapping[str, Any],
    target: str,
) -> set[str]:
    changed = {
        str(node)
        for node in set(pre) | set(post)
        if pre.get(node) != post.get(node)
    }
    templates = set()
    for node in changed:
        if node == target:
            templates.add("$target")
        elif task_family == "dynamic_search":
            value = post.get(node, pre.get(node))
            if isinstance(value, Mapping) and value.get("kind"):
                templates.add(f"$kind:{value['kind']}")
        else:
            templates.add(node)
    return templates


def fit_killer_lookup(
    task_family: str,
    train_views: Sequence[Mapping[str, Any]],
) -> KillerLookup:
    """Fit source-union and query-signature baselines from train deltas only."""

    views = list(train_views)
    _training_views(views)
    if task_family not in TASK_FAMILIES:
        raise ValueError(f"unknown task family: {task_family}")
    source_unions: dict[str, set[str]] = defaultdict(set)
    signature_unions: dict[str, set[str]] = defaultdict(set)
    episode_ids = []
    for view in views:
        if task_family == "causal_formal":
            belongs = str(view.get("task", "")).startswith("causal_formal_")
        else:
            belongs = str(view.get("task")) == task_family
        if not belongs:
            raise ValueError(f"training view does not belong to {task_family}")
        transition = view["observed_transition"]
        if set(transition) != {"pre_state", "intervention", "post_state"}:
            raise ValueError("train transition contains non-runtime supervision")
        if transition["intervention"] != view["query"]["intervention"]:
            raise ValueError("train transition intervention disagrees with query")
        target = str(transition["intervention"]["node"])
        templates = _impact_templates(
            task_family,
            transition["pre_state"],
            transition["post_state"],
            target,
        )
        source_unions[_source_lookup_key(task_family, view)].update(templates)
        signature_unions[_query_signature_key(task_family, view)].update(templates)
        episode_ids.append(str(view["episode_id"]))
    return KillerLookup(
        task_family=task_family,
        source_unions={
            key: tuple(sorted(value)) for key, value in sorted(source_unions.items())
        },
        query_signature_unions={
            key: tuple(sorted(value))
            for key, value in sorted(signature_unions.items())
        },
        fit_episode_ids=tuple(sorted(episode_ids)),
    )


def _instantiate_impact_templates(
    task_family: str,
    templates: Iterable[str],
    view: Mapping[str, Any],
) -> tuple[str, ...]:
    state = view["memory_state"]
    target = str(view["query"]["intervention"]["node"])
    nodes = set()
    for template in templates:
        if template == "$target":
            nodes.add(target)
        elif task_family == "dynamic_search" and template.startswith("$kind:"):
            wanted_kind = template.split(":", 1)[1]
            nodes.update(
                node
                for node, value in state.items()
                if isinstance(value, Mapping) and str(value.get("kind")) == wanted_kind
            )
        else:
            nodes.add(str(template))
    nodes.add(target)
    return _canonical_nodes(nodes, state)


def predict_killer_masks(
    task_family: str,
    view: Mapping[str, Any],
    lookup: KillerLookup,
) -> dict[str, tuple[str, ...]]:
    """Predict value-free masks without history, a graph, a simulator, or gold."""

    _inference_view(view)
    if lookup.task_family != task_family:
        raise ValueError("killer lookup task family mismatch")
    source_key = _source_lookup_key(task_family, view)
    source_templates = lookup.source_unions.get(source_key, ("$target",))
    signature_templates = lookup.query_signature_unions.get(
        _query_signature_key(task_family, view), source_templates
    )
    return {
        "source_union": _instantiate_impact_templates(
            task_family, source_templates, view
        ),
        "query_signature": _instantiate_impact_templates(
            task_family, signature_templates, view
        ),
    }


def _summarize_mask_predictions(
    expected_masks: Sequence[set[str]],
    predicted_masks: Sequence[set[str]],
    state_node_sets: Sequence[set[str]],
    lookup_seen: Sequence[bool],
) -> dict[str, Any]:
    counts = {
        len(expected_masks),
        len(predicted_masks),
        len(state_node_sets),
        len(lookup_seen),
    }
    if len(counts) != 1:
        raise ValueError("mask-audit input counts disagree")
    precision = []
    recall = []
    f1 = []
    exact = []
    sufficient = []
    specificity = []
    write_fraction = []
    propagation_exact = []
    propagation_sufficient = []
    for expected, predicted, state_nodes in zip(
        expected_masks, predicted_masks, state_node_sets
    ):
        overlap = len(expected & predicted)
        item_precision = overlap / len(predicted) if predicted else float(not expected)
        item_recall = overlap / len(expected) if expected else float(not predicted)
        precision.append(item_precision)
        recall.append(item_recall)
        f1.append(
            2 * item_precision * item_recall / (item_precision + item_recall)
            if item_precision + item_recall
            else 0.0
        )
        matched = expected == predicted
        exact.append(float(matched))
        covers = expected <= predicted
        sufficient.append(float(covers))
        unaffected = state_nodes - expected
        specificity.append(
            len(unaffected - predicted) / len(unaffected) if unaffected else 1.0
        )
        write_fraction.append(len(predicted) / len(state_nodes) if state_nodes else 0.0)
        if len(expected) > 1:
            propagation_exact.append(float(matched))
            propagation_sufficient.append(float(covers))
    mean = lambda values: sum(values) / len(values) if values else 1.0
    propagation_sufficient_rate = mean(propagation_sufficient)
    return {
        "episodes": len(expected_masks),
        "propagation_episodes": len(propagation_exact),
        "lookup_coverage": mean([float(value) for value in lookup_seen]),
        "affected_precision": mean(precision),
        "affected_recall": mean(recall),
        "affected_f1": mean(f1),
        "affected_exact_match": mean(exact),
        "sufficient_mask_rate": mean(sufficient),
        "propagation_exact_match": mean(propagation_exact),
        "propagation_sufficient_mask_rate": propagation_sufficient_rate,
        "unaffected_specificity": mean(specificity),
        "mean_write_nodes": mean([float(len(nodes)) for nodes in predicted_masks]),
        "mean_write_fraction": mean(write_fraction),
        "query_only_stop_rule_triggered": bool(
            propagation_sufficient
            and propagation_sufficient_rate >= 0.95
        ),
    }


def audit_killer_lookups_on_dev(
    task_family: str,
    train_views: Sequence[Mapping[str, Any]],
    dev_episodes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Score shortcut baselines on dev only, with gold isolated to this scorer.

    This function deliberately rejects test episodes so the audit cannot become
    a post-hoc test-set tuning loop.  Predictions are built from gold-free
    runtime views before evaluator masks are read.
    """

    episodes = list(dev_episodes)
    if not episodes:
        raise ValueError("killer-baseline admission audit requires dev episodes")
    if any(episode.get("split") != "dev" for episode in episodes):
        raise ValueError("killer-baseline admission audit is dev-only")
    lookup = fit_killer_lookup(task_family, train_views)
    predictions = []
    source_seen = []
    signature_seen = []
    state_node_sets = []
    for episode in episodes:
        view = runtime_view(episode, training=False)
        predictions.append(predict_killer_masks(task_family, view, lookup))
        source_seen.append(_source_lookup_key(task_family, view) in lookup.source_unions)
        signature_seen.append(
            _query_signature_key(task_family, view) in lookup.query_signature_unions
        )
        state_node_sets.append(set(view["memory_state"]))
    expected = [set(episode["gold"]["affected_nodes"]) for episode in episodes]
    seen_by_arm = {
        "source_union": source_seen,
        "query_signature": signature_seen,
    }
    arms = {
        name: _summarize_mask_predictions(
            expected,
            [set(prediction[name]) for prediction in predictions],
            state_node_sets,
            seen_by_arm[name],
        )
        for name in ("source_union", "query_signature")
    }
    return {
        "schema": "causal-offline-lookup-admission/v1",
        "task_family": task_family,
        "split": "dev",
        "prediction_boundary": (
            "Masks use train observed deltas plus the current query semantic parse only; "
            "dev gold is read after prediction solely by this scorer."
        ),
        "lookup": lookup.summary(),
        "arms": arms,
        "hidden_dependency_admission_pass": not any(
            result["query_only_stop_rule_triggered"] for result in arms.values()
        ),
    }


def _rank_nodes(view: Mapping[str, Any]) -> list[str]:
    intervention = view["query"]["intervention"]
    target = str(intervention["node"])
    query_tokens = _tokens(view["query"].get("text", "")) | _tokens(target)
    history_text = json.dumps(view["history"], ensure_ascii=False, sort_keys=True)
    ranked = []
    for node, value in view["memory_state"].items():
        text = f"{node} {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
        score = len(query_tokens & _tokens(text))
        score += 10_000 if node == target else 0
        score += int(node in history_text)
        ranked.append((-score, str(node)))
    return [node for _, node in sorted(ranked)]


def _lexical_nodes(
    view: Mapping[str, Any], budget: int, *, required: Iterable[str] = ()
) -> tuple[str, ...]:
    state = view["memory_state"]
    required_nodes = list(_canonical_nodes(required, state))
    wanted = max(len(required_nodes), min(max(1, budget), len(state)))
    chosen = list(required_nodes)
    for node in _rank_nodes(view):
        if node not in chosen:
            chosen.append(node)
        if len(chosen) >= wanted:
            break
    return tuple(sorted(chosen))


def _rank_history(view: Mapping[str, Any], budget: int) -> tuple[int, ...]:
    query_tokens = _tokens(view["query"].get("text", "")) | _tokens(
        view["query"]["intervention"]["node"]
    )
    ranked = []
    for index, record in enumerate(view["history"]):
        overlap = len(query_tokens & _tokens(json.dumps(record, ensure_ascii=False)))
        ranked.append((-overlap, index))
    return tuple(sorted(index for _, index in sorted(ranked)[:budget]))


def _rank_edges(
    view: Mapping[str, Any], edges: Sequence[EdgeRef], budget: int
) -> tuple[EdgeRef, ...]:
    """Query-aware structural retrieval under an independently matched budget."""

    query_tokens = _tokens(view["query"].get("text", "")) | _tokens(
        view["query"]["intervention"]["node"]
    )
    history_text = json.dumps(view["history"], ensure_ascii=False, sort_keys=True)
    ranked = []
    for edge in edges:
        edge_text = f"{edge.source} {edge.target} {edge.label}"
        overlap = len(query_tokens & _tokens(edge_text))
        history_mentions = int(edge.source in history_text) + int(edge.target in history_text)
        target_bonus = 10_000 * int(
            edge.source == str(view["query"]["intervention"]["node"])
        )
        ranked.append((-(target_bonus + 10 * overlap + history_mentions), edge))
    return tuple(sorted(edge for _, edge in sorted(ranked)[:budget]))


def _make_plan(
    *,
    task_family: str,
    view: Mapping[str, Any],
    arm: str,
    write_nodes: Iterable[str],
    context_nodes: Iterable[str],
    history_ids: Iterable[int],
    edges: Iterable[EdgeRef],
    provenance: str,
) -> SelectionPlan:
    state = view["memory_state"]
    writes = _canonical_nodes(write_nodes, state)
    context = _canonical_nodes(set(context_nodes) | set(writes), state)
    edge_values = tuple(sorted(set(edges)))
    plan = SelectionPlan(
        schema_version=SCHEMA_VERSION,
        episode_id=str(view["episode_id"]),
        task_family=task_family,
        arm=arm,
        predicted_write_nodes=writes,
        selected_context_nodes=context,
        selected_history_ids=tuple(sorted(set(int(index) for index in history_ids))),
        selected_edges=edge_values,
        provenance=provenance,
        write_budget=len(writes),
        context_budget=len(context),
        edge_budget=len(edge_values),
    )
    validate_plan(plan, view, oracle_allowed=arm == "oracle_graph")
    return plan


def validate_plan(
    plan: SelectionPlan,
    view: Mapping[str, Any],
    *,
    oracle_allowed: bool = False,
) -> None:
    """Validate identity-only planning and its runtime bounds."""

    if plan.schema_version != SCHEMA_VERSION:
        raise ValueError("wrong selection-plan schema")
    if plan.task_family not in TASK_FAMILIES or plan.arm not in ARM_NAMES:
        raise ValueError("unknown task family or arm")
    if plan.episode_id != str(view.get("episode_id")):
        raise ValueError("selection plan episode mismatch")
    if plan.arm == "oracle_graph" and not oracle_allowed:
        raise ValueError("oracle plan requires an explicit evaluator boundary")
    if plan.arm != "oracle_graph":
        _inference_view(view)
    target = str(view["query"]["intervention"]["node"])
    state_nodes = set(view["memory_state"])
    writes = set(plan.predicted_write_nodes)
    context = set(plan.selected_context_nodes)
    if not writes or target not in writes:
        raise ValueError("every arm must make the intervention target writable")
    if not writes <= state_nodes or not context <= state_nodes:
        raise ValueError("plan references a node outside runtime memory_state")
    if not writes <= context:
        raise ValueError("write nodes must also be visible in selected context")
    if plan.write_budget != len(writes) or plan.context_budget != len(context):
        raise ValueError("selection-plan budgets disagree with node sets")
    if plan.edge_budget != len(plan.selected_edges):
        raise ValueError("selection-plan edge budget is inconsistent")
    if any(
        edge.source not in state_nodes or edge.target not in state_nodes
        for edge in plan.selected_edges
    ):
        raise ValueError("selected edge references a node outside runtime memory_state")
    if any(index < 0 or index >= len(view["history"]) for index in plan.selected_history_ids):
        raise ValueError("history index is outside runtime history")
    if plan.arm == "oracle_graph" and plan.provenance != "evaluator_oracle":
        raise ValueError("oracle plan provenance must be evaluator_oracle")
    if plan.arm != "oracle_graph" and plan.provenance == "evaluator_oracle":
        raise ValueError("non-oracle plan has evaluator provenance")


def fit_learned_selector(
    task_family: str, train_views: Sequence[Mapping[str, Any]]
) -> Any:
    """Fit the existing impact learner using train runtime transitions only."""

    views = list(train_views)
    _training_views(views)
    if task_family == "causal_formal":
        belongs = all(str(view.get("task", "")).startswith("causal_formal_") for view in views)
    else:
        belongs = all(str(view.get("task")) == task_family for view in views)
    if not belongs:
        raise ValueError(f"training views do not belong to {task_family}")
    if task_family == "dynamic_travel":
        return dynamic_travel.LearnedImpactSelector.fit(views)
    if task_family == "dynamic_shopping":
        return dynamic_shopping.fit_learned_selector(views)
    if task_family == "dynamic_search":
        return dynamic_search.LearnedImpactSelector().fit(views)
    if task_family == "causal_formal":
        return causal_formal.LearnedImpactSelector().fit(views)
    raise ValueError(f"unknown task family: {task_family}")


def _learned_write_nodes(task_family: str, view: Mapping[str, Any], selector: Any) -> tuple[str, ...]:
    state = view["memory_state"]
    target = str(view["query"]["intervention"]["node"])
    if task_family == "dynamic_travel":
        nodes = selector.predict(view)
    elif task_family == "dynamic_shopping":
        nodes = selector.predict_affected(view)
    elif task_family == "dynamic_search":
        # Do not call LearnedImpactSelector.predict(): that method attaches a
        # deterministic decoder post_state.  Its learned propagation gate is
        # value-free; reachability is then computed on runtime provenance.
        if selector._should_propagate(view):
            nodes = _descendants(target, _runtime_edges(task_family, view), state)
        else:
            nodes = (target,)
    elif task_family == "causal_formal":
        nodes = selector.select(view)
    else:
        raise ValueError(f"unknown task family: {task_family}")
    return _canonical_nodes(set(nodes) | {target}, state)


def _domain_write_nodes(
    task_family: str,
    view: Mapping[str, Any],
    _edges: Sequence[EdgeRef],
) -> tuple[str, ...]:
    """Return the strongest existing gold-free executable domain mask.

    Each solver may materialize a counterfactual internally from the runtime
    pre-state and query intervention.  Only its changed-node identifiers cross
    this boundary: no post-state values, required-read labels, or simulator
    metadata are attached to the resulting :class:`SelectionPlan`.
    """

    _inference_view(view)
    state = view["memory_state"]
    target = str(view["query"]["intervention"]["node"])
    if task_family == "dynamic_travel":
        nodes = dynamic_travel._domain_impacted(view)
    elif task_family == "dynamic_shopping":
        prediction = dynamic_shopping.domain_solver_selection(view)
        nodes = prediction["predicted_affected_nodes"]
    elif task_family == "dynamic_search":
        prediction = dynamic_search.provenance_domain_prediction(view)
        nodes = prediction["affected_nodes"]
    elif task_family == "causal_formal":
        prediction = causal_formal.oracle_graph_baseline(view)
        nodes = prediction["affected_nodes"]
    else:
        raise ValueError(f"unknown task family: {task_family}")
    return _canonical_nodes(
        set(str(node) for node in nodes) | {target}, state
    )


def _execution_context_nodes(
    task_family: str,
    view: Mapping[str, Any],
    write_nodes: Iterable[str],
    edges: Sequence[EdgeRef],
) -> tuple[str, ...]:
    """Gold-free pre-state needed by the value decoder for one mask.

    Search has an executable provenance read-set that does not materialize a
    post-state.  The other tasks use conservative parent closure over their
    runtime/public dependency structure.
    """

    state = view["memory_state"]
    context = set(_parent_closure(write_nodes, edges, state))
    if task_family == "dynamic_search":
        graph = [
            {"source": edge.source, "target": edge.target, "relation": edge.label}
            for edge in edges
        ]
        context.update(
            dynamic_search.required_reads(
                state, view["query"]["intervention"], graph
            )
        )
    return _canonical_nodes(context, state)


def build_nonoracle_plans(
    task_family: str,
    view: Mapping[str, Any],
    learned_selector: Any,
) -> dict[str, SelectionPlan]:
    """Build five gold-free test plans without attaching any outcome values.

    The domain arm may execute a public runtime mechanism internally to identify
    its exact changed-node mask.  The resulting plan still contains identifiers
    only, and the API prompt can look up values only from the pre-state.
    """

    _inference_view(view)
    if task_family not in TASK_FAMILIES:
        raise ValueError(f"unknown task family: {task_family}")
    state = view["memory_state"]
    target = str(view["query"]["intervention"]["node"])
    runtime_edges = _runtime_edges(task_family, view)

    learned_write = _learned_write_nodes(task_family, view, learned_selector)
    learned_context = _execution_context_nodes(
        task_family, view, learned_write, runtime_edges
    )
    learned_edges = _edges_within(runtime_edges, learned_context)
    learned_history = _history_ids_for_nodes(view, learned_context)

    exact = _make_plan(
        task_family=task_family,
        view=view,
        arm="exact_kv",
        write_nodes=(target,),
        context_nodes=(target,),
        history_ids=_history_ids_for_nodes(view, (target,)),
        edges=(),
        provenance="runtime_only",
    )

    domain_write = _domain_write_nodes(task_family, view, runtime_edges)
    domain_context = _execution_context_nodes(
        task_family, view, domain_write, runtime_edges
    )
    domain = _make_plan(
        task_family=task_family,
        view=view,
        arm="domain_solver",
        write_nodes=domain_write,
        context_nodes=domain_context,
        history_ids=_history_ids_for_nodes(view, domain_context),
        edges=_edges_within(runtime_edges, domain_context),
        provenance="runtime_domain_solver",
    )

    learned = _make_plan(
        task_family=task_family,
        view=view,
        arm="learned_graph",
        write_nodes=learned_write,
        context_nodes=learned_context,
        history_ids=learned_history,
        edges=learned_edges,
        provenance="train_fitted",
    )

    matched_write = _lexical_nodes(view, len(learned_write), required=(target,))
    matched_context = _lexical_nodes(
        view, len(learned_context), required=matched_write
    )
    # Edge retrieval is budget-matched separately from state-cell retrieval.
    # An edge may reference a node whose value was not selected; that is a
    # legitimate structural-only retrieval result and avoids silently shrinking
    # the matched arm's edge budget on dense graphs.
    matched_edges = _rank_edges(view, runtime_edges, len(learned_edges))
    matched = _make_plan(
        task_family=task_family,
        view=view,
        arm="matched_retrieval",
        write_nodes=matched_write,
        context_nodes=matched_context,
        history_ids=_rank_history(view, len(learned_history)),
        edges=matched_edges,
        provenance="runtime_only",
    )

    all_nodes = tuple(sorted(state))
    full = _make_plan(
        task_family=task_family,
        view=view,
        arm="full_state_history",
        write_nodes=all_nodes,
        context_nodes=all_nodes,
        history_ids=range(len(view["history"])),
        edges=runtime_edges,
        provenance="runtime_only",
    )
    return {
        "exact_kv": exact,
        "domain_solver": domain,
        "matched_retrieval": matched,
        "learned_graph": learned,
        "full_state_history": full,
    }


def _oracle_edges(episode: Mapping[str, Any]) -> tuple[EdgeRef, ...]:
    gold = episode.get("gold")
    if not isinstance(gold, Mapping):
        raise ValueError("oracle planning requires evaluator graph structure")
    # A post-intervention active graph can delete the very edge whose
    # deactivation invalidates downstream state.  The oracle upper bound uses
    # the full potential graph so both edge activation and deactivation retain
    # the complete possible propagation path.
    raw = gold.get("graph")
    if isinstance(raw, Mapping):
        raw = raw.get("edges")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("gold graph/active_edges must be an edge sequence")
    return _edge_refs(raw)


def build_oracle_plan(
    task_family: str,
    view: Mapping[str, Any],
    episode: Mapping[str, Any],
) -> SelectionPlan:
    """Build the evaluator-only graph upper bound without gold outcomes."""

    _inference_view(view)
    if str(episode.get("episode_id")) != str(view["episode_id"]):
        raise ValueError("oracle episode does not match runtime view")
    state = view["memory_state"]
    target = str(view["query"]["intervention"]["node"])
    edges = tuple(
        edge
        for edge in _oracle_edges(episode)
        if edge.source in state and edge.target in state
    )
    writes = _descendants(target, edges, state)
    context = _parent_closure(writes, edges, state)
    return _make_plan(
        task_family=task_family,
        view=view,
        arm="oracle_graph",
        write_nodes=writes,
        context_nodes=context,
        history_ids=_history_ids_for_nodes(view, context),
        edges=_edges_within(edges, context),
        provenance="evaluator_oracle",
    )


def build_six_arm_plans(
    task_family: str,
    view: Mapping[str, Any],
    learned_selector: Any,
    *,
    oracle_episode: Mapping[str, Any],
) -> dict[str, SelectionPlan]:
    """Return the normalized six-arm test matrix for one runtime view."""

    plans = build_nonoracle_plans(task_family, view, learned_selector)
    plans["oracle_graph"] = build_oracle_plan(task_family, view, oracle_episode)
    return {arm: plans[arm] for arm in ARM_NAMES}


def fit_all_learned_selectors(
    train_views_by_task: Mapping[str, Sequence[Mapping[str, Any]]]
) -> dict[str, Any]:
    """Fit all four learners from an explicit family-to-train-view mapping."""

    missing = sorted(set(TASK_FAMILIES) - set(train_views_by_task))
    if missing:
        raise ValueError(f"missing training task families: {missing}")
    return {
        task_family: fit_learned_selector(task_family, train_views_by_task[task_family])
        for task_family in TASK_FAMILIES
    }
