"""Deterministic dynamic-evidence benchmark for causal memory.

The upstream MemoryArena search task is a static BrowseComp-style retrieval and
aggregation problem.  This isolated prototype instead asks a memory system to
apply a source/document intervention and repair every *actually changed*
downstream conclusion.  Node identifiers are deliberately opaque: the query
names the intervened record, but it does not name the dossier, answer card, or
briefing that depend on it.

This module has no third-party dependencies.  A typical T0 run is::

    python code/causal_benchmarks/dynamic_search.py \
        --episodes 120 --seed 17 --out /tmp/dynamic_search.jsonl --audit
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:  # Package import in tests.
    from .common import (
        SCHEMA_VERSION,
        audit_predictions,
        changed_nodes,
        runtime_view,
        validate_episode,
    )
except ImportError:  # Direct ``python code/.../dynamic_search.py`` execution.
    from common import (
        SCHEMA_VERSION,
        audit_predictions,
        changed_nodes,
        runtime_view,
        validate_episode,
    )


TASK_NAME = "dynamic_search"
TRUST_WEIGHT = {"low": 0, "medium": 1, "high": 3}
SCENARIOS = (
    "pivotal_retraction",
    "entity_version_correction",
    "source_trust_demotion",
    "source_trust_promotion",
    "low_trust_update_negative",
    "citation_mirror_retraction_negative",
)
TOPICS = (
    "Aster vaccine trial",
    "Borealis battery recall",
    "Cygnus river restoration",
    "Dione satellite launch",
    "Eos crop resilience study",
    "Fornax bridge inspection",
    "Gaia coastal survey",
    "Helios reactor permit",
    "Iris groundwater report",
    "Juno freight corridor",
    "Kepler emissions audit",
    "Lumen habitat review",
    "Mira clinical registry",
    "Nereid flood barrier",
    "Orion mineral assessment",
    "Pavo wildfire model",
)
TOPIC_POOLS = {
    "train": TOPICS[:8],
    "dev": TOPICS[8:12],
    "test": TOPICS[12:],
}
_NODE_ID = re.compile(r"(?:source|document|claim|answer|brief):[A-Z][0-9]{10}")


def _opaque(
    rng: random.Random, prefix: str, used: set[str], namespace: int
) -> str:
    """Return a deterministic but non-semantic node identifier."""

    while True:
        # The episode namespace makes node IDs provably disjoint across splits;
        # the four-digit suffix only needs to be unique within one episode.
        token = f"{prefix}{namespace % 1_000_000:06d}{rng.randrange(1000, 9999):04d}"
        if token not in used:
            used.add(token)
            return token


def _edge_id(source: str, target: str, relation: str) -> str:
    return f"{source}|{relation}|{target}"


def _derived_value(kind: str, value: str) -> dict[str, str]:
    return {"kind": kind, "value": value}


def _eligible(document: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    return bool(
        document.get("active")
        and document.get("independent")
        and TRUST_WEIGHT.get(str(source.get("trust")), 0) > 0
    )


def _claim_status(
    state: Mapping[str, Any], document_nodes: Sequence[str]
) -> str:
    """Compute the dossier state from independent, trusted evidence.

    High-trust evidence has weight 3, medium-trust evidence weight 1, and
    low-trust evidence is gated out.  A score of at least +/-2 is needed for a
    decisive conclusion.  Citation mirrors are explicitly non-independent and
    never add a second vote.
    """

    score = 0
    for node in document_nodes:
        document = state[node]
        source = state[document["source_node"]]
        if not _eligible(document, source):
            continue
        sign = 1 if document["stance"] == "support" else -1
        score += sign * TRUST_WEIGHT[source["trust"]]
    if score >= 2:
        return "verified"
    if score <= -2:
        return "disproved"
    return "unresolved"


def _answer_for(status: str) -> str:
    return {"verified": "YES", "disproved": "NO", "unresolved": "UNCERTAIN"}[status]


def _brief_for(answer: str) -> str:
    return {
        "YES": "publish-confirmed",
        "NO": "publish-correction",
        "UNCERTAIN": "hold-for-review",
    }[answer]


def _edge_document(edge: Mapping[str, Any], state: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if edge["relation"] == "evidence":
        value = state[edge["source"]]
        return value if value.get("kind") == "document" else None
    if edge["relation"] == "trust_context":
        return state[edge["document"]]
    return None


def active_edge_ids(
    state: Mapping[str, Any], graph: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Evaluate graph guards in ``state`` and return enabled edge identifiers."""

    active: list[str] = []
    for edge in graph:
        if edge["relation"] in {"claim_to_answer", "answer_to_brief"}:
            active.append(edge["edge_id"])
            continue
        document = _edge_document(edge, state)
        if document is None:
            continue
        source = state[document["source_node"]]
        if _eligible(document, source):
            active.append(edge["edge_id"])
    return sorted(active)


def _descendant_claims(
    intervention_node: str, graph: Sequence[Mapping[str, Any]]
) -> list[str]:
    return sorted(
        {
            str(edge["target"])
            for edge in graph
            if edge["source"] == intervention_node
            and edge["relation"] in {"evidence", "trust_context"}
        }
    )


