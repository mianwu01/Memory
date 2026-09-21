"""Identifying the memory frontier by read interventions (docs/method-design-read-interventions-2026-09-20.md).

The memory system intervenes on its own reads: a logged episode is replayed with a subset of history records
visible, and the decision is scored.  With an exact oracle and a successful initial set, adaptive elimination
(ddmin) returns a 1-minimal sufficient set; no general O(k log n) guarantee is claimed. A conditional model predicts
for a new episode,
which records along which typed paths under which regime features are necessary, and selects them without
replays.  The same primitive, run with clean-replacement replays, localises the record that caused an anomaly.

Oracles: ExecutorOracle (deterministic executor, parser restricted to the visible records) and LLMOracle
(the actor itself, temperature 0).  Nothing here uses the generator's required_reads.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

from .core import Episode, FallbackTracker, State, execute_intervention, restricted_est, score_plan, segments
from .features import path_types
from .learners import Learner


# ------------------------------------------------------------ elimination

def minimal_sufficient(cands: Sequence[str], ok: Callable[[List[str]], bool]) -> Tuple[List[str], int]:
    """ddmin: a 1-minimal subset S of cands with ok(S) true, assuming ok(cands) is true.
    Returns (S, number of oracle calls). Report observed call counts; the generic
    worst case is quadratic. Monotonicity promotes 1-minimality to inclusion
    minimality but does not identify a unique minimum-cardinality set."""
    S = list(cands)
    calls = 0
    gran = 2
    while len(S) >= 2:
        chunk = math.ceil(len(S) / gran)
        removed = False
        for i in range(0, len(S), chunk):
            T = S[:i] + S[i + chunk:]
            calls += 1
            if ok(T):
                S = T
                gran = max(gran - 1, 2)
                removed = True
                break
        if not removed:
            if gran >= len(S):
                break
            gran = min(len(S), gran * 2)
    if len(S) == 1:
        calls += 1
        if ok([]):
            S = []
    return S, calls


# ------------------------------------------------------------------ oracles

class ExecutorOracle:
    """Replay with the deterministic executor: the parser sees only the visible records."""

    def __init__(self, domain, ep: Episode):
        self.domain, self.ep = domain, ep
        self.cache: Dict[frozenset, bool] = {}

    def __call__(self, records: List[str]) -> bool:
        key = frozenset(records)
        if key in self.cache:
            return self.cache[key]
        est = restricted_est(self.domain, self.ep.H, self.ep.S0, records)
        post = self.ep.S0.copy()
        try:
            _rc, txns, _tr = execute_intervention(self.domain, est, post, self.ep.I, FallbackTracker(est))
        except Exception:
            txns = []
        ok = bool(score_plan(self.domain, self.ep, txns)["ees"])
        self.cache[key] = ok
        return ok


def visible_objects(ep: Episode, records: List[str]) -> List[str]:
    """State objects shown with a record set: the cue's object, the records' referents and their 1-hop links."""
    src = ep.I["object_id"]
    rs = set(records)
    referents = {r["object_id"] for r in ep.H if r["rid"] in rs and r["object_id"] in ep.S0.objects}
    closure = set(referents) | {src}
    for oid in list(referents) + [src]:
        for targets in ep.S0.get(oid).links.values():
            closure.update(t for t in targets if t in ep.S0.objects)
    return sorted(closure)


class LLMOracle:
    """Replay with the actor itself.  ``chat`` is hm3.llm.Client.chat; the prompt is the panel's (v1/v2 by
    hm3.llm.PROMPT_VERSION), serialization verbose, objects = referent closure of the visible records."""

    def __init__(self, domain, ep: Episode, client, max_tokens: int = 16384, ledger: Optional[Path] = None,
                 ser: str = "verbose", repeats: int = 1):
        from . import llm as L
        self.L, self.domain, self.ep, self.client = L, domain, ep, client
        self.max_tokens, self.ledger, self.ser = max_tokens, ledger, ser
        # repeats > 1: the oracle is the majority of ``repeats`` independent calls (the actor at temperature 0
        # disagrees with itself call to call; the probe measured 0.58 under v1); votes stop early once decided
        self.repeats = repeats
        self.cache: Dict[frozenset, bool] = {}
        self.cost = 0.0
        self.calls = 0
        self.votes: List[List[bool]] = []

    def _one(self, sel: dict, messages) -> Tuple[bool, dict, dict]:
        r = self.client.chat(messages, max_tokens=self.max_tokens)
        txns = self.L.parse_transactions(r["text"])
        if txns is None:
            r2 = self.client.chat(messages + [{"role": "assistant", "content": r["text"]},
                                  {"role": "user", "content": "Return the final answer now as a fenced ```json block containing only the array of transactions."}],
                                  max_tokens=self.max_tokens)
            txns = self.L.parse_transactions(r2["text"])
            self.cost += r2["cost"]
        self.cost += r["cost"]
        self.calls += 1
        score = score_plan(self.domain, self.ep, txns or [], sel)
        return bool(score["ees"]), score, r

    def __call__(self, records: List[str]) -> bool:
        key = frozenset(records)
        if key in self.cache:
            return self.cache[key]
        order = {r["rid"]: i for i, r in enumerate(self.ep.H)}
        recs = sorted(records, key=lambda r: order[r])
        sel = {"objects": visible_objects(self.ep, recs), "records": recs}
        messages = self.L.build_messages(self.domain, self.ep, sel, self.ser)
        votes = []
        need = self.repeats // 2 + 1
        while len(votes) < self.repeats and votes.count(True) < need and votes.count(False) < need:
            ok1, score, r = self._one(sel, messages)
            votes.append(ok1)
            if self.ledger:
                with open(self.ledger, "a") as f:
                    f.write(json.dumps({"episode": self.ep.id, "n_visible": len(recs), "records": recs, "ees": ok1,
                                        "vote": len(votes), "affected_f1": score["affected_f1"], "input_tokens": r["input_tokens"],
                                        "output_tokens": r["output_tokens"], "cost": r["cost"]}) + "\n")
        ok = votes.count(True) >= need
        self.votes.append(votes)
        self.cache[key] = ok
        return ok


# --------------------------------------------------------------- discovery

def discover(domain, episodes: List[Episode], make_oracle: Callable[[Episode], Callable], log=None,
             orderings: int = 1) -> List[dict]:
    """Per episode: whether the full read is sufficient, a minimal sufficient set, and the replay count.
    ``orderings`` > 1 repeats the elimination over reversed / shuffled candidate orders and stores the union of
    the minimal sets found (``frontier``) alongside the first one (``frontier_first``): under redundant witnesses
    a minimal set is not unique, and the union labels every alternative the actor accepts."""
    out = []
    rng = np.random.default_rng(0)
    for ep in episodes:
        ok = make_oracle(ep)
        cands = [r["rid"] for r in ep.H]
        full = ok(cands)
        if not full:
            out.append({"episode": ep.id, "full_ok": False, "n": len(cands), "frontier": None, "calls": 1})
            if log:
                log(f"{ep.id}: full read fails, skipped")
            continue
        S, calls = minimal_sufficient(cands, ok)
        union = set(S)
        sets = [S]
        for k in range(1, orderings):
            order = list(reversed(cands)) if k == 1 else list(rng.permutation(cands))
            S2, c2 = minimal_sufficient(order, ok)
            calls += c2
            union |= set(S2)
            sets.append(S2)
        order_idx = {r: i for i, r in enumerate(cands)}
        out.append({"episode": ep.id, "full_ok": True, "n": len(cands), "frontier": sorted(union, key=order_idx.get),
                    "frontier_first": S, "minimal_sets": sets, "calls": calls + 1, "cost": getattr(ok, "cost", 0.0)})
        if log:
            log(f"{ep.id}: n={len(cands)} frontier={len(S)} union={len(union)} calls={calls + 1}")
    return out


# ----------------------------------------------------- frontier model

def _key_of(domain, obj) -> Optional[Tuple[str, str, object]]:
    cats = domain.categorical_fields().get(obj.type, [])
    for f in cats:
        v = obj.fields.get(f)
        if v is not None:
            return (obj.type, f, v)
    return None


def _numeric_context(domain, ep: Episode, anchor_oid: Optional[str], key_oid: Optional[str]) -> List[float]:
    """Regime features readable from the current state: the cue's new numeric values, the numeric fields of
    the reached object the record is keyed to and of the objects on its typed path, and their differences."""
    S0 = ep.S0
    num = domain.numeric_fields()
    src = S0.get(ep.I["object_id"])
    payload = ep.I.get("payload") or {}
    src_new = [float(payload.get(f, src.fields.get(f) or 0.0) or 0.0) for f in num.get(src.type, [])]
    src_delta = [float((payload.get(f, src.fields.get(f)) or 0.0)) - float(src.fields.get(f) or 0.0) for f in num.get(src.type, [])]
    out = src_new + src_delta
    for oid in (anchor_oid, key_oid):
        o = S0.objects.get(oid) if oid else None
        vals = [float(o.fields.get(f) or 0.0) if o else 0.0 for f in (num.get(o.type, []) if o else [])]
        # pad to a fixed width per slot: max numeric fields over types
        width = max((len(v) for v in num.values()), default=0)
        vals = vals + [0.0] * (width - len(vals))
        out += vals
        out += [sn - v for sn in src_new for v in vals]
        out.append(1.0 if o and o.status == "active" else 0.0)
    return out


def record_features(domain, ep: Episode, reached: Dict[str, Tuple]) -> Dict[str, dict]:
    """Categorical features per history record.  ``reached``: object id -> typed path from the cue's object
    (only the objects the structure reaches).  Parser-free: uses links and categorical fields only."""
    S0, H = ep.S0, ep.H
    keys_reached: Dict[Tuple, Tuple[str, Tuple]] = {}
    for oid, path in reached.items():
        k = _key_of(domain, S0.get(oid))
        if k is not None and (k not in keys_reached or len(path) < len(keys_reached[k][1])):
            keys_reached[k] = (oid, path)
    segs = segments(H)
    # segment anchors: the reached object whose key some record in the segment shares (nearest to the cue)
    seg_key: Dict[int, Tuple] = {}
    seg_keyed_obj: Dict[int, str] = {}
    key_segments: Dict[Tuple, List[int]] = defaultdict(list)
    for si, seg in enumerate(segs):
        best = None
        for r in seg:
            o = S0.objects.get(r["object_id"])
            if o is None:
                continue
            k = _key_of(domain, o)
            if k in keys_reached:
                cand = (len(keys_reached[k][1]), k, o.id)
                if best is None or cand[0] < best[0]:
                    best = cand
        if best is not None:
            seg_key[si], seg_keyed_obj[si] = best[1], best[2]
            key_segments[best[1]].append(si)
    # segment signature: which (kind, type) writes the segment contains; recency is ranked among the
    # segments that share the key *and* the signature, so "the latest segment in which a flight change
    # was followed by a transfer change for this provider" is expressible without a parser
    seg_sig: Dict[int, str] = {}
    for si, seg in enumerate(segs):
        sig = sorted({f"{r['kind']}:{S0.get(r['object_id']).type if r['object_id'] in S0.objects else 'foreign'}:{','.join(sorted((r.get('delta') or {}).keys()))}" for r in seg})
        seg_sig[si] = ",".join(sig)
    key_sig_segments: Dict[Tuple, List[int]] = defaultdict(list)
    for si in seg_key:
        key_sig_segments[(seg_key[si], seg_sig[si])].append(si)
    feats: Dict[str, dict] = {}
    for si, seg in enumerate(segs):
        k = seg_key.get(si)
        anchor_path = "none" if k is None else "/".join(f"{rel}:{t}" for rel, t in keys_reached[k][1]) or "self"
        recency = None if k is None else sorted(key_segments[k], reverse=True).index(si)
        recency_sig = None if k is None else sorted(key_sig_segments[(k, seg_sig[si])], reverse=True).index(si)
        kobj = seg_keyed_obj.get(si)
        rel_paths = path_types(S0, kobj, 2) if kobj else {}
        for pos, r in enumerate(seg):
            o = S0.objects.get(r["object_id"])
            rel = "none"
            if kobj is not None and o is not None:
                p = rel_paths.get(o.id)
                rel = "self" if o.id == kobj else ("/".join(f"{a}:{b}" for a, b in p) if p is not None else "far")
            direct = o is not None and o.id in reached
            # the record's own key, if its object shares one with a reached object
            ok_ = _key_of(domain, o) if o is not None else None
            own = "none"
            own_rec = "none"
            if ok_ is not None and ok_ in keys_reached:
                own = "/".join(f"{rel_}:{t}" for rel_, t in keys_reached[ok_][1]) or "self"
                own_rec = str(min(sorted(key_segments[ok_], reverse=True).index(si), 3)) if si in key_segments[ok_] else "none"
            fields = ",".join(sorted((r.get("delta") or {}).keys()))
            key_oid = keys_reached[ok_][0] if (ok_ is not None and ok_ in keys_reached) else None
            anchor_oid = keys_reached[k][0] if k is not None else None
            feats[r["rid"]] = {"_num": _numeric_context(domain, ep, anchor_oid, key_oid),
                               "fields": f"{r['kind']}:{o.type if o else 'foreign'}:{fields}",
                               "anchor_path": anchor_path, "anchor_type": "none" if k is None else k[0],
                               "kind": r["kind"], "rel_to_keyed": rel, "otype": o.type if o else "foreign",
                               "recency": "none" if recency is None else str(min(recency, 3)),
                               "recency_sig": "none" if recency_sig is None else str(min(recency_sig, 3)),
                               "sig": seg_sig[si], "own_path": own, "own_recency": own_rec,
                               "pos": str(min(pos, 3)), "direct": str(int(direct))}
    return feats


class FrontierModel:
    """p(record in frontier | typed path of its segment's anchor, regime features).  One decision tree over
    one-hot categorical features; the type-level structure is the projection of the positive anchor paths."""

    def __init__(self, max_depth: int = 12, min_support: int = 2, model: str = "gbm", numeric: bool = False,
                 balanced: bool = True):
        self.max_depth, self.min_support, self.model_kind, self.numeric = max_depth, min_support, model, numeric
        self.balanced = balanced

    def fit(self, domain, episodes: List[Episode], sets: List[dict], reached_fn) -> "FrontierModel":
        from sklearn.tree import DecisionTreeClassifier
        rows, labels = [], []
        edge_support: Counter = Counter()
        path_support: Counter = Counter()
        by_id = {ep.id: ep for ep in episodes}
        for rec in sets:
            if not rec.get("full_ok") or rec["frontier"] is None:
                continue
            ep = by_id[rec["episode"]]
            reached = reached_fn(ep)
            feats = record_features(domain, ep, reached)
            F = set(rec["frontier"])
            for rid, f in feats.items():
                rows.append(f)
                labels.append(int(rid in F))
                if rid in F:
                    path_support[f["anchor_path"]] += 1
            # type edges implied by the frontier: the typed paths of the anchors of frontier records
            for rid in F:
                f = feats.get(rid)
                if not f or f["anchor_path"] in ("none",):
                    continue
                prev = ep.S0.get(ep.I["object_id"]).type
                if f["anchor_path"] != "self":
                    for hop in f["anchor_path"].split("/"):
                        t = hop.split(":")[1]
                        if t != prev:
                            edge_support[(prev, t)] += 1
                        prev = t
        self.keys = sorted({(k, v) for f in rows for k, v in f.items() if k != "_num"})
        self.index = {kv: i for i, kv in enumerate(self.keys)}
        self.n_num = max((len(f.get("_num", [])) for f in rows), default=0) if self.numeric else 0
        X = self._matrix(rows)
        y = np.array(labels)
        if self.model_kind == "gbm":
            from sklearn.ensemble import HistGradientBoostingClassifier
            self.tree = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, min_samples_leaf=8,
                                                       l2_regularization=1.0, max_leaf_nodes=15, class_weight="balanced" if self.balanced else None, random_state=0)
        else:
            self.tree = DecisionTreeClassifier(max_depth=self.max_depth, min_samples_leaf=2, random_state=0, class_weight="balanced")
        self.tree.fit(X, y)
        self.edge_support = dict(edge_support)
        self.path_support = dict(path_support)
        self.type_edges: Set[Tuple[str, str]] = {e for e, c in edge_support.items() if c >= self.min_support}
        self.n_rows, self.n_pos = len(rows), int(y.sum())
        return self

    def _matrix(self, rows):
        X = np.zeros((len(rows), len(self.keys) + self.n_num))
        for i, f in enumerate(rows):
            for k, v in f.items():
                if k == "_num":
                    vals = list(v)[: self.n_num]
                    X[i, len(self.keys): len(self.keys) + len(vals)] = vals
                    continue
                j = self.index.get((k, v))
                if j is not None:
                    X[i, j] = 1.0
        return X

    def predict(self, domain, ep: Episode, reached: Dict[str, Tuple], threshold: float = 0.5,
                segment_level: bool = False) -> List[str]:
        """Records with p >= threshold; with segment_level, every record of a segment whose maximum p
        reaches the threshold (the witness arrives with the intervention that produced it)."""
        feats = record_features(domain, ep, reached)
        rids = list(feats)
        if not rids:
            return []
        p = self.tree.predict_proba(self._matrix([feats[r] for r in rids]))[:, 1]
        order = {r["rid"]: i for i, r in enumerate(ep.H)}
        if segment_level:
            seg_of = {r["rid"]: r["seg"] for r in ep.H}
            hit_segs = {seg_of[r] for r, pr in zip(rids, p) if pr >= threshold}
            return [r["rid"] for r in ep.H if r["seg"] in hit_segs]
        return sorted([r for r, pr in zip(rids, p) if pr >= threshold], key=lambda r: order[r])


# --------------------------------------------------------- reach + learner

def reach_by_type_edges(ep: Episode, edges: Set[Tuple[str, str]], max_hops: int = 5) -> Dict[str, Tuple]:
    """Objects reachable from the cue's object over instance links whose type pair is a recovered edge,
    with their typed paths."""
    src = ep.I["object_id"]
    S0 = ep.S0
    paths = {src: ()}
    frontier = [src]
    while frontier:
        nxt = []
        for oid in frontier:
            o = S0.get(oid)
            cands = [(rel, t) for rel, ts in o.links.items() for t in ts]
            for x in S0.objects.values():
                for rel, ts in x.links.items():
                    if oid in ts:
                        cands.append(("~" + rel, x.id))
            for rel, t in cands:
                if t in S0.objects and t not in paths and len(paths[oid]) < max_hops and (o.type, S0.get(t).type) in edges:
                    paths[t] = paths[oid] + ((rel, S0.get(t).type),)
                    nxt.append(t)
        frontier = nxt
    return paths


def reach_all(ep: Episode, max_hops: int = 3) -> Dict[str, Tuple]:
    return path_types(ep.S0, ep.I["object_id"], max_hops)


class FrontierSelect(Learner):
    """frontier_select: read interventions with the executor on the training episodes, fit the conditional
    frontier model, select records by the model and objects by the recovered type edges, execute."""

    name = "frontier_select"

    def __init__(self, threshold: float = 0.3, max_train: Optional[int] = None, orderings: int = 1,
                 model: str = "gbm", numeric: bool = False, fit_native: bool = False, segment_level: bool = False):
        self.threshold, self.max_train, self.orderings = threshold, max_train, orderings
        self.model_kind, self.numeric, self.segment_level = model, numeric, segment_level
        # fit_native=False: the replays run on the training logs as they are (the condition's length);
        # fit_native=True: replays on native-length training logs only (the ablation)
        self.fit_native = fit_native
        self.stats: dict = {}
        if orderings > 1 or threshold != 0.3 or numeric or fit_native or segment_level:
            self.name = f"frontier_select_o{orderings}_t{int(threshold * 100)}{'_num' if numeric else ''}{'_nf' if fit_native else ''}{'_seg' if segment_level else ''}"

    def fit(self, domain, train: List[Episode]) -> None:
        train = train[: self.max_train] if self.max_train else train
        t0 = time.time()
        self.sets = discover(domain, train, lambda ep: ExecutorOracle(domain, ep), orderings=self.orderings)
        # first pass: anchors from every object within 3 hops (structure unknown); the fitted model's
        # type edges then define the reach used at test time
        self.model = FrontierModel(model=self.model_kind, numeric=self.numeric).fit(domain, train, self.sets, reach_all)
        self.edges = set(self.model.type_edges)
        ok = [s for s in self.sets if s["full_ok"]]
        self.stats = {"n_train": len(train), "full_ok": len(ok), "seconds": time.time() - t0,
                      "mean_frontier": float(np.mean([len(s["frontier"]) for s in ok])) if ok else None,
                      "mean_calls": float(np.mean([s["calls"] for s in ok])) if ok else None,
                      "mean_n": float(np.mean([s["n"] for s in ok])) if ok else None,
                      "type_edges": sorted(f"{a}->{b}" for a, b in self.edges),
                      "edge_support": {f"{a}->{b}": c for (a, b), c in sorted(self.model.edge_support.items())},
                      "rows": self.model.n_rows, "positives": self.model.n_pos}

    def select(self, domain, ep: Episode) -> dict:
        reached = reach_by_type_edges(ep, self.edges)
        recs = self.model.predict(domain, ep, reached, self.threshold, self.segment_level)
        objs = sorted(set(reached) | set(visible_objects(ep, recs)))
        return {"objects": objs, "records": recs}

    def predict(self, domain, ep: Episode) -> dict:
        reads = self.select(domain, ep)
        est = restricted_est(domain, ep.H, ep.S0, reads["records"])
        post = ep.S0.copy()
        try:
            _rc, txns, _ = execute_intervention(domain, est, post, ep.I, FallbackTracker(est))
        except Exception:
            txns = []
        return {"txns": txns, "reads": reads}


# ------------------------------------------------- LLM-fitted frontier for the actor panel

def fit_llm_frontier(domain, sets_files: List[str], train_seed: int, n_train: int = 200) -> "FrontierModel":
    """Fit the conditional frontier model on minimal sets discovered with the LLM as the policy
    (hm3.replay_llm output, several shards pooled)."""
    from .generate import generate_split
    train = generate_split(domain, train_seed, "train", n_train)
    by = {ep.id: ep for ep in train}
    rows = []
    for f in sets_files:
        rows += [json.loads(l) for l in open(f)]
    ok = [r for r in rows if r.get("full_ok") and r["episode"] in by]
    eps = [by[r["episode"]] for r in ok]
    model = FrontierModel().fit(domain, eps, ok, reach_all)
    model.n_episodes = len(ok)
    return model


def frontier_reads(domain, ep: Episode, model: "FrontierModel", threshold: float = 0.3) -> dict:
    """Selection for the actor: records by the model, objects = the type-edge reach from the cue, its one-hop
    closure (children with no read edge, e.g. the activity, still have to be shown), and the referents of the
    selected records with their one-hop closure."""
    reached = reach_by_type_edges(ep, set(model.type_edges))
    recs = model.predict(domain, ep, reached, threshold)
    objs = set(reached) | set(visible_objects(ep, recs))
    for oid in list(reached):
        for targets in ep.S0.get(oid).links.values():
            objs.update(t for t in targets if t in ep.S0.objects)
    order = {r["rid"]: i for i, r in enumerate(ep.H)}
    return {"objects": sorted(objs), "records": sorted(recs, key=lambda r: order[r])}
