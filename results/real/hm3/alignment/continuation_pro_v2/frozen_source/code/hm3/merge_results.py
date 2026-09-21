"""Merge several run_det result files (same config, disjoint or overlapping learners) into one."""
import json
import sys

out = {"config": None, "runs": {}}
for path in sys.argv[2:]:
    r = json.load(open(path))
    out["config"] = out["config"] or r["config"]
    for key, run_ in r["runs"].items():
        dst = out["runs"].setdefault(key, {"generation_seconds": run_["generation_seconds"], "learners": {}})
        dst["learners"].update(run_["learners"])
json.dump(out, open(sys.argv[1], "w"), indent=1)
print("merged", len(out["runs"]), "runs ->", sys.argv[1])
