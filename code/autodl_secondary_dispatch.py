"""Dispatch pre-registered Travel cases through a secondary credential.

This scheduler never changes prompts, models, budgets, generation code, or the
frozen protocol.  It only claims exact, far-tail cases before starting them so
the primary campaign observes ``state=running`` and skips duplicate dispatch.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from autodl_travel_campaign import atomic, check_protocol, last_api_status
from faithful_memory import ROOT
from run_with_autodl import ENDPOINT, MODEL


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def secondary_environment(secret_path: Path) -> tuple[dict[str, str], str]:
    key = secret_path.read_text().strip()
    if not key or any(character.isspace() for character in key):
        raise ValueError("Invalid secondary AutoDL credential")
    fingerprint = hashlib.sha256(key.encode()).hexdigest()[:16]
    env = os.environ.copy()
    for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        env[name] = key
    for name in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "DEEPSEEK_BASE_URL"):
        env[name] = ENDPOINT
    for name in ("OPENAI_MODEL", "DEEPSEEK_MODEL"):
        env[name] = MODEL
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[name] = "2"
    env.update(CUDA_VISIBLE_DEVICES="", HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1")
    return env, fingerprint


def reserve(base: Path, cases: list[dict], manifest_sha: str, fingerprint: str) -> None:
    """Claim every assignment before the first child process is started."""
    for case in cases:
        folder = base / "cases" / case["key"]
        folder.mkdir(parents=True, exist_ok=True)
        state_path = folder / "case_state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            raise ValueError(f"Refusing already-started assignment {case['key']}: {state.get('state')}")
        state = {**case, "attempts": [], "state": "running", "selected_attempt": None,
                 "secondary_reservation": {"manifest_sha256": manifest_sha,
                    "key_fingerprint": fingerprint, "reserved_at": time.time()}}
        with state_path.open("x") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)


def run_case(base: Path, case: dict, protocol: dict, env: dict[str, str],
             manifest_sha: str, fingerprint: str) -> dict:
    folder = base / "cases" / case["key"]
    state_path = folder / "case_state.json"
    state = json.loads(state_path.read_text())
    reservation = state.get("secondary_reservation", {})
    if (state.get("state") != "running" or state.get("attempts")
            or reservation.get("manifest_sha256") != manifest_sha
            or reservation.get("key_fingerprint") != fingerprint):
        raise ValueError("Secondary reservation changed for " + case["key"])
    check_protocol(protocol)
    directory = "attempt_0"
    out = folder / directory
    if out.exists():
        raise ValueError("Refusing to overwrite " + str(out))
    attempt = {"directory": directory, "started_at": time.time(), "recovery": False,
               "dispatcher": "secondary", "key_fingerprint": fingerprint}
    state["attempts"].append(attempt)
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
    return {"key": case["key"], "state": state["state"],
            "elapsed_seconds": attempt["finished_at"] - attempt["started_at"],
            "error_type": attempt.get("error_type"),
            "last_api_status": attempt.get("last_api_status")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--secret", type=Path, default=ROOT / ".secrets/autodl_api_token_2")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    if not 1 <= args.workers <= 64:
        parser.error("workers must be in 1..64")
    base = args.base.resolve()
    protocol_path = base / "protocol.json"
    protocol = json.loads(protocol_path.read_text())
    check_protocol(protocol)
    manifest = json.loads(args.manifest.read_text())
    if manifest.get("protocol_sha256") != sha(protocol_path):
        raise ValueError("Manifest does not match protocol")
    by_key = {case["key"]: case for case in protocol["cases"]}
    keys = manifest.get("case_keys", [])
    if not keys or len(keys) != len(set(keys)) or not set(keys) <= set(by_key):
        raise ValueError("Manifest contains missing, duplicate, or unknown cases")
    cases = [by_key[key] for key in keys]
    env, fingerprint = secondary_environment(args.secret.resolve())
    if manifest.get("key_fingerprint") != fingerprint:
        raise ValueError("Secondary credential fingerprint changed")
    manifest_sha = sha(args.manifest)
    snapshot = base / "frozen_source/schedulers" / ("secondary_" + sha(Path(__file__)) + ".py")
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if not snapshot.exists():
        snapshot.write_bytes(Path(__file__).read_bytes())
    reserve(base, cases, manifest_sha, fingerprint)
    started = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_case, base, case, protocol, env, manifest_sha, fingerprint)
                   for case in cases]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    report = {"schema": "autodl-secondary-dispatch-report/v1", "started_at": started,
              "finished_at": time.time(), "workers": args.workers,
              "key_fingerprint": fingerprint, "manifest_sha256": manifest_sha,
              "scheduler_snapshot": str(snapshot.relative_to(base)), "results": results}
    atomic(args.manifest.with_name(args.manifest.stem + "_report.json"), report)
    if any(result["state"] != "complete" for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
