"""Backward provenance through the same learned graph (docs/hm3-provenance-design-2026-09-18.md).

For each episode one required witness record is minimally corrupted so that the
history parser reads a different value for a consulted key.  The forward
learner (the SAME fitted LearnedGraph object, identified by the SHA of its
serialised skeleton and models) produces a plan on the corrupted history; an
incident is a plan that differs from the clean plan and fails EES.  The
auditor receives only the anomalous objects (the ids whose transactions were
wrong, missing or illegal), traces backward along the skeleton to the records
the graph consulted on the path, and its top-ranked record is validated by
replacing it with the clean version and re-running the forward learner.
Controls: matched random record from the graph's reads, the most similar
non-ancestor record, the most recent record.

Usage: python3 -m hm3.provenance --domains travel shopping32 --seeds 0 1 2 --split dev \
           --out results/development/hm3/provenance/dev.json
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from .core import Episode, canonical_txn, hop_distances, plan_to_txns, restricted_est, score_plan
from .domains import get_domain
from .generate import generate_split
from .learners import LearnedGraph, follow_template
from .scaling import _tokens, augment_split, record_text


# ------------------------------------------------------------------ artifact

def graph_sha(g: LearnedGraph) -> str:
    """SHA of the learned structure and of the per-template decision models."""
    skel = sorted((k[0], list(k[1]), g.majority[k]) for k in g.skeleton)
    models = []
    for k in sorted(g.models, key=str):
        kind, m = g.models[k]
        if kind == "const":
            models.append((str(k), "const", str(m)))
        else:
            t = m.tree_
            models.append((str(k), "tree", t.node_count, t.feature.tolist(), np.round(t.threshold, 6).tolist(),
                           t.value.round(6).tolist()))
    blob = json.dumps([skel, models], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- corruption

def _candidates(domain, ep: Episode, r: dict) -> List[dict]:
    """Minimal edits of one record, in a fixed order."""
    out = []
    if r["kind"] in ("auto", "txn"):
        c = copy.deepcopy(r)
        c["kind"] = "txn" if r["kind"] == "auto" else "auto"
        out.append(c)
    for fld, (old, new) in (r.get("delta") or {}).items():
        if isinstance(new, (int, float)) and not isinstance(new, bool):
            for shift in (15, -15, 30, -30):
                c = copy.deepcopy(r)
                c["delta"][fld] = (old, new + shift)
                if isinstance(c.get("payload"), dict) and fld in c["payload"]:
                    c["payload"][fld] = new + shift
                out.append(c)
    if r["op"] in ("shift_reservation", "cancel_reservation"):
        c = copy.deepcopy(r)
        c["op"] = "cancel_reservation" if r["op"] == "shift_reservation" else "shift_reservation"
        out.append(c)
    if r["op"] == "replace_line" and "attrs" in (r.get("delta") or {}):
        oid = r["object_id"]
        if oid in ep.S0.objects:
            cat = ep.S0.get(oid).fields["category"]
            for v in ep.S0.meta.get("catalog", {}).get(cat, []):
                if v["sku"] != r["delta"].get("sku", (None, None))[1]:
                    c = copy.deepcopy(r)
                    c["delta"]["attrs"] = (r["delta"]["attrs"][0], dict(v["attrs"]))
                    c["delta"]["sku"] = (r["delta"].get("sku", (None, None))[0], v["sku"])
                    if "price" in c["delta"]:
                        c["delta"]["price"] = (c["delta"]["price"][0], v["price"])
                    if isinstance(c.get("payload"), dict):
                        c["payload"] = {"sku": v["sku"]}
                    out.append(c)
    if r["op"] == "remove_line":
        c = copy.deepcopy(r)
        c["kind"] = "auto" if r["kind"] == "txn" else "txn"
        out.append(c)
    return out


def corrupt(domain, ep: Episode, rng: random.Random) -> Optional[Tuple[Episode, str, str]]:
    """Return (corrupted episode, corrupted rid, key whose parsed value changed)."""
    est0 = domain.infer_params(ep.H, ep.S0)
    rids = [r for r in ep.required_reads["records"]]
    rng.shuffle(rids)
    by_rid = {r["rid"]: i for i, r in enumerate(ep.H)}
    for rid in rids:
        if rid not in by_rid:
            continue
        r = ep.H[by_rid[rid]]
        for c in _candidates(domain, ep, r):
            H2 = copy.deepcopy(ep.H)
            H2[by_rid[rid]] = c
            try:
                est1 = domain.infer_params(H2, ep.S0)
            except Exception:
                continue
            for pk in ep.relevant_params:
                name, key = pk.split("[", 1)
                key = key[:-1]
                if est0.get(name, {}).get(key) != est1.get(name, {}).get(key):
                    d = ep.__dict__.copy()
                    d["H"] = H2
                    return Episode(**d), rid, pk
    return None


# ------------------------------------------------------------------- tracing

def _run(domain, g: LearnedGraph, ep: Episode) -> Tuple[List[dict], dict, dict]:
    out = g.predict(domain, ep)
    est = restricted_est(domain, ep.H, ep.S0, out["reads"]["records"])
    txns, _info = plan_to_txns(domain, ep.S0, ep.I, out["plan"], est)
    return txns, out["reads"], score_plan(domain, ep, txns, out["reads"])


def anomalous_objects(domain, ep: Episode, txns: List[dict], score: dict) -> List[str]:
    """Objects whose transactions were wrong, missing or illegal: what the auditor sees."""
    gold = {t["object_id"]: canonical_txn(t) for t in ep.A}
    got = {t["object_id"]: canonical_txn(t) for t in txns}
    bad = [o for o in set(gold) | set(got) if gold.get(o) != got.get(o)]
    if not score["legal"] and not bad:
        bad = [t["object_id"] for t in txns]
    return sorted(bad)


def trace(domain, g: LearnedGraph, ep: Episode, anomalies: List[str], reads: dict, k: int = 5) -> List[str]:
    """Records the graph consulted for the objects on the skeleton paths from the
    source to each anomalous object, nearest-to-anomaly first, most recent first."""
    src = ep.I["object_id"]
    path_objs: Dict[str, int] = {}
    for a in anomalies:
        # objects reachable from the source along skeleton templates, with hop distance to the anomaly
        dist = hop_distances(ep.S0, a)
        frontier = [src]
        seen = {src}
        while frontier:
            o = frontier.pop(0)
            if o not in ep.S0.objects:
                continue
            for (ptype, template) in g.skeleton:
                if ptype != ep.S0.get(o).type:
                    continue
                for c in follow_template(ep.S0, o, template):
                    if c not in seen and c in ep.S0.objects:
                        seen.add(c)
                        frontier.append(c)
        for o in seen:
            if o in dist:
                path_objs[o] = min(path_objs.get(o, 99), dist[o])
        path_objs[a] = 0
    prov: Dict[str, list] = {}
    est = domain.infer_params(ep.H, ep.S0, prov)
    order = {r["rid"]: i for i, r in enumerate(ep.H)}
    scored = []
    for o, d in path_objs.items():
        if o not in ep.S0.objects:
            continue
        for name, key in domain.param_keys_for(ep.S0.get(o), ep.S0):
            attributed = prov.get(f"{name}[{key}]", [])
            for rid in attributed:
                if rid in order:
                    scored.append((d, -order[rid], rid))
            if not attributed:
                # the key has no witness the parser accepts (a silenced witness is one way a
                # corruption shows up): candidates are the newest records written to the
                # objects that carry this key, ranked after attributed witnesses at this distance
                owners = {o}
                if "|" in str(key):
                    for ts in ep.S0.get(o).links.values():
                        owners.update(t for t in ts if t in ep.S0.objects)
                recs = [r["rid"] for r in reversed(ep.H) if r["object_id"] in owners][:3]
                for j, rid in enumerate(recs):
                    scored.append((d + 0.5, -order[rid], rid))
    scored = sorted(set(scored))
    ranked = []
    for _d, _o, rid in scored:
        if rid not in ranked:
            ranked.append(rid)
    return ranked[:k], sorted(path_objs)


def mask_record(ep: Episode, rid: str) -> Episode:
    d = ep.__dict__.copy()
    d["H"] = [copy.deepcopy(r) for r in ep.H if r["rid"] != rid]
    return Episode(**d)


def trace_loo(domain, g: LearnedGraph, ep: Episode, anomalies: List[str], structural: List[str],
              bad_txns: List[dict], k: int = 5) -> List[str]:
    """Leave-one-record-out re-ranking of the structural candidates: a record scores
    by how many anomalous objects change their decision when the record is masked
    (audit-time information only: the corrupted history and the same graph)."""
    base = {t["object_id"]: canonical_txn(t) for t in bad_txns}
    scored = []
    for i, rid in enumerate(structural):
        try:
            txns, _r, _s = _run(domain, g, mask_record(ep, rid))
        except Exception:
            scored.append((0, i, rid))
            continue
        now = {t["object_id"]: canonical_txn(t) for t in txns}
        changed = sum(1 for o in anomalies if base.get(o) != now.get(o))
        scored.append((changed, -i, rid))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [rid for _c, _i, rid in scored[:k]]


def baseline_rankings(ep: Episode, anomalies: List[str], k: int = 5) -> Dict[str, List[str]]:
    """Provenance baselines that do not use the graph."""
    from .scaling import bm25_topk, _fmt
    rids = [r["rid"] for r in ep.H]
    out = {"recency": list(reversed(rids))[:k]}
    # BM25 against the anomalous objects' state lines
    lines = []
    for o in anomalies:
        if o in ep.S0.objects:
            ob = ep.S0.get(o)
            lines.append(f"{ob.id} {ob.type} " + " ".join(f"{a}={_fmt(v)}" for a, v in ob.fields.items()))
    q = " ".join(lines) or ep.query
    fake = copy.copy(ep)
    fake.query = q
    fake.I = dict(ep.I)
    try:
        out["bm25_anomaly"] = bm25_topk(fake, k)
    except Exception:
        out["bm25_anomaly"] = out["recency"]
    # source heuristic: records written to the anomalous objects or their 1-hop neighbours, newest first
    near = set(anomalies)
    for o in anomalies:
        if o in ep.S0.objects:
            for ts in ep.S0.get(o).links.values():
                near.update(t for t in ts if t in ep.S0.objects)
    out["source_heuristic"] = [r["rid"] for r in reversed(ep.H) if r["object_id"] in near][:k]
    return out


def controls(ep: Episode, reads: dict, ranked: List[str], path_objs: List[str], rng: random.Random) -> Dict[str, Optional[str]]:
    rids = [r["rid"] for r in ep.H]
    read_recs = [r for r in reads.get("records", []) if r in rids] or rids
    top = ranked[0] if ranked else None
    pool = [r for r in read_recs if r != top] or [r for r in rids if r != top]
    out = {"matched_random": rng.choice(pool) if pool else None, "recency": rids[-1] if rids else None}
    top3 = ranked[:3]
    pool3 = [r for r in read_recs if r not in top3] or [r for r in rids if r not in top3]
    out["matched_random3"] = rng.sample(pool3, min(len(top3), len(pool3))) if top3 and pool3 else None
    out["similar_kind"] = None
    if top is not None:
        tt = _tokens(record_text(next(r for r in ep.H if r["rid"] == top)))
        path = set(path_objs)
        cands = [(len(tt & _tokens(record_text(r))), i, r["rid"]) for i, r in enumerate(ep.H)
                 if r["object_id"] not in path and r["rid"] != top]
        kind = "non_ancestor"
        if not cands:
            # every object lies on the traced paths (small worlds): fall back to the most
            # similar record outside the trace's top-3
            cands = [(len(tt & _tokens(record_text(r))), i, r["rid"]) for i, r in enumerate(ep.H)
                     if r["rid"] not in top3]
            kind = "non_traced"
        cands.sort(key=lambda x: (-x[0], -x[1]))
        out["similar_non_ancestor"] = cands[0][2] if cands else None
        out["similar_kind"] = kind if cands else None
    else:
        out["similar_non_ancestor"] = None
    return out


def replace_record(ep_bad: Episode, ep_clean: Episode, rid) -> Episode:
    rids = set(rid) if isinstance(rid, (list, tuple, set)) else {rid}
    clean = {r["rid"]: r for r in ep_clean.H}
    d = ep_bad.__dict__.copy()
    d["H"] = [copy.deepcopy(clean[r["rid"]]) if r["rid"] in rids and r["rid"] in clean else copy.deepcopy(r)
              for r in ep_bad.H]
    return Episode(**d)


# ------------------------------------------------------------------- driver

def run_domain(domain, seed: int, split: str, n_train: int, n_eval: int, train_seed_offset: int,
               history: Optional[str] = None) -> dict:
    train = generate_split(domain, seed + train_seed_offset, "train", n_train)
    evals = generate_split(domain, seed, split, n_eval)
    if history and history != "native":
        target, mix = history.split(":")
        train, _ = augment_split(domain, train, int(target), mix, f"train{seed}")
        evals, _ = augment_split(domain, evals, int(target), mix, f"{split}{seed}")
    g = LearnedGraph()
    t0 = time.time()
    g.fit(domain, train)
    sha = graph_sha(g)
    rng = random.Random(seed * 7919 + 17)
    rows = []
    counts = {"episodes": len(evals), "no_corruption": 0, "clean_plan_wrong": 0, "no_incident": 0, "incidents": 0}
    for ep in evals:
        clean_txns, clean_reads, clean_score = _run(domain, g, ep)
        if not clean_score["ees"]:
            counts["clean_plan_wrong"] += 1
            continue
        got = corrupt(domain, ep, rng)
        if got is None:
            counts["no_corruption"] += 1
            continue
        bad, gold_rid, key = got
        bad_txns, bad_reads, bad_score = _run(domain, g, bad)
        if bad_score["ees"] or {canonical_txn(t) for t in bad_txns} == {canonical_txn(t) for t in clean_txns}:
            counts["no_incident"] += 1
            continue
        counts["incidents"] += 1
        anomalies = anomalous_objects(domain, bad, bad_txns, bad_score)
        structural, path_objs = trace(domain, g, bad, anomalies, bad_reads, k=12)
        ranked = trace_loo(domain, g, bad, anomalies, structural, bad_txns)
        ctrl = controls(bad, bad_reads, ranked, path_objs, rng)
        rank = ranked.index(gold_rid) + 1 if gold_rid in ranked else None
        rank_struct = structural.index(gold_rid) + 1 if gold_rid in structural[:5] else None
        baselines = baseline_rankings(bad, anomalies)
        baseline_rank = {n: (lst.index(gold_rid) + 1 if gold_rid in lst else None) for n, lst in baselines.items()}
        for n, lst in baselines.items():
            ctrl[f"bl_{n}"] = lst[0] if lst else None
        interventions = {}
        similar_kind = ctrl.pop("similar_kind", None)
        for name, rid in [("predicted", ranked[0] if ranked else None), ("predicted_top3", ranked[:3] or None)] + list(ctrl.items()):
            if rid is None:
                interventions[name] = None
                continue
            fixed = replace_record(bad, ep, rid)
            f_txns, _r, f_score = _run(domain, g, fixed)
            interventions[name] = {"rid": rid, "ees": bool(f_score["ees"]),
                                   "plan_restored": {canonical_txn(t) for t in f_txns} == {canonical_txn(t) for t in clean_txns}}
        rows.append({"episode": ep.id, "gold_rid": gold_rid, "key": key, "anomalies": anomalies, "similar_kind": similar_kind,
                     "ranked": ranked, "rank": rank, "structural": structural[:5], "rank_struct": rank_struct,
                     "baseline_rank": baseline_rank, "n_path_objects": len(path_objs), "n_records": len(bad.H),
                     "interventions": interventions})
    summ = summarize_rows(rows)
    summ.update(counts)
    summ["graph_sha"] = sha
    summ["fit_seconds"] = time.time() - t0
    return {"summary": summ, "rows": rows}


def summarize_rows(rows: List[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    p1 = np.mean([r["rank"] == 1 for r in rows])
    p3 = np.mean([r["rank"] is not None and r["rank"] <= 3 for r in rows])
    mrr = np.mean([1.0 / r["rank"] if r["rank"] else 0.0 for r in rows])
    out = {"n": n, "precision_at_1": float(p1), "precision_at_3": float(p3), "mrr": float(mrr),
           "precision_at_1_structural": float(np.mean([r.get("rank_struct") == 1 for r in rows])),
           "precision_at_3_structural": float(np.mean([r.get("rank_struct") is not None and r["rank_struct"] <= 3 for r in rows]))}
    for bl in ("recency", "bm25_anomaly", "source_heuristic"):
        rk = [r.get("baseline_rank", {}).get(bl) for r in rows]
        out[f"p1_{bl}"] = float(np.mean([x == 1 for x in rk]))
        out[f"p3_{bl}"] = float(np.mean([x is not None and x <= 3 for x in rk]))
    for name in ("predicted", "predicted_top3", "matched_random", "matched_random3", "similar_non_ancestor", "recency",
                 "bl_recency", "bl_bm25_anomaly", "bl_source_heuristic"):
        vals = [r["interventions"][name]["ees"] for r in rows if r["interventions"].get(name)]
        out[f"restore_{name}"] = float(np.mean(vals)) if vals else None
    return out


def paired_ci(rows: List[dict], a: str, b: str, n_boot: int = 4000, seed: int = 0) -> dict:
    d = np.array([int(r["interventions"][a]["ees"]) - int(r["interventions"][b]["ees"]) for r in rows
                  if r["interventions"].get(a) and r["interventions"].get(b)], dtype=float)
    if len(d) == 0:
        return {"n": 0}
    rng = np.random.default_rng(seed)
    boots = [rng.choice(d, len(d)).mean() for _ in range(n_boot)]
    return {"n": int(len(d)), "mean": float(d.mean()), "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="+", default=["travel", "shopping32"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--split", default="dev")
    ap.add_argument("--n_train", type=int, default=200)
    ap.add_argument("--n_eval", type=int, default=60)
    ap.add_argument("--train_seed_offset", type=int, default=0)
    ap.add_argument("--history", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    results = {"config": vars(a), "runs": {}}
    for dname in a.domains:
        domain = get_domain(dname)
        for seed in a.seeds:
            key = f"{dname}/seed{seed}"
            res = run_domain(domain, seed, a.split, a.n_train, a.n_eval, a.train_seed_offset, a.history)
            res["paired"] = {"predicted_minus_random": paired_ci(res["rows"], "predicted", "matched_random"),
                             "top3_minus_random3": paired_ci(res["rows"], "predicted_top3", "matched_random3"),
                             "predicted_minus_similar": paired_ci(res["rows"], "predicted", "similar_non_ancestor"),
                             "predicted_minus_recency": paired_ci(res["rows"], "predicted", "recency")}
            results["runs"][key] = res
            s = res["summary"]
            print(f"{key:20s} incidents {s.get('incidents')}/{s.get('episodes')} p@1 {s.get('precision_at_1')} "
                  f"mrr {s.get('mrr')} restore pred/rand/sim/rec "
                  f"{s.get('restore_predicted')}/{s.get('restore_matched_random')}/{s.get('restore_similar_non_ancestor')}/{s.get('restore_recency')} "
                  f"sha {s.get('graph_sha')}", flush=True)
            import os
            os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
            json.dump(results, open(a.out, "w"), indent=1, default=str)
