"""Deterministic dynamic-shopping prototype for causal-memory experiments.

This module intentionally does not import or modify the upstream MemoryArena
checkout.  It reuses the *idea* of a multi-item shopping episode while changing
the data-generating process: a terse event intervenes on an already-built cart,
and compatibility, budget, and policy dependencies determine which remembered
state must be inspected and repaired.

The observable query names only the intervention target.  The evaluator-owned
``gold`` section records the dependency graph, affected cells, required reads,
and counterfactual post-state.  This distinction is important: a flattened
state dictionary is convenient storage, but it is not evidence of causal
selection by itself.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Mapping

try:  # Package import in tests.
    from .common import (
        SCHEMA_VERSION,
        audit_predictions,
        changed_nodes,
        runtime_view,
        validate_episode,
    )
except ImportError:  # Direct execution: python code/causal_benchmarks/dynamic_shopping.py
    from common import (
        SCHEMA_VERSION,
        audit_predictions,
        changed_nodes,
        runtime_view,
        validate_episode,
    )


SLOTS = (
    "cpu",
    "motherboard",
    "memory",
    "cooler",
    "gpu",
    "case",
    "power_supply",
    "monitor",
    "keyboard",
)

CATALOG: dict[str, dict[str, Any]] = {
    "cpu_a": {"slot": "cpu", "price": 180.0, "socket": "AM4", "watts": 65},
    "cpu_b": {"slot": "cpu", "price": 230.0, "socket": "LGA1700", "watts": 125},
    # This entity is held out from train/dev interventions.  It shares the
    # AM4 mechanism but has a novel identifier and value in test.
    "cpu_nova_test": {
        "slot": "cpu",
        "price": 190.0,
        "socket": "AM4",
        "watts": 70,
    },
    "mb_a": {
        "slot": "motherboard",
        "price": 110.0,
        "socket": "AM4",
        "memory_gen": "DDR4",
        "form_factor": "ATX",
    },
    "mb_b": {
        "slot": "motherboard",
        "price": 150.0,
        "socket": "LGA1700",
        "memory_gen": "DDR5",
        "form_factor": "mATX",
    },
    "ram_4": {"slot": "memory", "price": 70.0, "memory_gen": "DDR4"},
    "ram_5": {"slot": "memory", "price": 100.0, "memory_gen": "DDR5"},
    "cooler_a": {"slot": "cooler", "price": 45.0, "sockets": ["AM4"], "height": 150},
    "cooler_b": {
        "slot": "cooler",
        "price": 65.0,
        "sockets": ["LGA1700"],
        "height": 165,
    },
    "gpu_compact": {
        "slot": "gpu",
        "price": 260.0,
        "watts": 160,
        "length": 240,
        "output": "HDMI",
    },
    "gpu_performance": {
        "slot": "gpu",
        "price": 380.0,
        "watts": 300,
        "length": 320,
        "output": "DisplayPort",
    },
    "case_roomy": {
        "slot": "case",
        "price": 120.0,
        "forms": ["ATX", "mATX"],
        "cooler_height": 175,
        "gpu_length": 340,
    },
    "case_small": {
        "slot": "case",
        "price": 75.0,
        "forms": ["mATX"],
        "cooler_height": 155,
        "gpu_length": 260,
    },
    "psu_550": {"slot": "power_supply", "price": 65.0, "capacity": 550},
    "psu_850": {"slot": "power_supply", "price": 110.0, "capacity": 850},
    "monitor_hdmi_value": {
        "slot": "monitor",
        "price": 110.0,
        "inputs": ["HDMI"],
        "tier": "value",
    },
    "monitor_hdmi_premium": {
        "slot": "monitor",
        "price": 250.0,
        "inputs": ["HDMI"],
        "tier": "premium",
    },
    "monitor_dp_value": {
        "slot": "monitor",
        "price": 120.0,
        "inputs": ["DisplayPort"],
        "tier": "value",
    },
    "monitor_dp_premium": {
        "slot": "monitor",
        "price": 230.0,
        "inputs": ["DisplayPort"],
        "tier": "premium",
    },
    "keyboard_ansi": {"slot": "keyboard", "price": 40.0, "layout": "ANSI"},
}

SCENARIOS = (
    "cpu_cancel",
    "gpu_cancel_strict",
    "gpu_cancel_adapters",
    "cpu_price_hard_cap",
    "cpu_price_flexible",
    "adapter_ban",
)

# The hard-cap CPU cancellation is a compositional regime combination absent
# from train/dev.  Test also contains the ordinary mechanisms under new values,
# entities, and surface templates.
TEST_SCENARIOS = (
    "cpu_cancel_hard_cap",
    *SCENARIOS,
)


def _round_money(value: float) -> float:
    return round(float(value) + 1e-9, 2)


def _items_for_slot(slot: str) -> list[str]:
    return sorted(
        (item_id for item_id, item in CATALOG.items() if item["slot"] == slot),
        key=lambda item_id: (CATALOG[item_id]["price"], item_id),
    )


def _initial_cart(
    performance_gpu: bool = False, cpu_id: str = "cpu_a"
) -> dict[str, str]:
    return {
        "cpu": cpu_id,
        "motherboard": "mb_a",
        "memory": "ram_4",
        "cooler": "cooler_a",
        "gpu": "gpu_performance" if performance_gpu else "gpu_compact",
        "case": "case_roomy",
        "power_supply": "psu_850" if performance_gpu else "psu_550",
        "monitor": "monitor_hdmi_premium",
        "keyboard": "keyboard_ansi",
    }


def _make_state(
    scenario: str, region: str, novel_cpu_entity: bool = False
) -> dict[str, Any]:
    performance_gpu = scenario == "adapter_ban"
    cpu_id = "cpu_nova_test" if novel_cpu_entity else "cpu_a"
    cart = _initial_cart(performance_gpu=performance_gpu, cpu_id=cpu_id)
    state: dict[str, Any] = {
        f"cart.{slot}": item_id for slot, item_id in cart.items()
    }
    for item_id in CATALOG:
        state[f"availability.{item_id}"] = True
    if novel_cpu_entity:
        # Otherwise the deterministic cheapest replacement would be CPU-A and
        # the novel cancellation would not exercise the socket propagation.
        state["availability.cpu_a"] = False
    else:
        # The held-out entity is absent, rather than merely false, so train/dev
        # runtime state never exposes its identifier.
        state.pop("availability.cpu_nova_test")
    for slot, item_id in cart.items():
        state[f"price.{slot}"] = CATALOG[item_id]["price"]

    state["policy.display_mode"] = (
        "adapters_allowed"
        if scenario in {"gpu_cancel_adapters", "adapter_ban"}
        else "strict"
    )
    state["policy.budget_mode"] = (
        "hard_cap"
        if scenario in {"cpu_price_hard_cap", "cpu_cancel_hard_cap"}
        else "flexible"
    )
    if scenario == "cpu_price_flexible":
        state["policy.budget_mode"] = "flexible"
    state["constraint.max_total"] = (
        1200.0
        if scenario
        in {"cpu_price_hard_cap", "cpu_price_flexible", "cpu_cancel_hard_cap"}
        else 1500.0
    )
    state["account.shipping_region"] = region
    state["account.gift_message"] = "Happy building!"
    _update_ledger(state)
    return state


def _update_ledger(state: dict[str, Any]) -> None:
    subtotal = sum(float(state[f"price.{slot}"]) for slot in SLOTS if slot != "monitor")
    total = subtotal + float(state["price.monitor"])
    state["ledger.subtotal_before_monitor"] = _round_money(subtotal)
    state["ledger.total_spend"] = _round_money(total)
    state["ledger.remaining_budget"] = _round_money(
        float(state["constraint.max_total"]) - total
    )


def _available(state: Mapping[str, Any], item_id: str) -> bool:
    return bool(state.get(f"availability.{item_id}", False))


def _valid(state: Mapping[str, Any], slot: str, item_id: str) -> bool:
    item = CATALOG[item_id]
    cart = {name: CATALOG[str(state[f"cart.{name}"])] for name in SLOTS}
    if slot == "motherboard":
        return item["socket"] == cart["cpu"]["socket"]
    if slot == "memory":
        return item["memory_gen"] == cart["motherboard"]["memory_gen"]
    if slot == "cooler":
        return cart["cpu"]["socket"] in item["sockets"]
    if slot == "case":
        return (
            cart["motherboard"]["form_factor"] in item["forms"]
            and cart["cooler"]["height"] <= item["cooler_height"]
            and cart["gpu"]["length"] <= item["gpu_length"]
        )
    if slot == "power_supply":
        required = cart["cpu"]["watts"] + cart["gpu"]["watts"] + 120
        return item["capacity"] >= required
    if slot == "monitor":
        if state["policy.display_mode"] == "adapters_allowed":
            return True
        return cart["gpu"]["output"] in item["inputs"]
    return True


def _choose(state: Mapping[str, Any], slot: str) -> str:
    candidates = [
        item_id
        for item_id in _items_for_slot(slot)
        if _available(state, item_id) and _valid(state, slot, item_id)
    ]
    if not candidates:
        raise RuntimeError(f"no available compatible candidate for {slot}")
    return candidates[0]


def _availability_keys_for_slot(
    state: Mapping[str, Any], slot: str
) -> list[str]:
    """Return the runtime availability cells consulted by a slot scan.

    The held-out CPU is intentionally absent from train/dev state, so deriving
    this list from ``state`` also prevents a catalog scan from revealing that
    test-only entity early.
    """

    return [
        f"availability.{item_id}"
        for item_id in _items_for_slot(slot)
        if f"availability.{item_id}" in state
    ]


def _set_cart_item(state: dict[str, Any], slot: str, item_id: str) -> None:
    state[f"cart.{slot}"] = item_id
    state[f"price.{slot}"] = CATALOG[item_id]["price"]


def _repair_if_invalid(state: dict[str, Any], slot: str) -> bool:
    current = str(state[f"cart.{slot}"])
    if _available(state, current) and _valid(state, slot, current):
        return False
    replacement = _choose(state, slot)
    _set_cart_item(state, slot, replacement)
    return replacement != current


def simulate(
    memory_state: Mapping[str, Any], intervention: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    """Apply one event and deterministically propagate cart constraints.

    Returns ``(post_state, required_reads, tool_queries)``.  Required reads are
    prior memory cells consulted by the repair policy; candidate product facts
    are separately represented as catalog tool queries.
    """

    before = copy.deepcopy(dict(memory_state))
    state = copy.deepcopy(before)
    target = str(intervention["node"])
    state[target] = intervention["new_value"]
    reads: set[str] = {target}
    tool_queries: list[dict[str, Any]] = []

    root_slot: str | None = None
    if target.startswith("availability.") and intervention["new_value"] is False:
        unavailable_id = target.split(".", 1)[1]
        root_slot = str(CATALOG[unavailable_id]["slot"])
        reads.add(f"cart.{root_slot}")
        if state[f"cart.{root_slot}"] == unavailable_id:
            reads.update(_availability_keys_for_slot(state, root_slot))
            tool_queries.append({"slot": root_slot, "constraint": "available replacement"})
            _set_cart_item(state, root_slot, _choose(state, root_slot))

    # A changed root or display policy can invalidate downstream items.  The
    # order is a topological order of the compatibility graph.
    if root_slot in {"cpu", "gpu"} or target == "policy.display_mode":
        repair_order = (
            ("motherboard", "memory", "cooler", "case", "power_supply", "monitor")
            if root_slot == "cpu"
            else ("case", "power_supply", "monitor")
            if root_slot == "gpu"
            else ("monitor",)
        )
        dependency_reads = {
            "motherboard": ["cart.cpu", "cart.motherboard"],
            "memory": ["cart.motherboard", "cart.memory"],
            "cooler": ["cart.cpu", "cart.cooler"],
            "case": ["cart.motherboard", "cart.cooler", "cart.gpu", "cart.case"],
            "power_supply": ["cart.cpu", "cart.gpu", "cart.power_supply"],
            "monitor": ["policy.display_mode", "cart.gpu", "cart.monitor"],
        }
        for slot in repair_order:
            reads.update(dependency_reads[slot])
            old = state[f"cart.{slot}"]
            # ``_repair_if_invalid`` first checks the current item's runtime
            # availability.  If it repairs the slot, ``_choose`` scans every
            # candidate availability cell; record both operations explicitly.
            reads.add(f"availability.{old}")
            if _repair_if_invalid(state, slot):
                reads.update(_availability_keys_for_slot(state, slot))
                tool_queries.append(
                    {"slot": slot, "constraint": "compatible", "replaces": old}
                )

    # All interventions can alter the ledger.  A hard budget has a gated edge
    # from the pre-monitor subtotal to the monitor choice; flexible budgets do
    # not propagate back into product selection.
    reads.update(f"price.{slot}" for slot in SLOTS)
    reads.update({"constraint.max_total", "policy.budget_mode"})
    _update_ledger(state)
    if (
        state["policy.budget_mode"] == "hard_cap"
        and state["ledger.total_spend"] > state["constraint.max_total"]
    ):
        reads.update({"cart.gpu", "cart.monitor", "policy.display_mode"})
        old_monitor = state["cart.monitor"]
        reads.update(_availability_keys_for_slot(state, "monitor"))
        replacement = _choose(state, "monitor")
        if replacement != old_monitor:
            _set_cart_item(state, "monitor", replacement)
            tool_queries.append(
                {
                    "slot": "monitor",
                    "constraint": "cheapest compatible item under hard budget",
                    "replaces": old_monitor,
                }
            )
        _update_ledger(state)
    return state, sorted(reads), tool_queries


def _edge(source: str, target: str, condition: str = "always") -> dict[str, str]:
    return {"source": source, "target": target, "condition": condition}


def dependency_graph(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return the auditable potential graph used by the simulator."""

    edges = [
        _edge("availability.cpu_a", "cart.cpu"),
        _edge("availability.cpu_b", "cart.cpu"),
        _edge("availability.gpu_compact", "cart.gpu"),
        _edge("availability.gpu_performance", "cart.gpu"),
        _edge("cart.cpu", "cart.motherboard"),
        _edge("cart.cpu", "cart.cooler"),
        _edge("cart.cpu", "cart.power_supply"),
        _edge("cart.motherboard", "cart.memory"),
        _edge("cart.motherboard", "cart.case"),
        _edge("cart.cooler", "cart.case"),
        _edge("cart.gpu", "cart.case"),
        _edge("cart.gpu", "cart.power_supply"),
        _edge("cart.gpu", "cart.monitor", "display_mode=strict"),
        _edge("policy.display_mode", "cart.monitor"),
        _edge("ledger.subtotal_before_monitor", "cart.monitor", "budget_mode=hard_cap"),
    ]
    if "availability.cpu_nova_test" in state:
        edges.append(_edge("availability.cpu_nova_test", "cart.cpu"))
    for slot in SLOTS:
        edges.append(_edge(f"cart.{slot}", f"price.{slot}"))
        if slot == "monitor":
            edges.append(_edge("price.monitor", "ledger.total_spend"))
        else:
            edges.append(_edge(f"price.{slot}", "ledger.subtotal_before_monitor"))
    edges.extend(
        [
            _edge("constraint.max_total", "ledger.remaining_budget"),
            _edge("ledger.subtotal_before_monitor", "ledger.total_spend"),
            _edge("ledger.total_spend", "ledger.remaining_budget"),
            _edge("policy.budget_mode", "cart.monitor", "budget_mode=hard_cap"),
        ]
    )
    return {
        "nodes": sorted(state),
        "edges": edges,
        "regime_variables": ["policy.display_mode", "policy.budget_mode"],
    }


