"""P2 — does our plugin improve the memory systems already in MemoryArena?

Runs REAL MemoryArena memory systems through their REAL HTTP interface
(/memory/initialize, /memory/add, /memory/wrap_user_prompt) on REAL travel
episodes, and measures the two things a memory system is actually for:

  ANSWERABILITY  did the memory context contain the value the query needs?
                 Ground truth = the source cell parsed from the query text
                 ("...join Eric", "...within $150 of Eric's") resolved against
                 the episode's gold daily_plans. This is a fact about the
                 CONTEXT, not about any LLM, so it is exactly reproducible.
  COST           tokens of memory context shipped to the agent.

Why this layer and not end-to-end task success: the travel agent runs up to 30
ReAct steps per round, so an end-to-end sweep over 4 systems is thousands of LLM
calls and, at the episode counts that are affordable, PS/SPS moves inside noise.
Answerability-at-cost is the mechanism those metrics are downstream of, it is
measured without an LLM in the loop, and it is legible per-case: for each query
you can print the needed cell, whether it survived, and what it cost.
(Downstream end-to-end numbers: arena_p2_endtoend.py, small N, run separately.)

Systems compared (all served by the same process, see code/arena_serve_causal.py):
  long_context  every chunk, verbatim          -- the information upper bound
  bm25 / rag    lexical retrieval, top-k       -- strongest non-causal baseline
  causal        ours: slots + An_G(query) mask -- the claim
  causal-noG    ours minus the graph           -- ablation: is the graph doing it?

Usage:
  python3 code/arena_p2_benchmark.py --server http://127.0.0.1:8123 --episodes 40
"""
from __future__ import annotations

import os as _os
# CPU-only by contract. `import torch` (pulled in transitively) probes the driver
# via NVML even without running a kernel, which a node watchdog can flag as GPU use.
_os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARENA = Path(__file__).resolve().parents[1] / "benchmarks" / "MemoryArena"
sys.path.insert(0, str(ARENA))

from t0_travel import build_chunks, parse_episode  # noqa: E402


