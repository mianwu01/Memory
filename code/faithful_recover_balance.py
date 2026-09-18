"""Run one registered recovery after the 2026-09-15 balance interruption."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from faithful_memory import ARMS, ROOT

NATIVE = ("mem0", "amem", "lightmem")
TRAVEL_DIR = "travel_recovery_balance"
NATIVE_DIR = "native_recovery_balance"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def travel_state(base, arm):
    status = base / "travel" / f"{arm}_101" / "status.json"
    if not status.exists():
        return "missing"
    return "complete" if json.loads(status.read_text()).get("complete") is True else "failed"


def native_state(base, arm, amendment):
    folder = amendment["new_native_output"] if amendment and arm == "amem" else "native/" + arm
    validation = base / folder / "validation.json"
    if not validation.exists():
        return "missing"
    return "complete" if json.loads(validation.read_text()).get("passed") is True else "failed"


def plan(base, include_native):
    amendment_path = base / "amem_budget_amendment.json"
    amendment = json.loads(amendment_path.read_text()) if amendment_path.exists() else None
    travel = [arm for arm in ARMS if travel_state(base, arm) != "complete"]
    native = [arm for arm in NATIVE if native_state(base, arm, amendment) != "complete"] if include_native else []
    return travel, native


def load_registered_path(value):
    value = Path(value)
    if value.is_absolute():
        raise ValueError("Registered artifact path must be repository-relative")
    path = (ROOT / value).resolve()
    if path != ROOT.resolve() and ROOT.resolve() not in path.parents:
        raise ValueError("Registered artifact path escapes the repository")
    return path


def recovery_output(base, value):
    value = Path(value)
    if value.is_absolute():
        raise ValueError("Recovery output must be family-relative")
    path = (base / value).resolve()
    if path != base.resolve() and base.resolve() not in path.parents:
        raise ValueError("Recovery output escapes the development family")
    return path


def validate_amendment(base, amendment, workers):
    if amendment.get("schema") != "faithful-memory-balance-recovery/v1":
        raise ValueError("Unsupported balance recovery amendment")
    endpoint, model = os.environ["OPENAI_BASE_URL"].rstrip("/"), os.environ["OPENAI_MODEL"]
    if amendment.get("endpoint", "").rstrip("/") != endpoint or amendment.get("model") != model:
        raise ValueError("Registered recovery route differs from the active route")
    if amendment.get("workers") != workers:
        raise ValueError("Registered worker count differs from the requested worker count")
    probe_path = load_registered_path(amendment["generation_probe_record"])
    probe = json.loads(probe_path.read_text())
    if (not probe.get("passed") or probe.get("schema") != "faithful-memory-generation-probe/v1"
            or probe.get("endpoint", "").rstrip("/") != endpoint or probe.get("model") != model
            or digest(probe_path) != amendment.get("generation_probe_sha256")):
        raise ValueError("Generation probe does not validate the registered route")
    concurrency_path = load_registered_path(amendment["concurrency_probe_record"])
    concurrency = json.loads(concurrency_path.read_text())
    successful = [level["concurrency"] for level in concurrency.get("levels", []) if level.get("failed") == 0]
    if (concurrency.get("schema") != "faithful-memory-concurrency-probe/v1"
            or concurrency.get("endpoint", "").rstrip("/") != endpoint or concurrency.get("model") != model
            or digest(concurrency_path) != amendment.get("concurrency_probe_sha256")
            or not successful or max(successful) < workers):
        raise ValueError("Concurrency probe does not justify the registered worker count")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--defer-native", action="store_true")
    ap.add_argument("--native-only", action="store_true")
    ap.add_argument("--actor-thinking", choices=["default"], default="default")
    args = ap.parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    if args.defer_native and args.native_only:
        raise ValueError("native-only is the completion of an earlier deferred recovery")
    if Path(args.family).name != args.family or args.family in {".", ".."}:
        raise ValueError("Expected one family name")
    base = ROOT / "results/development" / args.family
    amendment_path = base / "balance_recovery_amendment.json"
    if not amendment_path.exists():
        raise ValueError("Register balance_recovery_amendment.json before any paid retry")
    amendment = json.loads(amendment_path.read_text())
    validate_amendment(base, amendment, args.workers)
    mapping_path = base / "development_recovery_sources.json"
    if args.native_only:
        if not mapping_path.exists():
            raise ValueError("No deferred recovery registration exists")
        mappings = json.loads(mapping_path.read_text())
        if mappings.get("schema") != "faithful-memory-recovery-sources/v2" or mappings.get("native_gates") != "deferred":
            raise ValueError("Registered recovery did not defer native gates")
        if digest(amendment_path) != mappings.get("amendment_sha256"):
            raise ValueError("Balance recovery amendment changed after registration")
        status_path = base / "deferred_native_recovery_status.json"
        if status_path.exists():
            raise ValueError("Deferred native recovery already initiated")
        travel, native = [], list(mappings.get("deferred_native_arms", []))
    else:
        if mapping_path.exists():
            raise ValueError("Recovery already initiated; never repeat a registered retry")
        status_path = base / "development_recovery_status.json"
        travel, required_native = plan(base, include_native=True)
        native = [] if args.defer_native else required_native
        registered_travel = amendment.get("retried_gates", {}).get("travel")
        registered_native = amendment.get("retried_gates", {}).get("native")
        if registered_travel != travel or registered_native != required_native:
            raise ValueError("Amendment retry scope differs from the incomplete gates")
        expected_mode = "deferred" if args.defer_native else "required"
        if amendment.get("native_gates") != expected_mode:
            raise ValueError("Registered native-gate mode differs from the requested recovery")
        mappings = {"schema": "faithful-memory-recovery-sources/v2",
                    "registered_at": time.time(),
                    "amendment": str(amendment_path.relative_to(ROOT)),
                    "amendment_sha256": digest(amendment_path),
                    "generation_probe_sha256": amendment["generation_probe_sha256"],
                    "concurrency_probe_sha256": amendment["concurrency_probe_sha256"],
                    "endpoint": os.environ["OPENAI_BASE_URL"].rstrip("/"),
                    "model": os.environ["OPENAI_MODEL"], "workers": args.workers,
                    "native_gates": "deferred" if args.defer_native else "included",
                    "deferred_native_arms": required_native if args.defer_native else []}
        for arm in travel:
            mappings[arm] = f"{TRAVEL_DIR}/{arm}_101"
        for arm in required_native:
            mappings["native/" + arm] = f"{NATIVE_DIR}/{arm}"
        with mapping_path.open("x") as handle:
            json.dump(mappings, handle, indent=2)
    for arm in travel:
        if (base / mappings[arm]).exists():
            raise ValueError("Never repeat an existing recovery attempt: " + arm)
    for arm in native:
        if (base / mappings["native/" + arm]).exists():
            raise ValueError("Never repeat an existing recovery attempt: native/" + arm)
    logs = base / "logs"
    logs.mkdir(exist_ok=True)
    env = os.environ.copy()
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "2"
    env["HF_HUB_OFFLINE"] = "1"
    env["HF_DATASETS_OFFLINE"] = "1"
    lock = threading.Lock()

    def run(case):
        kind, arm = case
        started = time.monotonic()
        if kind == "travel":
            out = recovery_output(base, mappings[arm])
            command = [sys.executable, "-u", str(ROOT / "code/faithful_arena_run.py"), "--arm", arm,
                       "--id", "101", "--out", str(out), "--actor-thinking", args.actor_thinking]
            log = logs / f"{arm}_101_balance_recovery.log"
        else:
            out = recovery_output(base, mappings["native/" + arm])
            command = [sys.executable, "-u", str(ROOT / "code/faithful_locomo_validate.py"),
                       "--arm", arm, "--out", str(out)]
            log = logs / f"native_{arm}_balance_recovery.log"
        with log.open("x") as handle:
            code = subprocess.call(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
        row = {"kind": kind, "arm": arm, "complete": code == 0, "exit_code": code,
               "seconds": time.monotonic() - started}
        with lock:
            print(json.dumps(row), flush=True)
        return row

    cases = [("native", arm) for arm in native] + [("travel", arm) for arm in travel]
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(run, cases))
        report = {"complete": all(row["complete"] for row in rows), "rows": rows,
                  "mode": "native_only" if args.native_only else "initial",
                  "native_gates": mappings["native_gates"], "workers": args.workers}
    except Exception as exc:
        report = {"complete": False, "error_type": type(exc).__name__, "diagnostic": str(exc),
                  "mode": "native_only" if args.native_only else "initial"}
    with status_path.open("x") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report), flush=True)
    if not report["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
