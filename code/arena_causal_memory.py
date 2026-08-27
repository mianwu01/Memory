"""CausalMemorySystem — MemoryArena plugin for the temporal-causal-memory method.

Duck-typed to MemoryArena's memory-system interface, verified against
benchmarks/MemoryArena (commit 6cd9de1):
    add_chunk(chunk: str) -> Any            # memory/server.py:107-111 (JSON-able)
    wrap_user_prompt(prompt: str) -> str    # must emit the </memory_context>
                                            # sentinel; run_travel.py:262 splits on it

This file is STANDALONE ON PURPOSE. MemoryArena ships with no LICENSE file, so we
register into it at runtime instead of vendoring or forking their code:

    from arena_causal_memory import CausalMemorySystem
    MEMORY_FACTORIES["causal"] = CausalMemorySystem          # memory/server.py:49

Method (docs/agentic-experiment-plan.md §2, docs/memoryarena-instantiation.md §6):
  1. parse each round's chunk into fixed-schema (person, day, slot) cells,
     where slot in the 7-slot travel schema (travel_env.py:11);
  2. hold rule: a cell keeps its value until overwritten; provenance = round idx;
  3. at query time select An_G(query) -- the ancestor cells of the queried cells
     under graph G -- and serialize ONLY those. Whole-chunk retrieval ships the
     entire 30-step ReAct scratchpad; slot-level extraction is the compression
     lever this method is claiming.

G is pluggable:
  "rule"    : name-anchored instance graph parsed from the query (T0-Arena arm;
              travel's dependencies are named in the query -- see t0-results.md,
              so this is an ORACLE-ish upper bound on retrieval, and the honest
              claim on travel is compression/efficiency, NOT discovery necessity)
  "offline" : a discovered type-level graph loaded from JSON (milestone M4)

CPU-only, no API dependency: importable and testable without a key.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# The 7-slot travel schema, verified at env/env_systems/travel_env.py:11
SLOTS = ["current_city", "transportation", "breakfast", "attraction",
         "lunch", "dinner", "accommodation"]

# Rendering used by run_travel.format_person_plan (run_travel.py:65-78):
#   "=== {name}'s Plan ===" / "Day {d}:" / "Current City: ..." / "Lunch: ..." etc.
_PLAN_HEADER = re.compile(r"===\s*(.+?)'s Plan\s*===")
_DAY_LINE = re.compile(r"^Day\s+(\d+)\s*:", re.MULTILINE)
_SLOT_LINE = re.compile(r"^([A-Za-z ]+):\s*(.*)$")

_LABEL_TO_SLOT = {lab.replace("_", " ").title(): lab for lab in SLOTS}
_LABEL_TO_SLOT["Current City"] = "current_city"


def parse_plan(text: str) -> Dict[Tuple[int, str], str]:
    """Parse a formatted plan into {(day, slot): value}; '-' means unset."""
    cells: Dict[Tuple[int, str], str] = {}
    day = None
    for line in (text or "").splitlines():
        line = line.strip()
        dm = _DAY_LINE.match(line)
        if dm:
            day = int(dm.group(1))
            continue
        if day is None:
            continue
        sm = _SLOT_LINE.match(line)
        if sm:
            slot = _LABEL_TO_SLOT.get(sm.group(1).strip())
            val = sm.group(2).strip()
            if slot and val and val != "-":
                cells[(day, slot)] = val
    return cells


class CausalMemorySystem:
    """Structured-slot travel memory with causal-ancestor masking at query time."""

    def __init__(
        self,
        graph_mode: str = "rule",
        offline_graph_path: Optional[str] = None,
        user_id: Optional[str] = None,
        keep_provenance: bool = True,
        max_slots: Optional[int] = None,
        fallback_to_raw: bool = True,
    ):
        self.graph_mode = graph_mode
        self.user_id = user_id
        self.keep_provenance = keep_provenance
        self.max_slots = max_slots
        self.fallback_to_raw = fallback_to_raw

        # Form A state: (person, day, slot) -> (value, write_round)
        self._cells: Dict[Tuple[str, int, str], Tuple[str, int]] = {}
        self._people: List[str] = []              # insertion order == round order
        self._raw_chunks: List[str] = []
        self._offline_graph: Dict[str, List[str]] = {}

        if graph_mode == "offline":
            if not offline_graph_path:
                raise ValueError("graph_mode='offline' requires offline_graph_path")
            with open(offline_graph_path) as f:
                g = json.load(f)
            if not isinstance(g, dict):
                raise ValueError(f"offline graph at {offline_graph_path} must be a JSON object")
            self._offline_graph = g

    # --- interface method 1 --------------------------------------------------
    def add_chunk(self, chunk: str) -> Dict[str, Any]:
        """Parse a round's chunk into cells. Returns a JSON-able ack (server.py:109)."""
        idx = len(self._raw_chunks)
        self._raw_chunks.append(chunk)

        name, plan_text = None, ""
        try:
            obj = json.loads(chunk)
            if isinstance(obj, dict):
                name = obj.get("name")
                plan_text = obj.get("final_plan") or ""
        except (json.JSONDecodeError, TypeError):
            plan_text = chunk or ""
        if not name:
            m = _PLAN_HEADER.search(plan_text or chunk or "")
            name = m.group(1).strip() if m else f"round_{idx}"
        if name not in self._people:
            self._people.append(name)

        cells = parse_plan(plan_text)
        for (day, slot), val in cells.items():
            self._cells[(name, day, slot)] = (val, idx)   # overwrite = new write
            # unmatched cells simply hold their previous (value, round)
        return {"name": name, "cells_parsed": len(cells), "round": idx}

    # --- interface method 2 --------------------------------------------------
    def wrap_user_prompt(self, prompt: str) -> str:
        """Serialize only An_G(query) into the memory context."""
        selected = self._ancestors_of(prompt)
        lines = ["<memory_context>"]
        body = self._render(selected)
        if body:
            lines.append(body)
        elif self.fallback_to_raw and self._raw_chunks:
            # never starve the agent: if selection is empty but memory exists,
            # fall back to the most recent plan rather than emitting "None".
            last = self._people[-1] if self._people else None
            fb = self._render({k for k in self._cells if last and k[0] == last})
            lines.append(fb or "None")
        else:
            lines.append("None")
        lines.append("</memory_context>")            # load-bearing sentinel
        lines.append(f"User: {prompt}")
        return "\n".join(lines)

    # --- graph selection -----------------------------------------------------
    def _ancestors_of(self, query: str) -> Set[Tuple[str, int, str]]:
        """An_G(query): cells the query's targets causally depend on.

        rule mode: travel names its dependencies ("join Eric", "same room type as
        Emma's second-day accommodation"), so the instance graph is read off the
        query -- persons named in the query, restricted to the slots/days the
        query mentions when it names them, else all of that person's cells.
        """
        q = query or ""
        ql = q.lower()
        if self.graph_mode == "offline" and self._offline_graph:
            named = [p for p in self._people if p.lower() in ql]
            keep = set()
            for p in named:
                allowed = self._offline_graph.get(p) or self._offline_graph.get("*") or SLOTS
                keep |= {k for k in self._cells if k[0] == p and k[2] in allowed}
            return keep

        named = [p for p in self._people if p and p.lower() in ql]
        slots_named = [s for s in SLOTS
                       if s.replace("_", " ") in ql or s in ql]
        days_named = {int(d) for d in re.findall(r"day\s+(\d+)", ql)}
        for word, d in (("first", 1), ("second", 2), ("third", 3),
                        ("fourth", 4), ("fifth", 5), ("sixth", 6), ("seventh", 7)):
            if f"{word} day" in ql or f"{word}-day" in ql:
                days_named.add(d)

        keep: Set[Tuple[str, int, str]] = set()
        for p in named:
            cand = {k for k in self._cells if k[0] == p}
            if slots_named:
                narrowed = {k for k in cand if k[2] in slots_named}
                cand = narrowed or cand
            if days_named:
                narrowed = {k for k in cand if k[1] in days_named}
                cand = narrowed or cand
            keep |= cand

        if self.max_slots is not None and len(keep) > self.max_slots:
            keep = set(sorted(keep, key=lambda k: -self._cells[k][1])[:self.max_slots])
        return keep

    def _render(self, keys: Set[Tuple[str, int, str]]) -> str:
        if not keys:
            return ""
        out: List[str] = []
        for person in self._people:
            pk = sorted([k for k in keys if k[0] == person], key=lambda k: (k[1], k[2]))
            if not pk:
                continue
            out.append(f"=== {person}'s Plan ===")
            cur_day = None
            for k in pk:
                if k[1] != cur_day:
                    cur_day = k[1]
                    out.append(f"Day {cur_day}:")
                val, rnd = self._cells[k]
                label = k[2].replace("_", " ").title()
                out.append(f"{label}: {val}" + (f"  (round {rnd})" if self.keep_provenance else ""))
        return "\n".join(out)

    # --- diagnostics (compression axis) --------------------------------------
    def context_stats(self, prompt: str) -> Dict[str, float]:
        wrapped = self.wrap_user_prompt(prompt)
        ctx = wrapped.split("</memory_context>")[0]
        full = "\n".join(self._raw_chunks) or "None"
        return {
            "selected_chars": float(len(ctx)),
            "full_history_chars": float(len(full)),
            "compression_ratio": len(ctx) / max(1, len(full)),
            "n_cells_selected": float(len(self._ancestors_of(prompt))),
            "n_cells_total": float(len(self._cells)),
        }


