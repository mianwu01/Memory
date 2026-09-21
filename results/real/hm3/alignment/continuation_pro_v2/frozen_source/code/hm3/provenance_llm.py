"""Actor-level validation of backward provenance (docs/hm3-provenance-design-2026-09-18.md §5).

For every incident reproduced from the deterministic pipeline (same seeds, same
corruption, same graph artifact and trace), the LLM actor receives the
graph_closed/compact prompt under three histories: the corrupted one, the one
where the auditor's top-3 records are replaced by their clean versions, and the
one where three matched random records are replaced.  The actor's EES on each is
the behavioural test of the attribution.

Usage: OPENAI_API_KEY=... OPENAI_BASE_URL=... python3 -m hm3.provenance_llm --domains travel \
           --seed 30 --n_eval 60 --out_dir results/real/hm3/provenance_llm/travel_s30 --budget_usd 6
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from .core import canonical_txn, score_plan
from .domains import get_domain
from .generate import generate_split
from .learners import LearnedGraph
from .llm import Client, build_messages, parse_transactions, Selector
from . import llm as llm_mod
from .provenance import (_run, anomalous_objects, baseline_rankings, controls, corrupt, graph_sha, replace_record,
                         trace, trace_loo)


def run(domain_name: str, seed: int, n_eval: int, out_dir: Path, model: str, budget_usd: float,
        n_train: int = 200, train_seed_offset: int = 100, dry_run: bool = False,
        selection: str = "graph_seg", serialization: str = "verbose", max_tokens: int = 4096):
    out_dir.mkdir(parents=True, exist_ok=True)
    domain = get_domain(domain_name)
    train = generate_split(domain, seed + train_seed_offset, "train", n_train)
    evals = generate_split(domain, seed, "test", n_eval)
    g = LearnedGraph()
    g.fit(domain, train)
    sha = graph_sha(g)
    selector = Selector(domain, train)
    rng = random.Random(seed * 7919 + 17)          # identical to provenance.run_domain
    ledger = out_dir / "llm_ledger.jsonl"
    done = set()
    spent = 0.0
    if ledger.exists():
        for l in open(ledger):
            r = json.loads(l)
            if r.get("event") == "cell":
                done.add(r["cell"]); spent += r["cost"]
    client = None if dry_run else Client(model)
    json.dump({"domain": domain_name, "seed": seed, "n_eval": n_eval, "model": model, "graph_sha": sha, "max_tokens": max_tokens,
               "arms": ["clean", "corrupted", "top3_replaced", "random3_replaced"], "selection": f"{selection}/{serialization}",
               "prompt_version": llm_mod.PROMPT_VERSION, "budget_usd": budget_usd}, open(out_dir / "protocol.json", "w"), indent=1)
    n_inc = 0
    for ep in evals:
        clean_txns, _cr, clean_score = _run(domain, g, ep)
        if not clean_score["ees"]:
            continue
        got = corrupt(domain, ep, rng)
        if got is None:
            continue
        bad, gold_rid, key = got
        bad_txns, bad_reads, bad_score = _run(domain, g, bad)
        if bad_score["ees"] or {canonical_txn(t) for t in bad_txns} == {canonical_txn(t) for t in clean_txns}:
            continue
        n_inc += 1
        anomalies = anomalous_objects(domain, bad, bad_txns, bad_score)
        structural, path_objs = trace(domain, g, bad, anomalies, bad_reads, k=12)
        ranked = trace_loo(domain, g, bad, anomalies, structural, bad_txns)
        ctrl = controls(bad, bad_reads, ranked, path_objs, rng)
        _ = baseline_rankings(bad, anomalies)   # keeps the rng stream identical to provenance.run_domain
        arms = {"clean": ep, "corrupted": bad,
                "top3_replaced": replace_record(bad, ep, ranked[:3]),
                "random3_replaced": replace_record(bad, ep, ctrl.get("matched_random3") or [])}
        for arm, epi in arms.items():
            cell = f"{domain_name}/{ep.id}/{arm}"
            if cell in done:
                continue
            if spent >= budget_usd:
                print(f"budget {budget_usd} reached at {spent:.3f}", flush=True)
                return
            sel = selector.select(domain, epi, selection)
            messages = build_messages(domain, epi, sel, serialization)
            if dry_run:
                rec = {"event": "cell", "cell": cell, "dry_run": True, "prompt_chars": sum(len(m["content"]) for m in messages)}
                open(ledger, "a").write(json.dumps(rec) + "\n"); continue
            try:
                r = client.chat(messages, max_tokens=max_tokens)
            except Exception as exc:
                open(ledger, "a").write(json.dumps({"event": "infrastructure_failure", "cell": cell, "error": str(exc)[:200]}) + "\n")
                continue
            txns = parse_transactions(r["text"])
            attempts = [r]
            if txns is None:
                r2 = client.chat(max_tokens=max_tokens, messages=messages + [{"role": "assistant", "content": r["text"]},
                                             {"role": "user", "content": "Return the final answer now as a fenced ```json block containing only the array of transactions."}])
                attempts.append(r2); txns = parse_transactions(r2["text"])
            score = score_plan(domain, epi, txns or [], sel)
            rec = {"event": "cell", "cell": cell, "episode": ep.id, "arm": arm, "gold_rid": gold_rid, "key": key,
                   "ranked": ranked[:3], "random3": ctrl.get("matched_random3"), "gold_in_top3": gold_rid in ranked[:3],
                   "anomalies": anomalies, "n_records": len(sel["records"]), "n_objects": len(sel["objects"]),
                   "input_tokens": sum(a["input_tokens"] for a in attempts), "output_tokens": sum(a["output_tokens"] for a in attempts),
                   "cost": sum(a["cost"] for a in attempts), "returned_model": attempts[-1]["returned_model"],
                   "parse_ok": txns is not None, "raw_reply": attempts[-1]["text"][:3000],
                   "score": {k: v for k, v in score.items() if k != "error"}}
            spent += rec["cost"]
            open(ledger, "a").write(json.dumps(rec) + "\n")
            done.add(cell)
            print(f"{cell:44s} EES={int(score['ees'])} legal={int(score['legal'])} ${spent:.3f}", flush=True)
    print(f"incidents {n_inc}", flush=True)


def summarize(out_dir: Path) -> dict:
    import numpy as np
    rows = [json.loads(l) for l in open(out_dir / "llm_ledger.jsonl")]
    cells = {r["cell"]: r for r in rows if r.get("event") == "cell" and not r.get("dry_run")}
    eps = sorted({r["episode"] for r in cells.values()})
    by_arm = {}
    paired = []
    for e in eps:
        arms = {a: cells.get(f"{r['cell'].split('/')[0]}/{e}/{a}") for r in cells.values() if r["episode"] == e for a in ("clean", "corrupted", "top3_replaced", "random3_replaced")}
        if all(arms.values()):
            paired.append({a: int(arms[a]["score"]["ees"]) for a in arms})
    out = {"n_paired": len(paired)}
    if paired:
        for a in ("clean", "corrupted", "top3_replaced", "random3_replaced"):
            out[f"ees_{a}"] = float(np.mean([p[a] for p in paired]))
        rng = np.random.default_rng(0)
        for a, b in (("top3_replaced", "corrupted"), ("top3_replaced", "random3_replaced"), ("clean", "corrupted"), ("top3_replaced", "clean")):
            d = np.array([p[a] - p[b] for p in paired], float)
            boots = [rng.choice(d, len(d)).mean() for _ in range(4000)]
            out[f"{a}_minus_{b}"] = {"mean": float(d.mean()), "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]}
    out["cost"] = float(sum(r["cost"] for r in cells.values()))
    json.dump(out, open(out_dir / "summary.json", "w"), indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="+", default=["travel"])
    ap.add_argument("--seed", type=int, default=30)
    ap.add_argument("--n_eval", type=int, default=60)
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--budget_usd", type=float, default=6.0)
    ap.add_argument("--prompt", default="v2", choices=["v1", "v2"])
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--selection", default="graph_seg")
    ap.add_argument("--serialization", default="verbose")
    ap.add_argument("--max_tokens", type=int, default=4096, help="actor completion cap (the 2026-09-19 runs used 4096)")
    a = ap.parse_args()
    llm_mod.PROMPT_VERSION = a.prompt
    if a.summarize:
        print(json.dumps(summarize(Path(a.out_dir)), indent=1))
    else:
        for d in a.domains:
            run(d, a.seed, a.n_eval, Path(a.out_dir) / f"{d}_s{a.seed}", a.model, a.budget_usd, dry_run=a.dry_run,
                selection=a.selection, serialization=a.serialization, max_tokens=a.max_tokens)
