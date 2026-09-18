"""Frozen, resumable paired Travel campaign for the newly authorized provider."""
from __future__ import annotations

import argparse
import fcntl
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from faithful_memory import ARMS, ROOT
from run_with_autodl import ENDPOINT, MODEL, environment

SOURCE_NAMES = ("faithful_arena_run.py", "faithful_memory.py", "faithful_transport.py",
                "arena_causal_memory.py", "arena_e2e_inherit.py", "relay_chat_transport.py",
                "travel_implicit.py", "autodl_travel_campaign.py", "run_with_autodl.py",
                "autodl_report.py", "autodl_core_report.py")


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_protocol(base, phase, graph):
    ids = [101] if phase == "development" else list(range(111, 161))
    repeats = 1 if phase == "development" else 3
    variants = {"implicit": list(ARMS), "explicit": ["ours", "noGcompact", "query_only"]}
    metadata = json.loads(graph.read_text())
    if not set(ids) <= set(metadata["excluded_episode_ids"]):
        raise ValueError("Graph training includes a requested development/test episode")
    cases = []
    # Interleave methods, query conditions and repeated calls throughout time.
    for repeat in range(repeats):
        for offset, ident in enumerate(ids):
            ordered = list(ARMS[offset % len(ARMS):] + ARMS[:offset % len(ARMS)])
            for arm in ordered:
                for variant, arms in variants.items():
                    if arm in arms:
                        cases.append({"key": f"{variant}/{arm}/{ident}/r{repeat}",
                                      "variant": variant, "arm": arm, "id": ident, "repeat": repeat})
    from faithful_memory import environment as configure_local
    configure_local()
    from env.env_systems.travel_planner_env.data_loader import load_travel_data
    data_sha = hashlib.sha256(json.dumps(load_travel_data(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    protocol = {"schema": "autodl-travel-campaign/v1", "created_at": time.time(),
                "phase": phase, "model": MODEL, "endpoint": ENDPOINT,
                "actor_thinking": "default", "graph_path": str(graph), "graph_sha256": sha(graph),
                "episode_ids": ids, "repeats": repeats, "variants": variants, "cases": cases,
                "source_hashes": {**{"code/" + n: sha(ROOT / "code" / n) for n in SOURCE_NAMES}, "dataset:MemoryArena": data_sha},
                "max_steps": 30, "actor_max_tokens": 32768,
                "memory_mode": {"thinking": "disabled", "reasoning_effort": "none"},
                "memory_budget_adaptation": {"amem_max_tokens": 16000,
                    "evidence": "results/development/autodl_20260918/amem_budget_amendment.json"},
                "interpretation": "Matched history notes; implicit requests omit source dependencies, explicit requests retain them. Original full-plan actor and gold evaluator. Historical benchmark content has previously been inspected; paired descriptive extension, not a pristine benchmark. Native memory implementations are adapted, not reproductions of published scores.",
                "failure_policy": "Preserve all attempts. Never resample semantic failures. Stop new dispatch on authentication/balance failures; retain pending cases. Resume completed cases without rerunning them. Any technical recovery is registered in each case state.",
                "unknown_price_policy": "Report tokens and provider-reported billing; do not invent AutoDL token prices."}
    with (base / "protocol.json").open("x") as handle:
        json.dump(protocol, handle, ensure_ascii=False, indent=2)
    for name in SOURCE_NAMES:
        target = base / "frozen_source/code" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / "code" / name).read_bytes())
    return protocol


def check_protocol(protocol):
    if protocol["model"] != MODEL or protocol["endpoint"] != ENDPOINT:
        raise ValueError("Unexpected model/endpoint in campaign")
    if sha(Path(protocol["graph_path"])) != protocol["graph_sha256"]:
        raise ValueError("Frozen graph changed")
    for name, digest in protocol["source_hashes"].items():
        if name.startswith("dataset:"):
            continue
        if sha(ROOT / name) != digest:
            raise ValueError("Frozen source changed: " + name)


def last_api_status(folder):
    path = folder / "events.jsonl"
    if not path.exists():
        return None
    found = None
    with path.open() as handle:
        for line in handle:
            try: row = json.loads(line)
            except json.JSONDecodeError: continue
            if row.get("event") == "api_error":
                found = row.get("status_code")
    return found


def execute_case(base, case, protocol, env, python, retry_failed):
    case_dir = base / "cases" / case["key"]
    state_path = case_dir / "case_state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {**case, "attempts": []}
    if state.get("state") == "complete":
        return state
    if state.get("state") in {"failed", "running"}:
        if not retry_failed:
            return state
        if len(state.get("attempts", [])) >= 3:
            return state
        # The caller can authorize a recorded recovery only for API/transport failures.
        old = case_dir / state["attempts"][-1]["directory"]
        old_status_path = old / "status.json"
        old_status = json.loads(old_status_path.read_text()) if old_status_path.exists() else {}
        if last_api_status(old) not in (429, 500, 502, 503, 504) and old_status.get("error_type") not in ("APIConnectionError", "APITimeoutError", "TimeoutError"):
            return state
    check_protocol(protocol)
    number = len(state["attempts"])
    directory = f"attempt_{number}"
    out = case_dir / directory
    case_dir.mkdir(parents=True, exist_ok=True)
    attempt = {"directory": directory, "started_at": time.time(), "recovery": number > 0}
    state["attempts"].append(attempt)
    state.update(state="running", selected_attempt=None)
    atomic(state_path, state)
    command = [python, "-u", str(ROOT / "code/faithful_arena_run.py"),
               "--arm", case["arm"], "--id", str(case["id"]), "--out", str(out),
               "--variant", case["variant"], "--graph", protocol["graph_path"],
               "--repeat", str(case["repeat"]),
               "--actor-thinking", protocol["actor_thinking"], "--env-port", "8941"]
    with (case_dir / (directory + ".log")).open("x") as log:
        proc = subprocess.Popen(command, cwd="/tmp", env=env, stdout=log, stderr=subprocess.STDOUT)
        attempt["pid"] = proc.pid; atomic(state_path, state)
        code = proc.wait()
    status_path = out / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    good = code == 0 and status.get("complete") is True
    attempt.update(finished_at=time.time(), exit_code=code, error_type=status.get("error_type"),
                   last_api_status=last_api_status(out))
    state.update(state="complete" if good else "failed", selected_attempt=directory if good else None)
    atomic(state_path, state)
    return state


def dispatch_limit(path, maximum):
    if path is None:
        return maximum
    settings = json.loads(path.read_text())
    limit = settings.get("workers", maximum)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
        raise ValueError("Dispatch worker cap must be an integer in 1..maximum")
    if settings.get("pause_dispatch", False):
        return 0
    return limit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--phase", choices=["development", "evaluation"], required=True)
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--control", type=Path, help="Atomic JSON workers/pause_dispatch control; changes scheduling only")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--retry-failed", action="store_true")
    args = ap.parse_args()
    if args.workers < 1: ap.error("workers must be positive")
    base = args.base.resolve(); base.mkdir(parents=True, exist_ok=True)
    lock = (base / ".lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    path = base / "protocol.json"
    if path.exists():
        if not args.resume: raise ValueError("Existing campaign requires --resume")
        protocol = json.loads(path.read_text())
        if protocol["phase"] != args.phase: raise ValueError("Phase changed")
    else:
        protocol = create_protocol(base, args.phase, args.graph.resolve())
    check_protocol(protocol)
    env = environment()
    jobs = []
    states = {}
    for case in protocol["cases"]:
        f = base / "cases" / case["key"] / "case_state.json"
        state = json.loads(f.read_text()) if f.exists() else None
        if state: states[case["key"]] = state
        if not state or (args.retry_failed and state.get("state") != "complete"):
            jobs.append(case)
    running = {}; cursor = 0; stop = False; stop_reason = None
    limit = dispatch_limit(args.control, args.workers)
    def drain(signum, _frame):
        nonlocal stop, stop_reason
        stop = True
        stop_reason = f"signal_{signum}_drain"
    signal.signal(signal.SIGINT, drain)
    signal.signal(signal.SIGTERM, drain)
    started = time.time()
    def save():
        counts = dict(Counter(s["state"] for s in states.values()))
        result = {"pid": os.getpid(), "started_at": started, "updated_at": time.time(),
                  "workers": args.workers, "total": len(protocol["cases"]), "counts": counts,
                  "dispatch_limit": limit, "control": str(args.control) if args.control else None,
                  "inflight": len(running), "remaining_dispatch": len(jobs) - cursor,
                  "stopped_for_api": stop_reason == "authentication_or_balance",
                  "stop_reason": stop_reason,
                  "complete": counts.get("complete", 0) == len(protocol["cases"])}
        atomic(base / "campaign_state.json", result)
        return result
    save()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while running or (cursor < len(jobs) and not stop):
            try:
                limit = dispatch_limit(args.control, args.workers)
            except (OSError, ValueError):
                # An incomplete external edit must not accidentally dispatch at
                # maximum concurrency. Existing requests continue undisturbed.
                limit = 0
            while cursor < len(jobs) and len(running) < limit and not stop:
                case = jobs[cursor]; cursor += 1
                states[case["key"]] = {**case, "state": "running"}
                future = pool.submit(execute_case, base, case, protocol, env, sys.executable, args.retry_failed)
                running[future] = case
            if not running and cursor < len(jobs) and not stop:
                save()
                time.sleep(1)
                continue
            done, _ = wait(running, timeout=30, return_when=FIRST_COMPLETED)
            for future in done:
                case = running.pop(future)
                try: state = future.result()
                except Exception as exc:
                    state = {**case, "state": "failed", "launcher_error": type(exc).__name__}
                states[case["key"]] = state
                attempts = state.get("attempts", [])
                if attempts and attempts[-1].get("last_api_status") in (401, 402, 403):
                    stop = True
                    stop_reason = "authentication_or_balance"
                print(json.dumps({"case": case["key"], "state": state["state"], "completed": sum(s["state"] == "complete" for s in states.values()), "total": len(protocol["cases"])}), flush=True)
            save()
    final = save()
    print(json.dumps(final), flush=True)
    if not final["complete"]: raise SystemExit(1)


if __name__ == "__main__":
    main()
