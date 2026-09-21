"""Merge independent audit partitions after verifying identical protocols."""
import argparse
import hashlib
import json
from pathlib import Path


def main(args):
    base = json.loads(Path(args.inputs[0]).read_text())
    merged = {"config": base["config"], "source_artifacts": [], "runs": {}}
    semantic = ("n_eval", "split", "no_matched", "graph_artifact_sha256", "graph_seed", "tokenizer_proxy", "permutation_seeds")
    for filename in args.inputs:
        raw = Path(filename).read_bytes()
        part = json.loads(raw)
        for key in semantic:
            if part["config"].get(key) != base["config"].get(key):
                raise ValueError(f"protocol mismatch for {key} in {filename}")
        for key, cell in part["runs"].items():
            if key in merged["runs"] and merged["runs"][key] != cell:
                raise ValueError(f"inconsistent duplicate cell {key}")
            merged["runs"][key] = cell
        merged["source_artifacts"].append({"path": filename, "sha256": hashlib.sha256(raw).hexdigest(), "config": part["config"]})
    expected = {f"{d}/seed{s}/{c}" for d in base["config"]["domains"] for s in base["config"]["seeds"] for c in base["config"]["conditions"]}
    missing = sorted(expected - set(merged["runs"]))
    if missing:
        raise ValueError(f"incomplete audit: {missing}")
    merged["complete"] = True
    Path(args.out).write_text(json.dumps(merged, indent=1))
    print(json.dumps({"cells": len(merged["runs"]), "episodes": sum(c["n"] for c in merged["runs"].values()), "out": args.out}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inputs", nargs="+", default=["results/real/hm3/alignment/controls_historical.json", "results/real/hm3/alignment/controls_shopping31.json", "results/real/hm3/alignment/controls_shopping32.json"])
    p.add_argument("--out", default="results/real/hm3/alignment/controls_complete.json")
    main(p.parse_args())
