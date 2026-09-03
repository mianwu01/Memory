"""Paired analysis of API round 4 (graph_closed selection) against round 3's full/verbose cells."""
import glob
import json
import random
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load(pattern):
    cells = {}
    for p in glob.glob(str(ROOT / pattern)):
        for l in open(p):
            r = json.loads(l)
            if r.get("event") == "cell" and not r.get("dry_run"):
                cells.setdefault((r["domain"], r["episode"], r["selection"], r["serialization"]), (r["score"]["ees"], r["input_tokens"]))
    return cells


r3 = load("results/real/hm3/round3/shards/*/llm_ledger.jsonl")
r4 = load("results/real/hm3/round4/shards/*/llm_ledger.jsonl")
rng = random.Random(0)


def paired(d, a_cells, a, b_cells, b):
    eps = sorted({k[1] for k in a_cells if k[0] == d and (k[2], k[3]) == a})
    diffs = [a_cells[(d, e, *a)][0] - b_cells[(d, e, *b)][0] for e in eps if (d, e, *b) in b_cells]
    arr = [float(x) for x in diffs]
    bs = [float(np.mean(rng.choices(arr, k=len(arr)))) for _ in range(5000)] if arr else []
    toks_a = sum(a_cells[(d, e, *a)][1] for e in eps if (d, e, *b) in b_cells)
    toks_b = sum(b_cells[(d, e, *b)][1] for e in eps if (d, e, *b) in b_cells)
    return {"n": len(arr), "mean": float(np.mean(arr)) if arr else None,
            "ci_lo": float(np.percentile(bs, 2.5)) if bs else None, "ci_hi": float(np.percentile(bs, 97.5)) if bs else None,
            "wtl": [int(sum(x > 0 for x in arr)), int(sum(x == 0 for x in arr)), int(sum(x < 0 for x in arr))],
            "ees_a": float(np.mean([a_cells[(d, e, *a)][0] for e in eps if (d, e, *b) in b_cells])) if arr else None,
            "ees_b": float(np.mean([b_cells[(d, e, *b)][0] for e in eps if (d, e, *b) in b_cells])) if arr else None,
            "input_reduction": (1 - toks_a / toks_b) if toks_b else None}


out = {}
for d in ("travel", "search"):
    out[d] = {}
    for ser in ("compact", "verbose"):
        m = paired(d, r4, ("graph_closed", ser), r3, ("full", "verbose"))
        m["point_rule_pass"] = bool(m["n"] and m["mean"] >= -0.10 and (m["input_reduction"] or 0) >= 0.30)
        out[d][f"graph_closed/{ser} - full/verbose(r3)"] = m
        if m["n"]:
            print(f"{d} graph_closed/{ser} {m['ees_a']:.3f} vs full/verbose {m['ees_b']:.3f} (n={m['n']}): paired {m['mean']:+.3f} "
                  f"[{m['ci_lo']:+.3f}, {m['ci_hi']:+.3f}] W/T/L {m['wtl']}, input -{m['input_reduction']*100:.1f}%, point rule {'PASS' if m['point_rule_pass'] else 'FAIL'}")
    m = paired(d, r4, ("graph_closed", "compact"), r3, ("graph", "compact"))
    out[d]["graph_closed/compact - graph/compact(r3)"] = m
    if m["n"]:
        print(f"{d} closure effect (graph_closed/compact - graph/compact): {m['mean']:+.3f} [{m['ci_lo']:+.3f}, {m['ci_hi']:+.3f}] n={m['n']}")
json.dump(out, open(ROOT / "results/real/hm3/round4/paired_analysis.json", "w"), indent=1)
print("saved results/real/hm3/round4/paired_analysis.json")
