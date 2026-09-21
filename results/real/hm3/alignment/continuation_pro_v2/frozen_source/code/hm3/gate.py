"""Zero-API development gate for Hidden Mechanism v3.

Eight checks, thresholds fixed before any test-split or API output exists
(see docs/hidden-mechanism-v3-preregistration.md):
  C1 query leak          the query names only the source; no descendant ids, no gate vocabulary
  C2 split separation    train / dev / test episode ids and topology hashes are disjoint
  C3 history load-bearing same query + same visible state summary, different history -> different gold
  C4 killers fail        exact-KV, source union, source+regime, kNN, superset: dev EES <= 0.50 each
  C5 identifiable        oracle and runtime-history oracle: dev EES = 1.0
  C6 non-idempotent      oracle plan + one idempotent extra write fails the endpoint in 100% of episodes
  C7 graph > black box   learned graph beats flat, flat_est, gnn, gnn_est on >= 2/3 dev seeds and on the mean
  C8 program ran         the relational program learner has results; tie flag if |graph - program| <= 0.05
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Dict, List

import numpy as np

from .core import Tracker, canonical_txn, execute_intervention, score_plan, txn
from .domains import ALL_DOMAINS, get_domain
from .generate import DEFAULT_CFG, generate_episode, generate_split
from .run_det import summarize

HIDDEN_VOCAB = ["auto_rebook", "buffer", "enforce_late", "late_seating", "linked", "compat", "strict_promo",
                "auto_promo", "enforce_budget", "trust", "dedup", "policy", "auto_base", "section_shadows",
                "sensitive", "stmt_sensitive", "auto_local", "descendant", "gate", "composition", "affected"]
KILLERS = ["exact_kv", "source_union", "source_regime", "knn", "superset"]
BLACKBOX = ["flat", "flat_est", "gnn", "gnn_est"]


def check_query_leak(domain, eps) -> dict:
    leaks = []
    for ep in eps:
        text = ep.query + " " + json.dumps(ep.I)
        ids = set(ep.affected) | set(ep.auto_affected)
        ids.discard(ep.I["object_id"])
        for oid in ids:
            if re.search(rf"\b{re.escape(oid)}\b", text):
                leaks.append((ep.id, oid))
        for w in HIDDEN_VOCAB:
            if w in text.lower():
                leaks.append((ep.id, w))
    return {"pass": not leaks, "n": len(eps), "leaks": leaks[:10]}


def check_split_separation(domain, train, dev, test) -> dict:
    ids = [set(e.id for e in s) for s in (train, dev, test)]
    hashes = [set(e.topology_hash for e in s) for s in (train, dev, test)]
    id_ok = not (ids[0] & ids[1]) and not (ids[0] & ids[2]) and not (ids[1] & ids[2])
    hash_overlap = len(hashes[0] & hashes[1]) + len(hashes[0] & hashes[2]) + len(hashes[1] & hashes[2])
    return {"pass": id_ok and hash_overlap == 0, "id_disjoint": id_ok, "topology_hash_overlap": hash_overlap,
            "n_train": len(train), "n_dev": len(dev), "n_test": len(test)}


def _gold_set(ep):
    return {(t["op"], t["object_id"], json.dumps(t["payload"], sort_keys=True)) for t in ep.A}


def _flip(value):
    if isinstance(value, str):
        return "ignore" if value == "propagate" else "propagate"
    if value in (0, 1):
        return 1 - value
    return None


def check_history_load_bearing(domain, seed: int, n_pairs: int = 30) -> dict:
    rng = random.Random(1000 + seed)
    direct_changes = direct_total = 0
    first_total, first_changes = [0], [0]
    pair_diff = pair_total = pair_same_summary_diff = pair_same_summary = 0
    examples = []
    tries = 0
    while pair_total < n_pairs and tries < n_pairs * 4:
        tries += 1
        params, state0 = domain.sample_world(rng, DEFAULT_CFG)
        try:
            A = generate_episode(domain, seed, "pair", tries, world_state=(params, state0))
        except RuntimeError:
            continue
        # direct flip: does flipping some consulted hidden parameter (holding S0 and I
        # fixed) change the gold plan?  Every flippable consulted parameter is tried;
        # the first-parameter-only variant is kept as a stricter diagnostic.
        flip = None
        any_flippable = False
        first_changed = None
        for pk in A.relevant_params:
            name, key = pk.split("[", 1)
            key = key[:-1]
            new = _flip(params[name][key])
            if new is None:
                continue
            p2 = json.loads(json.dumps(params))
            p2[name][key] = new
            post = A.S0.copy()
            try:
                _rc, txns, _t = execute_intervention(domain, p2, post, A.I, Tracker(p2))
            except Exception:
                continue
            any_flippable = True
            changed = {canonical_txn(t)[:2] + (canonical_txn(t)[3],) for t in txns} != \
                {canonical_txn(t)[:2] + (canonical_txn(t)[3],) for t in A.A}
            if first_changed is None:
                first_changed = changed
            if changed and flip is None:
                flip = (name, key, new)
        if any_flippable:
            direct_total += 1
            direct_changes += flip is not None
            first_total[0] += 1
            first_changes[0] += bool(first_changed)
        if flip is None:
            continue
        name, key, new = flip
        p2 = json.loads(json.dumps(params))
        p2[name][key] = new
        try:
            B = generate_episode(domain, seed, "pairB", tries, world_state=(p2, state0), fixed_I=A.I)
        except RuntimeError:
            continue
        if B.I["object_id"] != A.I["object_id"] or B.I["op"] != A.I["op"]:
            continue
        pair_total += 1
        diff = _gold_set(A) != _gold_set(B)
        pair_diff += diff
        # visible summary of what the oracle read: fields (revision excluded) of the read objects
        def summary(ep):
            out = []
            for oid in ep.required_reads["objects"]:
                o = ep.S0.get(oid)
                out.append((oid, o.type, json.dumps(o.fields, sort_keys=True), o.status))
            return tuple(sorted(out))
        same = summary(A) == summary(B) and A.query == B.query
        pair_same_summary += same
        pair_same_summary_diff += (same and diff)
        if len(examples) < 3:
            examples.append({"query": A.query, "flipped": f"{name}[{key}]", "gold_A": sorted(_gold_set(A)),
                             "gold_B": sorted(_gold_set(B)), "same_summary": same})
    frac_direct = direct_changes / direct_total if direct_total else 0.0
    frac_pair = pair_diff / pair_total if pair_total else 0.0
    frac_same_diff = pair_same_summary_diff / pair_same_summary if pair_same_summary else 0.0
    return {"pass": frac_direct >= 0.8 and frac_pair >= 0.5 and pair_total >= 10,
            "direct_flip_changes_gold": frac_direct, "n_direct": direct_total,
            "first_param_flip_changes_gold": (first_changes[0] / first_total[0]) if first_total[0] else 0.0,
            "pairs_with_different_gold": frac_pair, "n_pairs": pair_total,
            "pairs_same_visible_summary": pair_same_summary,
            "same_summary_pairs_with_different_gold": frac_same_diff, "examples": examples}


def check_nonidempotent(domain, eps) -> dict:
    fails = total = 0
    for ep in eps:
        untouched = [o for oid, o in sorted(ep.S0.objects.items())
                     if oid not in ep.affected and oid not in ep.auto_affected and oid != ep.I["object_id"]]
        extra = None
        for o in untouched:
            w = domain.idempotent_write(o)
            if w:
                extra = txn(w[0], o.id, o.revision, w[1])
                break
        if extra is None:
            continue
        total += 1
        s = score_plan(domain, ep, ep.A + [extra])
        fails += (not s["ees"]) and s["legal"]
    return {"pass": total > 0 and fails == total, "n": total, "endpoint_failed": fails}


def results_checks(summary: dict, results: dict, dname: str) -> dict:
    out = {}
    L = summary.get(dname, {})
    ees = {k: v.get("ees", (None,))[0] for k, v in L.items()}
    out["C4_killers_fail"] = {"pass": all(ees.get(k) is not None and ees[k] <= 0.5 for k in KILLERS),
                              "ees": {k: ees.get(k) for k in KILLERS}}
    out["C5_identifiable"] = {"pass": ees.get("oracle") == 1.0 and ees.get("rh_oracle") == 1.0,
                              "oracle": ees.get("oracle"), "rh_oracle": ees.get("rh_oracle")}
    # per-seed comparison graph vs black boxes
    per_seed = {}
    for key, run_ in results["runs"].items():
        if not key.startswith(dname + "/"):
            continue
        seed = key.split("seed")[1]
        per_seed[seed] = {ln: r["summary"]["ees"] for ln, r in run_["learners"].items()}
    wins = {b: sum(1 for s in per_seed.values() if s.get("graph", 0) > s.get(b, 0)) for b in BLACKBOX}
    n_seeds = len(per_seed)
    out["C7_graph_beats_blackbox"] = {
        "pass": n_seeds > 0 and all(wins[b] * 3 >= 2 * n_seeds for b in BLACKBOX) and
                all(ees.get("graph", 0) > ees.get(b, 0) for b in BLACKBOX),
        "seed_wins": wins, "n_seeds": n_seeds, "graph_mean": ees.get("graph"),
        "blackbox_mean": {b: ees.get(b) for b in BLACKBOX}}
    g, p = ees.get("graph"), ees.get("program")
    out["C8_program_ran"] = {"pass": p is not None, "graph": g, "program": p,
                             "tie": (p is not None and g is not None and abs(g - p) <= 0.05),
                             "program_better": (p is not None and g is not None and p > g + 0.05)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results/development/hm3/det_dev.json")
    ap.add_argument("--out", default="results/development/hm3/gate.json")
    ap.add_argument("--domains", nargs="+", default=ALL_DOMAINS)
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    a = ap.parse_args()
    results = json.load(open(a.results))
    summary = summarize(results)
    report = {"thresholds": {"C3": "direct flip changes gold >= 0.8; regenerated pairs differ >= 0.5",
                             "C4": "each killer EES <= 0.50", "C5": "oracle = rh_oracle = 1.0",
                             "C6": "100% of extra-write plans fail", "C7": ">= 2/3 seeds and mean",
                             "C8": "program learner present; tie if |graph - program| <= 0.05"},
              "domains": {}}
    for dname in a.domains:
        domain = get_domain(dname)
        checks = {}
        dev_all, train_all = [], []
        for seed in a.seeds:
            train = generate_split(domain, seed, "train", 200)
            dev = generate_split(domain, seed, "dev", 60)
            test = generate_split(domain, seed + 10, "test", 60)
            train_all += train
            dev_all += dev
            c2 = check_split_separation(domain, train, dev, test)
            checks.setdefault("C2_split_separation", []).append(c2)
            checks.setdefault("C3_history_load_bearing", []).append(check_history_load_bearing(domain, seed))
        checks["C1_query_leak"] = check_query_leak(domain, dev_all)
        checks["C6_nonidempotent"] = check_nonidempotent(domain, dev_all)
        checks.update(results_checks(summary, results, dname))
        flat = {}
        for k, v in checks.items():
            if isinstance(v, list):
                flat[k] = {"pass": all(x["pass"] for x in v), "per_seed": v}
            else:
                flat[k] = v
        api_allowed = all(flat[k]["pass"] for k in flat if not k.startswith("C8"))
        report["domains"][dname] = {"checks": flat, "api_allowed": api_allowed}
        print(f"== {dname}: api_allowed={api_allowed}")
        for k, v in flat.items():
            print(f"   {k:28s} pass={v['pass']}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(report, open(a.out, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