def _condition_active(condition: str, state: Mapping[str, Any]) -> bool:
    if condition == "always":
        return True
    if condition == "display_mode=strict":
        return state["policy.display_mode"] == "strict"
    if condition == "budget_mode=hard_cap":
        return state["policy.budget_mode"] == "hard_cap"
    raise ValueError(f"unknown edge condition: {condition}")


def _active_edges(graph: Mapping[str, Any], state: Mapping[str, Any]) -> list[dict[str, str]]:
    return [edge for edge in graph["edges"] if _condition_active(edge["condition"], state)]


def _shortest_paths(
    source: str, affected: Iterable[str], edges: Iterable[Mapping[str, str]]
) -> list[list[str]]:
    children: dict[str, list[str]] = {}
    for edge in edges:
        children.setdefault(edge["source"], []).append(edge["target"])
    parent: dict[str, str | None] = {source: None}
    queue: deque[str] = deque([source])
    while queue:
        node = queue.popleft()
        for child in sorted(children.get(node, [])):
            if child not in parent:
                parent[child] = node
                queue.append(child)
    paths: list[list[str]] = []
    for target in sorted(set(affected) - {source}):
        if target not in parent:
            continue
        path = [target]
        while path[-1] != source:
            path.append(str(parent[path[-1]]))
        paths.append(list(reversed(path)))
    return paths


