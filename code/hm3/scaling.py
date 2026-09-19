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
from .learners import Learner, RuntimeHistoryOracle

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


def augment_episode(domain, ep: Episode, target: Optional[int], mix: str, tag: str = "") -> Tuple[Episode, dict]:
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
        if seg[0].get("_type") in INTERLEAVED and not _touches(domain, seg, probe, ep.relevant_params):
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


def augment_split(domain, eps: List[Episode], target: Optional[int], mix: str, tag: str = "") -> Tuple[List[Episode], dict]:
    out = []
    agg = {"n": len(eps), "dropped": 0, "retries": 0, "a_keys": 0, "a_diff": 0, "b": 0, "c": 0, "d": 0,
           "records": 0, "objects": 0, "fail_reasons": {}}
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
            agg["dropped"] += 1
            continue
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
        self.name = f"retrieval_k{k}" if mode == "lexical" else f"recency_k{k}"

    def fit(self, domain, train):
        return None

    def select(self, ep: Episode) -> List[str]:
        if self.mode == "recency":
            return [r["rid"] for r in ep.H[-self.k:]]
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


def scaling_learners() -> List[Learner]:
    return [RetrievalTopK(8), RetrievalTopK(16), RetrievalTopK(16, mode="recency")]
