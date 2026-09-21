"""Bounded Flash thinking qualification; no discovery calls. See frozen protocol."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import threading
import time

from .core import score_plan
from .domains import get_domain
from .generate import generate_split
from .llm import build_messages, parse_transactions
from .structure_alignment import digest, ordered_reads
from .continuation_actor import write_once

ROOT = Path(__file__).resolve().parents[2]
CONFIG = dict(model="deepseek-v4-flash", endpoint="https://www.autodl.art/api/v1",
              temperature=0, max_tokens=32768, extra_body={"thinking": {"type": "enabled"}},
              seed=80, split="dev", tasks=10, repeats=3, timeout=600,
              infrastructure_attempts=3, workers=3, prompt="v1", serialization="verbose",
              pass_correct=27, pass_stable=9)


def qualify(rows):
    results = [r for r in rows if r["event"] == "result"]
    by_case = {}
    for r in results:
        by_case.setdefault(r["episode"], []).append(r)
    stable = sum(len(rs) == 3 and all(r["correct"] for r in rs) for rs in by_case.values())
    models = sorted({r["returned_model"] for r in results})
    correct = sum(r["correct"] for r in results)
    trunc = sum(r["finish_reason"] == "length" for r in results)
    thinking = sum(r["thinking_observed"] for r in results)
    passed = (len(results) == 30 and correct >= 27 and stable >= 9 and trunc == 0
              and thinking == 30 and len(models) == 1 and "flash" in models[0].lower())
    return dict(passed=passed, completed=len(results), expected=30, correct=correct,
                stable_cases=stable, expected_cases=10, truncations=trunc,
                thinking_observed=thinking, returned_models=models,
                per_case={k: dict(completed=len(v), correct=sum(r["correct"] for r in v))
                          for k, v in sorted(by_case.items())},
                infrastructure_unresolved=sum(r["event"] != "result" for r in rows),
                input_tokens=sum((r.get("usage") or {}).get("prompt_tokens", 0) for r in results),
                output_tokens=sum((r.get("usage") or {}).get("completion_tokens", 0) for r in results),
                discovery_authorized_by_this_gate=False,
                scope="Development actor only; native task requires independent qualification")


def prepare(out, suffix_file=None):
    suffix = Path(suffix_file).read_text() if suffix_file else ""
    config = {**CONFIG, "prompt_suffix": suffix,
              "source_hashes": {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                                ["code/hm3/actor_gate.py", "code/hm3/llm.py", "code/hm3/core.py",
                                 "code/hm3/generate.py", "code/hm3/dgp_travel.py",
                                 "docs/actor-gates-protocol-2026-09-22.md"]}}
    write_once(out/"protocol.json", config)
    domain = get_domain("travel")
    episodes = generate_split(domain, 80, "dev", 10)
    write_once(out/"episodes.json", [ep.to_dict() for ep in episodes])
    jobs = []
    for ep in episodes:
        reads = ordered_reads(ep, ep.S0.objects, [r["rid"] for r in ep.H])
        messages = build_messages(domain, ep, reads, "verbose")
        if suffix:
            messages[0]["content"] += "\n" + suffix
        sha = digest(messages)
        write_once(out/"inputs"/f"{sha}.json", messages)
        for repeat in range(3):
            jobs.append(dict(episode=ep.id, repeat=repeat, reads=reads, messages=messages,
                             prompt_sha256=sha, job_id=digest([ep.id, repeat, sha, config]), ep=ep))
    write_once(out/"manifest.json", [{k:v for k,v in j.items() if k not in ("ep", "messages")} for j in jobs])
    return jobs


def run(args):
    out = Path(args.out)
    jobs = prepare(out, args.suffix_file)
    if args.prepare:
        print(json.dumps({"prepared": len(jobs), "out": str(out)}), flush=True)
        return
    from openai import OpenAI
    keys = [s.strip() for s in Path(args.key_file).read_text().splitlines()
            if s.strip() and not s.strip().startswith("#")]
    clients = [OpenAI(api_key=k, base_url=CONFIG["endpoint"], timeout=600, max_retries=0) for k in keys]
    lock = threading.Lock()
    ledger = out/"ledger.jsonl"
    previous = [json.loads(s) for s in ledger.read_text().splitlines()] if ledger.exists() else []
    intents_path = out/"requests.jsonl"
    intents = [json.loads(s) for s in intents_path.read_text().splitlines()] if intents_path.exists() else []
    done = {r["job_id"]: r for r in previous if r["event"] == "result"}
    failures = {r["job_id"]: r for r in previous if r["event"] != "result"}
    counts = {}
    for r in intents:
        counts[r["job_id"]] = max(counts.get(r["job_id"], 0), r["attempt"] + 1)

    def append(path, row):
        with path.open("a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()

    def worker(index, job):
        ident = job["job_id"]
        if ident in done:
            return done[ident]
        if ident in failures and not failures[ident].get("retryable"):
            return failures[ident]
        base = {k:v for k,v in job.items() if k not in ("ep", "messages")}
        start_attempt = counts.get(ident, 0)
        if start_attempt >= 3:
            return failures.get(ident, {**base, "event": "unresolved_inflight"})
        for attempt in range(start_attempt, 3):
            with lock:
                append(intents_path, {**base, "attempt": attempt, "started_at": time.time(),
                                     "requested_model": CONFIG["model"]})
            start = time.monotonic()
            try:
                response = clients[index % len(clients)].chat.completions.create(
                    model=CONFIG["model"], messages=job["messages"], temperature=0,
                    max_tokens=CONFIG["max_tokens"], extra_body=CONFIG["extra_body"])
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                retryable = status in (408, 429) or (isinstance(status, int) and status >= 500) or type(exc).__name__ in ("APIConnectionError", "APITimeoutError")
                row = {**base, "attempt": attempt, "event": "infrastructure_failure",
                       "error_type": type(exc).__name__, "status": status, "retryable": retryable,
                       "seconds": time.monotonic()-start}
            else:
                choice = response.choices[0]
                content = choice.message.content or ""
                reasoning = getattr(choice.message, "reasoning_content", None) or getattr(choice.message, "reasoning", None) or ""
                usage = response.usage.model_dump() if response.usage else {}
                rtokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
                txns = parse_transactions(content)
                try:
                    score = score_plan(get_domain("travel"), job["ep"], txns or [], job["reads"])
                    correct, score_error = bool(txns is not None and score["ees"]), None
                except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
                    score, correct, score_error = {}, False, type(exc).__name__
                row = {**base, "attempt": attempt, "event": "result", "correct": correct,
                       "score": score, "score_error": score_error, "parse_ok": txns is not None,
                       "txns": txns, "response": content, "reasoning_content": reasoning,
                       "reasoning_characters": len(reasoning), "thinking_observed": bool(reasoning or rtokens),
                       "usage": usage, "finish_reason": choice.finish_reason,
                       "returned_model": response.model, "requested_model": CONFIG["model"],
                       "provider_cost_cny": getattr(response, "cost_cny", None),
                       "seconds": time.monotonic()-start}
            with lock:
                append(ledger, row)
                print(json.dumps({k:row.get(k) for k in ("episode", "repeat", "attempt", "event", "correct", "thinking_observed", "finish_reason", "seconds")}), flush=True)
            if row["event"] == "result" or not row.get("retryable"):
                return row
            time.sleep(2 ** attempt)
        return row

    first = worker(0, jobs[0])
    if first["event"] != "result" or not first.get("thinking_observed") or "flash" not in first.get("returned_model", "").lower():
        write_once(out/"interface_stop.json", {"reason": "transport/model/thinking not confirmed", "job_id": jobs[0]["job_id"]})
        return
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = [first] + list(pool.map(lambda pair: worker(*pair), enumerate(jobs[1:], 1)))
    report = qualify(rows)
    write_once(out/"report.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument("--key-file", default="api/api.txt")
    p.add_argument("--suffix-file")
    p.add_argument("--prepare", action="store_true")
    run(p.parse_args())
