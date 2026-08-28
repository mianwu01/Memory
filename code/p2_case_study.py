"""P2 explainability — show, on one real travel round, what each memory system
actually hands the agent and why the numbers come out the way they do.

The summary table says causal reaches bm25-beating recall at half the tokens.
This prints the underlying object for a single round: the query, the gold cell
the query depends on, and each system's memory context side by side, so the
mechanism (slot-level ancestor extraction vs whole-chunk retrieval) is visible.

Usage: python3 code/p2_case_study.py --episode 1 --round 4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ARENA = Path(__file__).resolve().parents[1] / "benchmarks" / "MemoryArena"
sys.path.insert(0, str(ARENA))

from t0_travel import build_chunks, parse_episode          # noqa: E402
from arena_p2_benchmark import (MemClient, count_tokens,   # noqa: E402
                                gold_cells_for_round, value_present)


def show(text, width=96, indent="    "):
    out, line = [], ""
    for w in str(text).split():
        if len(line) + len(w) + 1 > width:
            out.append(indent + line); line = w
        else:
            line = (line + " " + w).strip()
    if line:
        out.append(indent + line)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8123")
    ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--round", type=int, default=4)
    ap.add_argument("--systems", nargs="+",
                    default=["long_context", "bm25", "causal-noG", "causal"])
    ap.add_argument("--max_ctx_chars", type=int, default=900)
    a = ap.parse_args()

    from datasets import load_dataset
    ds = load_dataset("ZexueHe/memoryarena", "group_travel_planner")
    raw = [dict(r) for r in ds[list(ds.keys())[0]]]
    ep = None
    for r in raw:
        e = parse_episode(r)
        if e["id"] == a.episode:
            ep = e
            break
    if ep is None:
        ep = parse_episode(raw[0])
    chunks = build_chunks(ep)
    t = min(a.round, len(ep["rounds"]))
    q = ep["rounds"][t - 1]["query"]
    gold = gold_cells_for_round(ep, t)

    print("=" * 100)
    print(f"P2 CASE STUDY — episode {ep['id']}, round {t}".center(100))
    print("=" * 100)
    print("\nTHE QUERY THE AGENT MUST ANSWER")
    print(show(q))
    print("\nWHAT IT DEPENDS ON  (gold cells parsed from the query, resolved to real values)")
    for g in gold:
        print(f"    - {g['person']}, day {g['day']}, {g['slot']}  =  {g['value'][:70]}")
    if not gold:
        print("    (this round names no prior person; nothing to retrieve)")

    full_tokens = count_tokens("\n".join(chunks[:t]))
    print(f"\nFULL HISTORY SO FAR: {full_tokens} tokens across {t} chunks")

    for s in a.systems:
        uid = f"case_{s}_{ep['id']}_{t}"
        mc = MemClient(a.server, uid, s)
        mc.add(chunks[0])
        for k in range(1, t):
            mc.add(chunks[k])
        ctx = mc.wrap(q).split("</memory_context>")[0]
        hits = [value_present(ctx, g["value"]) for g in gold]
        print("\n" + "-" * 100)
        print(f"[{s}]  tokens={count_tokens(ctx):5d}   "
              f"gold hit={sum(hits)}/{len(gold)}   "
              f"compression={count_tokens(ctx)/max(1,full_tokens):.2f}")
        print("-" * 100)
        body = ctx.replace("<memory_context>", "").strip()
        shown = body[: a.max_ctx_chars]
        print(shown + (f"\n    ... [{len(body)-len(shown)} more chars truncated for display]"
                       if len(body) > len(shown) else ""))
        for g, h in zip(gold, hits):
            if not h:
                print(f"    !! MISSING: {g['person']} day {g['day']} {g['slot']} "
                      f"= {g['value'][:50]}")

    print("\n" + "=" * 100)
    print("READ THIS AS: long_context ships every chunk verbatim (safe, expensive);")
    print("bm25 ships whole chunks it deems similar (can miss the needed one);")
    print("causal-noG ships every parsed slot (safe, still bulky);")
    print("causal ships only An_G(query) -- the named person's relevant cells.")


if __name__ == "__main__":
    main()