if __name__ == "__main__":
    # Offline smoke test — no API key, no GPU. Verifies the interface contract
    # against the real travel chunk format (run_travel.py:226-232, :320-325).
    def plan(name, days):
        L = [f"=== {name}'s Plan ==="]
        for d, cells in days.items():
            L.append(f"Day {d}:")
            for s in SLOTS:
                L.append(f"{s.replace('_',' ').title()}: {cells.get(s,'-')}")
            L.append("")
        return "\n".join(L)

    mem = CausalMemorySystem(graph_mode="rule")
    mem.add_chunk(json.dumps({
        "name": "Eric", "query": "Plan a 2-day trip.", "is_base_person": True,
        "final_plan": plan("Eric", {1: {"current_city": "Boston", "lunch": "Sal's",
                                        "accommodation": "Hotel Alpha"},
                                    2: {"current_city": "Kyoto", "dinner": "Ramen Ya"}})}))
    mem.add_chunk(json.dumps({
        "name": "Emma", "query": "Join Eric on day 1.",
        "scratchpad": [{"step_idx": i, "thought": "x" * 200} for i in range(30)],
        "final_plan": plan("Emma", {1: {"current_city": "Boston",
                                        "accommodation": "Hotel Beta"}})}))

    q = ("For accommodation on the first day, I'd like to join Eric, "
         "but priced within $150 of his.")
    w = mem.wrap_user_prompt(q)
    assert "</memory_context>" in w, "sentinel missing — run_travel would break"
    assert "Hotel Alpha" in w, "must retain the named ancestor cell"
    assert "Ramen Ya" not in w, "day-2 dinner is not an ancestor; should be masked"
    assert "step_idx" not in w, "raw scratchpad leaked into context"
    print(w)
    print("\n[stats]", mem.context_stats(q))
    print("\nOK: sentinel present, ancestors selected, scratchpad masked.")
