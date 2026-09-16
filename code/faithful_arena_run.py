"""One unmodified MemoryArena actor/episode with a validated memory backend."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from faithful_memory import ARMS, ROOT, AuthorMemory, ConventionalMemory, Runtime, StructuredMemory, environment


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=ARMS, required=True)
    ap.add_argument("--id", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--env-port", type=int, default=8941)
    ap.add_argument("--actor-thinking", choices=["default", "disabled"], default="disabled")
    args = ap.parse_args()
    environment()
    runtime = Runtime(args.out.resolve(), args.arm, args.id, actor_thinking=args.actor_thinking)
    # Per-process evidence is needed when a multi-process development launch
    # overlaps a code edit. Formal runs additionally check a frozen manifest.
    provenance = {"source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [ROOT / "code" / name for name in (
                        "faithful_arena_run.py", "faithful_memory.py", "faithful_transport.py",
                        "arena_causal_memory.py", "arena_e2e_inherit.py", "relay_chat_transport.py")]},
                  "model": os.environ["OPENAI_MODEL"], "endpoint": os.environ["OPENAI_BASE_URL"],
                  "actor_thinking": args.actor_thinking, "actor_length_policy": "native_passthrough"}
    (runtime.directory / "provenance.json").write_text(json.dumps(provenance, indent=2))
    runtime.install_clients()
    arena = ROOT / "benchmarks/MemoryArena"
    import run_travel
    from agent.travel_planner import TravelPlannerAgent
    from env.env_systems.travel_planner_env import prompts
    assert run_travel.TravelPlannerAgent is TravelPlannerAgent
    actor_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        arena / "agent/travel_planner.py", arena / "env/env_systems/travel_planner_env/prompts.py",
        arena / "env/env_systems/travel_planner_env/tool_schemas.py")}
    runtime.event("actor_contract", hashes=actor_hashes, custom_decoder=False,
                  custom_prompt=False, tool_filter=False, max_steps=30, thinking=args.actor_thinking)
    original_loader = run_travel.load_travel_data

    def load_one():
        rows = [row for row in original_loader() if int(row["id"]) == args.id]
        if len(rows) != 1:
            raise ValueError("Expected exactly one registered episode")
        return rows

    def memory_factory(*_args, **_kwargs):
        if args.arm in {"ours", "noGcompact", "query_only"}:
            return StructuredMemory(args.arm, runtime)
        if args.arm in {"dense", "summary"}:
            return ConventionalMemory(args.arm, runtime)
        memory = AuthorMemory(args.arm, runtime)

        class Boundary:
            def add(self, text):
                # Each official Travel write completes one session. Sleep-time
                # updates may use this completed history, never later records.
                timestamp = f"2026-09-15 {12 + runtime.round // 60:02}:{runtime.round % 60:02}:00"
                result = memory.add(text, timestamp=timestamp, finalize=True)
                memory.consolidate()
                return result

            def wrap_user_prompt(self, query):
                text = memory.wrap_user_prompt(query)
                runtime.phase = "actor"
                return text

        return Boundary()

    run_travel.load_travel_data = load_one
    run_travel.get_memory_system = memory_factory
    cfg = json.loads((arena / "configs/travel_planner_configs/bm25.json").read_text())
    cfg["agent"].update(model_name=os.environ["OPENAI_MODEL"], base_url=os.environ["OPENAI_BASE_URL"])
    cfg["memory"]["memory_system_name"] = "faithful-" + args.arm
    cfg["env"]["env_server_url"] = f"http://127.0.0.1:{args.env_port}"
    cfg["output"] = {"output_dir": str(runtime.directory / "plans"),
                     "log_dir": str(runtime.directory / "actor_logs"),
                     "global_csv": str(runtime.directory / "results.csv")}
    cfg_path = runtime.directory / "config.json"
    cfg_path.write_text(json.dumps(cfg, indent=2))
    os.chdir(arena)
    sys.argv = [str(arena / "run_travel.py"), "--config", str(cfg_path)]
    try:
        run_travel.main()
        runtime.require_valid()
        if not (runtime.directory / "plans" / f"generated_plan_{args.id}.json").exists():
            raise RuntimeError("Official runner did not complete the episode")
        status = {"complete": True, "arm": args.arm, "id": args.id, "counts": runtime.counts,
                  "scope": "original MemoryArena actor; full plan; no custom decoder"}
    except Exception as exc:
        status = {"complete": False, "arm": args.arm, "id": args.id, "counts": runtime.counts,
                  "error_type": type(exc).__name__, "failures": runtime.failures}
        (runtime.directory / "status.json").write_text(json.dumps(status, indent=2))
        print(json.dumps(status), flush=True)
        raise SystemExit(1)
    (runtime.directory / "status.json").write_text(json.dumps(status, indent=2))
    print(json.dumps(status), flush=True)


if __name__ == "__main__":
    main()
