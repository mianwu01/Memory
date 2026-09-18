"""Keep the validated secondary credential busy on balanced far-tail batches.

The controller writes an exact manifest before each batch and delegates all
generation to ``autodl_secondary_dispatch.py``.  It only selects registered
repeat-2 cases that have no state file, leaving the primary cursor and every
frozen scientific setting unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from autodl_travel_campaign import atomic, check_protocol
from faithful_memory import ROOT


GROUPS = [("implicit", arm) for arm in
          ("ours", "noGcompact", "query_only", "bm25", "full", "dense",
           "summary", "mem0", "amem", "lightmem")]
GROUPS += [("explicit", arm) for arm in ("ours", "noGcompact", "query_only")]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_for_report(path: Path) -> dict:
    while not path.exists():
        time.sleep(30)
    return json.loads(path.read_text())


def acceptable(report: dict, minimum_fraction: float) -> bool:
    results = report.get("results", [])
    if not results:
        return False
    if any(row.get("last_api_status") in (401, 402, 403) for row in results):
        return False
    return sum(row.get("state") == "complete" for row in results) / len(results) >= minimum_fraction


def balanced_unstarted(protocol: dict, base: Path, count: int) -> list[dict]:
    grouped = defaultdict(list)
    for case in protocol["cases"]:
        if case["repeat"] != 2:
            continue
        state = base / "cases" / case["key"] / "case_state.json"
        if not state.exists():
            grouped[(case["variant"], case["arm"])].append(case)
    queues = {group: deque(sorted(grouped[group], key=lambda row: row["id"], reverse=True))
              for group in GROUPS}
    selected = []
    while len(selected) < count:
        changed = False
        for group in GROUPS:
            if queues[group] and len(selected) < count:
                selected.append(queues[group].popleft())
                changed = True
        if not changed:
            break
    return selected


def register_manifest(base: Path, protocol_path: Path, cases: list[dict],
                      fingerprint: str, workers: int, sequence: int,
                      previous_report: Path) -> Path:
    manifest = {
        "schema": "autodl-secondary-dispatch-manifest/v1",
        "created_at": time.time(),
        "purpose": "Automatic balanced far-tail key2 batch after a successful validated batch.",
        "protocol_sha256": sha(protocol_path),
        "key_fingerprint": fingerprint,
        "workers": workers,
        "case_keys": [case["key"] for case in cases],
        "selection": {
            "repeat": 2,
            "episode_ids": sorted({case["id"] for case in cases}),
            "distribution": dict(Counter(f"{case['variant']}/{case['arm']}" for case in cases)),
            "reason": "Unstarted repeat-2 cases, descending episode id and round-robin across all arms.",
        },
        "previous_report": str(previous_report.relative_to(ROOT)),
        "policy": "Scheduling-only amendment; exact frozen child source/model/endpoint/budgets. Preserve every attempt.",
    }
    path = base / "monitoring" / f"secondary_key2_auto_{sequence:03d}.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    amendment = {key: manifest[key] for key in
                 ("schema", "created_at", "purpose", "protocol_sha256", "key_fingerprint",
                  "workers", "case_keys", "selection", "previous_report", "policy")}
    with (base / "scheduling_amendments.jsonl").open("a") as handle:
        handle.write(json.dumps(amendment, ensure_ascii=False) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--secret", type=Path, default=ROOT / ".secrets/autodl_api_token_2")
    parser.add_argument("--wait-report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--minimum-success-fraction", type=float, default=0.75)
    args = parser.parse_args()
    if not 1 <= args.workers <= 64 or not 1 <= args.batch_size <= 64:
        parser.error("workers and batch-size must be in 1..64")
    if not 0.5 <= args.minimum_success_fraction <= 1.0:
        parser.error("minimum-success-fraction must be in 0.5..1.0")
    base = args.base.resolve()
    protocol_path = base / "protocol.json"
    protocol = json.loads(protocol_path.read_text())
    check_protocol(protocol)
    credential = args.secret.resolve().read_text().strip()
    fingerprint = hashlib.sha256(credential.encode()).hexdigest()[:16]
    previous = args.wait_report.resolve()
    sequence = 1
    while True:
        report = wait_for_report(previous)
        if not acceptable(report, args.minimum_success_fraction):
            atomic(base / "monitoring/secondary_key2_controller_state.json",
                   {"state": "stopped_health_threshold", "time": time.time(),
                    "previous_report": str(previous), "success_fraction":
                    sum(x.get("state") == "complete" for x in report.get("results", [])) /
                    max(1, len(report.get("results", [])))})
            return
        cases = balanced_unstarted(protocol, base, args.batch_size)
        if not cases:
            atomic(base / "monitoring/secondary_key2_controller_state.json",
                   {"state": "complete_no_unstarted_repeat2", "time": time.time(),
                    "previous_report": str(previous)})
            return
        while (base / "monitoring" / f"secondary_key2_auto_{sequence:03d}.json").exists():
            sequence += 1
        manifest = register_manifest(base, protocol_path, cases, fingerprint,
                                     args.workers, sequence, previous)
        atomic(base / "monitoring/secondary_key2_controller_state.json",
               {"state": "running", "time": time.time(), "sequence": sequence,
                "manifest": str(manifest), "case_count": len(cases)})
        command = [sys.executable, "-u", str(ROOT / "code/autodl_secondary_dispatch.py"),
                   "--base", str(base), "--manifest", str(manifest),
                   "--secret", str(args.secret.resolve()), "--workers", str(args.workers)]
        process = subprocess.run(command, cwd="/tmp", check=False)
        previous = manifest.with_name(manifest.stem + "_report.json")
        if not previous.exists():
            atomic(base / "monitoring/secondary_key2_controller_state.json",
                   {"state": "stopped_missing_batch_report", "time": time.time(),
                    "manifest": str(manifest), "return_code": process.returncode})
            return
        sequence += 1


if __name__ == "__main__":
    main()
