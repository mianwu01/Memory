"""MemAudit baseline — per-record causal attribution + structural anomaly detection.

Reimplementation of arXiv 2605.23723 ("MemAudit: Post-hoc Auditing of Poisoned
Agent Memory via Causal Attribution and Structural Anomaly Detection"), which is
the primary competitor for our P3 claim. The authors released NO code, so this is
built from the paper's description; treat it as a faithful-in-spirit baseline and
say so in any write-up.

It has two halves, both implemented here:

  1. CMIS -- Counterfactual Memory Influence Score. For each memory record m,
     how much worse does the agent behave WITH m present than without it? The
     paper defines it as harm(with m) - harm(without m). We compute it from a
     recorded trajectory by leave-one-out over the retrieval sets: for every
     round where m was retrieved, compare the anomaly rate on those rounds
     against the anomaly rate on matched rounds where m was NOT retrieved,
     matched on the observable regime so the score is not just picking up
     "rounds that look dangerous anyway".

  2. Memory Consistency Graph -- an undirected graph over records with an edge
     where two records are semantically related, then flag records that sit in
     structurally odd positions (unusually low agreement with their neighbours).
     The paper uses DeBERTa-v3 NLI for relatedness.

     >>> DOCUMENTED SUBSTITUTION <<<
     We do NOT run DeBERTa here: it is a neural model and this project is
     CPU-only by contract (and the node kills GPU-touching processes). We use
     token-overlap relatedness plus ANSWER-LABEL agreement, which preserves the
     structural test (a record whose answer disagrees with its semantic
     neighbours is anomalous) while dropping the entailment nuance. Anywhere the
     numbers matter, this substitution must be disclosed. Pass
     `relatedness="nli"` to plug a real NLI scorer in later.

What this baseline CANNOT do, and why we are not it: MemAudit scores records
one at a time and builds a static semantic graph. It never learns temporal
structure, so it cannot say WHICH EARLIER ROUND's write drives a later action,
nor hand the same graph back to the memory system for selection. That boundary is
the novelty claim, so this file exists to make the comparison concrete rather
than rhetorical.

CPU-only. Usage:
    python3 code/memaudit_baseline.py --trace results/real/minja_trace_llm.csv \
        --transcript results/real/minja_trace_llm.transcript.json
"""
from __future__ import annotations

import os as _os
_os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("the a an of to in on for and or is are was were be been it its this that "
            "which with as by at from what who whom how why when".split())


def _toks(s: str) -> set:
    return {w for w in _WORD.findall(str(s).lower()) if w not in _STOP and len(w) > 2}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --------------------------------------------------------------------------- #
# 1. CMIS
# --------------------------------------------------------------------------- #
def cmis(transcript: List[Dict], match_on: str = "note_present") -> pd.DataFrame:
    """Counterfactual Memory Influence Score per memory record.

    score(m) = P(anomalous | m retrieved) - P(anomalous | m not retrieved),
    computed WITHIN strata of `match_on` and then pooled by stratum size, so a
    record does not score highly merely because it happens to be retrieved on
    rounds that are dangerous for a visible reason.
    """
    rounds = []
    for r in transcript:
        rounds.append({
            "t": r["t"],
            "anomalous": int(r.get("anomalous", 0)),
            "stratum": int(r.get(match_on, 0)),
            "retrieved": [x.get("id") for x in r.get("retrieved", [])],
            "is_poison": {x.get("id"): bool(x.get("is_poison")) for x in r.get("retrieved", [])},
        })
    if not rounds:
        return pd.DataFrame(columns=["record", "cmis", "n_with", "n_without", "is_poison"])

    all_ids = sorted({rid for r in rounds for rid in r["retrieved"] if rid})
    truth = {}
    for r in rounds:
        truth.update({k: v for k, v in r["is_poison"].items() if k})

    strata = sorted({r["stratum"] for r in rounds})
    out = []
    for rid in all_ids:
        num, den, n_with, n_without = 0.0, 0, 0, 0
        for s in strata:
            grp = [r for r in rounds if r["stratum"] == s]
            with_m = [r["anomalous"] for r in grp if rid in r["retrieved"]]
            without = [r["anomalous"] for r in grp if rid not in r["retrieved"]]
            n_with += len(with_m)
            n_without += len(without)
            if with_m and without:
                num += len(grp) * (float(np.mean(with_m)) - float(np.mean(without)))
                den += len(grp)
        out.append({"record": rid,
                    "cmis": (num / den) if den else float("nan"),
                    "n_with": n_with, "n_without": n_without,
                    "is_poison": bool(truth.get(rid, False))})
    df = pd.DataFrame(out).sort_values("cmis", ascending=False, na_position="last")
    return df.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 2. Memory Consistency Graph + structural anomaly
