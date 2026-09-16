"""One registered development retry for an explicit relay stream interruption."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from faithful_memory import ARMS, ROOT
from faithful_report import events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    args = ap.parse_args()
    base = ROOT / "results/development" / args.family
    if not (base / "stream_recovery_amendment.json").exists():
        raise ValueError("No registered recovery policy")
    mapping_path = base / "development_recovery_sources.json"
    if mapping_path.exists():
        raise ValueError("Recovery already initiated")
    mappings, lock = {}, threading.Lock()
    mapping_path.write_text("{}")
    env = os.environ.copy()
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "2"

    def run(arm):
        original = base / "travel" / f"{arm}_101"
        deadline = time.time() + 4 * 3600
        while not (original / "status.json").exists():
            if time.time() > deadline:
                raise RuntimeError("Development process did not finish: " + arm)
            time.sleep(10)
        status = json.loads((original / "status.json").read_text())
        if status["complete"]:
            return {"arm": arm, "recovered": False, "complete": True}
        failures = [r for r in events(original / "events.jsonl") if r["event"] == "api_error"]
        if len(failures) != 1 or not any(a.get("code") == "upstream_stream_read_error" and a.get("stream_opened")
                                      for a in failures[0].get("attempts", [])):
            raise RuntimeError("Failure is outside registered stream recovery: " + arm)
        rel = f"travel_recovery/{arm}_101"
        out = base / rel
        if out.exists():
            raise ValueError("Never repeat an existing recovery attempt: " + arm)
        with lock:
            mappings[arm] = rel
            mapping_path.write_text(json.dumps(mappings, indent=2))
        logfile = base / "logs" / (arm + "_101_stream_recovery.log")
        with logfile.open("x") as handle:
            code = subprocess.call([sys.executable, "-u", str(ROOT / "code/faithful_arena_run.py"),
                "--arm", arm, "--id", "101", "--out", str(out), "--actor-thinking", "default"],
                cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
        row = {"arm": arm, "recovered": True, "complete": code == 0}
        print(json.dumps(row), flush=True)
        return row

    # Put already failed cases first; ordering is independent of scores.
    order = sorted(ARMS, key=lambda arm: not (base / "travel" / f"{arm}_101/status.json").exists())
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(run, order))
        report = {"complete": all(r["complete"] for r in rows), "rows": rows}
    except Exception as exc:
        report = {"complete": False, "error_type": type(exc).__name__, "diagnostic": str(exc)}
    (base / "development_recovery_status.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    if not report["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
