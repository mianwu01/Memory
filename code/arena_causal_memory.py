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
  "learned" : a type-level slot graph DISCOVERED from data by
              code/travel_grace_discovery.py (milestone M4). Schema
              "travel-type-level-slot-graph/v1"; see _load_learned_graph.
              This mode never reads person names out of the query -- the whole
              point is to test whether a learned graph can drive the mask
              WITHOUT the rule graph's query-parsing oracle.
  "offline" : legacy placeholder schema {person: [slots]}, kept so older configs
              keep working. Not produced by the discovery pipeline.

CPU-only, no API dependency: importable and testable without a key.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# The 7-slot travel schema, verified at env/env_systems/travel_env.py:11
SLOTS = ["current_city", "transportation", "breakfast", "attraction",
         "lunch", "dinner", "accommodation"]

# The trip spine: slots any complete itinerary depends on regardless of what the
# query's constraint sentences happen to mention. See CausalMemorySystem.
SCAFFOLD_SLOTS = ["current_city", "transportation", "accommodation"]

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


def _load_learned_graph(path: str) -> Dict[str, Any]:
    """Read a discovered type-level slot graph (schema travel-type-level-slot-graph/v1).

    Required keys (written by code/travel_grace_discovery.py --export):
      slots             the 7-slot schema the graph is over
      max_lag           L; the learned lag horizon, in ROUNDS
      slot_ancestors    {effect_slot: [cause slots, transitively]} over lags 1..L
      persistent_slots  slots whose value is constant across every round of a trial
      edges             [{cause, effect, lag, weight}]  (kept for auditing/logging)
    """
    with open(path) as f:
        g = json.load(f)
    if not isinstance(g, dict) or "slot_ancestors" not in g:
        raise ValueError(
            f"{path} is not a learned type-level graph: expected a JSON object with "
            f"'slot_ancestors' (schema travel-type-level-slot-graph/v1)")
    g.setdefault("slots", list(SLOTS))
    g.setdefault("max_lag", 3)
    g.setdefault("persistent_slots", [])
    unknown = set(g["slot_ancestors"]) - set(SLOTS)
    if unknown:
        raise ValueError(f"{path}: slot_ancestors names slots not in the travel "
                         f"schema: {sorted(unknown)}")
    return g


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
        ablate_graph: bool = False,
        include_scaffold: bool = False,
        learned_graph_path: Optional[str] = None,
        use_names: bool = False,
        restrict_days: bool = False,
    ):
        self.graph_mode = graph_mode
        self.user_id = user_id
        self.keep_provenance = keep_provenance
        self.max_slots = max_slots
        self.fallback_to_raw = fallback_to_raw
        # ablation: keep the slot parsing + hold rule but drop graph selection,
        # so any gain over this arm is attributable to An_G, not to structuring.
        self.ablate_graph = ablate_graph
        # Trip-scaffold dependency (found by running the real agent end to end):
        # a traveller must emit a COMPLETE itinerary, so every round depends on the
        # group's shared city / flight / lodging even when the query's constraint
        # sentences mention only meals. The name-anchored rule graph encodes the
        # explicit constraint edges only and drops the scaffold, which starves the
        # agent -- it burns its whole step budget re-searching flights. This flag
        # adds the scaffold back. Kept as a SEPARATE mode so the constraint-only
        # arm stays measurable and the difference is attributable.
        self.include_scaffold = include_scaffold
        # learned mode knobs (see _learned_select)
        self.use_names = use_names
        self.restrict_days = restrict_days

        # Form A state: (person, day, slot) -> (value, write_round)
        self._cells: Dict[Tuple[str, int, str], Tuple[str, int]] = {}
        self._people: List[str] = []              # insertion order == round order
        self._raw_chunks: List[str] = []
        self._offline_graph: Dict[str, List[str]] = {}
        self._learned: Dict[str, Any] = {}

        if graph_mode == "offline":
            if not offline_graph_path:
                raise ValueError("graph_mode='offline' requires offline_graph_path")
            with open(offline_graph_path) as f:
                g = json.load(f)
            if not isinstance(g, dict):
                raise ValueError(f"offline graph at {offline_graph_path} must be a JSON object")
            self._offline_graph = g
        elif graph_mode == "learned":
            path = learned_graph_path or offline_graph_path
            if not path:
                raise ValueError("graph_mode='learned' requires learned_graph_path")
            self._learned = _load_learned_graph(path)

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
        if self.ablate_graph:
            return set(self._cells)          # structured slots, no graph selection
        if self.graph_mode == "learned" and self._learned:
            return self._learned_select(q)
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

        if self.include_scaffold:
            keep |= self._scaffold_cells(named)

        if self.max_slots is not None and len(keep) > self.max_slots:
            keep = set(sorted(keep, key=lambda k: -self._cells[k][1])[:self.max_slots])
        return keep

    # --- learned-graph selection (milestone M4) -------------------------------
    @staticmethod
    def _query_slots_days(ql: str) -> Tuple[Set[str], Set[int]]:
        """Slots and days the query mentions. NOT the name oracle -- these are the
        target cells the round is about, which any memory system may read."""
        slots = {s for s in SLOTS if s.replace("_", " ") in ql or s in ql}
        days = {int(d) for d in re.findall(r"day\s+(\d+)", ql)}
        for word, d in (("first", 1), ("second", 2), ("third", 3), ("fourth", 4),
                        ("fifth", 5), ("sixth", 6), ("seventh", 7)):
            if f"{word} day" in ql or f"{word}-day" in ql:
                days.add(d)
        return slots, days

    def _learned_select(self, query: str) -> Set[Tuple[str, int, str]]:
        """An_G(Y_t) under the DISCOVERED type-level graph.

        Y_t (the target cells) is the WHOLE 7-slot schema, not just the slots the
        query's constraint sentences name: the travel agent must emit a complete
        itinerary every round (env/env_systems/travel_env.py:11 scores all 7 slots),
        so every slot is a target and its learned ancestors must survive. This is
        exactly where the hand-written rule graph is under-specified -- it takes
        Y_t = the named cells only and therefore drops the trip scaffold.

        Three levers, all read off the learned artifact, none hand-set:
          slot mask   keep slot types in  U_{s in Y} slot_ancestors[s]
          lag horizon keep the last `max_lag` writers (provenance = write round);
                      the learned graph has no edge beyond lag L, so older rounds
                      are non-ancestors
          persistence for a slot in `persistent_slots` the value is identical in
                      every round, so ONE retained copy (the earliest writer)
                      reconstructs all of them -- pure compression, no loss
        """
        g = self._learned
        ql = query.lower()
        slots_named, days_named = self._query_slots_days(ql)

        keep_slots: Set[str] = set()
        for s in SLOTS:                                   # every slot is a target
            keep_slots |= set(g["slot_ancestors"].get(s, []))
            if s in g["slot_ancestors"]:                  # a slot with no learned
                keep_slots.add(s)                         # ancestor still needs itself
        persistent = set(g.get("persistent_slots", [])) & keep_slots

        L = int(g.get("max_lag", 3))
        cur_round = len(self._raw_chunks)                 # rounds written so far
        recent = {p for i, p in enumerate(self._people) if i >= cur_round - L}
        named = {p for p in self._people if p and p.lower() in ql} if self.use_names else set()

        keep: Set[Tuple[str, int, str]] = set()
        for k in self._cells:
            person, day, slot = k
            if slot not in keep_slots or slot in persistent:
                continue
            if person not in recent and person not in named:
                continue
            if (self.restrict_days and days_named and slots_named
                    and slot in slots_named and day not in days_named):
                continue
            keep.add(k)

        # persistent slots: one copy per (day, slot), from the earliest writer
        for slot in persistent:
            first: Dict[int, Tuple[str, int, str]] = {}
            for k, (_v, rnd) in self._cells.items():
                if k[2] != slot:
                    continue
                cur = first.get(k[1])
                if cur is None or rnd < self._cells[cur][1]:
                    first[k[1]] = k
            keep |= set(first.values())
        return keep

    def _scaffold_cells(self, named: List[str]) -> Set[Tuple[str, int, str]]:
        """The shared-trip spine every itinerary depends on.

        Taken from the earliest-written person present (the base person anchors
        the group's city/flight/lodging), falling back to anyone named.
        """
        anchor = self._people[0] if self._people else None
        sources = [p for p in ([anchor] + list(named)) if p]
        return {k for k in self._cells
                if k[0] in sources and k[2] in SCAFFOLD_SLOTS}

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
    assert "Boston" not in w, ("this assertion documents the rule graph's known "
                               "under-specification: current_city is never named in "
                               "a travel query, so the name-anchored graph drops the "
                               "trip scaffold. See docs/p2-grace-integration-results.md")
    print("\nOK: sentinel present, ancestors selected, scratchpad masked.")

    # --- learned-graph mode (milestone M4) --------------------------------
    import os
    gp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "results", "real", "travel_learned_graph.json")
    if os.path.exists(gp):
        lm = CausalMemorySystem(graph_mode="learned", learned_graph_path=gp)
        for c in mem._raw_chunks:
            lm.add_chunk(c)
        wl = lm.wrap_user_prompt(q)
        assert "</memory_context>" in wl, "sentinel missing"
        assert "Hotel Alpha" in wl, "learned graph must keep the accommodation ancestor"
        assert "Boston" in wl, ("learned graph must keep the trip scaffold "
                                "(current_city) -- that is the whole point of M4")
        assert "step_idx" not in wl, "raw scratchpad leaked into context"
        print("\n--- learned mode ---")
        print(wl)
        print("\n[stats]", lm.context_stats(q))
        print("\nOK: learned graph loaded, scaffold retained, scratchpad masked.")
    else:
        print(f"\n(skipped learned-mode smoke test: {gp} not built yet; run "
              f"code/travel_grace_discovery.py --export)")
