"""Recorded recovery of transport failures, including wrapped broken streams.

Generation source and scientific settings remain exactly those of the frozen
campaign. Semantic/model failures never qualify. All attempts remain on disk.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from autodl_travel_campaign import atomic, check_protocol, last_api_status
from faithful_memory import ROOT
from run_with_autodl import environment, MODEL, ENDPOINT


def verify_generation(protocol):
    if protocol.get("schema") != "autodl-budget-development/v1":
        check_protocol(protocol)
        return
    # This one-case development family predates the scheduler/core-view tools.
    # Those tools are not imported by its child actor. Every generating module,
    # route, budget implementation, and graph must still match its freeze.
    if protocol["model"] != MODEL or protocol["endpoint"] != ENDPOINT:
        raise ValueError("Development route/model changed")
    names = ("faithful_arena_run.py", "faithful_memory.py", "faithful_transport.py",
             "arena_causal_memory.py", "arena_e2e_inherit.py", "relay_chat_transport.py",
             "travel_implicit.py", "run_with_autodl.py")
    for name in names:
        actual = hashlib.sha256((ROOT / "code" / name).read_bytes()).hexdigest()
        if protocol["source_hashes"].get("code/" + name) != actual:
            raise ValueError("Development generating source changed: " + name)
    if hashlib.sha256(Path(protocol["graph_path"]).read_bytes()).hexdigest() != protocol["graph_sha256"]:
        raise ValueError("Development graph changed")


def reason_for_recovery(rows, traceback_text):
    errors = [(i, row) for i, row in enumerate(rows) if row.get("event") == "api_error"]
    if not errors:
        return None
    index, error = errors[-1]
    if any(row.get("event") == "llm" for row in rows[index + 1:]):
        return None
    if any(row.get("event") == "invalid" and row.get("reason") == "Truncated memory completion"
           for row in rows):
        return None
    status = error.get("status_code")
    if status in (401, 402, 403):
        return None
    if status in (429, 500, 502, 503, 504):
        return f"http_{status}"
    if error.get("error_type") in ("APIConnectionError", "APITimeoutError", "TimeoutError",
                                  "RemoteProtocolError", "ReadError", "ReadTimeout", "ConnectTimeout"):
        return error["error_type"]
    marker = "RuntimeError: incomplete stream: missing finish reason or usage"
    if error.get("error_type") == "RuntimeError" and marker in traceback_text:
        return "incomplete_stream_missing_finish_or_usage"
    attempts = error.get("attempts") or []
    if (error.get("error_type") == "RuntimeError" and attempts
            and attempts[-1].get("stream_opened") is True):
        # Some native callers swallow the original exception chain. This receipt
        # is emitted inside create(), before a completion exists or the native
        # semantic parser runs. Keep the missing message explicit.
        return "stream_reconstruction_runtime_error_message_unavailable"
    return None


def recover(base, case, protocol):
    folder = base / "cases" / case["key"]
    state_path = folder / "case_state.json"
    if not state_path.exists():
        return {"key": case["key"], "action": "not_dispatched"}
    lock = (folder / ".recovery.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = json.loads(state_path.read_text())
    attempts = state.get("attempts", [])
    if state.get("state") != "failed" or not attempts or len(attempts) >= 3:
        return {"key": case["key"], "action": "ineligible_state_or_attempt_limit"}
    previous = folder / attempts[-1]["directory"]
    receipt = previous / "events.jsonl"
    trace = previous / "error_traceback.txt"
    rows = [json.loads(line) for line in receipt.read_text().splitlines()] if receipt.exists() else []
    reason = reason_for_recovery(rows, trace.read_text() if trace.exists() else "")
    if reason is None:
        return {"key": case["key"], "action": "not_a_supported_transport_failure"}
    verify_generation(protocol)
    number = len(attempts)
    directory = f"attempt_{number}"
    out = folder / directory
    if out.exists():
        raise ValueError("Refusing to overwrite recovery output")
    authorization = {
        "registered_at": time.time(), "reason": reason,
        "previous_attempt": attempts[-1]["directory"],
        "previous_events_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
        "recovery_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "protocol_sha256": hashlib.sha256((base / "protocol.json").read_bytes()).hexdigest(),
        "policy": "At most three total attempts; same frozen generation source/settings; all attempts charged; no semantic resampling.",
    }
    snapshot = base / "frozen_source/code" / ("recovery_" + authorization["recovery_source_sha256"] + ".py")
    if not snapshot.exists():
        snapshot.write_bytes(Path(__file__).read_bytes())
    authorization["recovery_source_snapshot"] = str(snapshot.relative_to(base))
    atomic(folder / f"recovery_authorization_{number}.json", authorization)
    attempt = dict(directory=directory, started_at=time.time(), recovery=True, recovery_reason=reason)
    attempts.append(attempt)
    state.update(state="running", selected_attempt=None)
    atomic(state_path, state)
    command = [sys.executable, "-u", str(ROOT / "code/faithful_arena_run.py"),
               "--arm", case["arm"], "--id", str(case["id"]), "--out", str(out),
               "--variant", case["variant"], "--graph", protocol["graph_path"],
               "--repeat", str(case["repeat"]), "--actor-thinking", protocol["actor_thinking"],
               "--env-port", "8941"]
    with (folder / f"{directory}.log").open("x") as log:
        proc = subprocess.Popen(command, cwd="/tmp", env=environment(), stdout=log, stderr=subprocess.STDOUT)
        attempt["pid"] = proc.pid
        atomic(state_path, state)
        code = proc.wait()
    status_path = out / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    good = code == 0 and status.get("complete") is True
    attempt.update(finished_at=time.time(), exit_code=code,
                   error_type=status.get("error_type"), last_api_status=last_api_status(out))
    state.update(state="complete" if good else "failed", selected_attempt=directory if good else None)
    atomic(state_path, state)
    return {"key": case["key"], "action": "recovered" if good else "recovery_failed", "reason": reason}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--case", action="append", help="Optional exact registered case keys")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    base = args.base.resolve()
    protocol = json.loads((base / "protocol.json").read_text())
    verify_generation(protocol)
    cases = protocol["cases"]
    if args.case:
        wanted = set(args.case)
        if not wanted <= {case["key"] for case in cases}:
            raise ValueError("Unknown case requested")
        cases = [case for case in cases if case["key"] in wanted]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(lambda case: recover(base, case, protocol), cases):
            if result["action"] not in ("not_dispatched", "ineligible_state_or_attempt_limit"):
                print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
