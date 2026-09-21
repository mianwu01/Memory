"""Pair the memory-system selector arms (results/real/hm3/memsys/<dir>/<domain>_<cond>) with the actor cells of
the same episodes.  --ref 4096 pairs with the original 4096-cap scaling runs (graph_closed/compact, full/verbose,
bm25_k16/compact); --ref 16k pairs with the 16k same-serialization panels in results/real/hm3/long_out
(graph_seg/verbose, graph_closed/verbose, full/verbose; prompt v2).  --dir names the result directory when it
differs from the system name (amem16k holds amem cells rerun at the 16k cap).

Usage: python3 -m hm3.memsys_summary --system amem --dir amem16k --ref 16k --domains travel shopping32
       python3 -m hm3.memsys_summary --system mem0_raw --ref 16k
"""
from __future__ import annotations
import argparse, glob, json, os
import numpy as np

REF = {"native": "results/real/hm3/scaling", "100": "results/real/hm3/scaling_v2", "500": "results/real/hm3/scaling_v2"}
REF_SHOP = {"native": "results/real/hm3/scaling", "100": "results/real/hm3/scaling_v3", "500": "results/real/hm3/scaling_v3"}
REF16 = {"native": "results/real/hm3/long_out", "100": "results/real/hm3/long_out", "500": "results/real/hm3/long_out"}
ARMS = {"4096": (("graph_closed", "compact"), ("full", "verbose"), ("bm25_k16", "compact")),
        "16k": (("graph_seg", "verbose"), ("graph_closed", "verbose"), ("full", "verbose"))}


def cells(root):
    """Cells under root/shards*/; each cell carries the shard protocol's output cap as _cap
    (memsys ledgers do not store max_tokens per cell; the protocol file does)."""
    out = {}
    for d in glob.glob(root + "/shards*/*/"):
        lp = os.path.join(d, "llm_ledger.jsonl")
        if not os.path.exists(lp):
            continue
        pp = os.path.join(d, "llm_protocol.json")
        proto = json.load(open(pp)) if os.path.exists(pp) else {}
        cap = int(proto.get("max_tokens", 4096))
        for l in open(lp):
            try:
                r = json.loads(l)
            except Exception:
                continue
            if r.get("event") == "cell":
                r["_cap"] = cap
                out[(r["selection"], r["serialization"], r["episode"])] = r
    return out


def ci(d, seed=0):
    d = np.asarray(d, float)
    if len(d) == 0:
        return "—"
    rng = np.random.default_rng(seed)
    b = [rng.choice(d, len(d)).mean() for _ in range(4000)]
    return f"{d.mean():+.3f} [{np.percentile(b, 2.5):+.3f}, {np.percentile(b, 97.5):+.3f}]"


def main(system, domains, root, dirname=None, ref_kind="4096"):
    dirname = dirname or system
    arms = ARMS[ref_kind]
    print(f"| domain | history | {system} EES ({dirname}) | n | cap hits | write LLM calls / tokens per episode | actor input tok | "
          + " | ".join(f"vs {a}/{b} ({ref_kind})" for a, b in arms) + " |")
    print("|---|---|---:|---:|---:|---|---:|" + "---|" * len(arms))
    for D in domains:
        for cond in ["native", "100", "500"]:
            m = cells(f"{root}/{dirname}/{D}_{cond}")
            if not m:
                continue
            refroot = (REF16 if ref_kind == "16k" else (REF_SHOP if D.startswith("shopping") else REF))[cond]
            ref = cells(f"{refroot}/{D}_{cond}")
            if ref_kind == "16k":
                # only the 16k-cap cells of the prompt-v2 panels (protocol per shard dir)
                keep = {}
                for d in glob.glob(f"{refroot}/{D}_{cond}/shards*/*/"):
                    pp = os.path.join(d, "llm_protocol.json")
                    proto = json.load(open(pp)) if os.path.exists(pp) else {}
                    if int(proto.get("max_tokens", 4096)) < 16384 or proto.get("prompt_version") != "v2":
                        continue
                    lp = os.path.join(d, "llm_ledger.jsonl")
                    if not os.path.exists(lp):
                        continue
                    for l in open(lp):
                        try:
                            r = json.loads(l)
                        except Exception:
                            continue
                        if r.get("event") == "cell":
                            keep[(r["selection"], r["serialization"], r["episode"])] = r
                ref = keep
            key = f"{system}_k16"
            eps = sorted(e for (s, z, e) in m if s == key and z == "compact")
            mm = [m[(key, "compact", e)] for e in eps]
            if not mm:
                continue
            ees = np.mean([r["score"]["ees"] for r in mm])
            cap = sum(1 for r in mm if r["output_tokens"] >= r["_cap"])
            wc = np.mean([r["write"]["calls"] for r in mm]); wt = np.mean([r["write"]["input_tokens"] + r["write"]["output_tokens"] for r in mm])
            it = np.mean([r["input_tokens"] for r in mm])
            comps = []
            for (s, z) in arms:
                pe = [e for e in eps if (s, z, e) in ref]
                comps.append(ci([int(m[(key, "compact", e)]["score"]["ees"]) - int(ref[(s, z, e)]["score"]["ees"]) for e in pe]) + f" (n={len(pe)})")
            print(f"| {D} | {cond} | {ees:.2f} | {len(eps)} | {cap} | {wc:.0f} / {wt:.0f} | {it:.0f} | " + " | ".join(comps) + " |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="amem")
    ap.add_argument("--domains", nargs="+", default=["travel", "shopping32"])
    ap.add_argument("--root", default="results/real/hm3/memsys")
    ap.add_argument("--dir", default=None, help="result directory under --root when it differs from --system (e.g. amem16k)")
    ap.add_argument("--ref", default="4096", choices=["4096", "16k"])
    a = ap.parse_args()
    main(a.system, a.domains, a.root, a.dir, a.ref)
