"""Post-hoc attribution audit of frozen read-gate fits; never refit GRACE.

Reconstruct the identical randomized panel and run the exact PCMCI-G2 skeleton
used by GRACE. This diagnostic was added after observing the held-out results,
so it cannot be described as a pre-registered baseline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .domains import get_domain
from .generate import generate_split
from .grace_logs import pcmci_skeleton
from .read_gate_tcd import panel
from .replay import ExecutorOracle


def audit(paths):
    rows = []
    for path in paths:
        source = json.loads(Path(path).read_text())
        c = source["config"]
        domain = get_domain(c["domain"])
        episodes = generate_split(domain, c["seed"], c["split"], c["episodes"])
        for index, (ep, original) in enumerate(zip(episodes, source["episodes"])):
            assert ep.id == original["episode"]
            records = [r["rid"] for r in ep.H]
            names = [f"g{i}" for i in range(len(records))] + ["decision_correct"]
            oracle = ExecutorOracle(domain, ep)
            X, _, outcomes = panel(oracle, records, c["trials"], c["mask_seed"]+index)
            assert float(outcomes.mean()) == original["train_success_rate"]
            skeleton = pcmci_skeleton([X[1:]], names, 1, pc_alpha=.05, test="gsquared")
            parents = {names[i] for i in range(len(records)) if skeleton[i, -1, 1]}
            learned = set(original["methods"]["grace_pcmci_g2"]["parents"])
            empirical = set(original["empirical_effect_parents"])
            selected = [records[i] for i in range(len(records)) if names[i] in parents]
            rows.append({"episode": ep.id, "seed": c["seed"],
                         "parents": sorted(parents), "selected_records": selected,
                         "correct": bool(oracle(selected)), "full_read_correct": bool(oracle(records)),
                         "empty_read_correct": bool(oracle([])),
                         "same_parents_as_grace": parents == learned,
                         "skeleton_lagged_edges": int(skeleton[:, :, 1:].sum()),
                         "same_skeleton_edge_count_as_original": int(skeleton[:, :, 1:].sum()) == original["fits"]["grace_pcmci_g2"]["skeleton_edges"],
                         "empirical_flip_precision": len(parents & empirical)/len(parents) if parents else None,
                         "empirical_flip_recall": len(parents & empirical)/len(empirical) if empirical else None})
    return {"status": "post-hoc frozen-input component attribution; no GRACE retraining or parameter tuning",
            "config": {"inputs": paths, "pc_alpha": .05, "test": "gsquared", "max_lag": 1},
            "episodes": rows}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inputs", nargs="+", default=[f"results/real/hm3/alignment/read_gate_tcd_s{s}.json" for s in (50, 51, 52)])
    p.add_argument("--out", default="results/real/hm3/alignment/read_gate_attribution.json")
    args = p.parse_args()
    result = audit(args.inputs)
    Path(args.out).write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"n": len(result["episodes"]),
                      "correct": sum(r["correct"] for r in result["episodes"]),
                      "same_parents_as_grace": sum(r["same_parents_as_grace"] for r in result["episodes"])}))