def _query_template(
    split: str, kind: str, entity: str, value: Any, variant: int
) -> tuple[str, str]:
    """Return a split-exclusive surface template and its auditable identifier."""

    templates = {
        "train": {
            "cancellation": [
                "The retailer cancelled {entity} from this order. Repair the "
                "order using the existing requirements.",
                "A cancellation notice says {entity} is unavailable. Bring "
                "the saved order back into compliance.",
            ],
            "price_change": [
                "The retailer corrected the CPU-A line price to ${value:.2f}. "
                "Update the existing order.",
                "CPU-A now costs ${value:.2f}. Reconcile the saved order.",
            ],
            "policy_change": [
                "The customer no longer allows display adapters. Apply this "
                "policy to the existing order.",
                "External display adapters are now forbidden. Reconcile the saved order.",
            ],
        },
        "dev": {
            "cancellation": [
                "Remove the retailer-cancelled {entity} and make the prior order valid again."
            ],
            "price_change": [
                "Reprice CPU-A at ${value:.2f}, then make the prior order valid again."
            ],
            "policy_change": [
                "Enforce the new no-adapter rule across the saved order."
            ],
        },
        "test": {
            "cancellation": [
                "A fulfilment alert voided {entity}; reconcile the previously saved build."
            ],
            "price_change": [
                "A billing audit sets CPU-A to ${value:.2f}; reconcile the previously saved build."
            ],
            "policy_change": [
                "The revised build policy disallows adapters; reconcile the previously saved build."
            ],
        },
    }
    choices = templates[split][kind]
    template_index = variant % len(choices)
    template_id = f"{split}:{kind}:{template_index}"
    numeric_value = float(value) if isinstance(value, (int, float)) else 0.0
    return choices[template_index].format(entity=entity, value=numeric_value), template_id


