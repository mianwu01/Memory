"""One command for the actor-layer panels after the 2026-09-19 truncation / prompt audit.

Reads every llm_ledger.jsonl under the listed roots, groups cells by (domain, condition, prompt,
output cap), and prints per-arm means with cap-hit statistics plus paired bootstrap differences.
A cell "hit the cap" when any attempt returned >= cap output tokens (per-attempt counts are
recorded from 2026-09-19 on; older ledgers only have the sum over attempts, which over-counts a
truncated first attempt by the size of the format repair -- documented in the table header).

Usage: PYTHONPATH=<pylib>:. python3 -m hm3.panel_summary --domain travel \
           --out ../results/real/hm3/long_out/panel_summary.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics as st
from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "results", "real", "hm3")

# (glob under results/real/hm3, condition label)
SOURCES = [
    ("scaling/{d}_native/shards*/*/", "native"),
    ("scaling_v2/{d}_100/shards*/*/", "100"), ("scaling_v2/{d}_500/shards*/*/", "500"),
    ("scaling_v2/{d}_c100/shards*/*/", "c100"), ("scaling_v2/{d}_d100/shards*/*/", "d100"),
    ("scaling_v3/{d}_native/shards*/*/", "native"), ("scaling_v3/{d}_100/shards*/*/", "100"),
    ("scaling_v3/{d}_500/shards*/*/", "500"),
    ("keysel/{d}_native/shards*/*/", "native"), ("keysel/{d}_100/shards*/*/", "100"), ("keysel/{d}_500/shards*/*/", "500"),
    ("long_out/{d}_native/shards*/*/", "native"), ("long_out/{d}_100/shards*/*/", "100"),
    ("long_out/{d}_500/shards*/*/", "500"), ("long_out/{d}_c100/shards*/*/", "c100"),
    ("long_out/{d}_native_v1/shards*/*/", "native"), ("long_out/{d}_100_v1/shards*/*/", "100"),
    ("long_out/{d}_500_v1/shards*/*/", "500"), ("long_out/{d}_c100_v1/shards*/*/", "c100"),
    # substrate port (hm3.arena_run): arena/<domain>_<cond>/shard_<s>_<e>/<prompt>/
    ("frontier_llm/{d}_c100/shards*/*/", "c100"), ("frontier_llm/{d}_500/shards*/*/", "500"),
    ("frontier_llm/{d}_c100_exec/shards*/*/", "c100"), ("frontier_llm/{d}_500_exec/shards*/*/", "500"),
    ("frontier_llm/{d}_native_exec/shards*/*/", "native"), ("frontier_llm/{d}_100_exec/shards*/*/", "100"),
    ("frontier_llm/{d}_100_exec_v2/shards*/*/", "100"), ("frontier_llm/{d}_500_exec_v2/shards*/*/", "500"),
    ("frontier_llm/{d}_c100_llmk3_v*/shards*/*/", "c100"), ("frontier_llm/{d}_500_llmk3_v*/shards*/*/", "500"),
    # seed replication (hm3.autodl_shards with SEED=31/32): seeds/<domain>_<cond>_s<seed>/shards/
    ("seeds/{d}_native_s*/shards*/*/", "native"), ("seeds/{d}_100_s*/shards*/*/", "100"),
    ("seeds/{d}_c100_s*/shards*/*/", "c100"), ("seeds/{d}_500_s*/shards*/*/", "500"),
    ("seeds/{d}_c100_s*_v2/shards*/*/", "c100"), ("seeds/{d}_500_s*_v2/shards*/*/", "500"),
    ("frontier_llm/{d}_100/shards*/*/", "100"), ("frontier_llm/{d}_native/shards*/*/", "native"),
    ("arena/{d}_native/shard_*/*/", "native"), ("arena/{d}_100/shard_*/*/", "100"),
    ("arena/{d}_c100/shard_*/*/", "c100"), ("arena/{d}_500/shard_*/*/", "500"),
]
ARMS = [("full", "verbose"), ("graph_closed", "compact"), ("graph_closed", "verbose"), ("graph_seg", "verbose"), ("frontier_llm", "verbose"), ("frontier_exec", "verbose"),
        ("causal", "verbose"), ("long_context", "verbose"), ("bm25", "verbose"), ("bm25_k16", "verbose"), ("amem", "verbose"),
        ("graph_key2", "compact"), ("graph_key2", "verbose"), ("graph_key3", "compact"), ("bm25_k16", "compact"), ("recency_k16", "compact"),
        ("program", "compact")]
PAIRS = [(("frontier_llm", "verbose"), ("full", "verbose")), (("frontier_llm", "verbose"), ("graph_seg", "verbose")),
         (("frontier_exec", "verbose"), ("full", "verbose")), (("frontier_exec", "verbose"), ("graph_seg", "verbose")),
         (("graph_closed", "compact"), ("full", "verbose")), (("graph_closed", "verbose"), ("full", "verbose")),
         (("graph_seg", "verbose"), ("full", "verbose")), (("graph_seg", "verbose"), ("graph_closed", "compact")),
         (("graph_key2", "compact"), ("graph_closed", "compact")),
         (("graph_key2", "verbose"), ("graph_seg", "verbose")), (("graph_key2", "verbose"), ("full", "verbose")),
         (("graph_key2", "compact"), ("full", "verbose")), (("graph_key3", "compact"), ("graph_closed", "compact")),
         (("bm25_k16", "compact"), ("full", "verbose")), (("recency_k16", "compact"), ("full", "verbose")),
         (("causal", "verbose"), ("long_context", "verbose")), (("causal", "verbose"), ("bm25", "verbose")),
         (("causal", "verbose"), ("bm25_k16", "verbose")), (("causal", "verbose"), ("amem", "verbose")),
         (("amem", "verbose"), ("long_context", "verbose")), (("bm25_k16", "verbose"), ("long_context", "verbose"))]


def load(domain: str) -> Dict[Tuple[str, str, int], Dict[Tuple[str, str], Dict[str, dict]]]:
    """(condition, prompt, cap) -> (selection, serialization) -> episode -> cell (last write wins)."""
    panels: Dict = defaultdict(lambda: defaultdict(dict))
    for pat, cond in SOURCES:
        for d in sorted(glob.glob(os.path.join(ROOT, pat.format(d=domain)))):
            lp = os.path.join(d, "llm_ledger.jsonl")
            pp = os.path.join(d, "llm_protocol.json")
            if not os.path.exists(lp):
                continue
            proto = json.load(open(pp)) if os.path.exists(pp) else {}
            prompt = proto.get("prompt_version", "v1")
            cap = int(proto.get("max_tokens", 4096))
            if proto.get("domain", domain) != domain and "system" in proto:
                continue  # memsys ledgers have their own summariser
            for l in open(lp):
                r = json.loads(l)
                if r.get("event") != "cell" or r.get("dry_run") or r.get("domain", domain) != domain:
                    continue
                r["_cap"] = cap
                panels[(cond, prompt, cap)][(r["selection"], r["serialization"])][r["episode"]] = r
    return panels


def ees(r) -> int:
    return int(bool((r.get("score") or {}).get("ees")))


def hit(r) -> bool:
    per = r.get("output_tokens_per_attempt")
    return (max(per) if per else r["output_tokens"]) >= r["_cap"]


def boot(d: List[int], n_boot: int = 4000, seed: int = 0) -> dict:
    d = np.asarray(d, float)
    rng = np.random.default_rng(seed)
    b = [rng.choice(d, len(d)).mean() for _ in range(n_boot)]
    return {"n": int(len(d)), "mean": float(d.mean()), "ci95": [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]}


def fmt(c: dict) -> str:
    return f"{c['mean']:+.2f} [{c['ci95'][0]:+.2f}, {c['ci95'][1]:+.2f}] n={c['n']}"


def arm_row(rs: List[dict]) -> dict:
    h = [r for r in rs if hit(r)]
    nh = [r for r in rs if not hit(r)]
    sc = [r.get("score") or {} for r in rs]
    return {"n": len(rs), "ees": float(np.mean([ees(r) for r in rs])),
            "aff_f1": float(np.mean([s.get("affected_f1", 0) or 0 for s in sc])),
            "val_acc": float(np.mean([s.get("value_accuracy", 0) or 0 for s in sc])), "hit_cap": len(h),
            "ees_hit": float(np.mean([ees(r) for r in h])) if h else None,
            "ees_not_hit": float(np.mean([ees(r) for r in nh])) if nh else None,
            "legal": float(np.mean([int(bool(s.get("legal"))) for s in sc])),
            "collateral": float(np.mean([s.get("collateral_txns", 0) or 0 for s in sc])),
            "med_in": float(st.median(r["input_tokens"] for r in rs)),
            "med_out": float(st.median(r["output_tokens"] for r in rs))}


def paired(A: Dict[str, dict], B: Dict[str, dict], metric: str = "ees"):
    eps = sorted(set(A) & set(B))
    if not eps:
        return None
    if metric == "ees":
        return boot([ees(A[e]) - ees(B[e]) for e in eps])
    return boot([(A[e].get("score") or {}).get(metric, 0) - (B[e].get("score") or {}).get(metric, 0) for e in eps])


SEED_FILTER = None   # set from --seed: keep only episodes of that seed (episode ids carry "-s<seed>-")


def summarise(domain: str) -> Tuple[dict, str]:
    panels = load(domain)
    if SEED_FILTER is not None:
        tag = f"-s{SEED_FILTER}-"
        panels = {k: {a: {e: c for e, c in cells.items() if tag in e} for a, cells in arms.items()} for k, arms in panels.items()}
        panels = {k: {a: cells for a, cells in arms.items() if cells} for k, arms in panels.items()}
        panels = {k: arms for k, arms in panels.items() if arms}
    out = {"domain": domain, "panels": {}, "cross": {}}
    lines = [f"## {domain}: actor panels (cap-hit = any attempt at the output cap; pre-2026-09-19 ledgers use the summed output tokens)"]
    order = {"native": 0, "100": 1, "c100": 2, "d100": 3, "500": 4}
    for key in sorted(panels, key=lambda k: (order.get(k[0], 9), k[1], k[2])):
        cond, prompt, cap = key
        arms = panels[key]
        pk = f"{cond}/{prompt}/{cap}"
        entry = {"arms": {}, "paired": {}}
        lines.append(f"\n### {domain} {cond}, prompt {prompt}, cap {cap}\n")
        lines.append("| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for a in ARMS:
            if a not in arms:
                continue
            row = arm_row(list(arms[a].values()))
            entry["arms"][f"{a[0]}/{a[1]}"] = row
            f = lambda v: "—" if v is None else f"{v:.2f}"
            lines.append(f"| {a[0]}/{a[1]} | {row['n']} | {row['ees']:.2f} | {row['aff_f1']:.2f} | {row['val_acc']:.2f} | {row['hit_cap']} | {f(row['ees_hit'])} | {f(row['ees_not_hit'])} | "
                         f"{row['legal']:.2f} | {row['collateral']:.2f} | {row['med_in']:.0f} | {row['med_out']:.0f} |")
        for a, b in PAIRS:
            if a in arms and b in arms:
                c = paired(arms[a], arms[b])
                if c:
                    cf = paired(arms[a], arms[b], "affected_f1")
                    cv = paired(arms[a], arms[b], "value_accuracy")
                    entry["paired"][f"{a[0]}/{a[1]} - {b[0]}/{b[1]}"] = {"ees": c, "affected_f1": cf, "value_accuracy": cv}
                    lines.append(f"- {a[0]}/{a[1]} − {b[0]}/{b[1]}: EES {fmt(c)}; affected F1 {fmt(cf)}; value acc {fmt(cv)}")
        out["panels"][pk] = entry
    # cross-prompt and cross-cap comparisons of the same arm on the same episodes
    lines.append(f"\n### {domain}: same arm across prompt / cap (paired on episodes)\n")
    keys = list(panels)
    for cond in sorted({k[0] for k in keys}, key=lambda c: order.get(c, 9)):
        for a in (("full", "verbose"), ("graph_closed", "compact"), ("graph_key2", "compact")):
            have = [(k, panels[k][a]) for k in keys if k[0] == cond and a in panels[k]]
            for i in range(len(have)):
                for j in range(i + 1, len(have)):
                    (k1, A), (k2, B) = have[i], have[j]
                    c = paired(A, B)
                    if c:
                        lab = f"{cond} {a[0]}: {k1[1]}/{k1[2]} − {k2[1]}/{k2[2]}"
                        out["cross"][lab] = c
                        lines.append(f"- {lab}: {fmt(c)}")
    return out, "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="travel")
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=None, help="restrict to one test seed (default: pool every seed found)")
    a = ap.parse_args()
    if a.seed is not None:
        globals()['SEED_FILTER'] = a.seed
    res, text = summarise(a.domain)
    print(text)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
