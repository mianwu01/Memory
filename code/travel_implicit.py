"""Lossless, actor-ready history-dependent MemoryArena Travel variant.

Only the timing of constraint disclosure changes. A named dependency line is
quoted verbatim in a notice written with its latest already-seen source person;
the target's later query contains only a target-cell pointer. Answers, public
base plans, the official actor, tools and evaluator remain unchanged.

This is a history-lookup task, not evidence that learned graphs are necessary.
The three structured arms must share HistoryNotes, including the zero-edge arm.
No function in this module reads answers to transform or resolve a query.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from t0_travel import norm, parse_episode
from travel_r import pointer


VERSION = "travel-implicit-history-v1"
NOTE_START = "<future_traveler_notices>"
NOTE_END = "</future_traveler_notices>"
NOTE_PREFIX = "Traveler notice: "
NOTE_HELP = (
    "These are advance notices for OTHER travelers. Preserve them for those "
    "travelers' later requests; do not apply them to the current traveler's plan. "
    "Each quoted requirement uses the named target traveler's own first-person voice."
)
POINTER_HELP = (
    "Apply my previously announced requirements from the stored traveler notices "
    "when completing the arrangements referenced below."
)
_NOTE_BLOCK = re.compile(re.escape(NOTE_START) + r"\n.*?\n" + re.escape(NOTE_END), re.S)


def strip_future_notices(query: str) -> str:
    """Current-person requirements only, excluding notices for future people."""
    return _NOTE_BLOCK.sub("", query).strip()


def extract_notices(query: str) -> list[dict[str, Any]]:
    notices = []
    for block in _NOTE_BLOCK.findall(query):
        for line in block.splitlines():
            if line.startswith(NOTE_PREFIX):
                notice = json.loads(line[len(NOTE_PREFIX):])
                if set(notice) != {"target", "requirement"}:
                    raise ValueError("Unexpected traveler-notice fields")
                if not all(isinstance(notice[k], str) for k in notice):
                    raise ValueError("Traveler notices must contain text only")
                notices.append(notice)
    return notices


def _append_notices(query: str, notices: list[dict[str, str]]) -> str:
    if not notices:
        return query
    lines = [query.rstrip(), NOTE_START, NOTE_HELP]
    lines.extend(NOTE_PREFIX + json.dumps(n, ensure_ascii=False) for n in notices)
    lines.append(NOTE_END)
    return "\n".join(lines)


def _raw_row(row: dict[str, Any]) -> dict[str, Any]:
    """Accept both HuggingFace rows and official env reset observations."""
    questions = [q["query"] if isinstance(q, dict) else q for q in row["questions"]]
    # Official loader rows use id, but TravelPlannerEnvironment.reset emits
    # group_id. Normalize only the parser view; preserve the caller's schema.
    ident = row.get("id", row.get("group_id"))
    if ident is None:
        raise ValueError("Travel row/observation must identify id or group_id")
    return {**row, "id": ident, "questions": questions}


def transform_row(row: dict[str, Any], variant: str = "implicit") -> dict[str, Any]:
    """Copy a raw/converted row and move dependencies without changing gold."""
    if variant not in {"implicit", "explicit"}:
        raise ValueError(f"Unknown Travel variant: {variant}")
    raw = _raw_row(row)
    if any(NOTE_START in q for q in raw["questions"]) or NOTE_START in raw["base_person"]["query"]:
        raise ValueError("Travel implicit transformation may only be applied once")
    ep = parse_episode(raw)
    notices: list[list[dict[str, str]]] = [[] for _ in ep["names"]]
    new_queries = []
    for round_ in ep["rounds"]:
        # Rewrite one original line at a time rather than reconstructing the
        # query from the parser: all nondependency text is retained exactly.
        replacements: dict[str, str] = {}
        for sentence in round_["sentences"]:
            if not sentence["is_dep"]:
                continue
            source_index = max(ep["names"].index(n) for n in sentence["srcs"])
            if source_index >= round_["t"]:
                raise ValueError("Notice host must be written before target reads")
            notices[source_index].append({"target": round_["name"], "requirement": sentence["text"]})
            replacements[sentence["text"]] = pointer(sentence)
        lines = [replacements.get(norm(line).strip(), line) if variant == "implicit" else line
                 for line in raw["questions"][round_["t"] - 1].splitlines()]
        if replacements and variant == "implicit":
            lines.insert(1, POINTER_HELP)
        new_queries.append("\n".join(lines))
    out = copy.deepcopy(row)
    out["base_person"]["query"] = _append_notices(raw["base_person"]["query"], notices[0])
    for i, query in enumerate(new_queries):
        query = _append_notices(query, notices[i + 1])
        if isinstance(out["questions"][i], dict):
            out["questions"][i]["query"] = query
        else:
            out["questions"][i] = query
    return out


def transform_observation(observation: dict[str, Any], variant: str = "implicit") -> dict[str, Any]:
    """Hook EnvironmentClient.reset output (loader-only replacement is insufficient)."""
    return transform_row(observation, variant)


def install_variant(run_travel: Any, variant: str) -> None:
    """Apply the identical variant at loader and actual actor-observation boundary."""
    if variant == "original":
        return
    if variant not in {"implicit", "explicit"}:
        raise ValueError(f"Unknown Travel variant: {variant}")
    if getattr(run_travel, "_travel_variant", None):
        raise ValueError("Travel variant is already installed")
    original_loader = run_travel.load_travel_data
    original_reset = run_travel.EnvironmentClient.reset

    def load_variant():
        return [transform_row(row, variant) for row in original_loader()]

    def reset_variant(client, *args, **kwargs):
        observation = original_reset(client, *args, **kwargs)
        return transform_observation(observation, variant)

    run_travel.load_travel_data = load_variant
    run_travel.EnvironmentClient.reset = reset_variant
    run_travel._travel_variant = variant


@dataclass(frozen=True)
class ResolvedNotices:
    selection_query: str
    memory_text: str
    notices: tuple[dict[str, Any], ...]


class HistoryNotes:
    """Index only notices actually written to this method's memory so far.

    This deterministic lookup is deliberately shared by ours/noGcompact/
    query_only. It reconstructs requirements, not answers or a gold graph.
    """

    def __init__(self) -> None:
        self._by_target: dict[str, list[dict[str, Any]]] = {}
        self._writes = 0

    def add_chunk(self, text: str) -> str:
        """Store notices and return chunk with current-only query for cell parsing."""
        chunk = json.loads(text)
        for notice in extract_notices(str(chunk.get("query", ""))):
            entry = {**notice, "write_round": self._writes, "written_with": str(chunk.get("name", ""))}
            self._by_target.setdefault(notice["target"], []).append(entry)
        self._writes += 1
        clean = {**chunk, "query": strip_future_notices(str(chunk.get("query", "")))}
        return json.dumps(clean, ensure_ascii=False)

    def resolve(self, query: str) -> ResolvedNotices:
        current = strip_future_notices(query)
        name_match = re.match(r"I am (\w+)\.", norm(current))
        target = name_match.group(1) if name_match else ""
        notices = tuple(copy.deepcopy(self._by_target.get(target, [])))
        # Selection sees resolved requirements as in the explicit task. Actor
        # sees those requirements inside memory, never injected as new user text.
        requirements = [n["requirement"] for n in notices]
        existing = {norm(line).strip() for line in current.splitlines()}
        missing = [r for r in requirements if r not in existing]
        selection = current + ("\n" + "\n".join(missing) if missing else "")
        lines = ["<stored_requirements>"] if notices else []
        if notices:
            lines.append(f"Requirements announced earlier by {target} (quoted in {target}'s voice):")
            lines.extend(requirements)
            lines.append("</stored_requirements>")
        return ResolvedNotices(selection, "\n".join(lines), notices)


def training_rows(rows: list[dict[str, Any]], variant: str = "implicit") -> list[dict[str, Any]]:
    """Parsed historical requirement view for train-only indicator discovery.

    Input rows must already be restricted to the train split by the caller.
    Notes are disclosed only after their host write, just as at runtime. A dummy
    empty plan suffices: this view never reads completed plan values or answers.
    """
    output = []
    for row in rows:
        transformed = _raw_row(transform_row(row, variant))
        notes = HistoryNotes()
        notes.add_chunk(json.dumps({"name": row["base_person"]["name"],
                                    "query": transformed["base_person"]["query"]}))
        resolved_queries = []
        for query in transformed["questions"]:
            resolved = notes.resolve(query)
            resolved_queries.append(resolved.selection_query)
            target = re.match(r"I am (\w+)\.", norm(query)).group(1)
            notes.add_chunk(json.dumps({"name": target, "query": query}))
        output.append({**transformed, "questions": resolved_queries})
    return output


def audit_rows(original: list[dict[str, Any]], transformed: list[dict[str, Any]]) -> dict[str, Any]:
    """CPU-only checks of disclosure, losslessness and write-before-read order."""
    if len(original) != len(transformed):
        raise ValueError("Row counts differ")
    stats = {"rows": len(original), "rounds": 0, "moved_requirements": 0,
             "residual_current_dependencies": 0, "missing_requirements": 0,
             "answers_changed": 0, "base_plans_changed": 0, "future_note_reads": 0}
    for before, after in zip(original, transformed):
        raw_before, raw_after = _raw_row(before), _raw_row(after)
        ep = parse_episode(raw_before)
        audit_row = {**raw_after, "questions": [strip_future_notices(q) for q in raw_after["questions"]]}
        audit_ep = parse_episode(audit_row)
        stats["answers_changed"] += int(before.get("answers") != after.get("answers"))
        stats["base_plans_changed"] += int(before["base_person"].get("daily_plans") != after["base_person"].get("daily_plans"))
        index = HistoryNotes()
        index.add_chunk(json.dumps({"name": ep["names"][0], "query": raw_after["base_person"]["query"]}))
        for source, target in zip(ep["rounds"], audit_ep["rounds"]):
            stats["rounds"] += 1
            requirements = [s["text"] for s in source["sentences"] if s["is_dep"]]
            stats["moved_requirements"] += len(requirements)
            stats["residual_current_dependencies"] += sum(s["is_dep"] for s in target["sentences"])
            resolved = index.resolve(raw_after["questions"][source["t"] - 1])
            stats["missing_requirements"] += sum(r not in [n["requirement"] for n in resolved.notices] for r in requirements)
            stats["future_note_reads"] += sum(n["write_round"] >= source["t"] for n in resolved.notices)
            index.add_chunk(json.dumps({"name": source["name"], "query": raw_after["questions"][source["t"] - 1]}))
    stats["passed"] = all(stats[k] == 0 for k in (
        "residual_current_dependencies", "missing_requirements", "answers_changed",
        "base_plans_changed", "future_note_reads"))
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    original = json.loads(args.rows.read_text())
    transformed = [transform_row(r) for r in original]
    audit = {"variant": VERSION, "source_sha256": hashlib.sha256(args.rows.read_bytes()).hexdigest(),
             "checks": audit_rows(original, transformed),
             "evaluation": "unchanged official MemoryArena full-plan evaluator",
             "claim_boundary": "History lookup; learned-graph necessity must be tested against zero-edge lookup."}
    if not audit["checks"]["passed"]:
        raise RuntimeError(json.dumps(audit, indent=2))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(transformed, indent=2, ensure_ascii=False))
    audit["transformed_sha256"] = hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.audit.write_text(json.dumps(audit, indent=2))
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
