"""Parser-free selection: same-key precedent records along the learned skeleton.

The learned graph's forward reads (scaling.skeleton_reads) take the *objects* from the
skeleton and the *records* from the domain's history parser (infer_params), which knows the
name of every hidden policy and the arithmetic that recovers it.  This module replaces the
parser in the selection step with a rule that uses only generic structure:

  * the objects reached from the intervention source along the learned skeleton;
  * the declared key fields of each object type (domain.categorical_fields(): provider,
    hotel, restaurant, vendor ...) -- metadata, not policy knowledge;
  * the record log itself (which object a record is about, and which segment it sits in).

Rule ("latest same-key precedent, with its local context"): for every reached object o and
every key field f of its type, take the objects of the same type that share o's value of f,
find the most recent n_prec segments in which any of them was written, and read from each
such segment the intervention record plus every record about those objects or their 1-hop
neighbours.  If no such segment exists, fall back to the most recent segments in which a
1-hop neighbour of o was written (the absence of a response is itself the witness).
Nothing here knows what a "buffer" is or how it is computed.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set

from .core import Episode, FallbackTracker, State, execute_intervention, restricted_est, segments
from .learners import Learner


def _neighbours(S0: State, oid: str) -> Set[str]:
    o = S0.get(oid)
    near: Set[str] = set()
    for ts in o.links.values():
        near.update(t for t in ts if t in S0.objects)
    for x in S0.objects.values():
        if any(oid in ts for ts in x.links.values()):
            near.add(x.id)
    return near


def key_precedent_records(domain, ep: Episode, objects: List[str], n_prec: int = 1) -> List[str]:
    S0, H = ep.S0, ep.H
    segs = segments(H)
    obj_segs: Dict[str, Set[int]] = defaultdict(set)
    for si, seg in enumerate(segs):
        for r in seg:
            obj_segs[r["object_id"]].add(si)
    cats = domain.categorical_fields()
    chosen: Set[str] = set()

    def take(si: int, focus: Set[str]) -> None:
        seg = segs[si]
        near = set(focus)
        for p in focus:
            if p in S0.objects:
                near |= _neighbours(S0, p)
        for r in seg:
            if r["kind"] == "intervention" or r["object_id"] in near:
                chosen.add(r["rid"])

    for oid in objects:
        if oid not in S0.objects:
            continue
        o = S0.get(oid)
        keys = [(f, o.fields.get(f)) for f in cats.get(o.type, []) if o.fields.get(f) is not None]
        if not keys:
            continue
        for f, v in keys:
            same = {x.id for x in S0.objects.values() if x.type == o.type and x.fields.get(f) == v}
            hits = sorted({si for x in same for si in obj_segs.get(x, ())}, reverse=True)[:n_prec]
            if hits:
                for si in hits:
                    take(si, {x for x in same if si in obj_segs.get(x, ())})
            else:
                nb = _neighbours(S0, oid)
                hits = sorted({si for x in nb for si in obj_segs.get(x, ())}, reverse=True)[:n_prec]
                for si in hits:
                    take(si, {oid} | {x for x in nb if si in obj_segs.get(x, ())})
    order = {r["rid"]: i for i, r in enumerate(H)}
    return sorted(chosen, key=lambda r: order[r])


class KeySelect(Learner):
    """key_select{n}: objects along the learned skeleton, records by same-key precedent
    (no parser in the selection), runtime-history executor on those records only."""

    def __init__(self, n_prec: int = 1):
        self.n_prec = n_prec
        self.name = "key_select" if n_prec == 1 else f"key_select{n_prec}"

    def fit(self, domain, train):
        from .learners import LearnedGraph
        self.g = LearnedGraph()
        self.g.fit(domain, train)

    def select(self, domain, ep: Episode) -> dict:
        from .scaling import skeleton_reads
        objs = skeleton_reads(domain, self.g, ep)["objects"]
        recs = key_precedent_records(domain, ep, objs, self.n_prec)
        return {"objects": sorted(objs), "records": recs}

    def predict(self, domain, ep):
        reads = self.select(domain, ep)
        est = restricted_est(domain, ep.H, ep.S0, reads["records"])
        tr = FallbackTracker(est)
        post = ep.S0.copy()
        try:
            _rc, txns, tr = execute_intervention(domain, est, post, ep.I, tr)
        except Exception:
            txns = []
        return {"txns": txns, "reads": reads}