def count_tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.encoding_for_model("gpt-4o-mini").encode(
            text, disallowed_special=()))
    except Exception:
        return max(1, len(text) // 4)


class MemClient:
    def __init__(self, base_url: str, user_id: str, system: str, timeout: int = 120):
        self.base, self.uid, self.sys = base_url.rstrip("/"), user_id, system
        self.s = requests.Session()
        self.s.trust_env = False          # never route localhost through the proxy
        self.timeout = timeout
        self._post("/memory/initialize", {"user_id": self.uid,
                                          "memory_system_name": self.sys})

    def _post(self, path, payload):
        r = self.s.post(self.base + path, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def add(self, chunk: str):
        return self._post("/memory/add", {"user_id": self.uid,
                                          "memory_system_name": self.sys, "chunk": chunk})

    def wrap(self, question: str) -> str:
        return self._post("/memory/wrap_user_prompt",
                          {"user_id": self.uid, "memory_system_name": self.sys,
                           "question": question})["prompt"]


def gold_cells_for_round(ep, t):
    """The (person, day, slot, value) facts this round's query depends on.

    Parsed from the query text by the T0 parser, then resolved to the actual
    value in the episode's gold plans -- so a hit means the context carried the
    literal string the agent needs, not merely the right person's name.
    """
    row = ep["row"]
    names = ep["names"]
    out = []
    for sent in ep["rounds"][t - 1]["sentences"]:
        sc = sent.get("src_cell")
        if not sc or not sc.get("person") or not sc.get("slot"):
            continue
        person, day, slot = sc["person"], sc.get("day"), sc["slot"]
        if person not in names:
            continue
        pidx = names.index(person)
        plans = (row["base_person"]["daily_plans"] if pidx == 0
                 else row["answers"][pidx - 1])
        for d in plans:
            if day is not None and d.get("days") != day:
                continue
            val = d.get(slot)
            if val and str(val) != "-":
                out.append({"person": person, "day": d.get("days"),
                            "slot": slot, "value": str(val)})
                if day is not None:
                    break
    # dedupe
    seen, ded = set(), []
    for c in out:
        k = (c["person"], c["day"], c["slot"])
        if k not in seen:
            seen.add(k)
            ded.append(c)
    return ded


def value_present(ctx: str, value: str) -> bool:
    """Is the gold value recoverable from the context? Head-of-string match keeps
    this robust to the environment's own truncation of long venue names."""
    c, v = ctx.lower(), value.lower().strip()
    if not v:
        return False
    if v in c:
        return True
    head = v.split(",")[0].strip()
    return len(head) >= 6 and head in c


def run_system(system, episodes, server, limit_rounds=None, verbose=False):
    rows = []
    for ep in episodes:
        chunks = build_chunks(ep)
        uid = f"p2_{system}_{ep['id']}_{int(time.time()*1000)%100000}"
        try:
            mc = MemClient(server, uid, system)
        except Exception as e:
            print(f"  [{system}] initialize failed: {str(e)[:200]}")
            return rows
        mc.add(chunks[0])                       # base person, written before round 1
        T = len(ep["rounds"])
        for t in range(1, T + 1):
            if limit_rounds and t > limit_rounds:
                break
            q = ep["rounds"][t - 1]["query"]
            gold = gold_cells_for_round(ep, t)
            try:
                wrapped = mc.wrap(q)
            except Exception as e:
                print(f"  [{system}] wrap failed ep={ep['id']} t={t}: {str(e)[:150]}")
                continue
            ctx = wrapped.split("</memory_context>")[0]
            hits = [value_present(ctx, g["value"]) for g in gold]
            rows.append({
                "system": system, "episode": ep["id"], "t": t,
                "n_gold": len(gold), "n_hit": int(sum(hits)),
                "all_hit": int(len(gold) > 0 and all(hits)),
                "has_gold": int(len(gold) > 0),
                "ctx_tokens": count_tokens(ctx),
                "full_tokens": count_tokens("\n".join(chunks[:t])),
            })
            if verbose and gold:
                print(f"  [{system}] ep={ep['id']} t={t} gold={len(gold)} "
                      f"hit={sum(hits)} tok={rows[-1]['ctx_tokens']}")
            if t < len(chunks):
                mc.add(chunks[t])               # this round's plan enters memory
    return rows


def summarize(rows):
    import collections
    agg = collections.defaultdict(lambda: {"gold": 0, "hit": 0, "rounds": 0,
                                           "allhit": 0, "withgold": 0,
                                           "ctx": 0, "full": 0})
    for r in rows:
        a = agg[r["system"]]
        a["gold"] += r["n_gold"]; a["hit"] += r["n_hit"]; a["rounds"] += 1
        a["allhit"] += r["all_hit"]; a["withgold"] += r["has_gold"]
        a["ctx"] += r["ctx_tokens"]; a["full"] += r["full_tokens"]
    out = []
    for sysname, a in agg.items():
        out.append({
            "system": sysname,
            "cell_recall": a["hit"] / a["gold"] if a["gold"] else float("nan"),
            "round_solvable": a["allhit"] / a["withgold"] if a["withgold"] else float("nan"),
            "avg_ctx_tokens": a["ctx"] / a["rounds"] if a["rounds"] else 0,
            "compression": a["ctx"] / a["full"] if a["full"] else float("nan"),
            "rounds": a["rounds"], "gold_cells": a["gold"],
        })
    return sorted(out, key=lambda r: -r["cell_recall"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8123")
    ap.add_argument("--systems", nargs="+",
                    default=["long_context", "bm25", "causal-noG", "causal"])
    ap.add_argument("--episodes", type=int, default=40)
    ap.add_argument("--limit_rounds", type=int, default=None)
    ap.add_argument("--out", default="results/real/p2_benchmark.csv")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    # Load the RAW HF rows: load_travel_data() rewrites `questions` into dicts,
    # while the T0 parser (and the gold-cell resolution below) expects the raw
    # string form the dataset ships.
    from datasets import load_dataset
    ds = load_dataset("ZexueHe/memoryarena", "group_travel_planner")
    split = "train" if "train" in ds else list(ds.keys())[0]
    raw = [dict(r) for r in ds[split]]
    episodes = [parse_episode(r) for r in raw[:a.episodes]]
    print(f"episodes: {len(episodes)}  rounds: {sum(len(e['rounds']) for e in episodes)}")

    all_rows = []
    for s in a.systems:
        t0 = time.time()
        rows = run_system(s, episodes, a.server, a.limit_rounds, a.verbose)
        all_rows += rows
        print(f"{s:14s} {len(rows):5d} rounds  ({time.time()-t0:.1f}s)", flush=True)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    import csv as _csv
    if all_rows:
        with open(out, "w", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader(); w.writerows(all_rows)

    print("\n=== P2: answerability at cost (real MemoryArena systems) ===")
    print(f"{'system':14s} {'cell recall':>12s} {'round solvable':>15s} "
          f"{'ctx tokens':>11s} {'compression':>12s}")
    summ = summarize(all_rows)
    for r in summ:
        print(f"{r['system']:14s} {r['cell_recall']:12.3f} {r['round_solvable']:15.3f} "
              f"{r['avg_ctx_tokens']:11.0f} {r['compression']:12.3f}")
    with open(str(out).replace(".csv", "_summary.json"), "w") as f:
        json.dump(summ, f, indent=2)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
