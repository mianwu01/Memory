"""Rebuild qualification audit without making API calls."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .actor_gate import qualify
from .core import score_plan
from .domains import get_domain
from .generate import generate_split
from .llm import parse_transactions
from .structure_alignment import digest


def assess_model_identity(rows):
    """Post-run metadata correction; preserve the original literal-ID decision."""
    literal = qualify(rows)
    normalized_rows = [{**r, "returned_model": r["returned_model"].casefold()}
                       if r["event"] == "result" else r for r in rows]
    corrected = qualify(normalized_rows)
    return {**literal, "strict_literal_model_id_gate_passed": literal["passed"],
            "passed": corrected["passed"],
            "normalized_returned_models": corrected["returned_models"],
            "model_identity_amendment": "docs/actor-gate-model-id-amendment-2026-09-22.md; post-run casefold only, original IDs retained"}


def summarize(directory):
    p = Path(directory)
    config = json.loads((p/"protocol.json").read_text())
    manifest = json.loads((p/"manifest.json").read_text())
    ledger = [json.loads(s) for s in (p/"ledger.jsonl").read_text().splitlines()]
    requests = [json.loads(s) for s in (p/"requests.jsonl").read_text().splitlines()]
    by_id = {}
    for r in ledger:
        assert r["job_id"] in {m["job_id"] for m in manifest}
        if r["job_id"] in by_id and by_id[r["job_id"]]["event"] == "result":
            raise AssertionError("Successful API response repeated")
        by_id[r["job_id"]] = r
    # Never drop missing cases from the denominator.
    rows = [by_id.get(m["job_id"], {**m, "event": "not_completed"}) for m in manifest]
    report = assess_model_identity(rows)
    eps = {ep.id:ep for ep in generate_split(get_domain("travel"), 80, "dev", 10)}
    report["task_profile"] = dict(history_records=[len(ep.H) for ep in eps.values()],
                                  oracle_action_counts=[len(ep.A) for ep in eps.values()],
                                  empty_repair_tasks=sum(not ep.A for ep in eps.values()),
                                  scope="Synthetic short-history HM3 only; not long-history or native-agent qualification")
    outcomes = Counter()
    verified = 0
    for r in rows:
        inp = p/"inputs"/f"{r['prompt_sha256']}.json"
        assert digest(json.loads(inp.read_text())) == r["prompt_sha256"]
        if r["event"] != "result":
            continue
        transactions = parse_transactions(r["response"])
        try:
            score = score_plan(get_domain("travel"), eps[r["episode"]], transactions or [], r["reads"])
            correct = bool(transactions is not None and score["ees"])
        except (KeyError, ValueError, TypeError, AttributeError, IndexError):
            correct = False
        assert correct == r["correct"]
        verified += 1
        score = r.get("score") or {}
        if r["finish_reason"] == "length":
            outcomes["truncated"] += 1
        elif not r.get("parse_ok") or r.get("score_error"):
            outcomes["format_or_schema"] += 1
        elif r["correct"]:
            outcomes["correct"] += 1
        elif not score.get("legal"):
            outcomes["illegal_transaction"] += 1
        elif score.get("affected_f1") != 1:
            outcomes["wrong_affected_objects"] += 1
        elif score.get("value_accuracy") != 1:
            outcomes["wrong_payload"] += 1
        else:
            outcomes["other_exact_state_or_receipt_mismatch"] += 1
    results = [r for r in ledger if r["event"] == "result"]
    cached = sum(max(r["usage"].get("prompt_cache_hit_tokens", 0) or 0,
                     (r["usage"].get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0)
                 for r in results)
    reason = sum((r["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0 for r in results)
    est = ((report["input_tokens"]-cached)*2.5+cached*.25+report["output_tokens"]*10)/1e6
    completed_attempts = {(r["job_id"], r["attempt"]) for r in ledger}
    inflight = [r for r in requests if (r["job_id"], r["attempt"]) not in completed_attempts]
    report.update(dict(outcomes=dict(outcomes), rescored_responses=verified,
                       recorded_attempts=len(requests), failed_attempts=len(ledger)-len(results),
                       unresolved_inflight=len(inflight), reasoning_tokens=reason, cached_input_tokens=cached,
                       legacy_rate_scenario_usd=est,
                       cost_note="Legacy scenario, not confirmed Flash pricing or provider invoice; failed/in-flight usage unknown",
                       config=config, directory=str(p)))
    (p/"acceptance_audit.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


def main(args):
    reports = [summarize(p) for p in args.directories]
    combined = dict(versions=reports,
                    current_actor_passed=reports[-1]["passed"],
                    native_task_gate_passed=False, discovery_started=False, audit_started=False,
                    fresh_responses=sum(r["completed"] for r in reports),
                    input_tokens=sum(r["input_tokens"] for r in reports),
                    output_tokens=sum(r["output_tokens"] for r in reports),
                    legacy_rate_scenario_usd=sum(r["legacy_rate_scenario_usd"] for r in reports))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out/"report.json").write_text(json.dumps(combined, indent=2)+"\n")
    lines = ["# Flash thinking actor qualification", "",
             "Development only; fixed seed 80, first 10 cases, 3 independent calls each. "
             "This is not a structure experiment or a comparison with historical non-thinking runs.", "",
             "| version | correct / 30 | stable cases / 10 | truncations | thinking observed | gate |",
             "|---|---:|---:|---:|---:|---|"]
    for r in reports:
        lines.append(f"| {Path(r['directory']).name} | {r['correct']} | {r['stable_cases']} | "
                     f"{r['truncations']} | {r['thinking_observed']}/{r['completed']} | {'PASS' if r['passed'] else 'FAIL / incomplete'} |")
    lines.extend(["", "## Every frozen case", "", "| case | " + " | ".join(Path(r['directory']).name for r in reports) + " |",
                  "|---|" + "---:|"*len(reports)])
    for case in sorted({c for r in reports for c in r["per_case"]}):
        cells = [f"{r['per_case'].get(case, {}).get('correct',0)}/{r['per_case'].get(case, {}).get('completed',0)}" for r in reports]
        lines.append("| " + case + " | " + " | ".join(cells) + " |")
    lines.extend(["", f"Fresh responses: {combined['fresh_responses']}; input/output tokens: "
                  f"{combined['input_tokens']}/{combined['output_tokens']}.",
                  f"Legacy-rate scenario: ${combined['legacy_rate_scenario_usd']:.4f}; not an actual invoice.", "",
                  "The initial literal-ID gate failed because returned IDs differed only in case. "
                  "The post-run acceptance report uses casefold for model identity; original IDs and the literal decision remain in JSON. "
                  "See actor-gate-model-id-amendment-2026-09-22.md. No API responses were repeated.", "",
                  "Gate 2 is not passed. No discovery or audit calls were started. See native-task-screen-2026-09-22.md."])
    (out/"report.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({k:v for k,v in combined.items() if k != "versions"}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directories", nargs="+")
    p.add_argument("--out", default="results/development/hm3/actor_gate_summary")
    main(p.parse_args())
