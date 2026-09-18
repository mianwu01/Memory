"""Prespecify and score the complete core Travel panel without new API calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from autodl_report import collect, registered_cases

CORE = ["ours", "noGcompact", "query_only"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def derive(parent):
    registered_cases(parent)
    if set(parent["variants"]) != {"implicit", "explicit"}:
        raise ValueError("Both registered query conditions are required")
    if any(not set(CORE) <= set(arms) for arms in parent["variants"].values()):
        raise ValueError("Parent scope is missing a core method")
    child = dict(parent)
    child["variants"] = {variant: CORE[:] for variant in ("implicit", "explicit")}
    child["cases"] = [case for case in parent["cases"] if case["arm"] in CORE]
    registered_cases(child)
    return child


def register(base):
    if any((base / "cases").glob("**/case_state.json")):
        raise ValueError("The independent core panel must be registered before formal dispatch")
    parent_path = base / "protocol.json"
    parent = json.loads(parent_path.read_text())
    child = derive(parent)
    folder = base / "registered_core"
    folder.mkdir(exist_ok=False)
    child["analysis_registration"] = {
        "created_at": time.time(),
        "parent_protocol_sha256": digest(parent_path),
        "primary_comparisons": ["ours vs noGcompact", "ours vs query_only"],
        "metrics": "PS and input usage; SPS/SR secondary; all paired intervals descriptive",
        "scope": "All original episodes and repeats, both query conditions, all three core methods",
        "failure_policy": "No valid-only subset. All core cases must pass integrity checks.",
        "interpretation": "Core result does not imply completion or superiority over native baselines.",
    }
    (folder / "protocol.json").write_text(json.dumps(child, indent=2))
    # A view of the same generation, not a duplicate run or copied best sample.
    (folder / "cases").symlink_to(base / "cases", target_is_directory=True)
    return folder


def score(base):
    folder = base / "registered_core"
    child = json.loads((folder / "protocol.json").read_text())
    parent_path = base / "protocol.json"
    if digest(parent_path) != child["analysis_registration"]["parent_protocol_sha256"]:
        raise ValueError("Parent protocol changed after analysis registration")
    expected = derive(json.loads(parent_path.read_text()))
    for key in ("cases", "variants", "episode_ids", "repeats", "source_hashes"):
        if expected[key] != child[key]:
            raise ValueError("Registered core scope changed: " + key)
    return collect(folder)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    base = args.base.resolve()
    if args.register:
        print(register(base))
    else:
        result = score(base)
        print(json.dumps({key: result[key] for key in ("complete", "accepted_cases", "expected_cases")}))
        if not result["complete"]:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
