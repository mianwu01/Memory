"""Interleaved thinking on/off development checks, with a reusable API runner.

No correctness-based retries; all provider reasoning is stored as an experimental
artifact, not interpreted as a faithful account of internal causes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import threading
import time

from .continuation_actor import write_once
from .core import score_plan
from .domains import get_domain
from .generate import generate_split
from .llm import build_messages, parse_transactions
from .structure_alignment import digest, ordered_reads

CONFIG = dict(model="deepseek-v4-flash", endpoint="https://www.autodl.art/api/v1",
              temperature=0, max_tokens=32768, timeout=600, attempts=3, workers=6,
              seed=82, tasks=4, split="dev", repeats=3, shuffle_seed=2026092202)


def load_rows(path):
    return [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []


def run_jobs(out, jobs, scorer, key_file="api/api.txt", config=None):
    from openai import OpenAI
    config = dict(CONFIG if config is None else config)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    write_once(out / "protocol.json", config)
    for j in jobs:
        assert j["prompt_sha256"] == digest(j["messages"])
        write_once(out / "inputs" / f"{j['prompt_sha256']}.json", j["messages"])
    write_once(out / "manifest.json", [{k:v for k,v in j.items() if k != "messages"} for j in jobs])
    keys = [s.strip() for s in Path(key_file).read_text().splitlines()
            if s.strip() and not s.strip().startswith("#")]
    clients = [OpenAI(api_key=k, base_url=config["endpoint"],
                      timeout=config["timeout"], max_retries=0) for k in keys]
    ledger = out / "ledger.jsonl"
    requests = out / "requests.jsonl"
    old = {r["job_id"]:r for r in load_rows(ledger)}
    intents = load_rows(requests)
    counts = Counter(r["job_id"] for r in intents)
    lock = threading.Lock()

    def append(path, row):
        with path.open("a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()

    def worker(index, job):
        ident = job["job_id"]
        if ident in old and (old[ident]["event"] == "result" or not old[ident].get("retryable")):
            return old[ident]
        base = {k:v for k,v in job.items() if k != "messages"}
        row = {**base, "event":"unresolved_inflight"}
        for attempt in range(counts[ident], config["attempts"]):
            request = dict(model=config["model"], messages=job["messages"],
                           temperature=config["temperature"], max_tokens=config["max_tokens"],
                           extra_body={"thinking":{"type":job["mode"]}})
            with lock:
                append(requests, {**base, "attempt":attempt, "started_at":time.time(),
                                  "request_parameters":{k:v for k,v in request.items() if k != "messages"}})
            start = time.monotonic()
            try:
                response = clients[index % len(clients)].chat.completions.create(**request)
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                retryable = status in (408,429) or (isinstance(status,int) and status >= 500) or type(exc).__name__ in ("APIConnectionError","APITimeoutError")
                row = {**base, "event":"infrastructure_failure", "attempt":attempt,
                       "error_type":type(exc).__name__, "status":status, "retryable":retryable,
                       "seconds":time.monotonic()-start}
            else:
                choice = response.choices[0]
                text = choice.message.content or ""
                reasoning = getattr(choice.message,"reasoning_content",None) or getattr(choice.message,"reasoning",None) or ""
                usage = response.usage.model_dump() if response.usage else {}
                rtokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
                try:
                    score = scorer(job, text)
                except Exception as exc:
                    score = dict(correct=False, scoring_error=type(exc).__name__)
                row = {**base, "event":"result", "attempt":attempt, **score,
                       "response":text, "reasoning_content":reasoning,
                       "thinking_observed":bool(reasoning or rtokens), "usage":usage,
                       "finish_reason":choice.finish_reason, "returned_model":response.model,
                       "requested_model":config["model"], "seconds":time.monotonic()-start,
                       "provider_cost_cny":getattr(response,"cost_cny",None)}
            with lock:
                append(ledger,row)
                print(json.dumps({k:row.get(k) for k in ["case","arm","mode","repeat","event","correct","finish_reason","seconds"]}),flush=True)
            if row["event"] == "result" or not row.get("retryable"):
                return row
            time.sleep(2 ** attempt)
        return row

    order = list(enumerate(jobs))
    random.Random(config["shuffle_seed"]).shuffle(order)
    with ThreadPoolExecutor(max_workers=config["workers"]) as pool:
        rows = list(pool.map(lambda item:worker(*item),order))
    write_once(out / "completion.json", dict(expected=len(jobs), completed=sum(r["event"]=="result" for r in rows),
                                            unresolved=sum(r["event"]!="result" for r in rows)))
    return rows


def prepare():
    domain = get_domain("travel")
    episodes = generate_split(domain, CONFIG["seed"], "dev", CONFIG["tasks"])
    jobs = []
    for ep in episodes:
        for arm in ["full","no_history","policy_oracle"]:
            reads = ordered_reads(ep,ep.S0.objects,[r["rid"] for r in ep.H] if arm=="full" else [])
            messages = build_messages(domain,ep,reads,"verbose")
            if arm == "policy_oracle":
                messages[1]["content"] += "\n\nDIAGNOSTIC ONLY: the hidden entity policies are explicitly supplied below. Use them instead of inferring policies from history. This condition is an oracle capability check, not a memory method.\n"+json.dumps(ep.params,sort_keys=True)
            sha = digest(messages)
            for mode in ["enabled","disabled"]:
                for repeat in range(CONFIG["repeats"]):
                    jobs.append(dict(case=ep.id,arm=arm,mode=mode,repeat=repeat,reads=reads,
                                     messages=messages,prompt_sha256=sha,
                                     job_id=digest([ep.id,arm,mode,repeat,sha,CONFIG])))
    return episodes,jobs


def report(out):
    out = Path(out)
    manifest = json.loads((out/"manifest.json").read_text())
    last = {r["job_id"]:r for r in load_rows(out/"ledger.jsonl")}
    by = defaultdict(list)
    for j in manifest:
        by[j["mode"],j["arm"]].append(last.get(j["job_id"],{**j,"event":"missing"}))
    table = {}
    for (mode,arm),rr in by.items():
        valid = [r for r in rr if r["event"]=="result"]
        cases = sorted({r["case"] for r in rr})
        per = {c:dict(correct=sum(r.get("correct",False) for r in rr if r["case"]==c),
                      completed=sum(r["event"]=="result" for r in rr if r["case"]==c)) for c in cases}
        table[f"{mode}/{arm}"] = dict(correct=sum(r.get("correct",False) for r in valid),
            completed=len(valid),expected=len(rr),per_case=per,
            stable=sum(x["completed"]==3 and x["correct"]==3 for x in per.values()),
            truncated=sum(r.get("finish_reason")=="length" for r in valid),
            thinking_observed=sum(r.get("thinking_observed",False) for r in valid),
            models=dict(Counter(r["returned_model"] for r in valid)),
            input_tokens=sum(r["usage"].get("prompt_tokens",0) for r in valid),
            output_tokens=sum(r["usage"].get("completion_tokens",0) for r in valid),
            reasoning_tokens=sum((r["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens",0) or 0 for r in valid),
            errors=dict(Counter((r.get("score") or {}).get("error") for r in valid if not r.get("correct"))))
    f=table["enabled/full"]; e=table["enabled/no_history"]; o=table["enabled/policy_oracle"]
    passed = (all(x["completed"]==12 and x["truncated"]==0 for x in [f,e,o]) and
              f["correct"]>=10 and o["correct"]>=10 and f["stable"]>=3 and f["correct"]-e["correct"]>=4 and
              all(x["thinking_observed"]==12 for x in [f,e,o]) and
              len({m.casefold() for x in [f,e,o] for m in x["models"]})==1)
    result = dict(scope="Fixed four-case development diagnostic; no causal-discovery benefit claim",table=table,
                  actor_and_memory_gate_passed=passed,
                  all_attempts=len(load_rows(out/"ledger.jsonl")),old_results_reused=0)
    (out/"report.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result),flush=True)
    return result


def main(args):
    episodes,jobs=prepare()
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    write_once(out/"episodes.json",[ep.to_dict() for ep in episodes])
    if args.report:
        report(out); return
    lookup={ep.id:ep for ep in episodes}
    def scorer(job,text):
        txns=parse_transactions(text)
        score=score_plan(get_domain("travel"),lookup[job["case"]],txns or [],job["reads"])
        return dict(correct=bool(txns is not None and score["ees"]),parse_ok=txns is not None,txns=txns,score=score)
    config={**CONFIG,"source_hash":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "protocol":"docs/observed-memory-next-protocol-2026-09-22.md"}
    run_jobs(out,jobs,scorer,args.key_file,config)
    report(out)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",default="results/development/hm3/paired_actor_s82")
    p.add_argument("--key-file",default="api/api.txt")
    p.add_argument("--report",action="store_true")
    main(p.parse_args())
