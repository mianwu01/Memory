"""Continuously drain eligible Travel transport failures at fixed concurrency."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from autodl_transport_recovery import reason_for_recovery
from autodl_travel_campaign import atomic
from faithful_memory import ROOT


def eligible_count(base: Path, protocol: dict) -> tuple[int, dict[str, int]]:
    eligible = 0
    counts = {"complete": 0, "failed": 0, "running": 0, "not_started": 0}
    for case in protocol["cases"]:
        folder = base / "cases" / case["key"]
        state_path = folder / "case_state.json"
        if not state_path.exists():
            counts["not_started"] += 1
            continue
        try:
            state = json.loads(state_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        status = state.get("state")
        counts[status] = counts.get(status, 0) + 1
        attempts = state.get("attempts", [])
        if status != "failed" or not attempts or len(attempts) >= 3:
            continue
        previous = folder / attempts[-1]["directory"]
        event_path = previous / "events.jsonl"
        trace_path = previous / "error_traceback.txt"
        rows = []
        if event_path.exists():
            for line in event_path.read_text().splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        if reason_for_recovery(rows, trace_path.read_text() if trace_path.exists() else ""):
            eligible += 1
    return eligible, counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()
    base = args.base.resolve()
    protocol = json.loads((base / "protocol.json").read_text())
    state_path = base / "monitoring/recovery_campaign_state.json"
    passes = 0
    while True:
        eligible, counts = eligible_count(base, protocol)
        atomic(state_path, {"state": "running", "time": time.time(), "passes": passes,
                            "eligible_transport_failures": eligible, "case_states": counts})
        if eligible:
            command = [sys.executable, "-u", str(ROOT / "code/autodl_transport_recovery.py"),
                       "--base", str(base), "--workers", str(args.workers)]
            subprocess.run(command, cwd="/tmp", check=False)
            passes += 1
            continue
        if counts.get("running", 0) == 0 and counts.get("not_started", 0) == 0:
            atomic(state_path, {"state": "complete", "time": time.time(), "passes": passes,
                                "eligible_transport_failures": 0, "case_states": counts})
            return
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
