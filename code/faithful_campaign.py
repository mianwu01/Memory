"""Advance this authorized campaign only when every validation gate passes.

No retries, provider switching, subset selection or relaxed acceptance happens
inside this supervisor. It records a concrete failure and stops for diagnosis.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from faithful_memory import ARMS, ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--development-family", required=True)
    ap.add_argument("--evaluation-family", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--state-name", default="campaign_state.json")
    ap.add_argument("--native-gates", choices=["required", "deferred"], default="required",
                    help="deferred: native LoCoMo checks are reported separately and are not a precondition")
    args = ap.parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    for value in (args.development_family, args.evaluation_family):
        if Path(value).name != value or value in {".", ".."}:
            raise ValueError("Expected one family name")
    dev = ROOT / "results/development" / args.development_family
    if Path(args.state_name).name != args.state_name:
        raise ValueError("Expected one state filename")
    state_path = dev / args.state_name
    if state_path.exists():
        raise ValueError("Existing supervisor state requires explicit review")
    state = {"started_at": time.time(), "model": os.environ["OPENAI_MODEL"],
             "endpoint": os.environ["OPENAI_BASE_URL"], "evaluation_family": args.evaluation_family,
             "native_gates": args.native_gates, "workers": args.workers,
             "policy": "all selected gates; one formal attempt per case; no automatic recovery"}

    def record(phase, **values):
        state.update(phase=phase, updated_at=time.time(), **values)
        state_path.write_text(json.dumps(state, indent=2))
        print(json.dumps(state), flush=True)

    required = [(dev / "travel" / f"{arm}_101/status.json", "complete") for arm in ARMS]
    recovery_path = dev / "development_recovery_sources.json"
    mapping = {}
    if recovery_path.exists():
        # Mapping grows only under the separate registered recovery supervisor.
        # Wait for its final decision before evaluating any original failure.
        while not (dev / "development_recovery_status.json").exists():
            record("awaiting_registered_development_recovery")
            time.sleep(45)
        recovery_status = json.loads((dev / "development_recovery_status.json").read_text())
        if not recovery_status["complete"]:
            record("development_recovery_failed")
            raise SystemExit(1)
        mapping = json.loads(recovery_path.read_text())
        if mapping.get("schema") != "faithful-memory-recovery-sources/v2":
            raise ValueError("Unsupported recovery mapping schema")
        if mapping.get("native_gates") != ("deferred" if args.native_gates == "deferred" else "included"):
            raise ValueError("Campaign native-gate mode differs from registered recovery")
        required = [(dev / mapping.get(arm, f"travel/{arm}_101") / "status.json", "complete") for arm in ARMS]
    amendment_path = dev / "amem_budget_amendment.json"
    amendment = json.loads(amendment_path.read_text()) if amendment_path.exists() else None
    for arm in ("mem0", "amem", "lightmem"):
        online = amendment["new_online_output"] if amendment and arm == "amem" else "validation/" + arm + "_online"
        required.append((dev / online / "validation.json", "passed"))
        if args.native_gates == "required":
            native = amendment["new_native_output"] if amendment and arm == "amem" else "native/" + arm
            native = mapping.get("native/" + arm, native)
            required.append((dev / native / "validation.json", "passed"))
    while True:
        present = [(p, key, json.loads(p.read_text())) for p, key in required if p.exists()]
        bad = []
        for p, key, value in present:
            if value.get(key) is True:
                continue
            review_path = p.parent / "review.json"
            review = json.loads(review_path.read_text()) if review_path.exists() else {}
            if key == "passed" and review.get("schema") == "amem-optional-link-criterion-review/v1" and review.get("accepted"):
                from faithful_acceptance import evidence
                evidence(p, key)
                continue
            bad.append(str(p.relative_to(ROOT)))
        if bad:
            record("validation_failed", failures=bad)
            raise SystemExit(1)
        if len(present) == len(required):
            break
        record("awaiting_validations", complete=len(present), required=len(required))
        if time.time() - state["started_at"] > 12 * 3600:
            record("validation_timeout")
            raise SystemExit(1)
        time.sleep(45)

    def execute(label, *arguments):
        record(label)
        code = subprocess.call([sys.executable, "-u", *arguments], cwd=ROOT)
        if code:
            record(label + "_failed", exit_code=code)
            raise SystemExit(code)

    acceptance_args = ["--family", args.development_family]
    if args.native_gates == "deferred":
        acceptance_args.append("--defer-native")
    execute("acceptance", "code/faithful_acceptance.py", *acceptance_args)
    execute("freeze", "code/faithful_suite.py", "--phase", "evaluation", "--family", args.evaluation_family,
            "--development-family", args.development_family, "--workers", str(args.workers), "--freeze")
    execute("evaluation", "code/faithful_suite.py", "--phase", "evaluation", "--family", args.evaluation_family,
            "--workers", str(args.workers))
    execute("analysis", "code/faithful_report.py", "--base", str(ROOT / "results/real" / args.evaluation_family))
    record("complete")


if __name__ == "__main__":
    main()
