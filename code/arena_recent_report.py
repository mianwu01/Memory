"""Audit complete paired scope and combine actor + memory usage; no API calls."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

from arena_recent_memory import ARMS


def read_events(path):
    if not path.exists():
        return [], 0
    rows, malformed = [], 0
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            malformed += 1
    return rows, malformed


def metered_usage(rows):
    """CNY public price; prompt_tokens already includes cached input."""
    result = dict(responses_with_usage=0, input_tokens=0, output_tokens=0,
                  cached_input_tokens=0, cache_usage_unspecified=0,
                  estimated_cny=0.0, api_seconds=0.0,
                  explicit_rate_limit_rejections=0, provider_cost_responses=0,
                  transport_failures_without_usage=0, pre_stream_connection_failures=0,
                  provider_reported_cny=0.0)
    durations = []
    for row in rows:
        attempts = ((row.get("transport_metrics") or {}).get("attempts") or
                    row.get("transport_attempts") or [])
        failed = [a for a in attempts if a.get("status_code") != 200]
        result["transport_failures_without_usage"] += len(failed)
        result["explicit_rate_limit_rejections"] += sum(a.get("status_code") == 429 for a in failed)
        result["pre_stream_connection_failures"] += sum(
            a.get("error_type") in ("APIConnectionError", "APITimeoutError") and
            a.get("stream_opened") is False for a in failed)
        usage = row.get("usage")
        if not usage:
            continue
        inp, out = int(usage["prompt_tokens"]), int(usage["completion_tokens"])
        hit = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        if hit is None:
            hit = usage.get("prompt_cache_hit_tokens")
        if hit is None:
            hit = 0
            result["cache_usage_unspecified"] += 1
        if not 0 <= hit <= inp:
            raise ValueError("invalid cache-token accounting")
        result["responses_with_usage"] += 1
        result["input_tokens"] += inp
        result["output_tokens"] += out
        result["cached_input_tokens"] += hit
        result["estimated_cny"] += (2 * (inp - hit) + 0.04 * hit + 8 * out) / 1e6
        if row.get("provider_cost_cny") is not None:
            result["provider_cost_responses"] += 1
            result["provider_reported_cny"] += float(row["provider_cost_cny"])
        durations.append(float(row.get("duration_seconds", 0)))
    result["api_seconds"] = sum(durations)
    result["median_api_seconds"] = statistics.median(durations) if durations else None
    result["max_api_seconds"] = max(durations) if durations else None
    return result


def audit_family(base):
    base = Path(base)
    protocol = json.loads((base / "protocol.json").read_text())
    if protocol["endpoint"] != "https://tokenrhythm.studio/v1" or protocol["model"] != "deepseek-flash":
        raise ValueError("This public rate snapshot applies only to TokenRhythm deepseek-flash")
    ids = set(protocol["episode_ids"])
    rounds = {101: 7, 111: 6, 112: 8, 113: 8}
    report = dict(schema="memoryarena-recent-audit/v1", family=str(base),
                  phase=protocol["phase"], episode_ids=sorted(ids), model=protocol["model"],
                  endpoint=protocol["endpoint"], currency="CNY", pricing_source="https://tokenrhythm.studio/models",
                  rates_per_million={"uncached_input": 2, "cached_input": 0.04, "output": 8},
                  invoice_verified=False, arms={}, paired_scope_complete=False,
                  limitations=["Usage-based estimate, not reconciled billing; interrupted/retried requests may lack usage.",
                               "Scores are descriptive paired replication on reused historical holdout IDs."])
    all_good = True
    for arm in ARMS:
        path = base / "e2e" / arm
        actor, a_bad = read_events(path / "llm_call_usage.jsonl")
        memory, m_bad = read_events(path / "memory_events.jsonl")
        memory_calls = [r for r in memory if r.get("event") == "llm"]
        done = {int(p.stem.removeprefix("generated_plan_")) for p in path.glob("generated_plan_*.json")}
        issues = []
        if done != ids:
            issues.append("incomplete_or_unexpected_episode_set")
        if a_bad or m_bad:
            issues.append("malformed_ledger")
        failures = [r for r in actor + memory if r.get("event") in {"api_error", "llm_error", "metadata_error"}]
        if failures:
            issues.append("api_or_metadata_errors")
        if any(not r.get("usage") for r in actor + memory_calls):
            issues.append("response_usage_missing")
        returned = sorted({r.get("returned_model", "") for r in actor + memory_calls})
        if any(m != protocol["model"] for m in returned):
            issues.append("returned_model_mismatch")
        episodes = {}
        for episode in sorted(ids):
            a = [r for r in actor if r.get("episode_id") == episode]
            m = [r for r in memory if r.get("episode_id") == episode]
            writes = [r for r in m if r.get("event") == "write"]
            reads = [r for r in m if r.get("event") == "retrieve"]
            instances = {r["instance"] for r in m}
            attempts = {r["attempt_id"] for r in a}
            expected_rounds = set(range(1, rounds[episode] + 1))
            if len(writes) != rounds[episode] + 1 or len(reads) != rounds[episode]:
                issues.append(f"memory_round_coverage:{episode}")
            if len(instances) != 1 or len(attempts) != 1:
                issues.append(f"instance_or_attempt_coverage:{episode}")
            if {r.get("round_idx") for r in a} != expected_rounds:
                issues.append(f"actor_round_coverage:{episode}")
            episodes[str(episode)] = dict(actor=metered_usage(a), memory=metered_usage(m),
                writes=len(writes), reads=len(reads), instances=sorted(instances), attempts=sorted(attempts))
        report["arms"][arm] = dict(complete=not issues, issues=issues, completed_ids=sorted(done),
            actor=metered_usage(actor), memory=metered_usage(memory),
            recorded_api_errors=len(failures), returned_models=returned,
            actor_finish_reasons=dict(Counter(r.get("finish_reason", "error") for r in actor)),
            memory_finish_reasons=dict(Counter(r.get("finish_reason", "error") for r in memory_calls)),
            per_episode=episodes)
        all_good &= not issues
    report["paired_scope_complete"] = bool(all_good)
    report["latency_basis"] = "Client-observed duration, including configured rate-scheduler and retry waits"
    report["estimated_cny_all_logged_responses"] = sum(
        r[phase]["estimated_cny"] for r in report["arms"].values() for phase in ("actor", "memory"))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    args = ap.parse_args()
    report = audit_family(args.base)
    (args.base / "usage_integrity_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"complete": report["paired_scope_complete"],
        "estimated_cny": report["estimated_cny_all_logged_responses"],
        "arms": {k: {"complete": v["complete"], "issues": v["issues"],
                     "calls": v["actor"]["responses_with_usage"] + v["memory"]["responses_with_usage"]}
                 for k, v in report["arms"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
