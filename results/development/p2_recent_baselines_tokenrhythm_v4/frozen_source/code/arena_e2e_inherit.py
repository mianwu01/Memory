"""Copy unspecified travel slots from the public base itinerary.

MemoryArena's travel query describes the cells a new traveller changes, while
its official PS metric checks the complete plan.  A tool-using LLM tends to
replace unrelated meals and attractions after searching the database, turning
an otherwise constraint-correct answer into a PS failure.  This module provides
a query-only constrained decoder:

* parse the target ``(day, slot)`` cells stated in the current query;
* keep the LLM value for those cells;
* copy every other value from the base itinerary that the environment already
  supplies to the agent.

It never reads a person's gold answer or calls the evaluator to choose cells.
The CLI derives a new arm from preserved raw generations so the effect of the
decoder can be measured without another LLM sample.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DEFAULT_ARENA = REPO / "benchmarks" / "MemoryArena"
SLOTS = ["current_city", "transportation", "breakfast", "attraction",
         "lunch", "dinner", "accommodation"]
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4,
            "fifth": 5, "sixth": 6, "seventh": 7}

_DAY_PATTERNS = (
    re.compile(r"\b(first|second|third|fourth|fifth|sixth|seventh)[- ]day\b", re.I),
    re.compile(r"\bday[- ](\d+)\b", re.I),
)
_SLOT_PATTERN = re.compile(
    r"\b(breakfast|lunch|dinner|accommodation|attractions?|transportation|flights?)\b",
    re.I,
)
_TWO_MEALS = re.compile(
    r"\b(?:both\s+)?(breakfast|lunch|dinner)\s+and\s+(breakfast|lunch|dinner)\b",
    re.I,
)
_ACCOMMODATION_FALLBACK = re.compile(
    r"\b(stay|stays|staying|room|home|apartment)\b", re.I)
_SELF = re.compile(r"^I am\s+[^.]+\.$", re.I)
_PREAMBLE = re.compile(
    r"^I'm\s+(?:traveling with|joining|going on this trip with)\b", re.I)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_SOURCE_SLOT_PATTERN = re.compile(
    r"\b(breakfast|lunch|dinner|accommodation|stay|stays|room|"
    r"attractions?|transportation|flights?)\b", re.I)


def _normalise(text: str) -> str:
    return (text or "").replace("\u2019", "'").replace("\u2018", "'")


def _first_day(text: str) -> int | None:
    found = []
    for pattern in _DAY_PATTERNS:
        for match in pattern.finditer(text):
            token = match.group(1).lower()
            day = ORDINALS[token] if token in ORDINALS else int(token)
            found.append((match.start(), day))
    return min(found)[1] if found else None


def _target_slots(text: str) -> list[str]:
    pair = _TWO_MEALS.search(text)
    if pair:
        return [pair.group(1).lower(), pair.group(2).lower()]
    found = []
    for match in _SLOT_PATTERN.finditer(text):
        token = match.group(1).lower()
        if token.startswith("attraction"):
            token = "attraction"
        elif token.startswith("flight"):
            token = "transportation"
        found.append((match.start(), token))
    if found:
        return [min(found)[1]]
    if _ACCOMMODATION_FALLBACK.search(text):
        return ["accommodation"]
    return []


def target_cells_from_query(query: str) -> set[tuple[int, str]]:
    """Return cells the query explicitly allows the new traveller to change."""
    targets = set()
    lines = [line.strip() for line in _normalise(query).splitlines() if line.strip()]
    for line in lines:
        if _SELF.match(line) or _PREAMBLE.match(line):
            continue
        for sentence in _SENTENCE_BOUNDARY.split(line):
            day = _first_day(sentence)
            for slot in _target_slots(sentence):
                if day is not None:
                    targets.add((day, slot))
    return targets


def reference_cells_from_query(
        query: str, people: list[str]) -> dict[str, set[tuple[int, str]]]:
    """Resolve explicit earlier-traveler cell references from query text.

    This is a conservative runtime parser over visible language only.  It is
    used for memory selection, never for scoring.  A possessive/source phrase
    such as ``Karen's lunch on the second day`` maps to Karen/day-2/lunch;
    ``join Karen for breakfast on day 2`` maps to the same target cell.  When a
    source phrase omits its slot/day (``stay with Karen``), the line's explicit
    target is used.  Group-member preambles are excluded.
    """
    refs: dict[str, set[tuple[int, str]]] = {person: set() for person in people}

    def day_mentions(text: str) -> list[tuple[int, int]]:
        found = []
        for pattern in _DAY_PATTERNS:
            for match in pattern.finditer(text):
                token = match.group(1).lower()
                day = ORDINALS[token] if token in ORDINALS else int(token)
                found.append((match.start(), day))
        return sorted(found)

    def slot_mentions(text: str) -> list[tuple[int, str]]:
        found = []
        for match in _SOURCE_SLOT_PATTERN.finditer(text):
            token = match.group(1).lower()
            if token.startswith("attraction"):
                token = "attraction"
            elif token.startswith("flight"):
                token = "transportation"
            elif token in {"stay", "stays", "room"}:
                token = "accommodation"
            found.append((match.start(), token))
        return found

    lines = [line.strip() for line in _normalise(query).splitlines() if line.strip()]
    for line in lines:
        if _SELF.match(line) or _PREAMBLE.match(line):
            continue
        line_targets = target_cells_from_query(line)
        days = day_mentions(line)
        slots = slot_mentions(line)
        for person in people:
            for match in re.finditer(rf"\b{re.escape(person)}(?:'s)?\b", line, re.I):
                # Source descriptions ordinarily follow the name.  Cap the
                # window so a later, unrelated clause cannot be attached.
                after_slots = [(pos, slot) for pos, slot in slots
                               if match.start() <= pos <= match.end() + 100]
                after_days = [(pos, day) for pos, day in days
                              if match.start() <= pos <= match.end() + 100]
                slot = after_slots[0][1] if after_slots else None
                day = after_days[0][1] if after_days else None
                if slot is not None and day is not None:
                    refs[person].add((day, slot))
                    continue
                compatible_targets = [
                    cell for cell in sorted(line_targets)
                    if (slot is None or cell[1] == slot)
                    and (day is None or cell[0] == day)
                ]
                if compatible_targets:
                    refs[person].update(compatible_targets)
                elif len(line_targets) == 1:
                    refs[person].update(line_targets)
    return {person: cells for person, cells in refs.items() if cells}


def plan_cells(plan: list[dict] | None) -> dict[tuple[int, str], str]:
    cells = {}
    for row in plan or []:
        day = row.get("days") or row.get("day")
        if day is None:
            continue
        for slot in SLOTS:
            value = row.get(slot)
            if value is not None:
                cells[(int(day), slot)] = str(value).strip()
    return cells


def parse_plan_text(text: str) -> dict[tuple[int, str], str]:
    """Parse the benchmark's line format, preserving literal ``-`` values."""
    cells = {}
    day = None
    labels = {slot.replace("_", " ").title(): slot for slot in SLOTS}
    labels["Current City"] = "current_city"
    for raw in (text or "").splitlines():
        line = raw.strip()
        # Compact v2 asks for canonical headings, but real decoder output can
        # omit the trailing colon and prefix slot rows with a Markdown bullet.
        # Both are formatting variants, not semantic failures.
        match = re.fullmatch(r"Day\s+(\d+)\s*:?", line, re.I)
        if match:
            day = int(match.group(1))
            continue
        line = re.sub(r"^[-*]\s*", "", line)
        if day is None or ":" not in line:
            continue
        label, value = line.split(":", 1)
        slot = labels.get(label.strip().title())
        if slot:
            clean = re.sub(r"(?:\s+\(round\s+\d+\))+$", "", value.strip())
            cells[(day, slot)] = clean
    return cells


