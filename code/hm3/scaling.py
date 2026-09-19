"""History-length scaling (docs/hm3-history-scaling-design-2026-09-18.md).

augment_episode() grows an episode's history to a target number of records with
four frozen distractor types without touching the original chain: S0/S1 objects
of the original world, I, A, R, required reads and relevant params are kept.
Foreign objects get ids disjoint from S0; foreign segments are placed before the
real history so that the parser's last-witness-wins rule leaves the consulted
keys' est and prov unchanged.  validate() checks exactly that.

  A stale    head-of-history clones of the witness records of every consulted key,
             deltas re-chained to the field values at the start of the real history,
             auto<->txn kinds flipped on the non-intervention records
  B nearest  a renamed copy of the same world (same params, same policy keys, same
             names) with fresh random prior interventions: agreeing witnesses
  C lexical  a renamed copy of the same world with perturbed params: conflicting
             witnesses under the same names and keys
  D foreign  an unrelated world with fresh keys: pure volume

RetrievalTopK / RecencyK are the fixed-K reading arms: K history records go into
restricted_est and the runtime-history executor.
"""
from __future__ import annotations

import copy
import hashlib
import random
import re
from typing import Dict, List, Optional, Tuple

from .core import (Episode, FallbackTracker, Illegal, Obj, State, canonical_txn, execute_intervention,
                   restricted_est, score_plan, timeline)
from .generate import DEFAULT_CFG, run_segment
from .learners import LearnedGraph, Learner, RuntimeHistoryOracle, follow_template
from .features import path_types

KEY_FIELDS = {"travel": ["provider", "hotel", "restaurant", "vendor"]}
CONTINUOUS = {"buffer": [20, 25, 30, 35, 40, 45, 50, 55, 60]}
MAX_SEGS_PER_WORLD = 8
INTERLEAVED = "bcd"  # foreign segments that witness no consulted key may sit between real segments


