"""Reconcile an interrupted secondary batch, then resume its batch controller."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from autodl_travel_campaign import atomic
from faithful_memory import ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--secret", type=Path, default=ROOT / ".secrets/autodl_api_token_2")
    parser.add_argument("--extra-case", action="append", default=[])
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()
    base = args.base.resolve()
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text())
    orphaned = []
    for key in manifest["case_keys"] + args.extra_case:
        state = json.loads((base / "cases" / key / "case_state.json").read_text())
        if state.get("state") != "running" or not state.get("attempts"):
            continue
        pid = state["attempts"][-1].get("pid")
        if not pid or not Path("/proc", str(pid)).exists():
            orphaned.append(key)
    orphan_report = manifest_path.with_name(manifest_path.stem + "_orphan_recovery.json")
    if orphaned:
        command = [sys.executable, "-u", str(ROOT / "code/autodl_orphan_recovery.py"),
                   "--base", str(base), "--secret", str(args.secret.resolve()),
                   "--workers", str(min(args.workers, len(orphaned))),
                   "--report", str(orphan_report)]
        for key in orphaned:
            command.extend(("--case", key))
        subprocess.run(command, cwd="/tmp", check=False)
    states = []
    for key in manifest["case_keys"]:
        state = json.loads((base / "cases" / key / "case_state.json").read_text())
        if state.get("state") not in ("complete", "failed"):
            atomic(base / "monitoring/secondary_key2_controller_state.json",
                   {"state": "stopped_unreconciled_orphan", "time": time.time(),
                    "manifest": str(manifest_path), "case": key,
                    "case_state": state.get("state")})
            return
        attempt = state.get("attempts", [])[-1]
        states.append({"key": key, "state": state["state"],
                       "elapsed_seconds": attempt.get("finished_at", time.time()) -
                       attempt.get("started_at", time.time()),
                       "error_type": attempt.get("error_type"),
                       "last_api_status": attempt.get("last_api_status")})
    starts = []
    finishes = []
    for key in manifest["case_keys"]:
        state = json.loads((base / "cases" / key / "case_state.json").read_text())
        starts.extend(a.get("started_at") for a in state.get("attempts", []) if a.get("started_at"))
        finishes.extend(a.get("finished_at") for a in state.get("attempts", []) if a.get("finished_at"))
    report_path = manifest_path.with_name(manifest_path.stem + "_report.json")
    report = {"schema": "autodl-secondary-dispatch-report/v1",
              "started_at": min(starts) if starts else manifest["created_at"],
              "finished_at": max(finishes) if finishes else time.time(),
              "workers": manifest["workers"],
              "key_fingerprint": manifest["key_fingerprint"],
              "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "scheduler_snapshot": "reconstructed_after_local_dispatcher_loss",
              "reconstruction": {"time": time.time(), "orphaned_cases": orphaned,
                                 "orphan_report": str(orphan_report)},
              "results": states}
    atomic(report_path, report)
    command = [sys.executable, "-u", str(ROOT / "code/autodl_secondary_campaign.py"),
               "--base", str(base), "--wait-report", str(report_path),
               "--secret", str(args.secret.resolve()), "--workers", str(args.workers),
               "--batch-size", str(args.workers), "--minimum-success-fraction", "0.75"]
    os_result = subprocess.run(command, cwd="/tmp", check=False)
    raise SystemExit(os_result.returncode)


if __name__ == "__main__":
    main()
