"""Accounting sidecar for persisted usage gaps; no generation or score changes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unlogged_returned_response(trace):
    """Recognize only the observed post-create/pre-event failure stack."""
    frames = re.findall(r'File "[^"]*/(faithful_\w+\.py)", line \d+, in (\w+)\n\s+([^\n]+)', trace)
    target = [("faithful_memory.py", "measured", "reasoning_history.remember(choice.message)"),
              ("faithful_transport.py", "remember", "key = self.signature(calls)"),
              ("faithful_transport.py", "signature", "arguments = json.loads(arguments)")]
    return (any(frames[i:i + 3] == target for i in range(len(frames) - 2))
            and "json.decoder.JSONDecodeError:" in trace)


def failed_transport_receipts(row):
    attempts = ((row.get("transport") or {}).get("attempts", []) if row.get("event") == "llm"
                else row.get("attempts", []) if row.get("event") == "api_error" else []) or []
    return [item for item in attempts
            if item.get("error_type") or item.get("status_code") not in (None, 200)]


def collect(base):
    base = Path(base).resolve()
    protocol_path = base / "protocol.json"
    protocol = json.loads(protocol_path.read_text())
    # Ground the stack interpretation in the exact generating source used.
    for name in ("faithful_memory.py", "faithful_transport.py"):
        path = base / "frozen_source/code" / name
        if sha(path) != protocol["source_hashes"]["code/" + name]:
            raise ValueError("Generating source snapshot differs from protocol: " + name)
    source = (base / "frozen_source/code/faithful_memory.py").read_text()
    if not (source.index("result = create(*args, **kwargs)")
            < source.index("reasoning_history.remember(choice.message)")
            < source.index('runtime.event("llm", model=result.model')):
        raise ValueError("Post-create/pre-event accounting assumption does not hold")
    report = dict(schema="autodl-travel-usage-coverage/v1", created_at=time.time(),
                  analysis_sha256=sha(Path(__file__)), protocol_sha256=sha(protocol_path),
                  scope="all persisted attempts of registered cases; live scan is not atomic",
                  recorded_llm_responses=0, recorded_input_tokens=0, recorded_output_tokens=0,
                  recorded_llm_responses_without_usage=0, api_error_events_with_unknown_usage=0,
                  failed_transport_attempt_receipts=0, failed_transport_attempt_statuses={},
                  api_error_events_without_attempt_receipts=0,
                  minimum_unlogged_returned_responses=0, affected_attempts=[],
                  partial_trailing_records=[], monetary_cost=None,
                  note="Recorded token sums are lower bounds. Unknown response/failed-request usage is not zero; provider pricing is unknown.")
    seen = set()
    failed_statuses = Counter()
    for case in protocol["cases"]:
        folder = (base / "cases" / case["key"]).resolve()
        if not folder.is_relative_to(base / "cases") or folder in seen:
            raise ValueError("Invalid or duplicate registered case")
        seen.add(folder)
        for attempt in sorted(folder.glob("attempt_*")):
            if not attempt.is_dir():
                continue
            events = attempt / "events.jsonl"
            if events.exists():
                with events.open() as handle:
                    for number, line in enumerate(handle, 1):
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            if not line.endswith("\n"):
                                report["partial_trailing_records"].append(str(events.relative_to(base)))
                                continue
                            raise ValueError(f"Malformed event at {events}:{number}")
                        if row.get("event") == "api_error":
                            report["api_error_events_with_unknown_usage"] += 1
                            if not row.get("attempts"):
                                report["api_error_events_without_attempt_receipts"] += 1
                        for item in failed_transport_receipts(row):
                            report["failed_transport_attempt_receipts"] += 1
                            failed_statuses[str(item.get("status_code"))] += 1
                        if row.get("event") != "llm":
                            continue
                        report["recorded_llm_responses"] += 1
                        usage = row.get("usage")
                        if not usage:
                            report["recorded_llm_responses_without_usage"] += 1
                            continue
                        report["recorded_input_tokens"] += usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
                        report["recorded_output_tokens"] += usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
            trace = attempt / "error_traceback.txt"
            if trace.exists() and unlogged_returned_response(trace.read_text()):
                report["minimum_unlogged_returned_responses"] += 1
                report["affected_attempts"].append(dict(
                    case=case["key"], attempt=attempt.name, traceback_sha256=sha(trace),
                    minimum_unlogged_returned_responses=1, usage=None, finish_reason=None,
                    reason="Returned completion failed in reasoning_history.remember before its llm event; preceding logged response is not this response."))
    report["failed_transport_attempt_statuses"] = dict(failed_statuses)
    report["attempt_count_note"] = ("Failed attempt receipts include retries before successful responses and terminal API errors. "
                                    "Do not add the terminal api_error event count to receipt counts; these overlap. "
                                    "Receipts do not include absolute attempt timestamps; response-event time is not failure time.")
    report["known_usage_gaps"] = bool(report["minimum_unlogged_returned_responses"]
                                     or report["api_error_events_with_unknown_usage"]
                                     or report["failed_transport_attempt_receipts"]
                                     or report["recorded_llm_responses_without_usage"])
    out = base / "usage_coverage.json"
    temporary = out.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(out)
    (base / "usage_coverage.md").write_text(
        "# Travel 用量记录完整性\n\n"
        f"已记录 {report['recorded_llm_responses']} 条 LLM 响应，输入 {report['recorded_input_tokens']:,} tokens，"
        f"输出 {report['recorded_output_tokens']:,} tokens。\n\n"
        f"另有至少 {report['minimum_unlogged_returned_responses']} 条已返回响应在日志写入前解析失败，"
        f"以及 {report['failed_transport_attempt_receipts']} 次失败传输尝试记录（包含重试后成功的请求），用量未知。"
        f"最终 API 错误事件为 {report['api_error_events_with_unknown_usage']} 条，与尝试记录有重叠，不能相加。"
        "上述 token 总和是下界；未知用量不填零，费用也不作零值估计。\n\n"
        "本文件是独立计费覆盖附表，不修改冻结实验、失败处理或性能评分。逐例证据见 usage_coverage.json。\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.base)
    print(json.dumps({k: v for k, v in result.items() if k not in ("affected_attempts", "partial_trailing_records")}, indent=2))
