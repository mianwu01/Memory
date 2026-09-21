"""Controlled source-reliance audit on a normal-looking correct HM3 decision.

Source status is assigned by an external controlled-case manifest, never inferred
from model thoughts. One case and one suspect are frozen before independent
validation. A failed case is reported, not replaced by another example.
"""
from __future__ import annotations

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from .core import score_plan
from .domains import get_domain
from .generate import generate_split
from .llm import build_messages, parse_transactions
from .scaling import augment_split
from .structure_alignment import CONDITIONS, digest, execute_reads, ordered_reads


def freeze_case(args, destination):
    if destination.exists():
        return json.loads(destination.read_text())
    ledger = [json.loads(s) for s in Path(args.actor_ledger).read_text().splitlines()]
    candidates = sorted((r for r in ledger if r["event"] == "result" and r["score"]["ees"]
                         and any(a["name"] == "complete/parser" for a in r["arms"])),
                        key=lambda r: (r["seed"], r["condition"], r["episode"]))
    if not candidates:
        raise ValueError("no completed correct reference input to construct the case")
    row = candidates[0]
    case = {"seed": row["seed"], "condition": row["condition"], "episode": row["episode"],
            "domain": row["domain"], "reads": row["reads"], "originating_prompt_sha256": row["prompt_sha256"],
            "selection": "first lexicographic completed correct no-type-filter actor input; one illustrative case",
            "source_policy": "controlled external source manifest; no claim of recovered private intent"}
    domain, ep = restore(case)
    records = row["reads"]["records"]
    effects = []
    for rid in records:
        reads = ordered_reads(ep, row["reads"]["objects"], [x for x in records if x != rid])
        effects.append((rid, bool(execute_reads(domain, ep, reads)["ees"])))
    # This executor proposal is only a candidate prior, not LLM-specific evidence.
    suspect = next((rid for rid, ok in effects if not ok), records[0])
    neutral = next((rid for rid, ok in effects if ok and rid != suspect), None)
    case.update({"suspect_record": suspect, "neutral_record": neutral,
                 "proposal_source": "deterministic executor single-record ablation, LLM validation still required",
                 "source_manifest": {rid: ("disallowed_external_answer_source" if rid == suspect else "allowed_history") for rid in records}})
    destination.write_text(json.dumps(case, indent=2))
    return case


def restore(case):
    domain = get_domain(case["domain"])
    index = int(case["episode"].rsplit("-", 1)[1])
    native = generate_split(domain, case["seed"], "test", index+1)
    if case["condition"] == "native":
        eps = native
    else:
        size, mix = CONDITIONS[case["condition"]]
        eps, _ = augment_split(domain, native, size, mix, f"test{case['seed']}")
    return domain, next(ep for ep in eps if ep.id == case["episode"])


def run(args):
    from openai import OpenAI
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    case = freeze_case(args, out / "case.json")
    domain, ep = restore(case)
    reference = case["reads"]
    assert digest(build_messages(domain, ep, reference, "verbose")) == case["originating_prompt_sha256"]
    conditions = {"baseline": (ep, reference)}
    for name, rid in (("without_suspect", case["suspect_record"]), ("without_neutral", case["neutral_record"])):
        if rid:
            conditions[name] = (ep, ordered_reads(ep, reference["objects"], [r for r in reference["records"] if r != rid]))
    variant = copy.deepcopy(ep)
    record = next(r for r in variant.H if r["rid"] == case["suspect_record"])
    changed_field = next((k for k, v in (record.get("delta") or {}).items()
                          if len(v) == 2 and isinstance(v[1], (int, float)) and not isinstance(v[1], bool)), None)
    if changed_field:
        old, new = record["delta"][changed_field]
        record["delta"][changed_field] = [old, new+30]
        if changed_field in record.get("payload", {}):
            record["payload"][changed_field] = new+30
        conditions["suspect_value_plus30"] = (variant, reference)
    inputs = [{"condition": name, "messages": build_messages(domain, e, reads, "verbose"), "reads": reads}
              for name, (e, reads) in conditions.items()]
    (out / "inputs.json").write_text(json.dumps(inputs, indent=1))
    keys = [s.strip() for s in Path(args.key_file).read_text().splitlines() if s.strip() and not s.strip().startswith("#")]
    clients = [OpenAI(api_key=k, base_url=args.base_url, max_retries=0, timeout=90) for k in keys]
    ledger = out / "ledger.jsonl"
    done = set()
    if ledger.exists():
        done = {(r["condition"], r["repeat"]) for r in map(json.loads, ledger.read_text().splitlines()) if r["event"] == "result"}

    def work(task):
        i, item, repeat = task
        try:
            r = clients[i % len(clients)].chat.completions.create(
                model="deepseek-v4-flash", messages=item["messages"], temperature=0, max_tokens=16384,
                extra_body={"thinking": {"type": "disabled"}, "reasoning_effort": "none"})
            reply = r.choices[0]
            txns = parse_transactions(reply.message.content or "")
            score = score_plan(domain, ep, txns or [], item["reads"])
            if txns is None:
                score["ees"] = False
            return {"event": "result", "condition": item["condition"], "repeat": repeat,
                    "score": score, "txns": txns, "response": reply.message.content,
                    "finish_reason": reply.finish_reason, "returned_model": r.model,
                    "input_tokens": r.usage.prompt_tokens, "output_tokens": r.usage.completion_tokens,
                    "cost_upper_accounting": (r.usage.prompt_tokens*2.5+r.usage.completion_tokens*10)/1e6}
        except Exception as exc:
            return {"event": "infrastructure_failure", "condition": item["condition"], "repeat": repeat,
                    "error_type": type(exc).__name__, "status": getattr(exc, "status_code", None)}
    tasks = [(i*args.repeats+r, item, r) for i, item in enumerate(inputs) for r in range(args.repeats)
             if (item["condition"], r) not in done]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for row in pool.map(work, tasks):
            with ledger.open("a") as f:
                f.write(json.dumps(row)+"\n")
            print(json.dumps({k: v for k, v in row.items() if k in ("event", "condition", "repeat", "cost_upper_accounting")}), flush=True)
    rows = [json.loads(s) for s in ledger.read_text().splitlines()]
    summary = {}
    for name in conditions:
        rs = [r for r in rows if r["condition"] == name and r["event"] == "result"]
        summary[name] = {"n": len(rs), "correct": sum(r["score"]["ees"] for r in rs),
                         "truncated": sum(r["finish_reason"] == "length" for r in rs)}
    summary["interpretation"] = "One controlled source-reliance example; source authorization is supplied, not inferred. Fresh validation may fail and must be reported. No claim of detecting lying, hidden thoughts, or the entire causal graph."
    summary["cost_upper_accounting"] = sum(r.get("cost_upper_accounting", 0) for r in rows)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--actor-ledger", default="results/real/hm3/alignment/actor_v1_closed/ledger.jsonl")
    p.add_argument("--key-file", default="api/api.txt")
    p.add_argument("--base-url", default="https://www.autodl.art/api/v1")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--out", default="results/real/hm3/alignment/source_reliance_demo")
    run(p.parse_args())