def base_plan_from_memory_context(memory_context: str) -> list[dict]:
    """Extract the first (base-person) plan from a structured memory context."""
    text = memory_context or ""
    header = re.search(r"===\s*[^=]+?'s Plan\s*===", text)
    if not header:
        return []
    remainder = text[header.end():]
    boundary = re.search(r"\n===\s*[^=]+?'s Plan\s*===|\n<inheritance_policy>", remainder)
    body = remainder[:boundary.start()] if boundary else remainder
    cells = parse_plan_text(body)
    days = sorted({day for day, _slot in cells})
    return [
        {"days": day, **{slot: cells.get((day, slot), "-") for slot in SLOTS}}
        for day in days
    ]


def strip_decoder_base_from_memory_context(memory_context: str) -> str:
    """Remove the tagged public base before an inheritance-v2 LLM call.

    The full plan remains available to :func:`base_plan_from_memory_context` and
    the deterministic overlay decoder, but it is not repeatedly billed on every
    ReAct step.  Only an explicitly tagged section is removed; legacy contexts
    are returned byte-for-byte so old experiments remain reproducible.
    """
    text = memory_context or ""
    pattern = re.compile(
        r"<decoder_base_itinerary>.*?</decoder_base_itinerary>", re.DOTALL)
    if not pattern.search(text):
        return text
    return pattern.sub("<decoder_base_available_to_deterministic_decoder/>", text,
                       count=1)