def _scenario_intervention(
    scenario: str,
    split: str = "test",
    variant: int = 0,
    novel_cpu_entity: bool = False,
) -> tuple[dict[str, Any], str, str, bool]:
    if scenario in {"cpu_cancel", "cpu_cancel_hard_cap"}:
        entity_id = "cpu_nova_test" if novel_cpu_entity else "cpu_a"
        entity_name = "CPU-Nova" if novel_cpu_entity else "CPU-A"
        text, template_id = _query_template(
            split, "cancellation", entity_name, None, variant
        )
        return (
            {
                "event_type": "cancellation",
                "target": f"availability.{entity_id}",
                "value": False,
            },
            text,
            template_id,
            False,
        )
    if scenario in {"gpu_cancel_strict", "gpu_cancel_adapters"}:
        text, template_id = _query_template(
            split, "cancellation", "GPU-Compact", None, variant
        )
        return (
            {
                "event_type": "cancellation",
                "target": "availability.gpu_compact",
                "value": False,
            },
            text,
            template_id,
            False,
        )
    if scenario in {"cpu_price_hard_cap", "cpu_price_flexible"}:
        price = (
            340.0 + 20.0 * (variant % 3)
            if split == "train"
            else 405.0 + 5.0 * (variant % 2)
            if split == "dev"
            else 427.0 + 7.0 * (variant % 3)
        )
        text, template_id = _query_template(
            split, "price_change", "CPU-A", price, variant
        )
        return (
            {"event_type": "price_change", "target": "price.cpu", "value": price},
            text,
            template_id,
            split == "test",
        )
    if scenario == "adapter_ban":
        text, template_id = _query_template(
            split, "policy_change", "display adapters", "strict", variant
        )
        return (
            {
                "event_type": "policy_change",
                "target": "policy.display_mode",
                "value": "strict",
            },
            text,
            template_id,
            False,
        )
    raise ValueError(f"unknown scenario: {scenario}")


