"""Development-only prompt composition audit for MemoryArena inheritance-v2.

This script replays already generated plans without an LLM call.  It quantifies
which prompt components were repeatedly billed in the frozen 101--110 run and
estimates the effect of query-target delta serialization using the exact saved
ReAct step/tool-result structure.  It never loads evaluator functions or person
gold answers; the dataset loader is used only for public base plans and queries.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from arena_causal_memory import CausalMemorySystem, SLOTS
from arena_e2e_inherit import (
    strip_decoder_base_from_memory_context,
    target_cells_from_query,
)
from arena_e2e_run import INHERITANCE_V2_SYSTEM_PROMPT, INHERITANCE_V2_USER_PROMPT


ROOT = Path(__file__).resolve().parents[1]
ARENA = ROOT / "benchmarks" / "MemoryArena"
OLD_GRAPH = ROOT / "results" / "real" / "travel_learned_graph_holdout_101_110.json"
OLD_API_INPUT = {"current_pure": 858445, "current_noG": 1006049}


def format_plan(name: str, daily_plans: list[dict]) -> str:
    lines = [f"=== {name}'s Plan ==="]
    for row in daily_plans:
        day = row.get("days") or row.get("day")
        lines.append(f"Day {day}:")
        for slot in SLOTS:
            lines.append(f"{slot.replace('_', ' ').title()}: {row.get(slot, '-')}")
        lines.append("")
    return "\n".join(lines)


def load_rows() -> dict[int, dict]:
    sys.path.insert(0, str(ARENA))
    cwd = Path.cwd()
    try:
        os.chdir(ARENA)
        from env.env_systems.travel_planner_env.data_loader import load_travel_data
        # Deliberately project away ``answers`` immediately.  This development
        # audit has no reason to make person gold reachable downstream.
        return {
            int(row["id"]): {
                "id": int(row["id"]),
                "base_person": row["base_person"],
                "questions": row["questions"],
            }
            for row in load_travel_data()
        }
    finally:
        os.chdir(cwd)


def json_chars(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def dynamic_history_chars(scratchpad: list[dict]) -> int:
    """Characters resent from earlier tool steps at every later LLM call."""
    prior_messages: list[dict] = []
    total = 0
    for step in scratchpad:
        total += sum(json_chars(message) for message in prior_messages)
        calls = step.get("tool_calls") or []
        if calls:
            prior_messages.append({
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "id": call["id"], "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["args"]),
                    },
                } for call in calls],
            })
            for result in step.get("tool_results") or []:
                prior_messages.append({
                    "role": "tool",
                    "tool_call_id": result["tool_call_id"],
                    "content": result["result"],
                })
    return total


def memory_factory(kind: str, graph: Path):
    if kind == "current_pure":
        return CausalMemorySystem(
            graph_mode="learned", learned_graph_path=str(graph), use_names=False,
            inherit_unspecified_from_base=True, keep_provenance=False)
    if kind == "current_noG":
        return CausalMemorySystem(
            graph_mode="rule", ablate_graph=True,
            inherit_unspecified_from_base=True, keep_provenance=False)
    if kind == "compact_v2":
        return CausalMemorySystem(
            graph_mode="learned", learned_graph_path=str(graph), use_names=False,
            inherit_unspecified_from_base=True, keep_provenance=False,
            compact_serialization=True, decoder_base_tag=True)
    if kind == "noG_v2":
        return CausalMemorySystem(
            graph_mode="rule", ablate_graph=True,
            inherit_unspecified_from_base=True, keep_provenance=False,
            decoder_base_tag=True)
    raise ValueError(kind)


def source_arm(kind: str) -> str:
    return (
        "causal-noG-inherit-holdout" if "noG" in kind
        else "causal-learned-pure-inherit-holdout"
    )


def replay(kind: str, ids: list[int], rows: dict[int, dict], graph: Path) -> dict:
    from env.env_systems.travel_planner_env.prompts import (
        AGENT_SYSTEM_PROMPT, AGENT_USER_PROMPT_TEMPLATE)
    from env.env_systems.travel_planner_env.tool_schemas import TOOLS

    totals = {key: 0 for key in (
        "episodes", "rounds", "calls", "context_chars_once",
        "context_chars_repeated", "selected_cells", "stored_cells",
        "system_chars_repeated", "base_message_chars_repeated",
        "tool_schema_chars_repeated",
        "query_chars_repeated", "dynamic_history_chars", "proxy_input_chars")}
    per_episode = {}
    leaks = []
    for episode_id in ids:
        row = rows[episode_id]
        memory = memory_factory(kind, graph)
        base = row["base_person"]
        memory.add_chunk(json.dumps({
            "name": base["name"], "query": base["query"],
            "is_base_person": True,
            "final_plan": format_plan(base["name"], base["daily_plans"]),
        }, ensure_ascii=False))
        arm_dir = ARENA / "results" / "travel_e2e" / source_arm(kind)
        payload = json.loads((arm_dir / f"generated_plan_{episode_id}.json").read_text())
        persons = payload["deepseek-v4-flash_sole-planning_results"]
        scratches = payload["scratchpads"]
        episode = {key: 0 for key in totals if key != "episodes"}
        for person, scratch in zip(persons, scratches):
            query = person["query"]
            context = memory.wrap_user_prompt(query).split("</memory_context>")[0]
            context += "</memory_context>"
            if kind.endswith("v2"):
                context = strip_decoder_base_from_memory_context(context)
                system_prompt = INHERITANCE_V2_SYSTEM_PROMPT
                user_prompt = INHERITANCE_V2_USER_PROMPT.format(
                    name=person["name"], query=query)
                # The repaired v2 runner keeps the complete public base only in
                # the deterministic overlay and does not reinsert upstream's
                # BASE_PERSON_TEMPLATE into model messages.
                base_message_chars = 0
            else:
                system_prompt = AGENT_SYSTEM_PROMPT
                user_prompt = AGENT_USER_PROMPT_TEMPLATE.format(
                    name=person["name"], query=query)
                from env.env_systems.travel_planner_env.prompts import BASE_PERSON_TEMPLATE
                base_message_chars = len(BASE_PERSON_TEMPLATE.format(
                    base_name=base["name"], base_query=base["query"],
                    base_plan=format_plan(base["name"], base["daily_plans"])))
            calls = len(scratch["scratchpad"])
            dynamic = dynamic_history_chars(scratch["scratchpad"])
            effective_tools = TOOLS
            if kind.endswith("v2"):
                target_slots = {slot for _day, slot in target_cells_from_query(query)}
                names = set()
                if target_slots & {"breakfast", "lunch", "dinner"}:
                    names.add("RestaurantSearch")
                if "accommodation" in target_slots:
                    names.add("AccommodationSearch")
                if "attraction" in target_slots:
                    names.add("AttractionSearch")
                if target_slots & {"transportation", "current_city"}:
                    names.update({"FlightSearch", "DistanceMatrix", "CitySearch"})
                if names:
                    effective_tools = [
                        tool for tool in TOOLS
                        if tool.get("function", {}).get("name") in names
                    ]
            components = {
                "rounds": 1,
                "calls": calls,
                "context_chars_once": len(context),
                "context_chars_repeated": len(context) * calls,
                "selected_cells": len(memory._ancestors_of(query)),
                "stored_cells": len(memory._cells),
                "system_chars_repeated": len(system_prompt) * calls,
                "base_message_chars_repeated": base_message_chars * calls,
                "tool_schema_chars_repeated": json_chars(effective_tools) * calls,
                "query_chars_repeated": len(user_prompt) * calls,
                "dynamic_history_chars": dynamic,
            }
            components["proxy_input_chars"] = sum(
                components[key] for key in (
                    "context_chars_repeated", "system_chars_repeated",
                    "base_message_chars_repeated",
                    "tool_schema_chars_repeated", "query_chars_repeated",
                    "dynamic_history_chars"))
            for key, value in components.items():
                totals[key] += value
                episode[key] += value
            forbidden = [token for token in ("scratchpad", "step_idx", "tool_results",
                                              "decoder_base_itinerary")
                         if token in context]
            if forbidden:
                leaks.append({"episode_id": episode_id, "name": person["name"],
                              "tokens": forbidden})
            memory.add_chunk(json.dumps({
                "name": person["name"], "query": query,
                "final_plan": f"=== {person['name']}'s Plan ===\n{person['result']}",
            }, ensure_ascii=False))
        totals["episodes"] += 1
        per_episode[str(episode_id)] = episode

    totals["avg_context_chars"] = totals["context_chars_once"] / totals["rounds"]
    totals["avg_calls_per_round"] = totals["calls"] / totals["rounds"]
    totals["context_fraction_of_proxy_input"] = (
        totals["context_chars_repeated"] / totals["proxy_input_chars"])
    return {"aggregate": totals, "per_episode": per_episode,
            "serialization_leaks": leaks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", type=int, nargs="+", default=list(range(101, 111)))
    parser.add_argument("--graph", default=str(OLD_GRAPH))
    parser.add_argument(
        "--out", default="results/development/p2_compact_v2/context_audit.json")
    args = parser.parse_args()
    graph = Path(args.graph).resolve()
    rows = load_rows()
    report = {
        "schema": "memoryarena-context-composition-audit/v1",
        "scope": "development replay only; no LLM calls; no evaluator/person gold",
        "development_episode_ids": args.ids,
        "graph": str(graph),
        "arms": {
            kind: replay(kind, args.ids, rows, graph)
            for kind in ("current_pure", "current_noG", "compact_v2", "noG_v2")
        },
        "frozen_101_110_api_input_tokens": OLD_API_INPUT,
    }
    arms = report["arms"]
    report["diagnosis"] = {
        "old_api_input_reduction_fraction": 1 - (
            OLD_API_INPUT["current_pure"] / OLD_API_INPUT["current_noG"]),
        "old_context_reduction_fraction": 1 - (
            arms["current_pure"]["aggregate"]["context_chars_repeated"] /
            arms["current_noG"]["aggregate"]["context_chars_repeated"]),
        "compact_vs_current_context_reduction_fraction": 1 - (
            arms["compact_v2"]["aggregate"]["context_chars_repeated"] /
            arms["current_pure"]["aggregate"]["context_chars_repeated"]),
        "v2_proxy_input_reduction_fraction": 1 - (
            arms["compact_v2"]["aggregate"]["proxy_input_chars"] /
            arms["noG_v2"]["aggregate"]["proxy_input_chars"]),
        "note": (
            "Proxy counts serialize saved messages by characters; only held-out API "
            "usage is an acceptance metric. It is used here solely to localize cost."),
    }
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, output)
    print(json.dumps(report["diagnosis"], indent=2))
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
