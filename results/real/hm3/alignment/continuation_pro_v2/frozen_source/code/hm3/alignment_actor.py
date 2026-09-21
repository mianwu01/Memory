"""Bounded concurrent actor checks for the frozen alignment controls.

Credentials never enter output, argv, or exception strings. Exact duplicate full
messages within an episode share one call, explicitly recorded as such. This
tests selection equivalence without inventing independent replications.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import threading
import time

from .core import score_plan
from .domains import get_domain
from .generate import generate_split
from .llm import build_messages, parse_transactions, COST_RATES_USD_PER_MILLION
from .reader_repair import component_precedent_records
from .scaling import augment_split
from .structure_alignment import CONDITIONS, digest, matched_records, ordered_reads, permutations, selections
from .tcd_logs import type_edges_with_lag, type_vocab

ARMS = ["grace_open_x3/parser", "complete/parser", "query_only/parser", "full",
        "permuted_17/matched", "permuted_29/matched", "permuted_43/matched",
        "random_17/matched", "bm25_16", "recency_16", "complete/key2", "component2"]


def close_referents(ep, reads):
    """Same referent + one-hop context rule as the legacy graph_closed arm."""
    ids = set(reads["records"])
    referents = {r["object_id"] for r in ep.H if r["rid"] in ids and r["object_id"] in ep.S0.objects}
    objects = set(reads["objects"]) | referents
    for oid in referents:
        for targets in ep.S0.get(oid).links.values():
            objects.update(x for x in targets if x in ep.S0.objects)
    return ordered_reads(ep, objects, reads["records"])


def prepare(args):
    import tiktoken
    encoding = tiktoken.get_encoding("cl100k_base")
    fitted = json.loads(Path(args.graphs).read_text())["runs"]
    jobs = []
    for name in args.domains:
        domain = get_domain(name)
        for seed in args.seeds:
            native = generate_split(domain, seed, "test", args.n_eval)
            types = type_vocab(native)
            entry = fitted[f"{name}/seed{seed}"]["encodings"]["event"]
            graphs = {"complete": {(a, b): 1 for a in types for b in types if a != b}, "query_only": {}}
            for mode in ("grace_open", "grace_open_x3", "grace_pcmci_g2"):
                graphs[mode] = type_edges_with_lag(entry[mode])
            for pseed, mapping in permutations(types).items():
                graphs[f"permuted_{pseed}"] = {(mapping[a], mapping[b]): lag for (a, b), lag in graphs["grace_open_x3"].items()}
            for condition in args.conditions:
                target, mix = CONDITIONS[condition]
                eps, _ = (native, {}) if condition == "native" else augment_split(domain, native, target, mix, f"test{seed}")
                for ep in eps:
                    arms = selections(domain, ep, graphs, False, encoding)
                    objects = arms["complete/parser"][0]["objects"]
                    ids = component_precedent_records(domain, ep, objects)
                    arms["component2"] = (ordered_reads(ep, objects, ids), {})
                    if args.state_context == "referent_closed":
                        arms = {a: (close_referents(ep, r), m) for a, (r, m) in arms.items()}
                    reference = arms["grace_open_x3/parser"][0]
                    eligible = [r["rid"] for r in ep.H if r["object_id"] in reference["objects"]]
                    for pseed in (17, 29, 43):
                        preferred = arms[f"permuted_{pseed}/parser"][0]["records"]
                        arms[f"permuted_{pseed}/matched"] = matched_records(ep, reference, preferred, pseed, encoding, eligible)
                    arms["random_17/matched"] = matched_records(ep, reference, [], 17, encoding, eligible)
                    grouped = {}
                    for arm in args.arms:
                        reads, match = arms[arm]
                        messages = build_messages(domain, ep, reads, "verbose")
                        sha = digest(messages)
                        if sha not in grouped:
                            grouped[sha] = {"domain": name, "seed": seed, "condition": condition,
                                            "episode": ep.id, "prompt_sha256": sha, "messages": messages,
                                            "arms": [], "reads": reads, "ep": ep, "domain_object": domain}
                        grouped[sha]["arms"].append({"name": arm, "matching": match})
                    jobs.extend(grouped.values())
    return jobs


def run(args):
    from openai import OpenAI
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    safe_config = {k: v for k, v in vars(args).items() if k != "key_file"}
    safe_config.update({"prompt": "v1", "serialization": "verbose", "temperature": 0,
                        "format_repair": "one; first and repair responses logged separately",
                        "sample_status": "prospective diagnostic panel, not the 64-episode main table",
                        "duplicates": "same episode and exact full messages share one call",
                        "rates": COST_RATES_USD_PER_MILLION})
    proto = out / "protocol.json"
    if proto.exists() and json.loads(proto.read_text()) != safe_config:
        raise ValueError("existing output uses different protocol")
    proto.write_text(json.dumps(safe_config, indent=2))
    jobs = prepare(args)
    manifest = [{k: v for k, v in j.items() if k not in ("ep", "domain_object")} for j in jobs]
    (out / "inputs.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({"prepared_unique_calls": len(jobs), "arm_observations": sum(len(j["arms"]) for j in jobs), "dry_run": args.dry_run}), flush=True)
    if args.dry_run:
        return
    keys = [s.strip() for s in Path(args.key_file).read_text().splitlines() if s.strip() and not s.strip().startswith("#")]
    if not keys:
        raise ValueError("credential file contains no keys")
    clients = [OpenAI(api_key=k, base_url=args.base_url, timeout=90, max_retries=0) for k in keys]
    ledger = out / "ledger.jsonl"
    done, spent = set(), 0.0
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            row = json.loads(line)
            spent += row.get("cost", 0.0)
            if row["event"] == "result":
                done.add(row["job_id"])
    lock = threading.Lock()
    state = {"spent": spent, "reserved": 0.0, "completed": 0, "budget_skipped": 0}

    def job_id(j):
        return digest([j["episode"], j["condition"], j["prompt_sha256"]])

    def call(client, messages):
        for attempt in range(3):
            t0 = time.monotonic()
            try:
                response = client.chat.completions.create(
                    model=args.model, messages=messages, temperature=0, max_tokens=args.max_tokens,
                    extra_body={"thinking": {"type": "disabled"}, "reasoning_effort": "none"})
                u, choice = response.usage, response.choices[0]
                cached = int(getattr(u, "prompt_cache_hit_tokens", 0) or 0)
                details = getattr(u, "prompt_tokens_details", None)
                cached = max(cached, int(getattr(details, "cached_tokens", 0) or 0))
                cost = ((u.prompt_tokens-cached)*2.5 + cached*.25 + u.completion_tokens*10)/1e6
                return {"text": choice.message.content or "", "finish_reason": choice.finish_reason,
                        "returned_model": response.model, "input_tokens": u.prompt_tokens,
                        "output_tokens": u.completion_tokens, "cached_tokens": cached,
                        "cost": cost, "seconds": time.monotonic()-t0}
            except Exception as exc:
                code = getattr(exc, "status_code", None)
                if attempt == 2 or code in (400, 401, 403, 404):
                    # No exception text: proxies can echo request credentials.
                    raise RuntimeError(f"{type(exc).__name__}; status={code}") from None
                time.sleep(2 ** (attempt+1))

    def worker(index, j):
        ident = job_id(j)
        if ident in done:
            return
        # Conservative allowance for two outputs and the repeated input on repair.
        chars = sum(len(m["content"]) for m in j["messages"])
        reservation = 2 * (chars*2.5 + args.max_tokens*10) / 1e6
        with lock:
            if state["spent"] + state["reserved"] + reservation > args.budget_usd:
                state["budget_skipped"] += 1
                return
            state["reserved"] += reservation
        attempts = []
        base = {k: v for k, v in j.items() if k not in ("ep", "domain_object", "messages")}
        try:
            client = clients[index % len(clients)]
            attempts.append(call(client, j["messages"]))
            txns = parse_transactions(attempts[0]["text"])
            if txns is None:
                attempts.append(call(client, j["messages"] + [
                    {"role": "assistant", "content": attempts[0]["text"]},
                    {"role": "user", "content": "Return the final answer now as a fenced ```json block containing only the array of transactions."}]))
                txns = parse_transactions(attempts[-1]["text"])
            score = score_plan(j["domain_object"], j["ep"], txns or [], j["reads"])
            if txns is None:
                score["ees"] = False
            record = {**base, "event": "result", "job_id": ident, "attempts": attempts,
                      "parse_ok": txns is not None, "txns": txns, "score": score,
                      "truncated_first": attempts[0]["finish_reason"] == "length",
                      "truncated_any": any(a["finish_reason"] == "length" for a in attempts)}
        except Exception as exc:
            record = {**base, "event": "infrastructure_failure", "job_id": ident,
                      "error": str(exc), "attempts": attempts}
        cost = sum(a["cost"] for a in attempts)
        record["cost"] = cost
        with lock:
            state["reserved"] -= reservation
            state["spent"] += cost
            state["completed"] += 1
            with ledger.open("a") as f:
                f.write(json.dumps(record) + "\n")
            print(json.dumps({"completed": state["completed"], "event": record["event"],
                              "domain": j["domain"], "seed": j["seed"], "condition": j["condition"],
                              "arms": [a["name"] for a in j["arms"]],
                              "ees": record.get("score", {}).get("ees"), "spent": round(state["spent"], 4)}), flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(worker, i, j) for i, j in enumerate(jobs)]
        for future in as_completed(futures):
            future.result()
    (out / "completion.json").write_text(json.dumps({**state, "prepared": len(jobs), "previously_done": len(done)}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--key-file", default="api/api.txt")
    p.add_argument("--base-url", default="https://www.autodl.art/api/v1")
    p.add_argument("--model", default="deepseek-v4-flash")
    p.add_argument("--graphs", default="results/real/hm3/tcd/grace_graphs_test.json")
    p.add_argument("--domains", nargs="+", default=["travel"])
    p.add_argument("--seeds", nargs="+", type=int, default=[30, 31, 32])
    p.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=["c100", "500"])
    p.add_argument("--arms", nargs="+", choices=ARMS, default=ARMS)
    p.add_argument("--n-eval", type=int, default=16)
    p.add_argument("--max-tokens", type=int, default=16384)
    p.add_argument("--state-context", choices=["referent_closed"], default="referent_closed")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--budget-usd", type=float, default=40)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out", required=True)
    run(p.parse_args())