def _history_from_state(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = [
        {
            "turn": 0,
            "event": "constraints_saved",
            "max_total": state["constraint.max_total"],
            "budget_mode": state["policy.budget_mode"],
            "display_mode": state["policy.display_mode"],
        }
    ]
    for turn, slot in enumerate(SLOTS, start=1):
        history.append(
            {
                "turn": turn,
                "event": "item_added",
                "slot": slot,
                "product_id": state[f"cart.{slot}"],
                "paid": state[f"price.{slot}"],
            }
        )
    return history


def generate_episode(
    seed: int,
    index: int,
    scenario: str,
    split: str = "test",
    split_local_index: int | None = None,
) -> dict[str, Any]:
    rng = random.Random((seed + 1) * 1_000_003 + index)
    local_index = index if split_local_index is None else split_local_index
    region_pools = {
        "train": ["Hangzhou", "Shanghai"],
        "dev": ["Shenzhen"],
        "test": ["Chengdu", "Wuhan"],
    }
    region = rng.choice(region_pools[split])
    novel_cpu_entity = split == "test" and scenario in {
        "cpu_cancel",
        "cpu_cancel_hard_cap",
    }
    memory_state = _make_state(
        scenario, region, novel_cpu_entity=novel_cpu_entity
    )
    intervention, query_text, template_id, novel_value = _scenario_intervention(
        scenario,
        split=split,
        variant=local_index,
        novel_cpu_entity=novel_cpu_entity,
    )
    intervention = {
        "node": intervention["target"],
        "old_value": memory_state[intervention["target"]],
        "new_value": intervention["value"],
        "kind": intervention["event_type"],
    }
    post_state, required_reads, tool_queries = simulate(memory_state, intervention)
    affected = changed_nodes(memory_state, post_state)
    graph = dependency_graph(memory_state)
    # The post-intervention policy determines whether a gated display edge is
    # active; the pre-intervention budget regime determines its budget edge.
    regime_state = dict(memory_state)
    regime_state[intervention["node"]] = intervention["new_value"]
    active_edges = _active_edges(graph, regime_state)
    paths = _shortest_paths(intervention["node"], affected, active_edges)
    affected_state = {
        node: {"before": memory_state.get(node), "after": post_state.get(node)}
        for node in affected
    }
    episode = {
        "schema_version": SCHEMA_VERSION,
        "task": "dynamic_shopping",
        "episode_id": f"dynamic-shopping-s{seed:04d}-e{index:05d}",
        "split": split,
        "history": _history_from_state(memory_state),
        "memory_state": memory_state,
        "query": {
            "text": query_text,
            "intervention": intervention,
            # This is an auditable annotation of what the current query reveals,
            # not a downstream hint.
            "explicit_state_keys": [intervention["node"]],
        },
        "metadata": {
            "catalog_version": "synthetic-pc-cart/v1",
        },
        "gold": {
            "graph": graph,
            "active_edges": active_edges,
            "affected_nodes": affected,
            "affected_state": affected_state,
            "required_reads": required_reads,
            "required_tool_queries": tool_queries,
            "propagation_paths": paths,
            "post_state": post_state,
            "audit_annotations": {
                "scenario": scenario,
                "seed": seed,
                "index": index,
                "template_id": template_id,
                "novel_test_factors": {
                    "unseen_template": split == "test",
                    "unseen_entity": novel_cpu_entity,
                    "unseen_value": split == "test" and novel_value,
                    "heldout_regime_combination": (
                        split == "test" and scenario == "cpu_cancel_hard_cap"
                    ),
                },
                "negative_control_keys": [
                    "cart.keyboard",
                    "account.shipping_region",
                    "account.gift_message",
                ],
            },
        },
    }
    if split == "train":
        # This is a past, runtime-visible outcome used for T1 learning.  It has
        # no graph, affected-node list, or evaluator annotation.
        episode["observed_transition"] = {
            "pre_state": copy.deepcopy(memory_state),
            "intervention": copy.deepcopy(intervention),
            "post_state": copy.deepcopy(post_state),
        }
    validate_episode(episode)
    return episode


def generate_episodes(episodes: int = 24, seed: int = 7) -> list[dict[str, Any]]:
    if episodes <= 0:
        raise ValueError("episodes must be positive")
    rng = random.Random(seed)
    if episodes >= 24:
        train_count = max(len(SCENARIOS), int(episodes * 0.5))
        dev_count = max(1, int(episodes * 0.2))
        test_count = episodes - train_count - dev_count
        if test_count < len(TEST_SCENARIOS):
            shortage = len(TEST_SCENARIOS) - test_count
            train_count -= shortage
            test_count += shortage
        split_counts = {"train": train_count, "dev": dev_count, "test": test_count}
    elif episodes >= 12:
        split_counts = {"train": 6, "dev": 0, "test": episodes - 6}
    else:
        small_train = max(1, episodes // 2)
        split_counts = {
            "train": small_train,
            "dev": 0,
            "test": episodes - small_train,
        }

    def balanced(names: tuple[str, ...], count: int) -> list[str]:
        schedule: list[str] = []
        while len(schedule) < count:
            block = list(names)
            rng.shuffle(block)
            schedule.extend(block)
        return schedule[:count]

    generated: list[dict[str, Any]] = []
    global_index = 0
    for split in ("train", "dev", "test"):
        count = split_counts[split]
        names = TEST_SCENARIOS if split == "test" else SCENARIOS
        scenarios = balanced(names, count)
        # Ensure the held-out compositional regime is actually represented even
        # in small test partitions.
        if split == "test" and count and "cpu_cancel_hard_cap" not in scenarios:
            scenarios[0] = "cpu_cancel_hard_cap"
        for local_index, scenario in enumerate(scenarios):
            generated.append(
                generate_episode(
                    seed=seed,
                    index=global_index,
                    scenario=scenario,
                    split=split,
                    split_local_index=local_index,
                )
            )
            global_index += 1
    return generated


def generate_dataset(episodes: int = 24, seed: int = 7) -> list[dict[str, Any]]:
    """Cross-task runner entry point (thin alias for :func:`generate_episodes`)."""

    return generate_episodes(episodes=episodes, seed=seed)


def exact_key_baseline(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Apply only the state cell explicitly named by the current query."""

    state = copy.deepcopy(dict(episode["memory_state"]))
    intervention = episode["query"]["intervention"]
    target = str(intervention["node"])
    state[target] = intervention["new_value"]
    return {
        "episode_id": episode["episode_id"],
        "affected_nodes": changed_nodes(episode["memory_state"], state),
        "post_state": state,
    }


def oracle_propagation_baseline(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Use the known simulator rules, without reading evaluator gold."""

    state, _, _ = simulate(episode["memory_state"], episode["query"]["intervention"])
    return {
        "episode_id": episode["episode_id"],
        "affected_nodes": changed_nodes(episode["memory_state"], state),
        "post_state": state,
    }


def _intervention_signature(
    pre_state: Mapping[str, Any], intervention: Mapping[str, Any]
) -> tuple[str, ...]:
    """Abstract away concrete values/entities while retaining learned regimes."""

    node = str(intervention["node"])
    kind = str(intervention["kind"])
    if node.startswith("availability."):
        entity_id = node.split(".", 1)[1]
        slot = str(CATALOG[entity_id]["slot"])
        signature = [kind, "availability", slot]
        if slot == "gpu":
            signature.append(f"display={pre_state['policy.display_mode']}")
        # CPU cancellation deliberately omits budget_mode.  T1 evaluates
        # whether the independently learned hard-budget residual composes with
        # this mechanism in a held-out test combination.
        return tuple(signature)
    if node.startswith("price."):
        slot = node.split(".", 1)[1]
        return (kind, "price", slot, f"budget={pre_state['policy.budget_mode']}")
    if node == "policy.display_mode":
        return (kind, "policy", "display_mode")
    return (kind, "node", node)


def _impact_template(node: str, intervention_node: str) -> str:
    return "$target" if node == intervention_node else node


class ObservedImpactSelector:
    """Learn intervention-to-impact patterns only from observed train outcomes.

    This is an intentionally simple frequency learner, not GRACE.  Its purpose
    is to make the T1 information boundary executable: it consumes completed
    runtime transitions and never consumes evaluator graphs or affected-node
    labels.  It learns regime-specific impact templates and a compositional
    hard-budget residual.
    """

    def __init__(self) -> None:
        self.patterns: dict[tuple[str, ...], tuple[str, ...]] = {}
        self.hard_budget_extras: tuple[str, ...] = ()
        self.fit_audit: dict[str, Any] = {}

    def fit(self, training_views: Iterable[Mapping[str, Any]]) -> "ObservedImpactSelector":
        views = list(training_views)
        pattern_counts: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
        pattern_totals: Counter[tuple[str, ...]] = Counter()
        budget_counts: dict[str, Counter[str]] = {
            "hard_cap": Counter(),
            "flexible": Counter(),
        }
        budget_totals: Counter[str] = Counter()

        for view in views:
            if "gold" in view:
                raise ValueError("learner input must be a runtime_view without gold")
            if view.get("split") != "train":
                raise ValueError("learner may fit only train split transitions")
            transition = view.get("observed_transition")
            if not isinstance(transition, Mapping):
                raise ValueError("train runtime_view is missing observed_transition")
            if set(transition) != {"pre_state", "intervention", "post_state"}:
                raise ValueError("observed_transition contains non-runtime supervision")
            pre = transition["pre_state"]
            post = transition["post_state"]
            intervention = transition["intervention"]
            signature = _intervention_signature(pre, intervention)
            changed = changed_nodes(pre, post)
            templates = {
                _impact_template(node, str(intervention["node"])) for node in changed
            }
            pattern_totals[signature] += 1
            pattern_counts[signature].update(templates)

            if signature[:3] == ("price_change", "price", "cpu"):
                regime = str(pre["policy.budget_mode"])
                budget_totals[regime] += 1
                budget_counts[regime].update(templates)

        if not views:
            raise ValueError("at least one train transition is required")
        self.patterns = {
            signature: tuple(
                sorted(
                    node
                    for node, count in counts.items()
                    if count / pattern_totals[signature] >= 0.5
                )
            )
            for signature, counts in pattern_counts.items()
        }

        def stable_budget_pattern(regime: str) -> set[str]:
            total = budget_totals[regime]
            if not total:
                return set()
            return {
                node
                for node, count in budget_counts[regime].items()
                if count / total >= 0.5
            }

        self.hard_budget_extras = tuple(
            sorted(stable_budget_pattern("hard_cap") - stable_budget_pattern("flexible"))
        )
        self.fit_audit = {
            "train_transitions": len(views),
            "runtime_records_with_gold": sum("gold" in view for view in views),
            "learned_signatures": len(self.patterns),
            "hard_budget_extras": list(self.hard_budget_extras),
        }
        return self

    def predict_affected(self, runtime_record: Mapping[str, Any]) -> list[str]:
        if "gold" in runtime_record or "observed_transition" in runtime_record:
            raise ValueError("prediction accepts test-time runtime_view only")
        pre = runtime_record["memory_state"]
        intervention = runtime_record["query"]["intervention"]
        signature = _intervention_signature(pre, intervention)
        if signature not in self.patterns:
            raise KeyError(f"unseen intervention mechanism: {signature}")
        target = str(intervention["node"])
        predicted = {
            target if node == "$target" else node for node in self.patterns[signature]
        }
        if pre["policy.budget_mode"] == "hard_cap":
            predicted.update(self.hard_budget_extras)
        return sorted(node for node in predicted if node in pre)

    def learned_dependency_summary(self) -> dict[str, Any]:
        """Serializable impact templates learned without evaluator graph access."""

        return {
            "signature_impacts": {
                "|".join(signature): list(nodes)
                for signature, nodes in sorted(self.patterns.items())
            },
            "hard_budget_extras": list(self.hard_budget_extras),
        }


def fit_learned_selector(
    training_views: Iterable[Mapping[str, Any]],
) -> ObservedImpactSelector:
    return ObservedImpactSelector().fit(training_views)


def _selection(
    name: str, predicted: Iterable[str], selected: Iterable[str]
) -> dict[str, Any]:
    return {
        "arm": name,
        "predicted_affected_nodes": sorted(set(predicted)),
        "selected_cells": sorted(set(selected)),
    }


def exact_key_selection(runtime_record: Mapping[str, Any]) -> dict[str, Any]:
    target = str(runtime_record["query"]["intervention"]["node"])
    return _selection("exact_kv", [target], [target])


def domain_solver_selection(runtime_record: Mapping[str, Any]) -> dict[str, Any]:
    """Strong hand-coded compatibility/budget solver using runtime state only."""

    state, required_reads, _ = simulate(
        runtime_record["memory_state"], runtime_record["query"]["intervention"]
    )
    affected = changed_nodes(runtime_record["memory_state"], state)
    return _selection(
        "domain_solver", affected, set(required_reads) | set(affected)
    )


def learned_graph_selection(
    runtime_record: Mapping[str, Any], learner: ObservedImpactSelector
) -> dict[str, Any]:
    affected = learner.predict_affected(runtime_record)
    return _selection("learned_graph", affected, affected)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def matched_retrieval_selection(
    runtime_record: Mapping[str, Any], budget: int
) -> dict[str, Any]:
    """Lexical/structured retrieval with exactly the learned arm's cell budget."""

    state = runtime_record["memory_state"]
    query = runtime_record["query"]
    intervention = query["intervention"]
    query_text = " ".join(
        [
            str(query["text"]),
            str(intervention["node"]),
            str(intervention["kind"]),
            json.dumps(intervention["new_value"]),
        ]
    )
    query_tokens = _tokens(query_text)
    target_tokens = _tokens(str(intervention["node"]))
    ranked: list[tuple[float, str]] = []
    for key, value in state.items():
        cell_tokens = _tokens(f"{key} {json.dumps(value, ensure_ascii=False)}")
        overlap = len(query_tokens & cell_tokens)
        target_overlap = len(target_tokens & _tokens(key))
        same_namespace = int(key.split(".", 1)[0] == str(intervention["node"]).split(".", 1)[0])
        score = 3.0 * target_overlap + float(overlap) + 0.25 * same_namespace
        ranked.append((score, key))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    selected = [key for _, key in ranked[: min(max(1, budget), len(ranked))]]
    return _selection("matched_retrieval", selected, selected)


def oracle_graph_selection(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluator-only reachability over the gold active graph (not gold impacts)."""

    target = str(episode["query"]["intervention"]["node"])
    children: dict[str, list[str]] = defaultdict(list)
    for edge in episode["gold"]["active_edges"]:
        children[str(edge["source"])].append(str(edge["target"]))
    reached = {target}
    queue: deque[str] = deque([target])
    while queue:
        node = queue.popleft()
        for child in children.get(node, []):
            if child not in reached:
                reached.add(child)
                queue.append(child)
    reached &= set(episode["memory_state"])
    return _selection("oracle_graph", reached, reached)


def full_state_history_selection(runtime_record: Mapping[str, Any]) -> dict[str, Any]:
    cells = sorted(runtime_record["memory_state"])
    return _selection("full_state_history", cells, cells)


def shared_oracle_value_decoder(
    episode: Mapping[str, Any], predicted_nodes: Iterable[str]
) -> dict[str, Any]:
    """Evaluator-only value oracle shared by every T1 selection arm.

    It writes the evaluator's counterfactual value only for nodes named by the
    selector.  Consequently task success isolates affected-node recall; this is
    deliberately *not* an end-to-end planning result.
    """

    state = copy.deepcopy(dict(episode["memory_state"]))
    for node in set(predicted_nodes):
        if node in episode["gold"]["post_state"]:
            state[node] = episode["gold"]["post_state"][node]
    return state


def _serialize_selection(
    runtime_record: Mapping[str, Any], selected_cells: Iterable[str], mode: str
) -> str:
    selected = sorted(set(selected_cells))
    state = runtime_record["memory_state"]
    if mode == "compact":
        payload: Any = {
            "query": runtime_record["query"]["text"],
            "state": {key: state[key] for key in selected},
        }
    elif mode == "verbose":
        selected_slots = {
            key.split(".", 1)[1]
            for key in selected
            if key.startswith(("cart.", "price."))
        }
        history_evidence = [
            event
            for event in runtime_record["history"]
            if event.get("slot") in selected_slots
            or (
                event.get("event") == "constraints_saved"
                and any(
                    key.startswith(("policy.", "constraint.", "ledger."))
                    for key in selected
                )
            )
        ]
        payload = {
            "query": runtime_record["query"],
            "selected_memory_records": [
                {
                    "state_key": key,
                    "current_value": state[key],
                    "source": "materialized_memory",
                }
                for key in selected
            ],
            "redundant_history_evidence": history_evidence,
        }
    else:
        raise ValueError(f"unknown serialization mode: {mode}")
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2 if mode == "verbose" else None,
    )


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _score_t1_arm(
    episodes: list[Mapping[str, Any]],
    runtime_records: list[Mapping[str, Any]],
    selections: list[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for episode, runtime_record, selection in zip(episodes, runtime_records, selections):
        expected = set(episode["gold"]["affected_nodes"])
        predicted = set(selection["predicted_affected_nodes"])
        selected = set(selection["selected_cells"])
        tp = len(expected & predicted)
        precision = tp / len(predicted) if predicted else 1.0
        recall = tp / len(expected) if expected else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        controls = set(
            episode["gold"]["audit_annotations"]["negative_control_keys"]
        )
        unaffected = set(episode["memory_state"]) - expected
        decoded = shared_oracle_value_decoder(episode, predicted)
        serializations: dict[str, dict[str, int]] = {}
        for mode in ("compact", "verbose"):
            text = _serialize_selection(runtime_record, selected, mode)
            serializations[mode] = {
                "characters": len(text),
                "token_proxy_chars_div_4": (len(text) + 3) // 4,
            }
        required = set(episode["gold"]["required_reads"])
        rows.append(
            {
                "episode_id": episode["episode_id"],
                "affected_precision": precision,
                "affected_recall": recall,
                "affected_f1": f1,
                "negative_control_specificity": (
                    len(controls - predicted) / len(controls) if controls else 1.0
                ),
                "unaffected_specificity": (
                    len(unaffected - predicted) / len(unaffected) if unaffected else 1.0
                ),
                "required_read_recall": (
                    len(required & selected) / len(required) if required else 1.0
                ),
                "selected_cells": len(selected),
                "task_success": decoded == episode["gold"]["post_state"],
                "serialization": serializations,
            }
        )
    return {
        "episodes": len(rows),
        "affected_precision": _mean(row["affected_precision"] for row in rows),
        "affected_recall": _mean(row["affected_recall"] for row in rows),
        "affected_f1": _mean(row["affected_f1"] for row in rows),
        "negative_control_specificity": _mean(
            row["negative_control_specificity"] for row in rows
        ),
        "unaffected_specificity": _mean(row["unaffected_specificity"] for row in rows),
        "required_read_recall": _mean(row["required_read_recall"] for row in rows),
        "selected_cells": _mean(row["selected_cells"] for row in rows),
        "task_success": _mean(float(row["task_success"]) for row in rows),
        "serialization": {
            mode: {
                "characters": _mean(
                    row["serialization"][mode]["characters"] for row in rows
                ),
                "token_proxy_chars_div_4": _mean(
                    row["serialization"][mode]["token_proxy_chars_div_4"]
                    for row in rows
                ),
            }
            for mode in ("compact", "verbose")
        },
        "per_episode": rows,
    }


def run_t1_experiment(dataset: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Fit on runtime-visible train outcomes and evaluate six arms on test."""

    dataset = list(dataset)
    train = [episode for episode in dataset if episode["split"] == "train"]
    dev_test = [episode for episode in dataset if episode["split"] != "train"]
    test = [episode for episode in dataset if episode["split"] == "test"]
    if not train or not test:
        raise ValueError("T1 requires non-empty train and test splits")
    train_views = [runtime_view(episode, training=True) for episode in train]
    test_views = [runtime_view(episode, training=False) for episode in test]
    learner = fit_learned_selector(train_views)

    selections_by_arm: dict[str, list[dict[str, Any]]] = {
        "exact_kv": [],
        "domain_solver": [],
        "matched_retrieval": [],
        "learned_graph": [],
        "oracle_graph": [],
        "full_state_history": [],
    }
    for episode, view in zip(test, test_views):
        learned = learned_graph_selection(view, learner)
        selections_by_arm["exact_kv"].append(exact_key_selection(view))
        selections_by_arm["domain_solver"].append(domain_solver_selection(view))
        selections_by_arm["learned_graph"].append(learned)
        selections_by_arm["matched_retrieval"].append(
            matched_retrieval_selection(view, len(learned["selected_cells"]))
        )
        selections_by_arm["oracle_graph"].append(oracle_graph_selection(episode))
        selections_by_arm["full_state_history"].append(
            full_state_history_selection(view)
        )

    arms = {
        name: _score_t1_arm(test, test_views, selections)
        for name, selections in selections_by_arm.items()
    }
    train_templates = {
        episode["gold"]["audit_annotations"]["template_id"] for episode in train
    }
    test_templates = {
        episode["gold"]["audit_annotations"]["template_id"] for episode in test
    }
    raw_dev_test_transition_leaks = sum(
        "observed_transition" in episode for episode in dev_test
    )
    runtime_dev_test_post_leaks = sum(
        "observed_transition" in runtime_view(episode, training=True)
        for episode in dev_test
    )
    heldout = [
        episode
        for episode in test
        if episode["gold"]["audit_annotations"]["novel_test_factors"][
            "heldout_regime_combination"
        ]
    ]
    learned = arms["learned_graph"]
    domain = arms["domain_solver"]
    report = {
        "benchmark": "dynamic_shopping",
        "stage": "T1_selection",
        "splits": {
            "train": len(train),
            "dev": sum(episode["split"] == "dev" for episode in dataset),
            "test": len(test),
        },
        "learner": {
            **learner.fit_audit,
            "model": learner.learned_dependency_summary(),
        },
        "leakage_audit": {
            "train_runtime_views_with_gold": sum("gold" in view for view in train_views),
            "test_runtime_views_with_gold": sum("gold" in view for view in test_views),
            "raw_dev_test_observed_transition_leaks": raw_dev_test_transition_leaks,
            "runtime_dev_test_post_state_leaks": runtime_dev_test_post_leaks,
            "episode_id_overlap": len(
                {episode["episode_id"] for episode in train}
                & {episode["episode_id"] for episode in test}
            ),
        },
        "novel_test": {
            "template_vocab_overlap": len(train_templates & test_templates),
            "unseen_template_episodes": sum(
                episode["gold"]["audit_annotations"]["novel_test_factors"][
                    "unseen_template"
                ]
                for episode in test
            ),
            "unseen_entity_episodes": sum(
                episode["gold"]["audit_annotations"]["novel_test_factors"][
                    "unseen_entity"
                ]
                for episode in test
            ),
            "unseen_value_episodes": sum(
                episode["gold"]["audit_annotations"]["novel_test_factors"][
                    "unseen_value"
                ]
                for episode in test
            ),
            "heldout_regime_combination_episodes": len(heldout),
            "heldout_regime_task_success": _mean(
                float(
                    shared_oracle_value_decoder(
                        episode,
                        learned_graph_selection(
                            runtime_view(episode), learner
                        )["predicted_affected_nodes"],
                    )
                    == episode["gold"]["post_state"]
                )
                for episode in heldout
            ),
        },
        "decoder": {
            "name": "shared_oracle_value_decoder",
            "shared_across_all_arms": True,
            "claim_boundary": (
                "Task success isolates impact selection; it is not end-to-end value generation."
            ),
        },
        "serialization_ablation": {
            "orthogonal_to_selection": True,
            "modes": ["compact", "verbose"],
            "same_selected_cell_set": True,
        },
        "arms": arms,
        "scientific_conclusion": {
            "learned_beats_domain_solver_on_task_success": (
                learned["task_success"] > domain["task_success"]
            ),
            "learned_matches_domain_solver_on_task_success": (
                learned["task_success"] == domain["task_success"]
            ),
            "causal_advantage_established": False,
            "reason": (
                "The learned selector is evaluated with an oracle value decoder and does not "
                "beat the hand-coded domain solver on correctness."
            ),
        },
    }
    return report


def _episode_success(episode: Mapping[str, Any], prediction: Mapping[str, Any]) -> bool:
    return prediction["post_state"] == episode["gold"]["post_state"]


def audit(episodes: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    episodes = list(episodes)
    for episode in episodes:
        validate_episode(episode)
    exact_predictions = [exact_key_baseline(episode) for episode in episodes]
    oracle_predictions = [oracle_propagation_baseline(episode) for episode in episodes]
    exact_metrics = audit_predictions(episodes, exact_predictions)
    oracle_metrics = audit_predictions(episodes, oracle_predictions)
    exact_metrics["episode_success_rate"] = sum(
        _episode_success(ep, pred) for ep, pred in zip(episodes, exact_predictions)
    ) / len(episodes)
    oracle_metrics["episode_success_rate"] = sum(
        _episode_success(ep, pred) for ep, pred in zip(episodes, oracle_predictions)
    ) / len(episodes)

    hidden_downstream = []
    negative_controls = []
    multi_hop = []
    for episode in episodes:
        explicit = set(episode["query"]["explicit_state_keys"])
        downstream = set(episode["gold"]["affected_nodes"]) - explicit
        hidden_downstream.append(bool(downstream) and not (downstream & explicit))
        negative_controls.append(
            all(
                episode["memory_state"][key] == episode["gold"]["post_state"][key]
                for key in episode["gold"]["audit_annotations"][
                    "negative_control_keys"
                ]
            )
        )
        multi_hop.append(
            any(len(path) >= 3 for path in episode["gold"]["propagation_paths"])
        )

    strict_monitor = [
        "cart.monitor" in ep["gold"]["affected_nodes"]
        for ep in episodes
        if ep["gold"]["audit_annotations"]["scenario"] == "gpu_cancel_strict"
    ]
    adapter_monitor = [
        "cart.monitor" in ep["gold"]["affected_nodes"]
        for ep in episodes
        if ep["gold"]["audit_annotations"]["scenario"] == "gpu_cancel_adapters"
    ]
    regime_pair_available = bool(strict_monitor and adapter_monitor)
    regime_contrast_pass = (
        regime_pair_available and all(strict_monitor) and not any(adapter_monitor)
    )
    summary = {
        "benchmark": "dynamic_shopping",
        "episodes": len(episodes),
        "exact_key": exact_metrics,
        "oracle_propagation": oracle_metrics,
        "diagnostics": {
            "hidden_downstream_rate": sum(hidden_downstream) / len(episodes),
            "multi_hop_rate": sum(multi_hop) / len(episodes),
            "negative_control_preservation_rate": sum(negative_controls) / len(episodes),
            "regime_pair_available": regime_pair_available,
            "regime_contrast_pass": regime_contrast_pass,
        },
    }
    summary["t0_pass"] = bool(
        exact_metrics["episode_success_rate"] < oracle_metrics["episode_success_rate"]
        and exact_metrics["affected_recall"] < 1.0
        and oracle_metrics["episode_success_rate"] == 1.0
        and oracle_metrics["affected_recall"] == 1.0
        and summary["diagnostics"]["hidden_downstream_rate"] == 1.0
        and summary["diagnostics"]["multi_hop_rate"] == 1.0
        and summary["diagnostics"]["negative_control_preservation_rate"] == 1.0
        and regime_contrast_pass
    )
    summary["admission"] = {
        "C1_no_query_time_downstream_oracle": (
            summary["diagnostics"]["hidden_downstream_rate"] == 1.0
        ),
        "C2_repeated_regime_mechanism": len(episodes) >= len(SCENARIOS),
        "C3_interventional_gold_valid": (
            oracle_metrics["episode_success_rate"] == 1.0
        ),
        "C4_exact_key_leaves_headroom": (
            exact_metrics["episode_success_rate"] < 0.95
            and exact_metrics["affected_recall"] < 0.95
        ),
        "negative_controls_preserved": (
            summary["diagnostics"]["negative_control_preservation_rate"] == 1.0
        ),
        "regime_contrast_pass": regime_contrast_pass,
        "pass": summary["t0_pass"],
    }
    return summary


def audit_dataset(dataset: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Cross-task runner entry point (thin alias for :func:`audit`)."""

    return audit(dataset)


def _audit_for_output(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Drop verbose per-episode rows from the CLI summary."""

    result = copy.deepcopy(dict(summary))
    result["exact_key"].pop("per_episode", None)
    result["oracle_propagation"].pop("per_episode", None)
    return result


def _t1_for_output(report: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(report))
    for arm in result["arms"].values():
        arm.pop("per_episode", None)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=24)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--audit", action="store_true", help="print a compact T0 audit to stdout"
    )
    parser.add_argument(
        "--t1",
        action="store_true",
        help="fit the train-only observed-impact learner and report six test arms",
    )
    args = parser.parse_args(argv)
    episodes = generate_episodes(episodes=args.episodes, seed=args.seed)
    summary = audit(episodes)
    t1_report = run_t1_experiment(episodes) if args.t1 else None
    payload = {
        "schema_version": SCHEMA_VERSION,
        "benchmark": "dynamic_shopping",
        "generation": {"episodes": args.episodes, "seed": args.seed},
        "episodes": episodes,
        "audit": _audit_for_output(summary),
    }
    if t1_report is not None:
        payload["t1"] = _t1_for_output(t1_report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    if args.audit or not args.out:
        print(json.dumps(_audit_for_output(summary), ensure_ascii=False, indent=2))
    if t1_report is not None and (args.audit or not args.out):
        print(json.dumps(_t1_for_output(t1_report), ensure_ascii=False, indent=2))
    return 0 if summary["t0_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
