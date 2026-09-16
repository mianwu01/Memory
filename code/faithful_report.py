"""Account for every recorded attempt; score only complete matched scope."""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import statistics
import time

from faithful_memory import ARMS, ROOT, environment

RATES = {"uncached_input": 2.0, "cached_input": 0.04, "output": 8.0}


def events(path, *, active=False):
    lines = path.read_text().splitlines(keepends=True)
    result = []
    for i, line in enumerate(lines):
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            if active and i == len(lines) - 1 and not line.endswith("\n"):
                break
            raise
    return result


def usage(rows):
    summary = {"calls": 0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
               "estimated_cny": 0.0, "provider_reported_cny": 0.0,
               "reasoning_tokens": 0, "nonthinking_requested_but_reasoning_observed_calls": 0,
               "transport_attempts": 0, "unknown_billing_attempts": 0,
               "unpriced_calls": 0, "api_errors_unknown_usage": 0, "length_responses": 0}
    phases = {}
    for row in rows:
        attempts = (row.get("transport") or {}).get("attempts", []) if row["event"] == "llm" else (row.get("attempts") or [])
        summary["transport_attempts"] += len(attempts)
        summary["unknown_billing_attempts"] += sum(bool(a.get("billing_unknown")) for a in attempts)
        if row["event"] == "api_error":
            summary["api_errors_unknown_usage"] += 1
        if row["event"] != "llm":
            continue
        u = row.get("usage")
        if not u:
            summary["api_errors_unknown_usage"] += 1
            continue
        inp, out = u["prompt_tokens"], u["completion_tokens"]
        reasoning = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        summary["reasoning_tokens"] += reasoning
        summary["nonthinking_requested_but_reasoning_observed_calls"] += int(
            reasoning > 0 and row.get("thinking") == {"type": "disabled"})
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens")
        if cached is None:
            cached = u.get("prompt_cache_hit_tokens", 0)
        if not 0 <= cached <= inp:
            raise ValueError("Invalid cached usage")
        endpoint = row.get("endpoint", "https://tokenrhythm.studio/v1")
        billed = row.get("provider_cost_cny")
        if billed is not None and row.get("billing_pending") is False:
            cost = float(billed)
            summary["provider_reported_cny"] += cost
        elif endpoint.rstrip("/") == "https://tokenrhythm.studio/v1":
            cost = ((inp - cached) * RATES["uncached_input"] + cached * RATES["cached_input"] + out * RATES["output"]) / 1e6
        else:
            cost = 0.0
            summary["unpriced_calls"] += 1
        phase = "actor" if row["phase"] == "actor" else "memory_or_native_qa"
        p = phases.setdefault(phase, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cny": 0.0})
        for d in (summary, p):
            d["calls"] += 1
            d["input_tokens"] += inp
            d["output_tokens"] += out
            d["estimated_cny"] += cost
        summary["cached_input_tokens"] += cached
        summary["length_responses"] += sum(c["finish_reason"] == "length" for c in row["choices"])
    summary["phases"] = phases
    summary["estimated_cny"] = round(summary["estimated_cny"], 8)
    return summary


def probe_rows(probe):
    """Normalize saved probes; model-list GETs are not generation attempts."""
    if "requests" in probe or "method" in probe:
        for index, item in enumerate(probe.get("requests", [probe])):
            if item.get("method") != "POST" or item.get("path") != "/chat/completions":
                continue
            try:
                response = json.loads(item.get("body", "{}"))
            except json.JSONDecodeError:
                response = {}
            yield index, {"response": response, "status_code": item.get("status")}
    else:
        yield from enumerate(probe.get("rows", [probe]))


def ledger():
    paths = sorted(p for folder in (ROOT / "results/development", ROOT / "results/real")
                   for family in folder.glob("faithful_memory*") for p in family.rglob("events.jsonl"))
    attempts = []
    seen = set()
    for p in paths:
        rows = events(p, active=True)
        if not rows:
            continue
        instance = rows[0]["instance"]
        if instance in seen:
            raise ValueError("Duplicate attempt instance; do not charge copied artifacts twice")
        seen.add(instance)
        attempts.append({"path": str(p.relative_to(ROOT)), "arm": rows[0]["arm"],
                         "episode": rows[0]["episode"], **usage(rows)})
    added = sum(a["estimated_cny"] for a in attempts)
    probes = []
    probe_paths = [ROOT / "results/development" / name for name in (
        "faithful_memory_backup_probe_2026_09_15.json", "faithful_memory_protocol_probe_2026_09_15.json")]
    probe_paths += sorted((ROOT / "results/development").glob("faithful_memory*/*access_diagnostic.json"))
    for probe_path in probe_paths:
        if not probe_path.exists():
            continue
        probe = json.loads(probe_path.read_text())
        for index, item in probe_rows(probe):
            response = item.get("response", {})
            billed = response.get("cost_cny")
            amount = float(billed) if billed is not None and response.get("billing_pending") is False else None
            probes.append({"path": str(probe_path.relative_to(ROOT)), "row": index,
                           "provider_reported_cny": amount, "usage": response.get("usage"),
                           "status_code": item.get("status_code"),
                           "billing_unknown": amount is None})
            added += amount or 0
    return {"as_of": time.time(), "rates_cny_per_million": RATES, "invoice_verified": False,
            "scope": "all faithful_memory event logs, including rejected/failed/development attempts",
            "attempts": attempts, "separate_probes": probes, "remediation_recorded_cny": round(added, 8),
            "previous_recorded_cny": 276.482109,
            "cumulative_recorded_cny": round(276.482109 + added, 8),
            "unknown_usage_errors": sum(a["api_errors_unknown_usage"] for a in attempts) + sum(p["usage"] is None for p in probes),
            "unknown_billing_attempts": sum(a["unknown_billing_attempts"] for a in attempts),
            "unpriced_calls": sum(a["unpriced_calls"] for a in attempts),
            "limitations": "Provider cost_cny with billing_pending=false takes precedence; TokenRhythm fallback uses advertised rates. Unpriced calls are counted, not assigned another provider's rate. Diagnostic probes outside event logs are listed separately."}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(base):
    environment()
    from env.env_systems.travel_planner_env import eval as official
    from arena_e2e_score import per_episode_metrics, bootstrap_mean_ci
    protocol = json.loads((base / "protocol.json").read_text())
    data_sha = hashlib.sha256(json.dumps(official.load_travel_data(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if data_sha != protocol["source_hashes"]["dataset:MemoryArena"]:
        raise ValueError("Official evaluation dataset differs from frozen generation dataset")
    gt, _, _ = official.load_ground_truth()
    expected_ids = set(protocol["episode_ids"])
    actor_hashes = {str(p.relative_to(ROOT)): digest(p) for p in (
        ROOT / "benchmarks/MemoryArena/agent/travel_planner.py",
        ROOT / "benchmarks/MemoryArena/env/env_systems/travel_planner_env/prompts.py",
        ROOT / "benchmarks/MemoryArena/env/env_systems/travel_planner_env/tool_schemas.py")}
    combined = base / "analysis"
    combined.mkdir(exist_ok=True)
    report = {"complete": False, "protocol_sha256": digest(base / "protocol.json"),
              "episode_ids": sorted(expected_ids), "arms": {}, "errors": [],
              "scope": protocol["interpretation"]}
    for arm in protocol["arms"]:
        records, all_events, hashes = [], [], {}
        for ident in sorted(expected_ids):
            folder = base / "travel" / f"{arm}_{ident}"
            try:
                status = json.loads((folder / "status.json").read_text())
                if not status["complete"]:
                    raise ValueError("incomplete method execution")
                prov = json.loads((folder / "provenance.json").read_text())
                for name, sha in prov["source_hashes"].items():
                    if protocol["source_hashes"][name] != sha:
                        raise ValueError("generation source differs from freeze")
                for name in ("model", "endpoint", "actor_thinking"):
                    if prov[name] != protocol[name]:
                        raise ValueError("generation setting differs from freeze")
                rows = events(folder / "events.jsonl")
                counts = Counter(r["event"] for r in rows)
                if dict(counts) != status["counts"] or counts.get("invalid", 0):
                    raise ValueError("event integrity failure")
                contract = [r for r in rows if r["event"] == "actor_contract"]
                if len(contract) != 1 or contract[0]["hashes"] != actor_hashes:
                    raise ValueError("original actor contract mismatch")
                if any(contract[0][k] for k in ("custom_decoder", "custom_prompt", "tool_filter")):
                    raise ValueError("custom actor behavior")
                if any(r["phase"] != "actor" and c["finish_reason"] == "length"
                       for r in rows if r["event"] == "llm" for c in r["choices"]):
                    raise ValueError("incomplete memory operation")
                paths = list((folder / "plans/submission").glob("*_submission.jsonl"))
                if len(paths) != 1:
                    raise ValueError("ambiguous submission")
                parsed = [json.loads(s) for s in paths[0].read_text().splitlines() if s.strip()]
                if len(parsed) != 1 or parsed[0]["id"] != ident:
                    raise ValueError("submission episode mismatch")
                person_ids = [p["person_idx"] for p in parsed[0]["persons"]]
                expected_people = {p for i, p in gt if i == ident}
                if len(person_ids) != len(set(person_ids)) or set(person_ids) != expected_people:
                    raise ValueError("submission drops people from official denominator")
                records.extend(parsed)
                all_events.extend(rows)
                for p in [folder / "events.jsonl", folder / "status.json", folder / "provenance.json", paths[0]]:
                    hashes[str(p.relative_to(base))] = digest(p)
            except (FileNotFoundError, KeyError, ValueError) as exc:
                report["errors"].append({"arm": arm, "id": ident, "error": str(exc)})
        report["arms"][arm] = {"usage": usage(all_events), "accepted_episodes": [r["id"] for r in records],
                               "artifact_sha256": hashes}
        if len(records) == len(expected_ids):
            submission = combined / f"{arm}_submission.jsonl"
            submission.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    if report["errors"]:
        (base / "integrity_report.json").write_text(json.dumps(report, indent=2))
        raise RuntimeError("Incomplete matched scope; inspect integrity_report.json. No paired ranking produced.")
    for arm, row in report["arms"].items():
        submission = combined / f"{arm}_submission.jsonl"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            row["official_metrics"] = official.evaluate(str(submission), model_name=protocol["model"], memory_system=arm)
            row["per_episode"] = per_episode_metrics(official, submission)
        (combined / f"{arm}_evaluator.txt").write_text(output.getvalue())
        row["episode_mean"] = {k: statistics.mean(e[k] for e in row["per_episode"].values()) for k in ("ps", "sps", "sr")}
    report["paired_comparisons"] = {}
    for baseline in [a for a in protocol["arms"] if a != "ours"]:
        left, right = report["arms"]["ours"]["per_episode"], report["arms"][baseline]["per_episode"]
        comparison = {}
        for metric in ("ps", "sps", "sr"):
            diffs = {str(i): left[str(i)][metric] - right[str(i)][metric] for i in sorted(expected_ids)}
            comparison[metric] = {"episode_deltas": diffs, "mean_delta_points": statistics.mean(diffs.values()),
                                  "bootstrap_95": bootstrap_mean_ci(list(diffs.values()), seed=20260915)}
        report["paired_comparisons"]["ours_minus_" + baseline] = comparison
    report["complete"] = True
    report["analysis_sha256"] = digest(Path(__file__))
    (base / "paired_results.json").write_text(json.dumps(report, indent=2))
    lines = ["# 完整实现与原版 actor 的配对评估", "", protocol["interpretation"], "",
             "每个方法采用原始完整计划输出；表中 PS 按 person 汇总，SPS/SR 使用官方定义。",
             "Actor 达到原生 token 上限的输出原样评分；不修复答案、不删除失败样本。", "",
             "| 方法 | PS % | SPS % | SR % | 调用 | Actor 长度上限次数 | usage 估算元 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for arm, row in report["arms"].items():
        m, u = row["official_metrics"], row["usage"]
        lines.append(f"| {arm} | {m['ps']:.2f} | {m['sps']:.2f} | {m['sr']:.2f} | {u['calls']} | {u['length_responses']} | {u['estimated_cny']:.4f} |")
    lines += ["", "使用复用的 10 个 graph holdout episodes，各一次实现；不构成未见测试集上的确认性结论。",
              "Mem0 是官方 OSS；A-Mem 使用作者论文仓库 robust 路径；LightMem 使用完整核心机制。",
              "Travel 的公共写回接口与 session 边界属于明确登记的任务接口，不等于重现作者论文分数。",
              "A-Mem 保留作者算法、提示词及原生 1000-token 输出预算；Mem0/LightMem 使用记录的 16000 上限。",
              "Memory 通过经失败请求对照验证的 reasoning_effort=none 关闭推理；若中转仍报告 memory reasoning tokens，该执行不能验收。",
              "真实数据 identifiability、结构必要性和风险缓解需要独立证据；本表不能自动证明这些主张。",
              "费用包含 actor 与 memory 写入/更新，优先使用中转 cost_cny（billing_pending=false）；仅 TokenRhythm 缺该字段时使用其公开单价，未知价格不套用其他中转单价。未进行账单对账。",
              "开发、失败与额外请求见 faithful_remediation_usage.json；未把开发结果拼入主表。", ""]
    (base / "results.md").write_text("\n".join(lines))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path)
    args = ap.parse_args()
    account = ledger()
    target = args.base.resolve() if args.base else ROOT / "results/development"
    (target / "faithful_remediation_usage.json").write_text(json.dumps(account, indent=2))
    if args.base:
        result = collect(target)
        print(json.dumps({"complete": result["complete"], "report": str(target / "results.md")}))
    print(json.dumps({k: account[k] for k in ("remediation_recorded_cny", "cumulative_recorded_cny", "unknown_usage_errors")}))


if __name__ == "__main__":
    main()
