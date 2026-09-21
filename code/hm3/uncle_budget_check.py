"""Post-hoc equal-record-budget PCMCI-G2 score-ranking attribution check.

This is not a threshold-retuned graph. Fixed top-k ranks use MCI p values, then
test statistic and record order to break ties. Selection never reads test gold.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np
from tigramite import data_processing as pp
from tigramite.independence_tests.gsquared import Gsquared
from tigramite.pcmci import PCMCI

from .alignment_report import paired
from .domains import get_domain
from .generate import generate_split
from .read_gate_tcd import panel
from .replay import ExecutorOracle


def main(args):
    domain = get_domain("travel")
    rows = []
    for path in args.inputs:
        data = json.loads(Path(path).read_text())
        config = data["config"]
        if len(data["episodes"]) != config["episodes"]:
            raise ValueError("wait for the frozen test campaign to complete")
        episodes = generate_split(domain, config["seed"], config["split"], config["episodes"])
        for index, (ep, original) in enumerate(zip(episodes, data["episodes"])):
            assert ep.id == original["episode"]
            records = [r["rid"] for r in ep.H]
            oracle = ExecutorOracle(domain, ep)
            X, _, _ = panel(oracle, records, 512, 20260921+index)
            X = X[1:].astype(int)
            names = [f"g{i}" for i in range(len(records))]+["decision_correct"]
            df = pp.DataFrame({0: X}, analysis_mode="multiple", var_names=names,
                              data_type={0: np.ones_like(X, dtype=int)})
            result = PCMCI(dataframe=df, cond_ind_test=Gsquared(significance="analytic"), verbosity=0).run_pcmciplus(tau_min=0, tau_max=1, pc_alpha=.05)
            pvalues, stats = result["p_matrix"][:-1, -1, 1], result["val_matrix"][:-1, -1, 1]
            rank = sorted(range(len(records)), key=lambda i: (pvalues[i], -stats[i], i))
            curves = {}
            for k in (2, 4, 8):
                selected = [records[i] for i in rank[:k]]
                curves[str(k)] = {"records": selected, "correct": bool(oracle(selected)),
                                  "uncle_correct": {n: m["topk"][str(k)]["correct"] for n, m in original["methods"].items()}}
            rows.append({"episode": ep.id, "seed": config["seed"], "pvalues": pvalues.tolist(),
                         "statistics": stats.tolist(), "ranking": [records[i] for i in rank], "topk": curves})
    summary = {}
    for k in ("2", "4", "8"):
        entry = {"pcmci_rank_correct": sum(r["topk"][k]["correct"] for r in rows), "n": len(rows), "uncle_minus_pcmci_rank": {}}
        for method in ("uncle_permutation", "uncle_parameter"):
            diffs = defaultdict(list)
            for r in rows:
                a = r["topk"][k]
                diffs[r["seed"]].append(int(a["uncle_correct"][method])-int(a["correct"]))
            entry["uncle_minus_pcmci_rank"][method] = paired(diffs)
        summary[k] = entry
    output = {"scope": "post-hoc attribution; equal record count and full object context, not guaranteed equal token count; top-k score selector is not an identified graph",
              "config": {"inputs": args.inputs, "alpha": .05, "tau_min": 0, "max_lag": 1,
                         "ranking": "ascending MCI p, descending statistic, stable record order"}, "summary": summary, "episodes": rows}
    Path(args.out).write_text(json.dumps(output, indent=2)+"\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inputs", nargs="+", default=[f"results/real/hm3/alignment/uncle_s{s}.json" for s in (60, 61, 62)])
    p.add_argument("--out", default="results/real/hm3/alignment/uncle_budget_check.json")
    main(p.parse_args())
