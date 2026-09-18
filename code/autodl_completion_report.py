"""Report every frozen Travel case's terminal outcome without partial scores.

This report is independent of the unchanged strict paired-score collector.
It never substitutes zero performance for a failed or missing execution.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import time

from autodl_report import (checked_child, combine_usage, digest, read_json,
                           registered_cases, validate_case)
from faithful_memory import ROOT, environment
from faithful_report import events, usage


POLICY = {
    "schema": "autodl-travel-failure-policy/v1",
    "scores": "none; no partial ranking, zero imputation, or performance bounds",
    "model_length": "an incomplete memory completion with observed finish_reason=length; actor length is an allowed scored actor outcome",
    "model_format": "explicit JSON decoding or registered metadata-parser fallback evidence; generic upstream fallback is insufficient",
    "transport_or_api": "api_error evidence, HTTP service failures, or SDK connection/timeout/authentication failures",
    "environment_or_implementation": "explicit import, file, configuration, or Python implementation exception",
    "mixed": "multiple independently evidenced failure categories; not assigned to model failures alone",
    "unknown": "a terminal failure without sufficient evidence for a narrower cause",
    "cost": "all attempts included; missing provider prices remain unavailable, never replaced with prior-provider prices",
}

ENV_ERRORS = {"KeyError", "ModuleNotFoundError", "ImportError", "FileNotFoundError",
              "PermissionError", "OSError", "TypeError", "AttributeError", "NameError"}
API_ERRORS = {"APIError", "APIStatusError", "APIConnectionError", "APITimeoutError",
              "AuthenticationError", "PermissionDeniedError", "RateLimitError",
              "InternalServerError", "BadRequestError"}


def classify_failure(status, rows, attempt_metadata=None):
    """Classify only observed evidence; never infer a cause from poor scores."""
    attempt_metadata = attempt_metadata or {}
    evidence = []
    labels = set()
    reasons = list(status.get("failures") or [])
    reasons.extend(str(row.get("reason", "")) for row in rows if row.get("event") == "invalid")
    for row in rows:
        if row.get("event") == "api_error":
            labels.add("transport_or_api")
            evidence.append({"kind": "api_error", "error_type": row.get("error_type"),
                             "status_code": row.get("status_code")})
        if row.get("event") == "llm" and row.get("phase") != "actor":
            if any(choice.get("finish_reason") == "length" for choice in row.get("choices", [])):
                labels.add("model_length")
                evidence.append({"kind": "memory_length", "phase": row.get("phase"),
                                 "max_tokens": row.get("max_tokens")})
    error_type = status.get("error_type") or attempt_metadata.get("error_type")
    if error_type in API_ERRORS or attempt_metadata.get("last_api_status") is not None:
        labels.add("transport_or_api")
        evidence.append({"kind": "exception_or_api_status", "error_type": error_type,
                         "status_code": attempt_metadata.get("last_api_status")})
    if error_type in ENV_ERRORS:
        labels.add("environment_or_implementation")
        evidence.append({"kind": "python_exception", "error_type": error_type})
    format_markers = ("JSONDecodeError", "A-Mem metadata heuristic fallback",
                      "LightMem update missing parsed result/usage")
    if error_type == "JSONDecodeError" or any(marker in reason for reason in reasons for marker in format_markers):
        labels.add("model_format")
        evidence.append({"kind": "explicit_parser_failure", "error_type": error_type,
                         "markers": sorted({marker for marker in format_markers
                                            if any(marker in reason for reason in reasons)})})
    return {"category": next(iter(labels)) if len(labels) == 1 else ("mixed" if labels else "unknown"),
            "evidenced_categories": sorted(labels), "evidence": evidence,
            "error_type": error_type}


def attempt_directory(case_folder, state):
    selected = state.get("selected_attempt")
    attempts = state.get("attempts") or []
    if not selected and attempts:
        selected = attempts[-1].get("directory")
    selected = selected or "attempt_0"
    path = checked_child(case_folder, selected)
    if path.parent != case_folder.resolve() or not path.name.startswith("attempt_"):
        raise ValueError("Invalid attempt selection")
    metadata = next((row for row in reversed(attempts) if row.get("directory") == selected), {})
    return path, metadata


def collect(base):
    base = Path(base).resolve()
    protocol = read_json(base / "protocol.json")
    if protocol.get("schema") != "autodl-travel-campaign/v1":
        raise ValueError("Unsupported campaign schema")
    cases = registered_cases(protocol)
    environment()
    from env.env_systems.travel_planner_env import eval as official
    gt, _, _ = official.load_ground_truth()
    people = defaultdict(set)
    for ident, person in gt:
        people[ident].add(person)
    global_integrity_errors = []
    graph = Path(protocol["graph_path"])
    graph = graph if graph.is_absolute() else ROOT / graph
    if not graph.exists() or digest(graph) != protocol["graph_sha256"]:
        global_integrity_errors.append("graph_artifact_differs_from_freeze")
    expected_dataset = protocol["source_hashes"].get("dataset:MemoryArena")
    if expected_dataset:
        actual_dataset = hashlib.sha256(json.dumps(official.load_travel_data(), sort_keys=True,
                                                   ensure_ascii=False).encode()).hexdigest()
        if actual_dataset != expected_dataset:
            global_integrity_errors.append("official_dataset_differs_from_freeze")
    actor_hashes = {str(path.relative_to(ROOT)): digest(path) for path in (
        ROOT / "benchmarks/MemoryArena/agent/travel_planner.py",
        ROOT / "benchmarks/MemoryArena/env/env_systems/travel_planner_env/prompts.py",
        ROOT / "benchmarks/MemoryArena/env/env_systems/travel_planner_env/tool_schemas.py")}
    report = dict(schema="autodl-travel-completion-report/v1", created_at=time.time(),
                  protocol_sha256=digest(base / "protocol.json"), analysis_sha256=digest(__file__),
                  failure_policy=POLICY, expected_cases=len(cases), terminal_cases=0,
                  validated_complete_cases=0, panels={}, cases={}, artifact_errors=[],
                  global_integrity_errors=global_integrity_errors,
                  performance_scores_included=False, zero_imputation=False,
                  prices_available_for_all_calls=False)
    seen_instances, all_usage = set(), []
    panel_usage, panel_complete_usage = defaultdict(list), defaultdict(list)
    panel_cases = defaultdict(list)
    for case in cases:
        key = case["key"]
        pair = (case["variant"], case["arm"])
        result = {**case, "state": "not_started", "terminal": False, "validated_complete": False}
        try:
            folder = checked_child(base / "cases", key)
            state_path = folder / "case_state.json"
            state = read_json(state_path) if state_path.exists() else {}
            result["state"] = state.get("state", "not_started")
            result["terminal"] = result["state"] in {"complete", "failed"}
            attempt, metadata = attempt_directory(folder, state)
            result["selected_or_latest_attempt"] = attempt.name
            selected_rows = []
            for candidate in sorted(folder.glob("attempt_*")):
                if not candidate.is_dir():
                    continue
                path = candidate / "events.jsonl"
                if not path.exists():
                    continue
                rows = events(path, active=True)
                if rows:
                    instance = rows[0]["instance"]
                    if instance in seen_instances:
                        raise ValueError("Duplicate attempt instance; refusing double-counted usage")
                    seen_instances.add(instance)
                    amount = usage(rows)
                    all_usage.append(amount)
                    panel_usage[pair].append(amount)
                if candidate.resolve() == attempt:
                    selected_rows = rows
            status_path = attempt / "status.json"
            status = read_json(status_path) if status_path.exists() else {}
            if result["state"] == "complete":
                if global_integrity_errors:
                    raise ValueError("Global frozen graph/dataset integrity failure")
                _, rows, hashes = validate_case(attempt, case, protocol, people[case["id"]], actor_hashes)
                result.update(validated_complete=True, category="complete", artifact_sha256=hashes,
                              selected_usage=usage(rows))
                panel_complete_usage[pair].append(result["selected_usage"])
            elif result["state"] == "failed":
                result.update(classify_failure(status, selected_rows, metadata))
                result["latest_attempt_usage"] = usage(selected_rows)
            else:
                result["category"] = "nonterminal"
        except (FileNotFoundError, KeyError, ValueError) as exc:
            # This is an artifact/reporting failure, never a zero model score.
            result.update(category="artifact_or_protocol_integrity", error_type=type(exc).__name__)
            report["artifact_errors"].append({"key": key, "error_type": type(exc).__name__})
        report["cases"][key] = result
        panel_cases[pair].append(result)
        report["terminal_cases"] += int(result["terminal"])
        report["validated_complete_cases"] += int(result["validated_complete"])
    for variant, arms in protocol["variants"].items():
        report["panels"][variant] = {}
        for arm in arms:
            pair = variant, arm
            rows = panel_cases[pair]
            complete = sum(row["validated_complete"] for row in rows)
            report["panels"][variant][arm] = dict(
                expected_cases=len(rows), terminal_cases=sum(row["terminal"] for row in rows),
                validated_complete_cases=complete, completion_rate=complete / len(rows),
                lifecycle_states=dict(Counter(row["state"] for row in rows)),
                outcomes=dict(Counter(row["category"] for row in rows)),
                complete_case_usage=combine_usage(panel_complete_usage[pair]),
                all_attempt_usage=combine_usage(panel_usage[pair]))
    report["all_scope_terminal"] = report["terminal_cases"] == len(cases)
    report["complete_success_matrix"] = report["validated_complete_cases"] == len(cases)
    report["all_attempt_usage"] = combine_usage(all_usage)
    report["cost_note"] = ("Only provider-reported or route-specific known amounts are accumulated; unpriced calls and "
                           "unknown-billing failures are separate. An accumulator of zero is not a zero-cost quote.")
    (base / "completion_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Travel 执行覆盖与失败报告", "",
             f"冻结范围 {len(cases)} cases；终态 {report['terminal_cases']}；完整且通过产物核对 {report['validated_complete_cases']}。",
             "此报告不输出部分任务的性能排名，不将模型失败、API 故障或未运行样本填成零分。", "",
             "| 条件 | 方法 | 完整/总数 | 终态 | 失败/未完成分类 | 全尝试输入 tokens | 全尝试输出 tokens | 无报价调用 |",
             "|---|---|---:|---:|---|---:|---:|---:|"]
    for variant, arms in report["panels"].items():
        for arm, row in arms.items():
            outcomes = "; ".join(f"{name}: {count}" for name, count in sorted(row["outcomes"].items()) if name != "complete") or "无"
            consumed = row["all_attempt_usage"]
            lines.append(f"| {variant} | {arm} | {row['validated_complete_cases']}/{row['expected_cases']} | "
                         f"{row['terminal_cases']} | {outcomes} | {consumed['input_tokens']} | "
                         f"{consumed['output_tokens']} | {consumed['unpriced_calls']} |")
    lines += ["", "模型长度失败限于 memory 操作的可见截断；actor 原预算截断仍按原 actor 规则评分。",
              "模型格式失败需要明确解析/元数据回退证据；泛化 upstream fallback 归证据不足。API/传输和环境/实现故障独立列出。",
              "金额未知时不套用其他接口价格；全部失败与被替代的尝试仍计入 token 与调用开销。",
              "完整配对结果须由各自事先冻结的完整面板检查通过后独立生成。"]
    (base / "completion_report.md").write_text("\n".join(lines) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.base)
    print(json.dumps({key: report[key] for key in ("expected_cases", "terminal_cases",
                     "validated_complete_cases", "all_scope_terminal", "complete_success_matrix")}, indent=2))


if __name__ == "__main__":
    main()
