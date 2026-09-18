"""Recover Travel attempts whose local dispatcher and child both disappeared.

This is only for infrastructure interruption: the state says running, the
recorded PID is absent, no status file exists, and the event stream has no
terminal API or semantic error.  Every interrupted attempt remains on disk.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from autodl_secondary_dispatch import secondary_environment
from autodl_travel_campaign import atomic, check_protocol, last_api_status
from faithful_memory import ROOT


def read_events(path: Path) -> list[dict]:
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def recover(base: Path, case: dict, protocol: dict, env: dict[str, str],
            fingerprint: str) -> dict:
    folder = base / "cases" / case["key"]
    lock = (folder / ".orphan_recovery.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state_path = folder / "case_state.json"
    state = json.loads(state_path.read_text())
    attempts = state.get("attempts", [])
    if state.get("state") != "running" or not attempts or len(attempts) >= 3:
        return {"key": case["key"], "action": "ineligible_state_or_attempt_limit"}
    previous_attempt = attempts[-1]
    pid = previous_attempt.get("pid")
    if pid and Path("/proc", str(pid)).exists():
        return {"key": case["key"], "action": "recorded_process_still_alive"}
    previous = folder / previous_attempt["directory"]
    status_path = previous / "status.json"
    if status_path.exists():
        status = json.loads(status_path.read_text())
        if status.get("complete") is True:
            state.update(state="complete", selected_attempt=previous_attempt["directory"])
            atomic(state_path, state)
            return {"key": case["key"], "action": "reconciled_complete_status"}
        return {"key": case["key"], "action": "terminal_status_requires_normal_classification"}
    event_path = previous / "events.jsonl"
    events = read_events(event_path)
    terminal = [row for row in events if row.get("event") in ("api_error", "invalid")]
    if terminal:
        return {"key": case["key"], "action": "terminal_event_requires_normal_classification"}
    check_protocol(protocol)
    number = len(attempts)
    directory = f"attempt_{number}"
    out = folder / directory
    if out.exists():
        raise ValueError("Refusing to overwrite " + str(out))
    authorization = {
        "registered_at": time.time(),
        "reason": "dispatcher_and_recorded_child_absent_without_terminal_event_or_status",
        "previous_attempt": previous_attempt["directory"],
        "previous_pid": pid,
        "previous_events_sha256": hashlib.sha256(event_path.read_bytes()).hexdigest()
        if event_path.exists() else None,
        "key_fingerprint": fingerprint,
        "policy": "Infrastructure-only continuation with identical frozen generation settings; interrupted attempt preserved.",
    }
    atomic(folder / f"orphan_recovery_authorization_{number}.json", authorization)
    now = time.time()
    previous_attempt.update(finished_at=now, exit_code=None,
                            error_type="DispatcherProcessLost", orphaned_at=now)
    attempt = {"directory": directory, "started_at": now, "recovery": True,
               "recovery_reason": authorization["reason"], "dispatcher": "secondary_orphan_recovery",
               "key_fingerprint": fingerprint}
    attempts.append(attempt)
    state.update(state="running", selected_attempt=None)
    atomic(state_path, state)
    command = [sys.executable, "-u", str(ROOT / "code/faithful_arena_run.py"),
               "--arm", case["arm"], "--id", str(case["id"]), "--out", str(out),
               "--variant", case["variant"], "--graph", protocol["graph_path"],
               "--repeat", str(case["repeat"]), "--actor-thinking", protocol["actor_thinking"],
               "--env-port", "8941"]
    with (folder / (directory + ".log")).open("x") as log:
        process = subprocess.Popen(command, cwd="/tmp", env=env, stdout=log,
                                   stderr=subprocess.STDOUT)
        attempt["pid"] = process.pid
        atomic(state_path, state)
        return_code = process.wait()
    status_path = out / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    complete = return_code == 0 and status.get("complete") is True
    attempt.update(finished_at=time.time(), exit_code=return_code,
                   error_type=status.get("error_type"), last_api_status=last_api_status(out))
    state.update(state="complete" if complete else "failed",
                 selected_attempt=directory if complete else None)
    atomic(state_path, state)
    return {"key": case["key"], "action": "recovered" if complete else "recovery_failed",
            "state": state["state"], "error_type": attempt.get("error_type")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--case", action="append", required=True)
    parser.add_argument("--secret", type=Path, default=ROOT / ".secrets/autodl_api_token_2")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    base = args.base.resolve()
    protocol = json.loads((base / "protocol.json").read_text())
    check_protocol(protocol)
    by_key = {case["key"]: case for case in protocol["cases"]}
    if len(args.case) != len(set(args.case)) or not set(args.case) <= set(by_key):
        raise ValueError("Duplicate or unknown case")
    env, fingerprint = secondary_environment(args.secret.resolve())
    started = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(recover, base, by_key[key], protocol, env, fingerprint)
                   for key in args.case]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    report = {"schema": "autodl-orphan-recovery-report/v1", "started_at": started,
              "finished_at": time.time(), "key_fingerprint": fingerprint, "results": results}
    atomic(args.report.resolve(), report)
    if any(row.get("action") not in ("recovered", "reconciled_complete_status") for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