def parse_runtime_graph(
    history: Sequence[Mapping[str, Any]], state: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Recover the deterministic provenance graph from runtime-visible history.

    This is an oracle *parser* for the synthetic history grammar, not a learned
    selector.  Keeping it independent of evaluator-owned ``gold`` makes the T0
    upper bound a genuine simulator while also exposing the strong provenance
    baseline that a learned graph must eventually beat.
    """

    edges: dict[str, dict[str, Any]] = {}
    for observation in history:
        observation_type = observation.get("type")
        node_ids = _NODE_ID.findall(str(observation.get("text", "")))
        if observation_type == "provenance_observation":
            claim_nodes = [node for node in node_ids if node.startswith("claim:")]
            document_nodes = list(
                dict.fromkeys(
                    node for node in node_ids if node.startswith("document:")
                )
            )
            if len(claim_nodes) != 1 or len(document_nodes) != 4:
                raise ValueError("malformed runtime provenance observation")
            claim_node = claim_nodes[0]
            for document_node in document_nodes:
                source_node = str(state[document_node]["source_node"])
                evidence_id = _edge_id(document_node, claim_node, "evidence")
                edges[evidence_id] = {
                    "edge_id": evidence_id,
                    "source": document_node,
                    "target": claim_node,
                    "relation": "evidence",
                    "guard": {"min_trust": "medium", "independent_only": True},
                }
                trust_id = _edge_id(source_node, claim_node, "trust_context")
                edges[trust_id] = {
                    "edge_id": trust_id,
                    "source": source_node,
                    "target": claim_node,
                    "relation": "trust_context",
                    "document": document_node,
                    "guard": {"document_active": True, "independent_only": True},
                }
        elif observation_type == "derivation_observation":
            claim_nodes = [node for node in node_ids if node.startswith("claim:")]
            answer_nodes = list(
                dict.fromkeys(node for node in node_ids if node.startswith("answer:"))
            )
            brief_nodes = [node for node in node_ids if node.startswith("brief:")]
            if len(claim_nodes) != 1 or len(answer_nodes) != 1 or len(brief_nodes) != 1:
                raise ValueError("malformed runtime derivation observation")
            downstream = (
                (claim_nodes[0], answer_nodes[0], "claim_to_answer"),
                (answer_nodes[0], brief_nodes[0], "answer_to_brief"),
            )
            for source, target, relation in downstream:
                edge_id = _edge_id(source, target, relation)
                edges[edge_id] = {
                    "edge_id": edge_id,
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "guard": None,
                }
    return [edges[edge_id] for edge_id in sorted(edges)]


def simulate_post_state(
    pre_state: Mapping[str, Any],
    intervention: Mapping[str, Any],
    graph: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply a surgical intervention and recompute its structural descendants.

    Guarded edges are retained in the structural graph even when disabled.  We
    therefore recompute a potential child after both edge activation and edge
    deactivation; whether the child's value actually changes is determined by
    its structural equation.
    """

    state = copy.deepcopy(dict(pre_state))
    node = str(intervention["node"])
    if node not in state:
        raise KeyError(f"intervention node is absent: {node}")
    state[node] = copy.deepcopy(intervention["new_value"])

    for claim_node in _descendant_claims(node, graph):
        document_nodes = sorted(
            str(edge["source"])
            for edge in graph
            if edge["target"] == claim_node and edge["relation"] == "evidence"
        )
        status = _claim_status(state, document_nodes)
        state[claim_node] = _derived_value("claim", status)

        answer_nodes = sorted(
            str(edge["target"])
            for edge in graph
            if edge["source"] == claim_node and edge["relation"] == "claim_to_answer"
        )
        for answer_node in answer_nodes:
            answer = _answer_for(status)
            state[answer_node] = _derived_value("answer", answer)
            brief_nodes = sorted(
                str(edge["target"])
                for edge in graph
                if edge["source"] == answer_node
                and edge["relation"] == "answer_to_brief"
            )
            for brief_node in brief_nodes:
                state[brief_node] = _derived_value("brief", _brief_for(answer))
    return state


def _topic_graph(
    topic: str,
    source_nodes: Mapping[str, str],
    document_nodes: Mapping[str, str],
    claim_node: str,
    answer_node: str,
    brief_node: str,
) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = []
    for role in ("authority", "journal", "blog", "mirror"):
        source_node = source_nodes[role]
        document_node = document_nodes[role]
        evidence = {
            "source": document_node,
            "target": claim_node,
            "relation": "evidence",
            "guard": {"min_trust": "medium", "independent_only": True},
            "topic": topic,
        }
        evidence["edge_id"] = _edge_id(document_node, claim_node, "evidence")
        graph.append(evidence)
        trust = {
            "source": source_node,
            "target": claim_node,
            "relation": "trust_context",
            "document": document_node,
            "guard": {"document_active": True, "independent_only": True},
            "topic": topic,
        }
        trust["edge_id"] = _edge_id(source_node, claim_node, "trust_context")
        graph.append(trust)

    downstream = (
        (claim_node, answer_node, "claim_to_answer"),
        (answer_node, brief_node, "answer_to_brief"),
    )
    for source, target, relation in downstream:
        graph.append(
            {
                "edge_id": _edge_id(source, target, relation),
                "source": source,
                "target": target,
                "relation": relation,
                "guard": None,
                "topic": topic,
            }
        )
    return graph


def _build_topic(
    rng: random.Random,
    topic: str,
    used: set[str],
    target_scenario: str | None,
    novel_regime: bool = False,
    node_namespace: int = 0,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    source_nodes = {
        role: f"source:{_opaque(rng, 'S', used, node_namespace)}"
        for role in ("authority", "journal", "blog", "mirror")
    }
    document_nodes = {
        role: f"document:{_opaque(rng, 'D', used, node_namespace)}"
        for role in ("authority", "journal", "blog", "mirror")
    }
    claim_node = f"claim:{_opaque(rng, 'C', used, node_namespace)}"
    answer_node = f"answer:{_opaque(rng, 'A', used, node_namespace)}"
    brief_node = f"brief:{_opaque(rng, 'B', used, node_namespace)}"

    trust = {"authority": "high", "journal": "medium", "blog": "low", "mirror": "high"}
    stance = {"authority": "support", "journal": "support", "blog": "support", "mirror": "support"}
    if target_scenario == "entity_version_correction":
        stance["journal"] = "refute"
    elif target_scenario == "source_trust_demotion" and novel_regime:
        stance["journal"] = "refute"
    elif target_scenario == "source_trust_promotion":
        trust["authority"] = "medium" if novel_regime else "low"
        if novel_regime:
            stance["journal"] = "refute"
    elif target_scenario is None:
        # Static distractors vary but remain valid under the same equations.
        stance["journal"] = rng.choice(("support", "refute"))
        stance["blog"] = rng.choice(("support", "refute"))
        if rng.random() < 0.35:
            trust["authority"] = "low"

    state: dict[str, Any] = {}
    labels = {
        "authority": "official registry",
        "journal": "peer-reviewed journal",
        "blog": "unverified newswire",
        "mirror": "citation mirror",
    }
    history: list[dict[str, Any]] = []
    for role in ("authority", "journal", "blog", "mirror"):
        source_node = source_nodes[role]
        document_node = document_nodes[role]
        state[source_node] = {
            "kind": "source",
            "trust": trust[role],
            "label": labels[role],
        }
        state[document_node] = {
            "kind": "document",
            "active": True,
            "version": 1,
            "stance": stance[role],
            "independent": role != "mirror",
            "source_node": source_node,
        }
        history.append(
            {
                "type": "source_observation",
                "text": (
                    f"For {topic}, {labels[role]} record {source_node} is "
                    f"{trust[role]} trust. Its document {document_node} version 1 "
                    f"is active and reports {stance[role]}."
                ),
            }
        )

    graph = _topic_graph(
        topic, source_nodes, document_nodes, claim_node, answer_node, brief_node
    )
    docs = list(document_nodes.values())
    status = _claim_status(state, docs)
    answer = _answer_for(status)
    state[claim_node] = _derived_value("claim", status)
    state[answer_node] = _derived_value("answer", answer)
    state[brief_node] = _derived_value("brief", _brief_for(answer))
    history.extend(
        [
            {
                "type": "provenance_observation",
                "text": (
                    f"Dossier {claim_node} combines independent records "
                    f"{document_nodes['authority']}, {document_nodes['journal']}, and "
                    f"{document_nodes['blog']}. Their reputation records are "
                    f"{source_nodes['authority']}, {source_nodes['journal']}, and "
                    f"{source_nodes['blog']}. Document {document_nodes['mirror']} is only "
                    f"a citation copy of {document_nodes['authority']} and never counts as "
                    "independent corroboration. Low-trust records are quarantined."
                ),
            },
            {
                "type": "derivation_observation",
                "text": (
                    f"Answer card {answer_node} is derived from dossier {claim_node}; "
                    f"monitoring brief {brief_node} is derived from answer card {answer_node}."
                ),
            },
        ]
    )
    ids = {
        "topic": topic,
        "source_nodes": source_nodes,
        "document_nodes": document_nodes,
        "claim_node": claim_node,
        "answer_node": answer_node,
        "brief_node": brief_node,
    }
    return state, graph, history, ids


def _make_intervention(
    scenario: str,
    state: Mapping[str, Any],
    ids: Mapping[str, Any],
    novel_regime: bool = False,
) -> tuple[dict[str, Any], str]:
    sources = ids["source_nodes"]
    documents = ids["document_nodes"]
    if scenario == "pivotal_retraction":
        node = documents["authority"]
        value = copy.deepcopy(state[node])
        value["active"] = False
        kind = "retract_document"
        event = f"document record {node} has been retracted"
    elif scenario == "entity_version_correction":
        node = documents["authority"]
        value = copy.deepcopy(state[node])
        version = 3 if novel_regime else 2
        value.update({"version": version, "stance": "refute"})
        kind = "replace_entity_version"
        event = f"document record {node} is replaced by version {version}, which reports refute"
    elif scenario == "source_trust_demotion":
        node = sources["authority"]
        value = copy.deepcopy(state[node])
        value["trust"] = "medium" if novel_regime else "low"
        kind = "change_source_trust"
        event = f"source reputation record {node} is now {value['trust']} trust"
    elif scenario == "source_trust_promotion":
        node = sources["authority"]
        value = copy.deepcopy(state[node])
        value["trust"] = "high"
        kind = "change_source_trust"
        event = f"source reputation record {node} is now high trust"
    elif scenario == "low_trust_update_negative":
        node = documents["blog"]
        value = copy.deepcopy(state[node])
        value.update({"version": 2, "stance": "refute"})
        kind = "replace_entity_version"
        event = f"document record {node} is replaced by version 2, which reports refute"
    elif scenario == "citation_mirror_retraction_negative":
        node = documents["mirror"]
        value = copy.deepcopy(state[node])
        value["active"] = False
        kind = "retract_document"
        event = f"citation-mirror document record {node} has been retracted"
    else:  # pragma: no cover - protected by generated scenarios.
        raise ValueError(f"unknown scenario: {scenario}")
    return {
        "kind": kind,
        "node": node,
        "old_value": copy.deepcopy(state[node]),
        "new_value": value,
    }, event


def required_reads(
    pre_state: Mapping[str, Any],
    intervention: Mapping[str, Any],
    graph: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Return a minimal family read-set for gated recomputation."""

    node = str(intervention["node"])
    claims = _descendant_claims(node, graph)
    if not claims:
        return [node]

    # If a document is ineligible both before and after the event, reading its
    # source gate suffices to prove this is a negative control.
    old_value = pre_state[node]
    new_value = intervention["new_value"]
    if old_value.get("kind") == "document":
        source_node = str(old_value["source_node"])
        source = pre_state[source_node]
        if not _eligible(old_value, source) and not _eligible(new_value, source):
            return sorted({node, source_node})

    reads = {node}
    for claim in claims:
        reads.add(claim)
        for edge in graph:
            if edge["target"] == claim and edge["relation"] == "evidence":
                document_node = str(edge["source"])
                reads.add(document_node)
                reads.add(str(pre_state[document_node]["source_node"]))
            if edge["source"] == claim and edge["relation"] == "claim_to_answer":
                answer = str(edge["target"])
                reads.add(answer)
                for child in graph:
                    if child["source"] == answer and child["relation"] == "answer_to_brief":
                        reads.add(str(child["target"]))
    return sorted(reads)


def _split(index: int) -> str:
    bucket = (index // len(SCENARIOS)) % 10
    return "train" if bucket < 7 else "dev" if bucket < 9 else "test"


def generate_episode(index: int, seed: int = 0, distractor_topics: int = 3) -> dict[str, Any]:
    """Generate one independently reproducible episode."""

    if distractor_topics < 1:
        raise ValueError("distractor_topics must be at least one")
    rng = random.Random((seed + 1) * 1_000_003 + index * 97_409)
    scenario = SCENARIOS[(seed + index) % len(SCENARIOS)]
    split = _split(index)
    topic_pool = TOPIC_POOLS[split]
    chosen = rng.sample(topic_pool, k=min(len(topic_pool), distractor_topics + 1))
    target_topic = chosen[0]
    used: set[str] = set()
    state: dict[str, Any] = {}
    graph: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    target_ids: dict[str, Any] | None = None

    for position, topic in enumerate(chosen):
        topic_state, topic_graph, topic_history, ids = _build_topic(
            rng,
            topic,
            used,
            scenario if position == 0 else None,
            novel_regime=(split == "test" and position == 0),
            node_namespace=index,
        )
        state.update(topic_state)
        graph.extend(topic_graph)
        history.extend(topic_history)
        if position == 0:
            target_ids = ids
    assert target_ids is not None
    rng.shuffle(history)

    intervention, event = _make_intervention(
        scenario, state, target_ids, novel_regime=(split == "test")
    )
    post_state = simulate_post_state(state, intervention, graph)
    affected = changed_nodes(state, post_state)
    reads = required_reads(state, intervention, graph)
    answer_node = str(target_ids["answer_node"])
    brief_node = str(target_ids["brief_node"])
    negative = scenario.endswith("_negative")
    if split == "train":
        query_template = "train-update"
        query_text = (
            f"New evidence event for {target_topic}: {event}. Apply this event and bring "
            "the evidence memory up to date. The event does not enumerate any dependent "
            "dossiers, answer cards, or briefs."
        )
    elif split == "dev":
        query_template = "dev-reconcile"
        query_text = (
            f"Archive notice concerning {target_topic}: {event}. Reconcile every record "
            "whose current validity follows from this notice; none is named here."
        )
    else:
        query_template = "test-control-notice"
        query_text = (
            f"Evidence-control notice for {target_topic}: {event}. Synchronize the archive "
            "after this notice. Dependent artifacts are intentionally unnamed."
        )
    pre_active_ids = set(active_edge_ids(state, graph))
    post_active_ids = set(active_edge_ids(post_state, graph))
    episode = {
        "schema_version": SCHEMA_VERSION,
        "task": TASK_NAME,
        "episode_id": f"dynamic-search-s{seed}-e{index:05d}",
        "split": split,
        "history": history,
        "memory_state": state,
        "query": {"text": query_text, "intervention": intervention},
        "metadata": {
            "entity_pool": split,
            "query_template": query_template,
            "heldout_regime": split == "test",
        },
        "gold": {
            "graph": graph,
            "intervention": intervention,
            "pre_active_edges": [
                edge for edge in graph if edge["edge_id"] in pre_active_ids
            ],
            "active_edges": [
                edge for edge in graph if edge["edge_id"] in post_active_ids
            ],
            "affected_nodes": affected,
            "required_reads": reads,
            "post_state": post_state,
            "final_answers": {
                "answer_node": answer_node,
                "answer": post_state[answer_node]["value"],
                "brief_node": brief_node,
                "brief": post_state[brief_node]["value"],
                "text": (
                    f"{target_topic}: {post_state[answer_node]['value']}; "
                    f"brief={post_state[brief_node]['value']}"
                ),
            },
            "scenario": scenario,
            "negative_control": negative,
            "propagation_required": len(affected) > 1,
            "target_topic": target_topic,
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


def generate_episodes(count: int, seed: int = 0) -> list[dict[str, Any]]:
    if count <= 0:
        raise ValueError("episodes must be positive")
    return [generate_episode(index, seed=seed) for index in range(count)]


def generate_dataset(episodes: int = 120, seed: int = 17) -> list[dict[str, Any]]:
    """Integration-runner adapter shared by all causal benchmark prototypes."""

    return generate_episodes(episodes, seed=seed)


def exact_key_prediction(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Strongest possible exact lookup that updates only the named key."""

    state = copy.deepcopy(episode["memory_state"])
    intervention = episode["query"]["intervention"]
    node = str(intervention["node"])
    state[node] = copy.deepcopy(intervention["new_value"])
    return {
        "affected_nodes": changed_nodes(episode["memory_state"], state),
        "post_state": state,
        "selected_reads": [node],
    }


def query_only_prediction(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Query-only structured parser baseline.

    The benchmark contract supplies an oracle semantic parse of the event so
    that parsing is not conflated with propagation.  Without history/graph, the
    parsed query still identifies only the surgically changed node.  Hence this
    baseline intentionally equals Exact-KV and is reported separately as a T0
    leakage check.
    """

    return exact_key_prediction(episode)


def oracle_prediction(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Parse runtime history and propagate without reading evaluator-owned gold."""

    graph = parse_runtime_graph(episode["history"], episode["memory_state"])
    intervention = episode["query"]["intervention"]
    state = simulate_post_state(episode["memory_state"], intervention, graph)
    return {
        "affected_nodes": changed_nodes(episode["memory_state"], state),
        "post_state": state,
        "selected_reads": required_reads(episode["memory_state"], intervention, graph),
        "selected_graph": graph,
    }


def provenance_domain_prediction(view: Mapping[str, Any]) -> dict[str, Any]:
    """Strong dependency-memory baseline: parse provenance, then run the domain SCM.

    This baseline has no fitted parameters and never reads evaluator gold.  It is
    intentionally strong: a learned impact selector must beat it at matched
    budget before the result can be described as evidence for causal learning.
    """

    if "gold" in view:
        raise ValueError("provenance baseline accepts runtime views, never gold")
    return oracle_prediction(view)


def oracle_graph_prediction(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluator upper bound using the hidden graph but recomputing all values."""

    graph = episode["gold"]["graph"]
    intervention = episode["query"]["intervention"]
    state = simulate_post_state(episode["memory_state"], intervention, graph)
    return {
        "affected_nodes": changed_nodes(episode["memory_state"], state),
        "post_state": state,
        "selected_reads": required_reads(episode["memory_state"], intervention, graph),
        "selected_graph": graph,
    }


def full_history_prediction(view: Mapping[str, Any]) -> dict[str, Any]:
    """Runtime-only full-history upper-cost arm with the shared domain decoder."""

    if "gold" in view:
        raise ValueError("full-history baseline accepts runtime views, never gold")
    graph = parse_runtime_graph(view["history"], view["memory_state"])
    intervention = view["query"]["intervention"]
    state = simulate_post_state(view["memory_state"], intervention, graph)
    return {
        "affected_nodes": changed_nodes(view["memory_state"], state),
        "post_state": state,
        "selected_reads": sorted(view["memory_state"]),
        "selected_graph": graph,
    }


def _changed_kinds(
    before: Mapping[str, Any], after: Mapping[str, Any], direct_node: str
) -> set[str]:
    return {
        str(before[node].get("kind", "unknown"))
        for node in changed_nodes(before, after)
        if node != direct_node and isinstance(before.get(node), Mapping)
    }


class LearnedImpactSelector:
    """Small empirical graph/gate selector fitted only on observed train transitions.

    The class learns typed impact edges and gate regularities.  It does *not*
    learn the value equations: every T1 arm deliberately shares the deterministic
    domain decoder so the experiment isolates selection from serialization and
    value generation.
    """

    def __init__(self) -> None:
        self.fitted = False
        self.typed_edges: set[tuple[str, str]] = set()
        self.positive_document_trust: set[str] = set()
        self.blocked_document_trust: set[str] = set()
        self.learned_independence_gate = False
        self.source_positive = 0
        self.source_total = 0
        self.document_positive = 0
        self.document_total = 0
        self.training_examples = 0

    def fit(self, train_views: Sequence[Mapping[str, Any]]) -> "LearnedImpactSelector":
        for view in train_views:
            if "gold" in view:
                raise ValueError("learner.fit must not receive evaluator gold")
            if view.get("split") != "train" or "observed_transition" not in view:
                raise ValueError("learner.fit requires runtime-visible train transitions")
            observed = view["observed_transition"]
            before = observed["pre_state"]
            after = observed["post_state"]
            intervention = observed["intervention"]
            node = str(intervention["node"])
            direct = before[node]
            direct_kind = str(direct.get("kind"))
            downstream_kinds = _changed_kinds(before, after, node)
            propagated = bool(downstream_kinds)
            self.training_examples += 1

            if propagated and "claim" in downstream_kinds:
                self.typed_edges.add((direct_kind, "claim"))
            if {"claim", "answer"} <= downstream_kinds:
                self.typed_edges.add(("claim", "answer"))
            if {"answer", "brief"} <= downstream_kinds:
                self.typed_edges.add(("answer", "brief"))

            if direct_kind == "document":
                self.document_total += 1
                self.document_positive += int(propagated)
                source = before[direct["source_node"]]
                trust = str(source["trust"])
                if propagated:
                    self.positive_document_trust.add(trust)
                else:
                    self.blocked_document_trust.add(trust)
                    if not direct.get("independent"):
                        self.learned_independence_gate = True
            elif direct_kind == "source":
                self.source_total += 1
                self.source_positive += int(propagated)
        if not self.training_examples:
            raise ValueError("learner.fit received no transitions")
        self.fitted = True
        return self

    def _should_propagate(self, view: Mapping[str, Any]) -> bool:
        intervention = view["query"]["intervention"]
        node = str(intervention["node"])
        old_value = intervention["old_value"]
        new_value = intervention["new_value"]
        kind = str(old_value.get("kind"))
        if (kind, "claim") not in self.typed_edges:
            return False
        if kind == "source":
            return bool(self.source_total and self.source_positive / self.source_total >= 0.5)
        if kind != "document":
            return False
        if self.learned_independence_gate and not bool(new_value.get("independent")):
            return False
        source = view["memory_state"][old_value["source_node"]]
        trust = str(source["trust"])
        if trust in self.positive_document_trust:
            return True
        if trust in self.blocked_document_trust:
            return False
        return bool(
            self.document_total
            and self.document_positive / self.document_total >= 0.5
        )

    def predict(self, view: Mapping[str, Any]) -> dict[str, Any]:
        if not self.fitted:
            raise ValueError("learner must be fitted before predict")
        if "gold" in view or "observed_transition" in view:
            raise ValueError("learner.predict accepts outcome-free runtime views")
        graph = parse_runtime_graph(view["history"], view["memory_state"])
        intervention = view["query"]["intervention"]
        node = str(intervention["node"])
        if self._should_propagate(view):
            state = simulate_post_state(view["memory_state"], intervention, graph)
            reads = required_reads(view["memory_state"], intervention, graph)
        else:
            state = copy.deepcopy(view["memory_state"])
            state[node] = copy.deepcopy(intervention["new_value"])
            reads = {node}
            old_value = intervention["old_value"]
            if old_value.get("kind") == "document":
                reads.add(str(old_value["source_node"]))
            reads = sorted(reads)
        return {
            "affected_nodes": changed_nodes(view["memory_state"], state),
            "post_state": state,
            "selected_reads": list(reads),
            "selected_graph": graph,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "training_examples": self.training_examples,
            "typed_edges": sorted([list(edge) for edge in self.typed_edges]),
            "positive_document_trust": sorted(self.positive_document_trust),
            "blocked_document_trust": sorted(self.blocked_document_trust),
            "learned_independence_gate": self.learned_independence_gate,
            "source_propagation_rate": (
                self.source_positive / self.source_total if self.source_total else 0.0
            ),
        }


def _tokens(text_value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text_value.lower()))


def _node_search_text(view: Mapping[str, Any]) -> dict[str, str]:
    corpus = {
        node: f"{node} {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
        for node, value in view["memory_state"].items()
    }
    for observation in view["history"]:
        text_value = str(observation.get("text", ""))
        for node in _NODE_ID.findall(text_value):
            if node in corpus:
                corpus[node] += " " + text_value
    return corpus


def lexical_structured_prediction(
    view: Mapping[str, Any], budget: int
) -> dict[str, Any]:
    """Matched-cell lexical/exact-structure retrieval with the shared decoder."""

    if "gold" in view:
        raise ValueError("lexical baseline accepts runtime views, never gold")
    graph = parse_runtime_graph(view["history"], view["memory_state"])
    intervention = view["query"]["intervention"]
    explicit = str(intervention["node"])
    query_tokens = _tokens(view["query"]["text"])
    corpus = _node_search_text(view)
    ranks: list[tuple[float, str]] = []
    for node, text_value in corpus.items():
        overlap = len(query_tokens & _tokens(text_value))
        score = float(overlap)
        if node == explicit:
            score += 1000.0
        old_value = intervention["old_value"]
        if old_value.get("kind") == "document" and node == old_value.get("source_node"):
            score += 100.0
        ranks.append((score, node))
    ranks.sort(key=lambda item: (-item[0], item[1]))
    selected = sorted(node for _, node in ranks[: max(1, min(budget, len(ranks)))])
    needed = set(required_reads(view["memory_state"], intervention, graph))
    if needed <= set(selected):
        state = simulate_post_state(view["memory_state"], intervention, graph)
    else:
        state = copy.deepcopy(view["memory_state"])
        state[explicit] = copy.deepcopy(intervention["new_value"])
    return {
        "affected_nodes": changed_nodes(view["memory_state"], state),
        "post_state": state,
        "selected_reads": selected,
        "selected_graph": graph,
    }


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 1.0


def _score_reads(
    episodes: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]]
) -> dict[str, float]:
    precision: list[float] = []
    recall: list[float] = []
    for episode, prediction in zip(episodes, predictions):
        gold = set(episode["gold"]["required_reads"])
        selected = set(prediction.get("selected_reads", []))
        overlap = len(gold & selected)
        precision.append(overlap / len(selected) if selected else float(not gold))
        recall.append(overlap / len(gold) if gold else 1.0)
    return {"required_read_precision": _mean(precision), "required_read_recall": _mean(recall)}


def _score_answers(
    episodes: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]]
) -> dict[str, float]:
    answers: list[float] = []
    briefs: list[float] = []
    propagation_answers: list[float] = []
    negative_specificity: list[float] = []
    for episode, prediction in zip(episodes, predictions):
        gold = episode["gold"]
        answer_node = gold["final_answers"]["answer_node"]
        brief_node = gold["final_answers"]["brief_node"]
        proposed = prediction["post_state"]
        answer_ok = proposed[answer_node] == gold["post_state"][answer_node]
        brief_ok = proposed[brief_node] == gold["post_state"][brief_node]
        answers.append(float(answer_ok))
        briefs.append(float(brief_ok))
        if gold["propagation_required"]:
            propagation_answers.append(float(answer_ok))
        if gold["negative_control"]:
            explicit = {episode["query"]["intervention"]["node"]}
            predicted_extra = set(prediction["affected_nodes"]) - explicit
            negative_specificity.append(float(not predicted_extra))
    return {
        "final_answer_accuracy": _mean(answers),
        "final_brief_accuracy": _mean(briefs),
        "propagation_episode_answer_accuracy": _mean(propagation_answers),
        "negative_control_specificity": _mean(negative_specificity),
    }


def _score_baseline(
    episodes: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    report = audit_predictions(episodes, predictions)
    report.pop("per_episode", None)
    report.update(_score_reads(episodes, predictions))
    report.update(_score_answers(episodes, predictions))
    return report


def _context_graph(prediction: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    selected = set(prediction.get("selected_reads", []))
    return [
        edge
        for edge in prediction.get("selected_graph", [])
        if edge.get("source") in selected and edge.get("target") in selected
    ]


def serialize_selected_context(
    view: Mapping[str, Any], prediction: Mapping[str, Any], mode: str
) -> str:
    """Serialize one fixed selection in verbose or compact form.

    Prediction is deliberately computed before this function is called.  The
    resulting matrix is therefore a selection x serialization ablation rather
    than a bundle in which shortening the prompt silently changes the selector.
    """

    selected = [node for node in prediction.get("selected_reads", []) if node in view["memory_state"]]
    state = {node: view["memory_state"][node] for node in selected}
    graph = _context_graph(prediction)
    if mode == "verbose":
        return json.dumps(
            {
                "intervention": view["query"]["intervention"],
                "selected_memory": state,
                "provenance_edges": graph,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    if mode != "compact":
        raise ValueError(f"unknown serialization mode: {mode}")
    intervention = view["query"]["intervention"]
    lines = [
        f"I|{intervention['node']}|{json.dumps(intervention['new_value'], sort_keys=True, separators=(',', ':'))}"
    ]
    lines.extend(
        f"M|{node}|{json.dumps(state[node], sort_keys=True, separators=(',', ':'))}"
        for node in selected
    )
    lines.extend(
        f"E|{edge['source']}|{edge['relation']}|{edge['target']}"
        for edge in graph
    )
    return "\n".join(lines)


def _effect_and_efficiency(
    episodes: Sequence[Mapping[str, Any]],
    views: Sequence[Mapping[str, Any]],
    predictions: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    effect = _score_baseline(episodes, predictions)
    effect["selected_cells_mean"] = _mean(
        len(prediction.get("selected_reads", [])) for prediction in predictions
    )
    rows: list[dict[str, Any]] = []
    for mode in ("verbose", "compact"):
        lengths = [
            len(serialize_selected_context(view, prediction, mode))
            for view, prediction in zip(views, predictions)
        ]
        rows.append(
            {
                "serialization": mode,
                "selected_cells_mean": effect["selected_cells_mean"],
                "serialization_chars_mean": _mean(lengths),
                "char_token_proxy_mean": _mean(length / 4.0 for length in lengths),
                "affected_precision": effect["affected_precision"],
                "affected_recall": effect["affected_recall"],
                "final_answer_accuracy": effect["final_answer_accuracy"],
                "final_brief_accuracy": effect["final_brief_accuracy"],
                "negative_control_specificity": effect["negative_control_specificity"],
            }
        )
    return effect, rows


def _trust_transition(episode: Mapping[str, Any]) -> str | None:
    intervention = episode["query"]["intervention"]
    old = intervention["old_value"]
    new = intervention["new_value"]
    if old.get("kind") != "source":
        return None
    return f"{old['trust']}->{new['trust']}"


def _novelty_audit(
    train: Sequence[Mapping[str, Any]], test: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    train_nodes = {node for episode in train for node in episode["memory_state"]}
    test_nodes = {node for episode in test for node in episode["memory_state"]}
    train_entities = {episode["gold"]["target_topic"] for episode in train}
    test_entities = {episode["gold"]["target_topic"] for episode in test}
    train_templates = {episode["metadata"]["query_template"] for episode in train}
    test_templates = {episode["metadata"]["query_template"] for episode in test}
    train_trust = {
        transition for episode in train if (transition := _trust_transition(episode))
    }
    test_trust = {
        transition for episode in test if (transition := _trust_transition(episode))
    }
    train_versions = {
        episode["query"]["intervention"]["new_value"].get("version")
        for episode in train
        if episode["query"]["intervention"]["kind"] == "replace_entity_version"
    }
    test_versions = {
        episode["query"]["intervention"]["new_value"].get("version")
        for episode in test
        if episode["query"]["intervention"]["kind"] == "replace_entity_version"
    }
    report = {
        "node_id_overlap": len(train_nodes & test_nodes),
        "entity_overlap": sorted(train_entities & test_entities),
        "query_template_overlap": sorted(train_templates & test_templates),
        "train_trust_transitions": sorted(train_trust),
        "test_trust_transitions": sorted(test_trust),
        "heldout_trust_transitions": sorted(test_trust - train_trust),
        "train_entity_versions": sorted(version for version in train_versions if version is not None),
        "test_entity_versions": sorted(version for version in test_versions if version is not None),
        "heldout_entity_versions": sorted(
            version for version in test_versions - train_versions if version is not None
        ),
    }
    report["pass"] = bool(
        report["node_id_overlap"] == 0
        and not report["entity_overlap"]
        and not report["query_template_overlap"]
        and report["heldout_trust_transitions"]
        and report["heldout_entity_versions"]
    )
    return report


def audit_t1(episodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Fit on observed train transitions and evaluate six isolated test arms."""

    train = [episode for episode in episodes if episode["split"] == "train"]
    test = [episode for episode in episodes if episode["split"] == "test"]
    if not train or not test:
        return {
            "status": "insufficient_split_coverage",
            "train_episodes": len(train),
            "test_episodes": len(test),
            "minimum_recommended_episodes": 60,
        }

    train_views = [runtime_view(episode, training=True) for episode in train]
    test_views = [runtime_view(episode, training=False) for episode in test]
    learner = LearnedImpactSelector().fit(train_views)

    exact = [exact_key_prediction(view) for view in test_views]
    provenance = [provenance_domain_prediction(view) for view in test_views]
    learned = [learner.predict(view) for view in test_views]
    lexical = [
        lexical_structured_prediction(view, len(prediction["selected_reads"]))
        for view, prediction in zip(test_views, learned)
    ]
    oracle = [oracle_graph_prediction(episode) for episode in test]
    full = [full_history_prediction(view) for view in test_views]
    predictions = {
        "exact_kv": exact,
        "provenance_domain": provenance,
        "matched_lexical_structured": lexical,
        "learned_graph": learned,
        "oracle_graph": oracle,
        "full_history": full,
    }

    effects: dict[str, Any] = {}
    efficiency_matrix: list[dict[str, Any]] = []
    for arm, arm_predictions in predictions.items():
        effect, rows = _effect_and_efficiency(test, test_views, arm_predictions)
        effects[arm] = effect
        for row in rows:
            efficiency_matrix.append({"arm": arm, **row})

    learned_effect = effects["learned_graph"]
    lexical_effect = effects["matched_lexical_structured"]
    provenance_effect = effects["provenance_domain"]
    better_than_lexical = bool(
        learned_effect["affected_recall"] > lexical_effect["affected_recall"]
        and learned_effect["selected_cells_mean"] <= lexical_effect["selected_cells_mean"]
    )
    better_than_provenance = bool(
        (
            learned_effect["affected_recall"] > provenance_effect["affected_recall"]
            or learned_effect["final_answer_accuracy"]
            > provenance_effect["final_answer_accuracy"]
        )
        and learned_effect["selected_cells_mean"] <= provenance_effect["selected_cells_mean"]
    )
    novelty = _novelty_audit(train, test)
    no_test_outcomes = all(
        "gold" not in view and "observed_transition" not in view for view in test_views
    )
    return {
        "status": "complete",
        "train_episodes": len(train),
        "test_episodes": len(test),
        "test_scenario_counts": {
            scenario: sum(episode["gold"]["scenario"] == scenario for episode in test)
            for scenario in SCENARIOS
        },
        "runtime_isolation": {
            "fit_views_have_no_gold": all("gold" not in view for view in train_views),
            "train_views_have_observed_transition": all(
                "observed_transition" in view for view in train_views
            ),
            "test_views_have_no_gold_or_outcome": no_test_outcomes,
        },
        "novel_test": novelty,
        "learner": learner.summary(),
        "effects": effects,
        "selection_x_serialization": efficiency_matrix,
        "admission": {
            "six_arms_present": len(effects) == 6,
            "runtime_gold_isolation_pass": no_test_outcomes,
            "novel_split_pass": novelty["pass"],
            "learned_beats_matched_lexical": better_than_lexical,
            "learned_beats_strong_provenance": better_than_provenance,
            "supports_causal_learning_claim": better_than_provenance,
        },
        "decoder_boundary": (
            "All six arms share a deterministic domain value decoder. Endpoint accuracy "
            "therefore measures whether selection supplied sufficient state; it is not an "
            "end-to-end learned causal-equation result."
        ),
        "efficiency_boundary": (
            "Character/token proxies measure the selected decoder payload only. Index "
            "construction and selector scans over runtime history are not counted as model "
            "input and must be timed separately in an end-to-end experiment."
        ),
        "claim_boundary": (
            "Citation traversal is the provenance/dataflow baseline. A learned selector "
            "supports causal-learning only if it beats provenance_domain at matched read "
            "budget; tying it supports dependency memory, not causal discovery."
        ),
    }


def audit_t0(episodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Run no-LLM admission diagnostics for query leakage and propagation headroom."""

    for episode in episodes:
        validate_episode(episode)
    exact = [exact_key_prediction(episode) for episode in episodes]
    query_only = [query_only_prediction(episode) for episode in episodes]
    oracle = [oracle_prediction(episode) for episode in episodes]

    downstream_mentions = 0
    downstream_total = 0
    for episode in episodes:
        explicit = str(episode["query"]["intervention"]["node"])
        query_mentions = set(_NODE_ID.findall(episode["query"]["text"]))
        downstream = set(episode["gold"]["affected_nodes"]) - {explicit}
        downstream_mentions += len(downstream & query_mentions)
        downstream_total += len(downstream)
    leakage = downstream_mentions / downstream_total if downstream_total else 0.0

    scenario_counts = {scenario: 0 for scenario in SCENARIOS}
    for episode in episodes:
        scenario_counts[episode["gold"]["scenario"]] += 1

    exact_score = _score_baseline(episodes, exact)
    query_score = _score_baseline(episodes, query_only)
    oracle_score = _score_baseline(episodes, oracle)
    propagation_count = sum(bool(e["gold"]["propagation_required"]) for e in episodes)
    negative_count = sum(bool(e["gold"]["negative_control"]) for e in episodes)
    admission = {
        "C1_no_query_time_oracle": leakage == 0.0,
        "C2_repeated_regime_mechanism": len(episodes) >= len(SCENARIOS),
        "C3_interventional_gold_valid": True,
        "C4_exact_key_leaves_headroom": (
            exact_score["propagation_episode_answer_accuracy"] < 0.95
            and oracle_score["propagation_episode_answer_accuracy"] == 1.0
        ),
        "gated_negative_controls_pass": (
            oracle_score["negative_control_specificity"] == 1.0
        ),
    }
    admission["pass"] = all(admission.values())
    return {
        "task": TASK_NAME,
        "episodes": len(episodes),
        "scenario_counts": scenario_counts,
        "diagnostics": {
            "propagation_required_fraction": propagation_count / len(episodes),
            "negative_control_fraction": negative_count / len(episodes),
            "query_downstream_id_leakage": leakage,
        },
        "baselines": {
            "query_only": query_score,
            "exact_key": exact_score,
            "oracle_propagation": oracle_score,
        },
        "admission": admission,
        "boundary": (
            "The emitted SCM and do-style updates test intervention propagation. "
            "Merely recovering or traversing the citation links tests provenance/dataflow "
            "memory; it is not by itself evidence of causal discovery."
        ),
    }


def audit_dataset(dataset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Integration-runner adapter containing both T0 and fitted T1 reports."""

    report = audit_t0(dataset)
    report["t1"] = audit_t1(dataset)
    return report


def _write_jsonl(path: Path, episodes: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for episode in episodes:
            handle.write(json.dumps(episode, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=120)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--audit", action="store_true", help="run and save T0 plus T1")
    args = parser.parse_args(argv)

    episodes = generate_episodes(args.episodes, seed=args.seed)
    _write_jsonl(args.out, episodes)
    summary: dict[str, Any] = {
        "task": TASK_NAME,
        "episodes": len(episodes),
        "seed": args.seed,
        "out": str(args.out),
    }
    if args.audit:
        audit = audit_dataset(episodes)
        audit_path = args.out.with_suffix(args.out.suffix + ".audit.json")
        audit_path.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary["audit_out"] = str(audit_path)
        summary["admission"] = audit["admission"]
        summary["exact_key_propagation_answer_accuracy"] = audit["baselines"][
            "exact_key"
        ]["propagation_episode_answer_accuracy"]
        summary["oracle_propagation_answer_accuracy"] = audit["baselines"][
            "oracle_propagation"
        ]["propagation_episode_answer_accuracy"]
        summary["t1_status"] = audit["t1"]["status"]
        if audit["t1"]["status"] == "complete":
            summary["supports_causal_learning_claim"] = audit["t1"]["admission"][
                "supports_causal_learning_claim"
            ]
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