def add_query_target_base_cells(
    memory_context: str,
    base_plan: list[dict],
    targets: set[tuple[int, str]],
) -> str:
    """Expose only public-base values for query target cells.

    A travel day's ``current_city`` can be a route (for example,
    ``Vernal -> Houston``), while meals on that day still belong to one route
    endpoint.  The target cell's public base value supplies that day-local city
    cue without resending the complete itinerary.  This uses neither person
    gold nor evaluator output and is shared by every v3 arm.
    """
    sentinel = "</memory_context>"
    if sentinel not in memory_context:
        raise ValueError("memory context is missing </memory_context>")
    base = plan_cells(base_plan)
    lines = ["<query_target_base_cells>",
             "day | slot | public base value (location cue, not target answer)"]
    for day, slot in sorted(targets):
        lines.append(f"{day} | {slot} | {base.get((day, slot), '-') or '-'}")
    lines.append("</query_target_base_cells>")
    return memory_context.replace(
        sentinel, "\n".join(lines + [sentinel]), 1)


def render_plan(name: str, base_plan: list[dict], generated: str,
                targets: set[tuple[int, str]]) -> str:
    """Overlay query-target values on the base plan and emit canonical text."""
    base = plan_cells(base_plan)
    proposed = parse_plan_text(generated)
    days = sorted({day for day, _slot in base})
    lines = [f"=== {name}'s Plan ==="]
    for day in days:
        lines.append(f"Day {day}:")
        for slot in SLOTS:
            key = (day, slot)
            value = proposed.get(key, base.get(key, "-")) if key in targets \
                else base.get(key, "-")
            lines.append(f"{slot.replace('_', ' ').title()}: {value or '-'}")
        lines.append("")
    return "\n".join(lines).rstrip()


def derive_arm(source_dir: Path, output_dir: Path, model: str,
               data_by_id: dict[int, dict], source_arm: str, output_arm: str,
               use_scratchpad_final: bool = False) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    key = f"{model}_sole-planning_results"
    n_groups = n_persons = 0
    for source in sorted(source_dir.glob("generated_plan_*.json")):
        data_idx = int(source.stem.rsplit("_", 1)[1])
        benchmark_row = data_by_id[data_idx]
        base_plan = benchmark_row["base_person"]["daily_plans"]
        payload = json.loads(source.read_text())
        transformed = []
        scratchpads = payload.get("scratchpads") or []
        for person_index, person in enumerate(payload[key]):
            row = dict(person)
            targets = target_cells_from_query(row.get("query", ""))
            generated = row.get("result") or ""
            if use_scratchpad_final and person_index < len(scratchpads):
                steps = scratchpads[person_index].get("scratchpad") or []
                finals = [step.get("final_output") for step in steps
                          if step.get("final_output")]
                if finals:
                    generated = finals[-1]
            row["result"] = render_plan(
                row.get("name") or f"Person{row.get('person_idx')}",
                base_plan, generated, targets)
            row["inheritance_target_cells"] = [list(x) for x in sorted(targets)]
            transformed.append(row)
        payload[key] = transformed
        payload["all_results"] = [transformed]
        payload.setdefault("metadata", {}).update({
            "memory_system": output_arm,
            "derived_from_arm": source_arm,
            "derived_decoder": "query-target/base-inheritance-v1",
            "derived_from_scratchpad_final": use_scratchpad_final,
            "new_llm_calls": 0,
        })
        (output_dir / source.name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False))
        n_groups += 1
        n_persons += len(transformed)

    stats = source_dir / "stats_results" / "usage_stats.json"
    if stats.is_file():
        target_stats = output_dir / "stats_results"
        target_stats.mkdir()
        shutil.copy2(stats, target_stats / stats.name)

    print(f"derived {n_groups} groups / {n_persons} persons: {source_arm} -> {output_arm}")


