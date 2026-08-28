"""Score finished end-to-end travel runs with MemoryArena's OWN metrics (PS/SPS/SR).

This is the number the P2 claim still lacks. Everything measured so far is about
the memory CONTEXT (answerability at cost); this measures whether the agent
actually planned the trip correctly, using the benchmark's official evaluator
rather than anything of ours:

    env/env_systems/travel_planner_env/eval.py :: evaluate(submission_path, ...)
      SR   group-level: every traveller in the group passes
      PS   person-level full pass rate
      SPS  data-level average constraint satisfaction rate

Usage (after run_travel.py has written plans):
    python3 code/arena_e2e_score.py                       # scores every arm found
    python3 code/arena_e2e_score.py --arms causal-learned long_context

Only scores arms that actually produced plan files, and prints how many episodes
each arm completed -- because comparing arms at different episode counts is not a
comparison. It refuses to rank arms whose completed-episode sets differ, and says
so, rather than quietly reporting numbers computed on different data.

CPU-only, no API, no network.
"""
from __future__ import annotations

import os as _os
_os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARENA = REPO / "benchmarks" / "MemoryArena"
E2E = ARENA / "results" / "travel_e2e"


def episodes_done(arm_dir: Path) -> set:
    out = set()
    for f in arm_dir.glob("generated_plan_*.json"):
        m = re.search(r"generated_plan_(.+)\.json$", f.name)
        if m:
            out.add(m.group(1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="*", default=None)
    ap.add_argument("--e2e_dir", default=str(E2E))
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--out", default="results/real/e2e_scores.json")
    a = ap.parse_args()

    e2e = Path(a.e2e_dir)
    if not e2e.exists():
        print(f"no end-to-end output at {e2e} — run_travel.py has not produced plans yet")
        return
    arms = a.arms or sorted(d.name for d in e2e.iterdir()
                            if d.is_dir() and d.name != "logs")
    if not arms:
        print(f"{e2e} exists but contains no arm directories")
        return

    done = {arm: episodes_done(e2e / arm) for arm in arms if (e2e / arm).exists()}
    print("completed episodes per arm:")
    for arm, eps in done.items():
        print(f"  {arm:24s} {len(eps)}")
    nonempty = {k: v for k, v in done.items() if v}
    if not nonempty:
        print("\nNothing to score: every arm completed 0 episodes.")
        print("(An episode only counts once run_travel.py writes its generated_plan_*.json.)")
        return
    common = set.intersection(*nonempty.values()) if len(nonempty) > 1 else next(iter(nonempty.values()))
    if len(nonempty) > 1 and any(len(v) != len(common) for v in nonempty.values()):
        print(f"\n!! arms completed DIFFERENT episode sets (common={len(common)}).")
        print("   Scores below are per-arm on that arm's own episodes and are NOT")
        print("   directly comparable. Re-run to a common episode set before ranking.")

    sys.path.insert(0, str(ARENA))
    os_cwd = Path.cwd()
    try:
        _os.chdir(ARENA)
        from env.env_systems.travel_planner_env.eval import evaluate
    except Exception as exc:
        print(f"could not import MemoryArena's evaluator: {exc}")
        _os.chdir(os_cwd)
        return

    rep = {}
    for arm, eps in nonempty.items():
        print(f"\n=== {arm}  ({len(eps)} episodes) ===")
        try:
            res = evaluate(str(e2e / arm), model_name=a.model, memory_system=arm)
            rep[arm] = {"n_episodes": len(eps), "metrics": res}
        except Exception as exc:
            print(f"  evaluator failed: {exc}")
            rep[arm] = {"n_episodes": len(eps), "error": str(exc)}
    _os.chdir(os_cwd)

    p = REPO / a.out
    p.parent.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(p, "w"), indent=1, default=str)
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