def _seed_int(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def _prefix(oid: str) -> str:
    m = re.match(r"[A-Za-z_]+", oid)
    return m.group(0) if m else "X"


class _Ids:
    """Fresh ids that never collide with the original world or earlier foreign copies."""

    def __init__(self, used):
        self.used = set(used)
        self.next: Dict[str, int] = {}

    def fresh(self, like: str) -> str:
        p = _prefix(like)
        n = self.next.get(p, 100)
        while f"{p}{n}" in self.used:
            n += 1
        self.next[p] = n + 1
        self.used.add(f"{p}{n}")
        return f"{p}{n}"


def _rename_world(params: dict, state: State, ids: _Ids, key_map: Optional[dict] = None) -> Tuple[dict, State]:
    id_map = {oid: ids.fresh(oid) for oid in state.objects}
    key_map = key_map or {}
    new = State([], copy.deepcopy(state.meta), state.tokens)
    for oid, o in state.objects.items():
        d = o.to_dict()
        d["id"] = id_map[oid]
        d["links"] = {rel: [id_map.get(t, t) for t in ts] for rel, ts in d.get("links", {}).items()}
        for f, v in list(d.get("fields", {}).items()):
            if isinstance(v, str):
                d["fields"][f] = id_map.get(v, key_map.get(v, v))
        new.add(Obj.from_dict(d))
    p2 = {}
    for name, kv in params.items():
        p2[name] = {id_map.get(k, key_map.get(k, k)): v for k, v in kv.items()}
    return p2, new


def _perturb(params: dict, rng: random.Random) -> dict:
    out = copy.deepcopy(params)
    for name, kv in out.items():
        for k, v in kv.items():
            if name in CONTINUOUS:
                kv[k] = rng.choice([x for x in CONTINUOUS[name] if x != v] or [v])
            elif isinstance(v, bool) or (isinstance(v, int) and v in (0, 1)):
                kv[k] = 1 - int(v)
    return out


def _foreign_segments(domain, params: dict, state: State, rng: random.Random, need: int) -> List[List[dict]]:
    """Run random prior interventions in place; return the records grouped by segment."""
    H: List[dict] = []
    segs: List[List[dict]] = []
    seg = 0
    while len(H) < need and seg < MAX_SEGS_PER_WORLD:
        I = domain.sample_intervention(rng, params, state)
        if I is None:
            break
        n0 = len(H)
        try:
            run_segment(domain, params, state, I, H, seg)
        except (Illegal, KeyError, IndexError, ValueError):
            break
        if len(H) == n0:
            break
        segs.append(H[n0:])
        seg += 1
    return segs


def _split_segments(H: List[dict]) -> List[List[dict]]:
    out: List[List[dict]] = []
    for r in H:
        if r["kind"] == "intervention" or not out:
            out.append([r])
        else:
            out[-1].append(r)
    return out


def _touches(domain, seg: List[dict], state: State, relevant: List[str]) -> bool:
    """Does this segment alone produce a witness for any consulted key?"""
    prov: Dict[str, list] = {}
    try:
        domain.infer_params(copy.deepcopy(seg), state, prov)
    except Exception:
        return True
    return any(prov.get(pk) for pk in relevant)


def stale_clones(domain, ep: Episode, snaps0: State) -> Tuple[List[List[dict]], int, int]:
    """Type A.  Returns (segments, n_keys_cloned, n_keys_whose_implied_value_differs)."""
    prov: Dict[str, list] = {}
    domain.infer_params(ep.H, ep.S0, prov)
    by_rid = {r["rid"]: r for r in ep.H}
    fee_of = {}
    for r in ep.H:
        fee_of.setdefault((r["kind"], r["op"]), r["fee"])
    out, n_keys, n_diff = [], 0, 0
    for pk in ep.relevant_params:
        rids = [r for r in prov.get(pk, []) if r in by_rid]
        if not rids:
            continue
        recs = sorted((by_rid[r] for r in rids), key=lambda r: ep.H.index(r))
        clone = []
        for r in recs:
            oid = r["object_id"]
            if oid not in snaps0.objects:
                continue
            o0 = snaps0.get(oid)
            c = copy.deepcopy(r)
            nd = {}
            for fld, (old, new) in (c.get("delta") or {}).items():
                cur = o0.status if fld == "status" else o0.fields.get(fld, new)
                if isinstance(new, (int, float)) and not isinstance(new, bool) and \
                        isinstance(old, (int, float)) and not isinstance(old, bool) and \
                        isinstance(cur, (int, float)):
                    nd[fld] = (cur - (new - old), cur)
                else:
                    nd[fld] = (old, cur)
            c["delta"] = nd
            c["rev"] = max(0, o0.revision)
            if c["kind"] == "intervention":
                if nd:
                    c["payload"] = {f: v[1] for f, v in nd.items()}
                try:
                    c["query"] = domain.nl_query({"object_id": oid, "op": c["op"], "payload": c["payload"]}, ep.S0)
                except Exception:
                    pass
            else:
                c["kind"] = "txn" if c["kind"] == "auto" else "auto"
                c["fee"] = fee_of.get((c["kind"], c["op"]), 0 if c["kind"] == "auto" else c["fee"])
                if nd:
                    c["payload"] = {f: v[1] for f, v in nd.items()}
            clone.append(c)
        if not clone or clone[0]["kind"] != "intervention":
            continue
        n_keys += 1
        name, key = pk.split("[", 1)
        key = key[:-1]
        try:
            implied = domain.infer_params(copy.deepcopy(clone), ep.S0).get(name, {}).get(key)
        except Exception:
            implied = None
        if implied is not None and implied != ep.params[name][key]:
            n_diff += 1
        out.append(clone)
    return out, n_keys, n_diff


def augment_episode(domain, ep: Episode, target: Optional[int], mix: str, tag: str = "",
                    interleave: bool = True) -> Tuple[Episode, dict]:
    rng = random.Random(_seed_int("scaling", ep.id, target, mix, tag))
    snaps0 = timeline(ep.S0, ep.H)[0]
    stats = {"a_keys": 0, "a_diff": 0, "b": 0, "c": 0, "d": 0, "foreign_objects": 0}
    segs_new: List[List[dict]] = []
    a_segs: List[List[dict]] = []
    if "a" in mix:
        a_segs, stats["a_keys"], stats["a_diff"] = stale_clones(domain, ep, snaps0)
    n_a = sum(len(s) for s in a_segs)
    ids = _Ids(ep.S0.objects)
    foreign_objs: List[Obj] = []
    types = [t for t in "bcd" if t in mix]
    if target is not None and types:
        budget = max(0, target - len(ep.H) - n_a)
        per = [budget // len(types)] * len(types)
        per[-1] += budget - sum(per)
        for t, need in zip(types, per):
            got, tries = 0, 0
            while got < need and tries < 60:
                tries += 1
                if t in "bc":
                    p, s = _rename_world(ep.params, snaps0, ids)
                    if t == "c":
                        p = _perturb(p, rng)
                else:
                    p0, s0 = domain.sample_world(rng, DEFAULT_CFG)
                    key_map = {}
                    for name, kv in p0.items():
                        for k in kv:
                            if k not in s0.objects and k != "global" and "|" not in k:
                                key_map[k] = ids.fresh(k)
                    p, s = _rename_world(p0, s0, ids, key_map)
                s.tokens = 100000
                segs = _foreign_segments(domain, p, s, rng, need - got)
                if not segs:
                    continue
                for seg in segs:
                    if got >= need:
                        break
                    for r in seg:
                        r["_type"] = t
                    segs_new.append(seg)
                    got += len(seg)
                    stats[t] += len(seg)
                foreign_objs.extend(s.objects.values())
    probe = ep.S0.copy()
    for o in foreign_objs:
        probe.add(Obj.from_dict(o.to_dict()))
    before, inter = [], []
    for seg in segs_new:
        if interleave and seg[0].get("_type") in INTERLEAVED and not _touches(domain, seg, probe, ep.relevant_params):
            inter.append(seg)
        else:
            before.append(seg)
    rng.shuffle(before)
    rng.shuffle(inter)
    real_segs = _split_segments([copy.deepcopy(r) for r in ep.H])
    # random insertion points: a foreign segment goes before real segment j (0..len(real_segs)),
    # never after the last real segment (its witnesses must stay the most recent for their keys)
    slots = [rng.randint(0, max(0, len(real_segs) - 1)) for _ in inter]
    merged: List[List[dict]] = []
    for j, seg in enumerate(real_segs):
        for k, ins in enumerate(inter):
            if slots[k] == j:
                merged.append(ins)
        merged.append(seg)
    ordered = a_segs + before + merged
    H_all = [r for seg in ordered for r in seg]
    real_ids = {id(r) for seg in real_segs for r in seg}
    if target is not None and len(H_all) > target:
        # drop the earliest foreign records until the target is met
        excess = len(H_all) - target
        keep = []
        for r in H_all:
            if excess > 0 and id(r) not in real_ids:
                excess -= 1
                continue
            keep.append(r)
        H_all = keep
    seg_no = 1000
    fi = 0
    for r in H_all:
        r.pop("_type", None)
        if id(r) in real_ids:
            continue
        if r["kind"] == "intervention":
            seg_no += 1
        r["rid"] = f"x{fi}"
        r["seg"] = seg_no
        fi += 1
    H_new = H_all
    S0 = ep.S0.copy()
    S1 = ep.S1.copy()
    for o in foreign_objs:
        S0.add(Obj.from_dict(o.to_dict()))
        S1.add(Obj.from_dict(o.to_dict()))
    stats["foreign_objects"] = len(foreign_objs)
    stats["interleaved"] = int(interleave and bool(inter))
    d = ep.__dict__.copy()
    d.update(H=H_new, S0=S0, S1=S1)
    aug = Episode(**d)
    stats["n_records"] = len(aug.H)
    stats["n_objects"] = len(aug.S0.objects)
    return aug, stats


def validate(domain, ep: Episode, aug: Episode) -> Tuple[bool, str]:
    prov_n: Dict[str, list] = {}
    prov_a: Dict[str, list] = {}
    est_n = domain.infer_params(ep.H, ep.S0, prov_n)
    est_a = domain.infer_params(aug.H, aug.S0, prov_a)
    for pk in ep.relevant_params:
        name, key = pk.split("[", 1)
        key = key[:-1]
        if est_n.get(name, {}).get(key) != est_a.get(name, {}).get(key):
            return False, f"est {pk}"
        if sorted(prov_n.get(pk, [])) != sorted(prov_a.get(pk, [])):
            return False, f"prov {pk}"
    if aug.required_reads != ep.required_reads:
        return False, "required_reads"
    try:
        out = RuntimeHistoryOracle().predict(domain, aug)
    except Exception as exc:
        return False, f"rh_oracle raised {type(exc).__name__}"
    if {canonical_txn(t) for t in out["txns"]} != {canonical_txn(t) for t in aug.A}:
        return False, "rh_oracle txns"
    if not score_plan(domain, aug, out["txns"], out["reads"])["ees"]:
        return False, "rh_oracle ees"
    if not score_plan(domain, aug, aug.A, aug.required_reads)["ees"]:
        return False, "oracle ees"
    return True, ""


def relabel(ep: Episode) -> Dict[str, str]:
    """Uniform record ids (h0..hN in history order) and sequential segment numbers, so
    that foreign and real records are indistinguishable by label; required reads are
    remapped through the same bijection."""
    mapping = {}
    seg_no = -1
    for i, r in enumerate(ep.H):
        mapping[r["rid"]] = f"h{i}"
        if r["kind"] == "intervention" or seg_no < 0:
            seg_no += 1
        r["seg"] = seg_no
    for r in ep.H:
        r["rid"] = mapping[r["rid"]]
    ep.required_reads = {"objects": list(ep.required_reads.get("objects", [])),
                         "records": [mapping.get(x, x) for x in ep.required_reads.get("records", [])]}
    return mapping


def augment_split(domain, eps: List[Episode], target: Optional[int], mix: str, tag: str = "") -> Tuple[List[Episode], dict]:
    out = []
    agg = {"n": len(eps), "dropped": 0, "retries": 0, "a_keys": 0, "a_diff": 0, "b": 0, "c": 0, "d": 0,
           "records": 0, "objects": 0, "fail_reasons": {}}
    agg["fallback_no_interleave"] = 0
    for ep in eps:
        ok = False
        for attempt in range(5):
            aug, st = augment_episode(domain, ep, target, mix, f"{tag}/{attempt}")
            good, why = validate(domain, ep, aug)
            if good:
                ok = True
                break
            agg["retries"] += 1
            agg["fail_reasons"][why] = agg["fail_reasons"].get(why, 0) + 1
        if not ok:
            # state-dependent witnesses (Shopping's promo strictness is read off the cart state
            # after a segment) can appear only in the context of the whole history, which the
            # per-segment interleaving check cannot see: fall back to placing every foreign
            # segment before the real history, which the validation then accepts
            for attempt in range(3):
                aug, st = augment_episode(domain, ep, target, mix, f"{tag}/nointer{attempt}", interleave=False)
                good, why = validate(domain, ep, aug)
                if good:
                    ok = True
                    agg["fallback_no_interleave"] += 1
                    break
                agg["fail_reasons"][why] = agg["fail_reasons"].get(why, 0) + 1
        if not ok:
            agg["dropped"] += 1
            continue
        relabel(aug)
        out.append(aug)
        for k in ("a_keys", "a_diff", "b", "c", "d"):
            agg[k] += st[k]
        agg["records"] += st["n_records"]
        agg["objects"] += st["n_objects"]
    n = max(1, len(out))
    agg["mean_records"] = agg["records"] / n
    agg["mean_objects"] = agg["objects"] / n
    agg["drop_rate"] = agg["dropped"] / max(1, len(eps))
    return out, agg


# ----------------------------------------------------------- fixed-K readers

_TOK = re.compile(r"[A-Za-z0-9]+")


def _fmt(v):
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}:{_fmt(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ",".join(_fmt(x) for x in v) + "]"
    return str(v)


def record_text(r: dict) -> str:
    delta = " ".join(f"{k}:{_fmt(a)}->{_fmt(b)}" for k, (a, b) in (r.get("delta") or {}).items())
    head = f"{r['rid']} seg{r['seg']} {r['kind']} {r['op']} {r['object_id']} rev={r['rev']}"
    if r["kind"] == "intervention":
        head += f" query=\"{r.get('query', '')}\""
    return f"{head} {delta}"


def query_text(ep: Episode) -> str:
    src = ep.S0.get(ep.I["object_id"])
    fields = " ".join(f"{k}={_fmt(v)}" for k, v in src.fields.items())
    links = " ".join(",".join(v) for v in src.links.values() if v)
    return f"{ep.query} {src.id} {src.type} {fields} {links} {_fmt(ep.I.get('payload', {}))}"


def _tokens(s: str) -> set:
    return {t.lower() for t in _TOK.findall(s)}


class RetrievalTopK(Learner):
    """Lexical top-K history records (query + source object text vs record text),
    ties broken by recency; parameters from those records only; runtime-history
    executor.  An upper bound for any K-record retriever."""

    def __init__(self, k: int = 16, mode: str = "lexical"):
        self.k = k
        self.mode = mode
        self.name = {"lexical": f"retrieval_k{k}", "recency": f"recency_k{k}", "bm25": f"bm25_k{k}"}[mode]

    def fit(self, domain, train):
        return None

    def select(self, ep: Episode) -> List[str]:
        if self.mode == "recency":
            return [r["rid"] for r in ep.H[-self.k:]]
        if self.mode == "bm25":
            return bm25_topk(ep, self.k)
        q = _tokens(query_text(ep))
        scored = []
        for i, r in enumerate(ep.H):
            scored.append((len(q & _tokens(record_text(r))), i, r["rid"]))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [rid for _s, _i, rid in scored[:self.k]]

    def predict(self, domain, ep):
        top = self.select(ep)
        est = restricted_est(domain, ep.H, ep.S0, top)
        tr = FallbackTracker(est)
        post = ep.S0.copy()
        try:
            _rc, txns, tr = execute_intervention(domain, est, post, ep.I, tr)
        except Exception:
            txns = []
        return {"txns": txns, "reads": {"objects": list(tr.read_objects), "records": top}}


def bm25_topk(ep: Episode, k: int, k1: float = 1.5, b: float = 0.75) -> List[str]:
    """Okapi BM25 over the compact record lines; query = query text + source object line."""
    import math
    docs = [_TOK.findall(record_text(r).lower()) for r in ep.H]
    q = _TOK.findall(query_text(ep).lower())
    n = len(docs)
    avg = sum(len(d) for d in docs) / max(1, n)
    df: Dict[str, int] = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    scores = []
    for i, d in enumerate(docs):
        tf: Dict[str, int] = {}
        for t in d:
            tf[t] = tf.get(t, 0) + 1
        sc = 0.0
        for t in q:
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            sc += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / max(1e-9, avg)))
        scores.append((sc, i))
    scores.sort(key=lambda x: (-x[0], -x[1]))
    return [ep.H[i]["rid"] for _s, i in scores[:k]]


def rewire_skeleton(g: LearnedGraph, train: List[Episode], perm_seed: int) -> Dict[str, str]:
    """Re-wire the learned skeleton's templates to other valid typed paths seen in
    training (same parent type, same number of templates, same majority labels).
    Returns the mapping old -> new for the record."""
    pool = set()
    for ep in train:
        src = ep.I["object_id"]
        stype = ep.S0.get(src).type
        for _c, template in path_types(ep.S0, src, g.MAX_TEMPLATE_HOPS).items():
            if template:
                pool.add((stype, tuple(template)))
        for o in list(ep.S0.objects.values())[:12]:
            for _c, template in path_types(ep.S0, o.id, g.MAX_TEMPLATE_HOPS).items():
                if template:
                    pool.add((o.type, tuple(template)))
    rng = random.Random(1000 + perm_seed)
    real = list(g.skeleton)
    used = set()
    new_skel, new_major, mapping = {}, {}, {}
    for key in real:
        ptype, template = key
        cands = [k for k in pool if k[0] == ptype and k not in g.skeleton and k not in used and len(k[1]) == len(template)]
        if not cands:
            cands = [k for k in pool if k[0] == ptype and k not in g.skeleton and k not in used]
        if not cands:
            cands = [k for k in pool if k not in used and k not in g.skeleton]
        if not cands:
            continue
        nk = rng.choice(sorted(cands))
        used.add(nk)
        new_skel[nk] = g.skeleton[key]
        new_major[nk] = g.majority[key]
        mapping[str(key)] = str(nk)
    g.skeleton, g.majority = new_skel, new_major
    g.models = {k: ("const", new_major[k]) for k in new_skel}
    return mapping


def skeleton_reads(domain, g: LearnedGraph, ep: Episode, max_expansions: int = 400) -> dict:
    """Objects reachable from the source along the skeleton templates, plus the
    history records the parser attributes to their policy keys."""
    src = ep.I["object_id"]
    seen = [src]
    frontier = [src]
    budget = max_expansions
    while frontier and budget > 0:
        o = frontier.pop(0)
        if o not in ep.S0.objects:
            continue
        for (ptype, template) in g.skeleton:
            if ptype != ep.S0.get(o).type:
                continue
            for c in follow_template(ep.S0, o, template):
                budget -= 1
                if c not in seen and c in ep.S0.objects:
                    seen.append(c)
                    frontier.append(c)
    prov: Dict[str, list] = {}
    domain.infer_params(ep.H, ep.S0, prov)
    records = set()
    for oid in seen:
        for name, key in domain.param_keys_for(ep.S0.get(oid), ep.S0):
            records.update(prov.get(f"{name}[{key}]", []))
    return {"objects": sorted(seen), "records": sorted(records)}


class SelectExecute(Learner):
    """Selection ladder with a fixed executor: read along the learned skeleton
    (graph_select) or along a re-wired skeleton (wrong_select_k), recover the
    parameters from those records only, execute with the runtime-history
    executor.  Isolates the value of the topology for *selection* from the
    learned gate models; comparable with retrieval_k / bm25_k / recency_k."""

    def __init__(self, perm_seed: Optional[int] = None):
        self.perm_seed = perm_seed
        self.name = "graph_select" if perm_seed is None else f"wrong_select_{perm_seed}"

    def fit(self, domain, train):
        self.g = LearnedGraph()
        self.g.fit(domain, train)
        self.rewired = rewire_skeleton(self.g, train, self.perm_seed) if self.perm_seed is not None else {}

    def predict(self, domain, ep):
        reads = skeleton_reads(domain, self.g, ep)
        est = restricted_est(domain, ep.H, ep.S0, reads["records"])
        tr = FallbackTracker(est)
        post = ep.S0.copy()
        try:
            _rc, txns, tr = execute_intervention(domain, est, post, ep.I, tr)
        except Exception:
            txns = []
        return {"txns": txns, "reads": reads}


class WrongGraph(LearnedGraph):
    """Appendix control: majority labels propagated along a re-wired skeleton
    (the superset rule on the wrong topology).  Inherits the superset rule's
    collateral writes, so it is not the matched topology control; see SelectExecute."""

    def __init__(self, perm_seed: int):
        super().__init__(superset=True)
        self.perm_seed = perm_seed
        self.name = f"wrong_graph_{perm_seed}"

    def fit(self, domain, train):
        super().fit(domain, train)
        self.rewired_from = rewire_skeleton(self, train, self.perm_seed)


class NativeFitGraph(LearnedGraph):
    """graph_nf / graph_pooled_nf: the same learned graph, but the gate models are fitted on the
    native training episodes of the seed (run_scaling passes train0 when fit_native is set) and
    only the evaluation histories are augmented.  Rationale (design §9.6): long histories change
    the evidence, not the mechanisms; refitting the gate on foreign-witness-polluted estimates is
    what the per-condition graph rows measure, and is reported next to these as the ablation."""

    fit_native = True

    def __init__(self, pooled: bool = False):
        super().__init__(pooled=pooled)
        self.name = "graph_pooled_nf" if pooled else "graph_nf"


class _ConflictMaskingDomain:
    """Proxy around a domain: infer_params returns the ordinary last-witness estimates and records,
    for the same est object, a masked copy in which a key is unknown when the latest witness about a
    *different* object disagrees with the last witness (same-object stale versions are kept: they are
    resolved by recency).  Keys inferred from the state snapshot alone (no record) are not checked."""

    def __init__(self, domain):
        self._d = domain
        self.masked: Dict[int, dict] = {}

    def __getattr__(self, name):
        return getattr(self._d, name)

    def infer_params(self, H, S0, prov=None):
        own: Dict[str, list] = {} if prov is None else prov
        est = self._d.infer_params(H, S0, own)
        by_rid = {r["rid"]: r for r in H}
        masked = {n: dict(v) for n, v in est.items()}
        for name, kv in est.items():
            for key, v1 in kv.items():
                rids = own.get(f"{name}[{key}]", [])
                objs = {by_rid[r]["object_id"] for r in rids if r in by_rid}
                if not objs:
                    continue
                H2 = [r for r in H if r["object_id"] not in objs]
                try:
                    v2 = self._d.infer_params(H2, S0).get(name, {}).get(key)
                except Exception:
                    v2 = None
                if v2 is not None and v2 != v1:
                    masked[name][key] = None
        self.masked[id(est)] = masked
        return est


class ConflictAwareGraph(LearnedGraph):
    """graph_cf: native-fit graph whose gate features see conflict-masked estimates (see
    _ConflictMaskingDomain); trackers and the value pathway keep the last-witness estimates."""

    def __init__(self, pooled: bool = False, indicator: bool = False):
        super().__init__(pooled=pooled)
        # graph_cf: native-fit, conflicting keys masked to unknown for the gate.
        # graph_cfa: per-condition fit, estimates kept, one conflict indicator per parameter family
        #            for the child and the parent appended to the gate features (the gate can learn
        #            what a conflict means only if its training histories contain conflicts).
        self.indicator = indicator
        self.fit_native = not indicator
        base = "graph_pooled" if pooled else "graph"
        self.name = base + ("_cfa" if indicator else "_cf")
        self._proxy = None

    def _feat(self, domain, p, p_new, c, state, est, pkind, wc=-1.0):
        m = self._proxy.masked.get(id(est), est) if self._proxy is not None else est
        if not self.indicator:
            return super()._feat(domain, p, p_new, c, state, m, pkind, wc)
        row = super()._feat(domain, p, p_new, c, state, est, pkind, wc)
        real = self._proxy._d if self._proxy is not None else domain
        for obj in (c, p):
            keys = real.param_keys_for(obj, state)
            for name in self.vocab.names:
                conflict = any(n == name and est.get(n, {}).get(k) is not None and m.get(n, {}).get(k) is None
                               for n, k in keys)
                row.append(1.0 if conflict else 0.0)
        return row

    def fit(self, domain, train):
        self._proxy = _ConflictMaskingDomain(domain)
        super().fit(self._proxy, train)
        self._proxy.masked.clear()

    def predict(self, domain, ep):
        self._proxy = _ConflictMaskingDomain(domain)
        out = super().predict(self._proxy, ep)
        self._proxy.masked.clear()
        return out


class UnionFitGraph(LearnedGraph):
    """graph_un: gate fitted on the native training episodes plus the same episodes augmented under
    the evaluation condition (run_scaling passes train0 + train when fit_union is set).  Each gate row
    therefore appears twice with the same label and estimates that differ only where foreign
    witnesses reached them; the tree cannot use those coordinates and keeps the structural ones."""

    fit_union = True

    def __init__(self, pooled: bool = False):
        super().__init__(pooled=pooled)
        self.name = "graph_pooled_un" if pooled else "graph_un"


class UnionConflictGraph(ConflictAwareGraph):
    """graph_un_cfa: union fit plus the conflict indicators of graph_cfa."""

    fit_union = True

    def __init__(self):
        super().__init__(indicator=True)
        self.fit_native = False
        self.name = "graph_un_cfa"


class SelectedGraph(Learner):
    """graph_sel: the gate-fitting protocol is chosen per (seed, condition) by held-out training
    episodes only.  Candidates: gate fitted on native training rows (graph_nf), on the condition's
    augmented rows (graph), and on the augmented rows with conflict indicators (graph_cfa).  The
    last 20% of training episodes (by id, fixed) are held out, augmented under the condition; each
    candidate is fitted on the remaining 80% and scored by EES on the held-out augmented episodes;
    the winner (ties -> native) is refitted on the full training set.  No dev/test episode is used."""

    fit_both = True

    def __init__(self, pooled: bool = False):
        self.pooled = pooled
        self.name = "graph_pooled_sel" if pooled else "graph_sel"
        self.choice = None
        self.scores = {}

    def _candidates(self):
        return {"native": NativeFitGraph(pooled=self.pooled), "condition": LearnedGraph(pooled=self.pooled),
                "condition_cfa": ConflictAwareGraph(pooled=self.pooled, indicator=True)}

    def fit_both(self, domain, train0, train):
        from .run_det import evaluate_learner
        ids = [ep.id for ep in train0]
        n_hold = max(1, len(ids) // 5)
        hold = set(ids[-n_hold:])
        t0_fit = [ep for ep in train0 if ep.id not in hold]
        ta_fit = [ep for ep in train if ep.id not in hold]
        ta_hold = [ep for ep in train if ep.id in hold]
        sets = {"native": t0_fit, "condition": ta_fit, "condition_cfa": ta_fit}
        self.scores = {}
        if train is train0 or not ta_hold:
            self.choice = "native"
        else:
            for name, cand in self._candidates().items():
                cand.fit(domain, sets[name])
                self.scores[name] = evaluate_learner(domain, cand, ta_hold)["summary"]["ees"]
            best = max(self.scores.values())
            order = ["native", "condition", "condition_cfa"]
            self.choice = next(n for n in order if self.scores[n] == best)
        self.model = self._candidates()[self.choice]
        self.model.fit(domain, {"native": train0, "condition": train, "condition_cfa": train}[self.choice])

    def fit(self, domain, train):
        self.fit_both(domain, train, train)

    def predict(self, domain, ep):
        out = self.model.predict(domain, ep)
        out["selection"] = {"choice": self.choice, "held_out_ees": self.scores}
        return out


class BaggedGraph(LearnedGraph):
    """graph_bag: the same learned graph and features, but every per-template gate is a bag of
    depth-5 trees (25 bootstrap fits on 80% of the gate rows, majority vote) instead of one tree.
    Motivation (results §2.4): under foreign-witness-polluted training rows the single tree sits on
    a knife edge (Shopping32 seed 0, 100 records: 195 training episodes -> dev EES 0.75, 199 ->
    0.18); bagging removes that variance without changing what the gate can see.  Per-condition
    fit, like graph."""

    def __init__(self, pooled: bool = False, n_estimators: int = 25, max_samples: float = 0.8):
        super().__init__(pooled=pooled)
        self.name = "graph_pooled_bag" if pooled else "graph_bag"
        self.n_estimators, self.max_samples = n_estimators, max_samples

    def fit(self, domain, train):
        import sklearn.tree
        from sklearn.ensemble import BaggingClassifier
        orig = sklearn.tree.DecisionTreeClassifier
        n, ms = self.n_estimators, self.max_samples

        def bagged(**kw):
            return BaggingClassifier(orig(**kw), n_estimators=n, max_samples=ms, random_state=0)
        sklearn.tree.DecisionTreeClassifier = bagged
        try:
            super().fit(domain, train)
        finally:
            sklearn.tree.DecisionTreeClassifier = orig


class NativeBaggedGraph(BaggedGraph):
    """graph_nf_bag: bagged gate (BaggedGraph) fitted on the native training episodes (NativeFitGraph
    protocol): clean mechanism learning plus variance reduction at prediction time."""

    fit_native = True

    def __init__(self, pooled: bool = False):
        super().__init__(pooled=pooled)
        self.name = "graph_pooled_nf_bag" if pooled else "graph_nf_bag"


class UnionBaggedGraph(BaggedGraph):
    """graph_un_bag: bagged gate fitted on native rows plus the condition's augmented rows."""

    fit_union = True

    def __init__(self, pooled: bool = False):
        super().__init__(pooled=pooled)
        self.name = "graph_pooled_un_bag" if pooled else "graph_un_bag"


def scaling_learners() -> List[Learner]:
    from .keysel import KeySelect
    from .tcd_logs import TCDSelect
    return [KeySelect(1), KeySelect(2), KeySelect(3),
            TCDSelect("parser"), TCDSelect("key"), TCDSelect("parser", estimator="pcmci"), TCDSelect("key", estimator="pcmci"),
            RetrievalTopK(8), RetrievalTopK(16), RetrievalTopK(16, mode="recency"), RetrievalTopK(16, mode="bm25"),
            SelectExecute(), SelectExecute(1), SelectExecute(2), SelectExecute(3),
            NativeFitGraph(), NativeFitGraph(pooled=True), ConflictAwareGraph(), ConflictAwareGraph(pooled=True), ConflictAwareGraph(indicator=True), UnionFitGraph(), UnionFitGraph(pooled=True), UnionConflictGraph(), SelectedGraph(), SelectedGraph(pooled=True), BaggedGraph(), NativeBaggedGraph(), UnionBaggedGraph()]