def validate_target_parser(eval_mod, rows: list[dict]) -> dict:
    """Audit query parsing against official changed cells; never used at runtime."""
    gt, base_plans, _group_counts = eval_mod.load_ground_truth()
    totals = Counter()
    by_slot = {}
    for row in rows:
        data_idx = int(row["id"])
        totals["groups"] += 1
        for question in row["questions"]:
            person_idx = int(question["round_idx"])
            parsed = target_cells_from_query(question.get("query") or "")
            official = eval_mod.find_constraint_slots(
                gt, base_plans, data_idx, person_idx)
            totals["rounds"] += 1
            totals["parsed_targets"] += len(parsed)
            totals["official_changed_cells"] += len(official)
            totals["true_positive"] += len(parsed & official)
            totals["false_negative"] += len(official - parsed)
            totals["extra_explicit_targets"] += len(parsed - official)
            for slot in SLOTS:
                slot_parsed = {cell for cell in parsed if cell[1] == slot}
                slot_official = {cell for cell in official if cell[1] == slot}
                counter = by_slot.setdefault(slot, Counter())
                counter["parsed_targets"] += len(slot_parsed)
                counter["official_changed_cells"] += len(slot_official)
                counter["true_positive"] += len(slot_parsed & slot_official)
                counter["false_negative"] += len(slot_official - slot_parsed)
                counter["extra_explicit_targets"] += len(slot_parsed - slot_official)

    official_n = totals["official_changed_cells"]
    return {
        **dict(totals),
        "official_cell_recall": (
            totals["true_positive"] / official_n if official_n else 1.0),
        "by_slot": {slot: dict(counts) for slot, counts in by_slot.items()},
        "scope_note": (
            "Offline parser audit only. Runtime inheritance does not load ground "
            "truth or call the evaluator."),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source_arm")
    parser.add_argument("--output_arm")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--arena_dir", default=str(DEFAULT_ARENA))
    parser.add_argument(
        "--e2e_dir", default=None,
        help="arm root; defaults to <arena>/results/travel_e2e")
    parser.add_argument(
        "--use_scratchpad_final", action="store_true",
        help="re-decode preserved raw v2 final outputs instead of inherited results")
    parser.add_argument("--validate_targets", action="store_true")
    parser.add_argument("--validation_out",
                        default="results/real/e2e_inherit_target_audit.json")
    args = parser.parse_args()

    arena = Path(args.arena_dir).resolve()
    e2e = Path(args.e2e_dir).resolve() if args.e2e_dir else (
        arena / "results" / "travel_e2e")
    if not args.validate_targets and (not args.source_arm or not args.output_arm):
        parser.error("--source_arm and --output_arm are required unless --validate_targets is used")

    source_dir = output_dir = None
    if not args.validate_targets:
        source_dir, output_dir = e2e / args.source_arm, e2e / args.output_arm
        if not source_dir.is_dir():
            raise SystemExit(f"source arm not found: {source_dir}")
        if output_dir.exists():
            raise SystemExit(f"refusing to overwrite existing output arm: {output_dir}")

    sys.path.insert(0, str(arena))
    old_cwd = Path.cwd()
    try:
        os.chdir(arena)
        from env.env_systems.travel_planner_env.data_loader import load_travel_data
        from env.env_systems.travel_planner_env.combination import combine
        from env.env_systems.travel_planner_env import eval as official_eval

        rows = load_travel_data()
        if args.validate_targets:
            report = validate_target_parser(official_eval, rows)
            target = REPO / args.validation_out
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=2))
            print(
                f"validated {report['groups']} groups / {report['rounds']} rounds: "
                f"official recall {report['official_cell_recall']:.2%}; "
                f"false negatives {report['false_negative']}; "
                f"extra explicit targets {report['extra_explicit_targets']}")
            print(f"wrote {target}")
            return

        data_by_id = {int(row["id"]): row for row in rows}
        derive_arm(source_dir, output_dir, args.model, data_by_id,
                   args.source_arm, args.output_arm, args.use_scratchpad_final)
        combine(args.model, str(output_dir), str(output_dir / "submission"),
                mode="sole_planning")
    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    main()
