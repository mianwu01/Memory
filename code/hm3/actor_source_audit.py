"""Discover and independently validate one fixed-policy source-reliance case.

Unlike an executor-proposed suspect, candidate read sets come from the actor's own
responses. Source authorization is a controlled, external manifest for the whole
memory bundle. This demonstrates group reliance, not hidden intent or necessity
of a particular record in the original redundant full history.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

from .core import score_plan
from .llm import build_messages, parse_transactions
from .memory_reliance_demo import restore
from .replay import minimal_sufficient
from .structure_alignment import digest, ordered_reads


def run(args):
    from openai import OpenAI
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    candidate_file = out / "candidates.json"
    if candidate_file.exists():
        candidates = json.loads(candidate_file.read_text())
    else:
        rows = [json.loads(s) for s in Path(args.actor_ledger).read_text().splitlines()]
        rows = sorted((r for r in rows if r["event"] == "result" and r["score"]["ees"]
                       and any(a["name"] == "complete/parser" for a in r["arms"])),
                      key=lambda r: (r["seed"], r["condition"], r["episode"]))
        candidates = [{k: r[k] for k in ("domain", "seed", "condition", "episode", "reads", "prompt_sha256")}
                      for r in rows[:8]]
        candidate_file.write_text(json.dumps(candidates, indent=2))
    keys = [s.strip() for s in Path(args.key_file).read_text().splitlines() if s.strip() and not s.strip().startswith("#")]
    clients = [OpenAI(api_key=k, base_url=args.base_url, max_retries=0, timeout=90) for k in keys]
    lock = threading.Lock()
    calls = {"n": 0}
    ledger = out / "ledger.jsonl"
    if ledger.exists():
        raise ValueError("this fixed-case experiment is one-shot; existing ledger must not be overwritten")

    def ask(case, domain, ep, records, stage, repeat=0):
        reads = ordered_reads(ep, case["reads"]["objects"], records)
        with lock:
            if calls["n"] >= 64:
                raise RuntimeError("fixed 64-call limit reached")
            index = calls["n"]
            calls["n"] += 1
        messages = build_messages(domain, ep, reads, "verbose")
        try:
            r = clients[index % len(clients)].chat.completions.create(
                model="deepseek-v4-flash", messages=messages, temperature=0, max_tokens=16384,
                extra_body={"thinking": {"type": "disabled"}, "reasoning_effort": "none"})
            choice = r.choices[0]
            txns = parse_transactions(choice.message.content or "")
            score = score_plan(domain, ep, txns or [], reads)
            correct = bool(txns is not None and score["ees"])
            row = {"event": "result", "episode": ep.id, "condition": case["condition"], "stage": stage,
                   "repeat": repeat, "records": records, "correct": correct, "txns": txns,
                   "response": choice.message.content, "finish_reason": choice.finish_reason,
                   "returned_model": r.model, "prompt_sha256": digest(messages),
                   "cost_upper_accounting": (r.usage.prompt_tokens*2.5+r.usage.completion_tokens*10)/1e6}
        except Exception as exc:
            row = {"event": "infrastructure_failure", "episode": ep.id, "stage": stage, "repeat": repeat,
                   "error_type": type(exc).__name__, "status": getattr(exc, "status_code", None)}
            correct = None
        with lock:
            with ledger.open("a") as f:
                f.write(json.dumps(row)+"\n")
            print(json.dumps({"call": index+1, "stage": stage, "correct": correct, "episode": ep.id}), flush=True)
        if correct is None:
            raise RuntimeError("infrastructure failure; do not treat it as a failed policy decision")
        return row

    selected = None
    for case in candidates:
        domain, ep = restore(case)
        full = case["reads"]["records"]
        assert digest(build_messages(domain, ep, case["reads"], "verbose")) == case["prompt_sha256"]
        yes = ask(case, domain, ep, full, "qualification_full")["correct"]
        no = ask(case, domain, ep, [], "qualification_empty")["correct"]
        if yes and not no:
            selected = case
            break
    if selected is None:
        (out / "summary.json").write_text(json.dumps({"status": "no qualifying case in frozen candidates", "calls": calls["n"]}, indent=2))
        return
    selected["source_manifest"] = {r: "disallowed_external_solution_store" for r in full}
    selected["source_scope"] = "controlled provenance assignment for the whole supplied memory bundle"
    (out / "case.json").write_text(json.dumps(selected, indent=2))
    cache = {frozenset(full): True, frozenset(): False}

    def oracle(records):
        key = frozenset(records)
        if key not in cache:
            cache[key] = ask(selected, domain, ep, records, "discovery")["correct"]
        return cache[key]
    frontier, algorithm_calls = minimal_sufficient(full, oracle)
    (out / "discovery.json").write_text(json.dumps({"records": frontier, "algorithm_queries": algorithm_calls,
                                                   "unique_discovery_contexts": len(cache)}, indent=2))
    # These are new calls, never the cached discovery/qualification responses.
    validations = [("validation_full", full), ("validation_frontier", frontier), ("validation_source_blocked", [])]
    validations += [(f"validation_minus_{rid}", [r for r in frontier if r != rid]) for rid in frontier]
    if calls["n"] + 3*len(validations) > 64:
        raise RuntimeError("insufficient fixed call budget for complete validation")
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(ask, selected, domain, ep, records, stage, repeat)
                   for stage, records in validations for repeat in range(3)]
        rows = [f.result() for f in futures]
    summary = {stage: {"correct": sum(r["correct"] for r in rows if r["stage"] == stage),
                       "n": sum(r["stage"] == stage for r in rows),
                       "truncated": sum(r["finish_reason"] == "length" for r in rows if r["stage"] == stage)}
               for stage, _ in validations}
    summary["calls"] = calls["n"]
    summary["frontier_records"] = frontier
    summary["claim_scope"] = "Illustrative external-memory source-group reliance, conditional on this fixed policy and supplied source labels. No prevalence estimate, recovered hidden thought, general graph identification, or necessity of each frontier member in the original full history."
    (out / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--actor-ledger", default="results/real/hm3/alignment/actor_v1_closed/ledger.jsonl")
    p.add_argument("--key-file", default="api/api.txt")
    p.add_argument("--base-url", default="https://www.autodl.art/api/v1")
    p.add_argument("--out", default="results/real/hm3/alignment/actor_source_audit")
    run(p.parse_args())
