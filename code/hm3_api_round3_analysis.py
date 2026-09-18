"""Paired analysis of API round 3 (80 episodes per cell, four cells, prompt v2)."""
import glob
import json
import random
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
cells = {}
for p in glob.glob(str(ROOT / "results/real/hm3/round3/shards/*/llm_ledger.jsonl")):
    for l in open(p):
        r = json.loads(l)
        if r.get("event") == "cell" and not r.get("dry_run"):
            cells.setdefault((r["domain"], r["episode"], r["selection"], r["serialization"]),
                             (r["score"]["ees"], r["input_tokens"]))
rng = random.Random(0)


def paired(d, a, b):
    eps = sorted({k[1] for k in cells if k[0] == d and (k[2], k[3]) == a})
    diffs = [cells[(d, e, *a)][0] - cells[(d, e, *b)][0] for e in eps if (d, e, *b) in cells]
    arr = [float(x) for x in diffs]
    bs = [float(np.mean(rng.choices(arr, k=len(arr)))) for _ in range(5000)] if arr else []
    return {"n": len(arr), "mean": float(np.mean(arr)) if arr else None,
            "ci_lo": float(np.percentile(bs, 2.5)) if bs else None, "ci_hi": float(np.percentile(bs, 97.5)) if bs else None,
            "wtl": [int(sum(x > 0 for x in arr)), int(sum(x == 0 for x in arr)), int(sum(x < 0 for x in arr))]}


out = {}
for d in ("travel", "search"):
    ees = {}
    for sel, ser in (("graph", "compact"), ("full", "verbose"), ("graph", "verbose"), ("full", "compact")):
        rows = [v for k, v in cells.items() if k[0] == d and (k[2], k[3]) == (sel, ser)]
        ees[f"{sel}/{ser}"] = {"n": len(rows), "ees": float(np.mean([r[0] for r in rows])) if rows else None,
                               "input_tokens": int(sum(r[1] for r in rows))}
    gc, fv = ees["graph/compact"], ees["full/verbose"]
    red = 1 - gc["input_tokens"] / fv["input_tokens"] if fv["input_tokens"] else None
    main = paired(d, ("graph", "compact"), ("full", "verbose"))
    out[d] = {"cells": ees, "main_judgement": {
        "ees_delta": (gc["ees"] - fv["ees"]) if gc["ees"] is not None and fv["ees"] is not None else None,
        "input_reduction": red, "point_rule_pass": bool(gc["ees"] is not None and gc["ees"] - fv["ees"] >= -0.10 and red >= 0.30),
        "paired": main},
        "selection_isolation": paired(d, ("graph", "verbose"), ("full", "verbose")),
        "serialization_isolation": paired(d, ("full", "compact"), ("full", "verbose"))}
    print(f"== {d}: " + ", ".join(f"{k} {v['ees']:.3f} (n={v['n']})" for k, v in ees.items() if v['ees'] is not None))
    mj = out[d]["main_judgement"]
    if mj["ees_delta"] is None or main["n"] == 0:
        print(f"   {d}: incomplete cells, no judgement")
        continue
    print(f"   main: delta {mj['ees_delta']:+.3f}, input -{red*100:.1f}%, point rule {'PASS' if mj['point_rule_pass'] else 'FAIL'}; "
          f"paired {main['mean']:+.3f} [{main['ci_lo']:+.3f}, {main['ci_hi']:+.3f}] W/T/L {main['wtl']}")
    for name in ("selection_isolation", "serialization_isolation"):
        m = out[d][name]
        if m["n"]:
            print(f"   {name}: {m['mean']:+.3f} [{m['ci_lo']:+.3f}, {m['ci_hi']:+.3f}] n={m['n']}")
json.dump(out, open(ROOT / "results/real/hm3/round3/paired_analysis.json", "w"), indent=1)
print("saved results/real/hm3/round3/paired_analysis.json")