# --------------------------------------------------------------------------- #
def consistency_graph(transcript: List[Dict], relatedness: str = "lexical",
                      edge_thresh: float = 0.12) -> pd.DataFrame:
    """Flag records that disagree with their semantic neighbours.

    Builds an undirected graph over distinct memory records (edge where question
    relatedness >= edge_thresh) and scores each record by how often its stored
    ANSWER differs from its neighbours'. The paper's DeBERTa-NLI relatedness is
    replaced by token overlap -- see the module docstring.
    """
    if relatedness != "lexical":
        raise NotImplementedError(
            "only the lexical substitute is implemented; wire a real NLI scorer "
            "here to match the paper exactly")

    recs: Dict[str, Dict] = {}
    for r in transcript:
        for x in r.get("retrieved", []):
            rid = x.get("id")
            if rid and rid not in recs:
                recs[rid] = {"id": rid,
                             "q": _toks(x.get("question", "")),
                             "answer": str(x.get("answer", ""))[:1].upper(),
                             "is_poison": bool(x.get("is_poison"))}
    # the transcript stores the retrieved record's thought, not always its answer;
    # fall back to the answer emitted on the round that WROTE it, when available.
    by_id = {str(r.get("id")): r for r in transcript}
    for rid, rec in recs.items():
        if not rec["answer"] and rid in by_id:
            rec["answer"] = str(by_id[rid].get("answer", ""))[:1].upper()

    ids = sorted(recs)
    out = []
    for a in ids:
        nb = [b for b in ids if b != a and _jaccard(recs[a]["q"], recs[b]["q"]) >= edge_thresh]
        if not nb:
            out.append({"record": a, "degree": 0, "disagreement": float("nan"),
                        "is_poison": recs[a]["is_poison"]})
            continue
        dis = float(np.mean([recs[a]["answer"] != recs[b]["answer"] for b in nb]))
        out.append({"record": a, "degree": len(nb), "disagreement": dis,
                    "is_poison": recs[a]["is_poison"]})
    return pd.DataFrame(out).sort_values("disagreement", ascending=False,
                                         na_position="last").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# detection scoring
# --------------------------------------------------------------------------- #
def score_detection(df: pd.DataFrame, score_col: str, k: Optional[int] = None) -> Dict:
    """How well does a per-record score rank the true poison records first?"""
    d = df.dropna(subset=[score_col])
    if d.empty or d["is_poison"].nunique() < 2:
        return {"auc": float("nan"), "precision_at_k": float("nan"),
                "n_poison": int(df["is_poison"].sum()), "n_records": int(len(df)),
                "note": "degenerate: need both poison and clean records to score"}
    y = d["is_poison"].to_numpy().astype(int)
    s = d[score_col].to_numpy(float)
    # rank-based AUC (Mann-Whitney), no sklearn dependency
    order = np.argsort(s)
    ranks = np.empty(len(s), float)
    ranks[order] = np.arange(1, len(s) + 1)
    npos, nneg = int(y.sum()), int((1 - y).sum())
    auc = (ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg)
    k = k or max(1, npos)
    topk = d.sort_values(score_col, ascending=False).head(k)
    return {"auc": float(auc),
            "precision_at_k": float(topk["is_poison"].mean()),
            "k": int(k), "n_poison": npos, "n_records": int(len(d))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", default="results/real/minja_trace_llm.transcript.json")
    ap.add_argument("--trace", default=None, help="unused; kept for symmetry")
    ap.add_argument("--out", default="results/real/memaudit_baseline.json")
    a = ap.parse_args()

    T = json.load(open(a.transcript))
    print(f"loaded {len(T)} rounds from {a.transcript}")

    print("\n=== MemAudit (1): CMIS — per-record counterfactual influence ===")
    c = cmis(T)
    print(c.head(8).to_string(index=False))
    s_cmis = score_detection(c, "cmis")
    print(f"  detection: AUC={s_cmis.get('auc'):.3f}  "
          f"precision@{s_cmis.get('k')}={s_cmis.get('precision_at_k'):.3f}"
          if not np.isnan(s_cmis.get("auc", float("nan")))
          else f"  detection: {s_cmis.get('note','n/a')}")

    print("\n=== MemAudit (2): consistency graph — structural anomaly ===")
    g = consistency_graph(T)
    print(g.head(8).to_string(index=False))
    s_graph = score_detection(g, "disagreement")
    print(f"  detection: AUC={s_graph.get('auc'):.3f}  "
          f"precision@{s_graph.get('k')}={s_graph.get('precision_at_k'):.3f}"
          if not np.isnan(s_graph.get("auc", float("nan")))
          else f"  detection: {s_graph.get('note','n/a')}")

    print("\n=== boundary (what this baseline structurally cannot do) ===")
    print("  * scores records, never edges -> cannot name WHICH earlier round's")
    print("    write drives a later action (no temporal ancestry)")
    print("  * the graph is semantic and static -> it is not reusable as a")
    print("    memory-selection policy, so no audit/memory dual use")

    rep = {"cmis": s_cmis, "consistency_graph": s_graph,
           "n_rounds": len(T),
           "substitution": "DeBERTa-v3 NLI replaced by lexical overlap (CPU-only)"}
    p = Path(a.out); p.parent.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(p, "w"), indent=1, default=str)
    c.to_csv(str(p).replace(".json", "_cmis.csv"), index=False)
    g.to_csv(str(p).replace(".json", "_graph.csv"), index=False)
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
