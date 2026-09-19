"""Pair the memory-system selector arms (results/real/hm3/memsys/<system>/<domain>_<cond>) with the
graph_closed/compact, full/verbose and bm25_k16/compact cells of the same episodes from the scaling runs.

Usage: python3 -m hm3.memsys_summary --system amem --domains travel shopping32
"""
from __future__ import annotations
import argparse, glob, json, os
import numpy as np

REF = {"native": "results/real/hm3/scaling", "100": "results/real/hm3/scaling_v2", "500": "results/real/hm3/scaling_v2"}
REF_SHOP = {"native": "results/real/hm3/scaling", "100": "results/real/hm3/scaling_v3", "500": "results/real/hm3/scaling_v3"}


def cells(root):
    out = {}
    for d in glob.glob(root + "/shards*/*/"):
        lp = os.path.join(d, "llm_ledger.jsonl")
        if not os.path.exists(lp):
            continue
        for l in open(lp):
            try:
                r = json.loads(l)
            except Exception:
                continue
            if r.get("event") == "cell":
                out[(r["selection"], r["serialization"], r["episode"])] = r
    return out


def ci(d, seed=0):
    d = np.asarray(d, float)
    if len(d) == 0:
        return "—"
    rng = np.random.default_rng(seed)
    b = [rng.choice(d, len(d)).mean() for _ in range(4000)]
    return f"{d.mean():+.3f} [{np.percentile(b, 2.5):+.3f}, {np.percentile(b, 97.5):+.3f}]"


def main(system, domains, root):
    print(f"| domain | history | {system} EES | n | write LLM calls / tokens per episode | actor input tok | vs graph_closed/compact | vs full/verbose | vs bm25_k16/compact |")
    print("|---|---|---:|---:|---|---:|---|---|---|")
    for D in domains:
        for cond in ["native", "100", "500"]:
            m = cells(f"{root}/{system}/{D}_{cond}")
            if not m:
                continue
            refroot = (REF_SHOP if D.startswith("shopping") else REF)[cond]
            ref = cells(f"{refroot}/{D}_{cond}")
            key = f"{system}_k16"
            eps = sorted(e for (s, z, e) in m if s == key and z == "compact")
            mm = [m[(key, "compact", e)] for e in eps]
            ees = np.mean([r["score"]["ees"] for r in mm])
            wc = np.mean([r["write"]["calls"] for r in mm]); wt = np.mean([r["write"]["input_tokens"] + r["write"]["output_tokens"] for r in mm])
            it = np.mean([r["input_tokens"] for r in mm])
            comps = []
            for (s, z) in (("graph_closed", "compact"), ("full", "verbose"), ("bm25_k16", "compact")):
                pe = [e for e in eps if (s, z, e) in ref]
                comps.append(ci([int(m[(key, "compact", e)]["score"]["ees"]) - int(ref[(s, z, e)]["score"]["ees"]) for e in pe]) + f" (n={len(pe)})")
            print(f"| {D} | {cond} | {ees:.2f} | {len(eps)} | {wc:.0f} / {wt:.0f} | {it:.0f} | " + " | ".join(comps) + " |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="amem")
    ap.add_argument("--domains", nargs="+", default=["travel", "shopping32"])
    ap.add_argument("--root", default="results/real/hm3/memsys")
    a = ap.parse_args()
    main(a.system, a.domains, a.root)
