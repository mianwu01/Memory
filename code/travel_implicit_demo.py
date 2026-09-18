"""Export a preselected implicit-Travel case from real traces, without API calls.

Missing or failed arms remain visible. By default select episode 101's first
round referring to a non-base historical traveler, using source queries only.
Never choose a successful round after looking at model outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from arena_causal_memory import parse_plan
from faithful_memory import ROOT
from t0_travel import parse_episode
from travel_implicit import HistoryNotes, strip_future_notices


DEFAULT_ROWS = ROOT / "results/development/travel_implicit_v1/original_rows.json"
DEFAULT_BASE = ROOT / "results/development/autodl_travel_dev"


def fixed_round(rows_path: Path, episode: int) -> int:
    row = next(r for r in json.loads(rows_path.read_text()) if int(r["id"]) == episode)
    raw = {**row, "questions": [q["query"] if isinstance(q, dict) else q for q in row["questions"]]}
    parsed = parse_episode(raw)
    for round_ in parsed["rounds"]:
        if any(any(n != parsed["base_name"] for n in s["srcs"]) for s in round_["sentences"]):
            return round_["t"]
    for round_ in parsed["rounds"]:
        if any(s["is_dep"] for s in round_["sentences"]):
            return round_["t"]
    raise ValueError("Episode has no historical dependency")


def _source(path: Path) -> dict[str, str]:
    try:
        name = str(path.relative_to(ROOT))
    except ValueError:
        name = str(path)
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    rows = []
    for i, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise
            # An actively written last line is pending, not an observed event.
    return rows


def read_case(directory: Path, round_index: int) -> dict[str, Any]:
    event_path = directory / "events.jsonl"
    rows = _events(event_path)
    reads = [r for r in rows if r["event"] == "retrieve" and r["round"] == round_index]
    writes = [r for r in rows if r["event"] == "write" and r["round"] == round_index]
    if len(reads) > 1 or len(writes) > 1:
        raise ValueError(f"Ambiguous fixed-round events in {directory}")
    status_path = directory / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {"complete": False, "pending": True}
    case: dict[str, Any] = {
        "directory": str(directory), "status": status, "round_observed": bool(reads),
        "answer_observed": bool(writes), "source": _source(event_path) if event_path.exists() else None,
        "query": reads[0]["query"] if reads else None,
        "memory_context": reads[0]["text"].split("</memory_context>")[0] + "</memory_context>" if reads else None,
        "selected_cells": reads[0].get("selected_cells") if reads else None,
        "actual_generated_plan": json.loads(writes[0]["text"]).get("final_plan") if writes else None,
        "failures": [r for r in rows if r["event"] in {"invalid", "api_error", "actor_generation_failure"}],
    }
    notes = HistoryNotes()
    cells = set()
    base_name = None
    for event in rows:
        if event["event"] == "retrieve" and event["round"] == round_index:
            break
        if event["event"] != "write" or event["round"] >= round_index:
            continue
        chunk = json.loads(event["text"])
        notes.add_chunk(event["text"])
        name = chunk.get("name", "")
        if chunk.get("is_base_person"):
            base_name = name
        cells.update((name, day, slot) for day, slot in parse_plan(chunk.get("final_plan", "")))
    if reads:
        resolved = notes.resolve(case["query"])
        case["active_current_query"] = strip_future_notices(case["query"])
        case["historical_requirements"] = list(resolved.notices)
        case["resolved_selection_query"] = resolved.selection_query
        case["context_characters"] = len(case["memory_context"])
    available = {cell for cell in cells if cell[0] != base_name}
    case["available_nonbase_cells"] = sorted(available)
    if case["selected_cells"] is not None:
        selected = {tuple(cell) for cell in case["selected_cells"]}
        case["discarded_nonbase_cells"] = sorted(available - selected)
        case["selection_is_subset_of_written_history"] = selected <= available
    actor_calls = [r for r in rows if r["event"] == "llm" and r["round"] == round_index and r["phase"] == "actor"]
    case["actor_usage"] = {"calls": len(actor_calls),
                           "prompt_tokens": sum((r.get("usage") or {}).get("prompt_tokens", 0) for r in actor_calls),
                           "completion_tokens": sum((r.get("usage") or {}).get("completion_tokens", 0) for r in actor_calls)}
    plan_path = directory / "plans" / f"generated_plan_{rows[0]['episode']}.json" if rows else None
    if plan_path and plan_path.exists():
        plan = json.loads(plan_path.read_text())
        case["actor_round_status"] = next((s for s in plan.get("scratchpads", []) if s.get("round") == round_index), None)
        # Preserve round success/error without duplicating enormous tool traces.
        if case["actor_round_status"]:
            case["actor_round_status"] = {k: v for k, v in case["actor_round_status"].items() if k != "scratchpad"}
    return case


def build(base: Path, out: Path, rows_path: Path = DEFAULT_ROWS, episode: int = 101,
          round_index: int | None = None, arms: tuple[str, ...] = ("ours", "query_only", "noGcompact"),
          variant: str = "implicit", repeat: int = 0, attempt: int = 0) -> dict[str, Any]:
    automatic = round_index is None
    if round_index is None:
        round_index = fixed_round(rows_path, episode)
    cases = {arm: read_case(base / "cases" / variant / arm / str(episode) / f"r{repeat}" / f"attempt_{attempt}", round_index)
             for arm in arms}
    queries = {c["query"] for c in cases.values() if c["query"] is not None}
    if len(queries) > 1:
        raise ValueError("Fixed paired methods received different current queries")
    evidence = {
        "episode": episode, "round": round_index, "variant": variant, "repeat": repeat, "attempt": attempt,
        "selection_rule": "First original query referencing a non-base historical traveler; fallback first dependency round. Selected before reading outcomes."
                          if automatic else "Caller-fixed round index; no outcome-based selection performed by exporter.",
        "scope": "Observed official actor runs with each method's own preceding outputs. Missing or failed arms remain visible. Not a same-history causal intervention.",
        "complete": all(c["status"].get("complete") and c["answer_observed"] for c in cases.values()),
        "same_observed_query": len(queries) <= 1, "cases": cases,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    esc = html.escape
    cards = []
    def pre(value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        return "<pre>" + esc(text if value is not None else "[尚无实际记录]") + "</pre>"
    for arm, case in cases.items():
        label = "已完成" if case["status"].get("complete") else "失败／未完成" if not case["status"].get("pending") else "运行中／尚未启动"
        cards.append("<section><h2>" + esc(arm) + " · " + label + "</h2>"
                     + "<h3>此前写入的要求</h3>" + pre(case.get("historical_requirements"))
                     + "<h3>选择的历史单元格</h3>" + pre(case["selected_cells"])
                     + "<details><summary>舍弃的非 base 单元格</summary>" + pre(case.get("discarded_nonbase_cells")) + "</details>"
                     + "<h3>actor 实际生成的计划</h3>" + pre(case["actual_generated_plan"])
                     + "<details><summary>实际可见 memory context</summary>" + pre(case["memory_context"]) + "</details>"
                     + "<details><summary>调用用量、执行状态和失败</summary>" + pre({k: case.get(k) for k in ("actor_usage", "actor_round_status", "status", "failures")}) + "</details></section>")
    query = next((c.get("active_current_query") for c in cases.values() if c.get("active_current_query")), None)
    page = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Travel 历史依赖：固定案例</title><style>body{font:16px/1.6 system-ui,sans-serif;background:#f3f5f8;color:#172536;margin:28px}h1{font-size:26px}h2{font-size:20px}h3{font-size:16px}main{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}section{background:white;padding:18px;border-radius:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf1f5;padding:12px;font:13px/1.5 ui-monospace,monospace;max-height:420px;overflow:auto}summary{cursor:pointer}@media(max-width:1000px){main{grid-template-columns:1fr}}</style>"""
    page += f"<h1>Travel · episode {episode} · round {round_index} · {esc(variant)}</h1>"
    page += "<p>固定选择第一个引用非 base 历史旅客的请求。三种方法保留相同的历史要求解析，query_only 仅移除学得的边。以下全部为实际记录；未完成或失败不会补成成功。</p>"
    page += "<h2>当前请求（排除留给未来旅客的 notices）</h2>" + pre(query)
    page += "<main>" + "".join(cards) + "</main><p>各方法使用自身先前生成的计划。actor 执行成功不等于 evaluator 满分；完整评分见正式结果表。来源、hash 和失败状态见 evidence.json。</p></html>"
    (out / "comparison.html").write_text(page)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rows", type=Path, default=DEFAULT_ROWS)
    parser.add_argument("--episode", type=int, default=101)
    parser.add_argument("--round", type=int)
    parser.add_argument("--arms", default="ours,query_only,noGcompact")
    parser.add_argument("--variant", default="implicit")
    parser.add_argument("--repeat", type=int, default=0)
    parser.add_argument("--attempt", type=int, default=0)
    args = parser.parse_args()
    evidence = build(args.base, args.out, args.rows, args.episode, args.round,
                     tuple(args.arms.split(",")), args.variant, args.repeat, args.attempt)
    print(json.dumps({"episode": evidence["episode"], "round": evidence["round"],
                      "complete": evidence["complete"], "out": str(args.out)}))


if __name__ == "__main__":
    main()
