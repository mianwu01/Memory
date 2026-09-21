"""E2: read-intervention discovery with the LLM actor as the policy (docs/method-design-read-interventions).

For each training episode where the full-history actor is correct, ddmin over the history records with the
actor replayed on the visible subset (temperature 0, verbose serialization, prompt v1/v2).  Writes per-episode
minimal sets and a replay ledger; fits the conditional frontier model on the LLM sets and reports its type
edges and its overlap with the executor's frontier.

usage (from code/): OPENAI_API_KEY=... OPENAI_BASE_URL=... python3 -m hm3.replay_llm --domain travel --seed 30 \
    --n_train 48 --prompt v1 --out_dir ../results/real/hm3/replay_llm/travel_s30_v1 --budget_usd 8
"""
from __future__ import annotations
import argparse, json, time
from pathlib import Path
import numpy as np
from . import llm as L
from .domains import get_domain
from .generate import generate_split
from .replay import discover, ExecutorOracle, LLMOracle, FrontierModel, reach_all, minimal_sufficient
from .tcd_logs import skeleton_type_edges, compare
from .learners import LearnedGraph


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="travel")
    ap.add_argument("--seed", type=int, default=30)
    ap.add_argument("--n_train", type=int, default=48)
    ap.add_argument("--ep_start", type=int, default=0)
    ap.add_argument("--prompt", default="v1", choices=["v1", "v2"])
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--max_tokens", type=int, default=16384)
    ap.add_argument("--budget_usd", type=float, default=8.0)
    ap.add_argument("--repeats", type=int, default=1, help="majority of k calls per replay (3 recommended)")
    ap.add_argument("--out_dir", required=True)
    a = ap.parse_args()
    L.PROMPT_VERSION = a.prompt
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    ledger = out / "replay_ledger.jsonl"
    d = get_domain(a.domain)
    train = generate_split(d, a.seed + 100, "train", a.ep_start + a.n_train)[a.ep_start:]
    client = L.Client(a.model)
    done = {}
    sets_path = out / "sets.jsonl"
    if sets_path.exists():
        for line in open(sets_path):
            r = json.loads(line); done[r["episode"]] = r
    spent = sum(r.get("cost", 0.0) for r in done.values())
    for ep in train:
        if ep.id in done:
            continue
        if spent > a.budget_usd:
            print("budget reached", spent, flush=True); break
        ok = LLMOracle(d, ep, client, max_tokens=a.max_tokens, ledger=ledger, repeats=a.repeats)
        rec = discover(d, [ep], lambda e: ok)[0]
        rec["cost"] = ok.cost; rec["llm_calls"] = ok.calls; rec["repeats"] = a.repeats
        rec["split_votes"] = sum(1 for v in ok.votes if len(set(v)) > 1)
        # executor frontier on the same episode, for the overlap
        ex = ExecutorOracle(d, ep)
        cands = [r["rid"] for r in ep.H]
        rec["executor_frontier"] = minimal_sufficient(cands, ex)[0] if ex(cands) else None
        spent += ok.cost
        done[ep.id] = rec
        with open(sets_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{ep.id}: full_ok={rec['full_ok']} n={rec['n']} frontier={len(rec['frontier']) if rec['frontier'] else None} "
              f"exec={len(rec['executor_frontier']) if rec['executor_frontier'] else None} calls={rec['calls']} ${spent:.2f}", flush=True)
    # summary
    ok_sets = [r for r in done.values() if r["full_ok"]]
    summ = {"episodes": len(done), "full_ok": len(ok_sets), "cost": spent,
            "frontier": float(np.mean([len(r["frontier"]) for r in ok_sets])) if ok_sets else None,
            "executor_frontier": float(np.mean([len(r["executor_frontier"]) for r in ok_sets if r["executor_frontier"]])) if ok_sets else None,
            "calls": float(np.mean([r["calls"] for r in ok_sets])) if ok_sets else None,
            "n_records": float(np.mean([r["n"] for r in ok_sets])) if ok_sets else None}
    if ok_sets:
        inter = [len(set(r["frontier"]) & set(r["executor_frontier"])) / max(1, len(set(r["executor_frontier"]))) for r in ok_sets if r["executor_frontier"]]
        summ["executor_frontier_covered_by_llm"] = float(np.mean(inter)) if inter else None
        by = {ep.id: ep for ep in train}
        eps = [by[r["episode"]] for r in ok_sets]
        model = FrontierModel().fit(d, eps, ok_sets, reach_all)
        g = LearnedGraph(); g.fit(d, generate_split(d, a.seed + 100, "train", 200))
        summ["type_edges"] = sorted(f"{x}->{y}" for x, y in model.type_edges)
        summ["edge_support"] = {f"{x}->{y}": c for (x, y), c in sorted(model.edge_support.items())}
        summ["vs_skeleton"] = compare(model.type_edges, skeleton_type_edges(g))
    json.dump(summ, open(out / "summary.json", "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
