"""Generic (domain-agnostic) feature extraction shared by the learners.

Every learner sees the same training data (H, S0, I, A, S1, R).  What differs
is which part of it a learner is built to exploit:
  * structural features: typed shortest path from the intervention source;
  * regime estimates: the history parser's output for the parameters that
    could govern an object (``param_keys_for``);
  * witness statistics: how often, in this episode's history, objects that
    share a key with the candidate changed when a neighbour changed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from .core import Episode, Obj, State, segments

POLICY_CODES = {"propagate": 0, "ignore": 1}


def path_types(state: State, source_id: str, max_hops: int = 5) -> Dict[str, Tuple]:
    """Typed shortest path from the source: ((rel, type), ...) per object."""
    rev: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for o in state.objects.values():
        for rel, targets in o.links.items():
            for t in targets:
                rev[t].append(("~" + rel, o.id))
    paths = {source_id: ()}
    frontier = [source_id]
    while frontier:
        nxt = []
        for oid in frontier:
            o = state.get(oid)
            edges = [(rel, t) for rel, ts in o.links.items() for t in ts] + rev.get(oid, [])
            for rel, t in edges:
                if t in state.objects and t not in paths and len(paths[oid]) < max_hops:
                    paths[t] = paths[oid] + ((rel, state.get(t).type),)
                    nxt.append(t)
        frontier = nxt
    return paths


def label_of(ep: Episode, oid: str) -> str:
    items = []
    for e in ep.R:
        if e["object_id"] == oid and e["kind"] == "auto":
            items.append(f"{e['op']}|auto|{','.join(sorted(e['delta'].keys()))}")
    for t in ep.A:
        if t["object_id"] == oid:
            items.append(f"{t['op']}|txn|{','.join(sorted(t['payload'].keys()))}")
    return ";".join(sorted(items)) if items else "none"


def parse_label(label: str) -> List[dict]:
    if label == "none":
        return []
    out = []
    for item in label.split(";"):
        op, kind, fields = item.split("|")
        out.append({"op": op, "kind": kind, "fields": [f for f in fields.split(",") if f]})
    return out


def source_new_fields(ep_or_state, I: dict) -> dict:
    state = ep_or_state.S0 if isinstance(ep_or_state, Episode) else ep_or_state
    src = state.get(I["object_id"])
    new = dict(src.fields)
    new.update({k: v for k, v in I["payload"].items() if not isinstance(v, (dict, list))})
    return new


def numeric_slots(domain) -> List[Tuple[str, str]]:
    return [(t, f) for t, fs in sorted(domain.numeric_fields().items()) for f in fs]


def numeric_vector(obj: Obj, slots, fields=None) -> List[float]:
    fields = fields if fields is not None else obj.fields
    out = []
    for t, f in slots:
        v = fields.get(f) if obj.type == t else None
        out.append(float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else
                   (float(v) if isinstance(v, bool) else 0.0))
    return out


def own_history(H: List[dict], oid: str) -> List[float]:
    n = n_auto = n_txn = n_int = 0
    for r in H:
        if r["object_id"] == oid:
            n += 1
            n_auto += r["kind"] == "auto"
            n_txn += r["kind"] == "txn"
            n_int += r["kind"] == "intervention"
    return [float(n), float(n_auto), float(n_txn), float(n_int)]


def global_history(H: List[dict], ops_vocab: List[str]) -> List[float]:
    c = Counter((r["kind"], r["op"]) for r in H)
    vec = [float(len(segments(H)))]
    for op in ops_vocab:
        for kind in ("intervention", "auto", "txn"):
            vec.append(float(c.get((kind, op), 0)))
    return vec


def param_names(domain) -> List[str]:
    # the parameter families a domain's history parser can produce
    names = getattr(domain, "PARAM_NAMES", None)
    if names:
        return sorted(names)
    probe = domain.infer_params([], _EMPTY_STATE)
    return sorted(probe.keys())


_EMPTY_STATE = State()


def est_vector(domain, est: dict, obj: Obj, state: State, names: List[str], per_name: int = 3) -> List[float]:
    keys = domain.param_keys_for(obj, state)
    vec = []
    for name in names:
        vals = [est.get(name, {}).get(k) for n, k in keys if n == name][:per_name]
        vals += [None] * (per_name - len(vals))
        for v in vals:
            if v is None:
                vec.append(-1.0)
            elif isinstance(v, str):
                vec.append(float(POLICY_CODES.get(v, 2)))
            else:
                vec.append(float(v))
    return vec


def shares_tokens(a: Obj, b_fields: dict, b_id: str) -> float:
    """Overlap between one object's field values and another's (lists and
    dict values included); captures 'uses the same name', 'same attribute'."""
    def toks(fields, oid):
        out = {oid}
        for v in fields.values():
            if isinstance(v, (str, int)) and not isinstance(v, bool):
                out.add(str(v))
            elif isinstance(v, list):
                out.update(str(x) for x in v)
            elif isinstance(v, dict):
                out.update(str(x) for x in v.values())
        return out
    return float(len(toks(a.fields, a.id) & toks(b_fields, b_id)))


def witness_vector(domain, H: List[dict], S0: State, obj: Obj) -> List[float]:
    """Firing statistics for objects sharing a key with ``obj``: for each
    relation and each key field (identity + categorical fields), how often a
    same-key object changed in a segment where one of its neighbours via that
    relation changed, and how often that change was automatic."""
    rels = domain.relation_names()
    cat = domain.categorical_fields().get(obj.type, [])[:2]
    keyfields = ["_id"] + cat + [None] * (2 - len(cat))
    segs = segments(H)
    changed_per_seg = [{r["object_id"]: r["kind"] for r in seg} for seg in segs]
    same_type = [o for o in S0.objects.values() if o.type == obj.type]
    vec = []
    for rel in rels:
        for kf in keyfields:
            if kf is None:
                vec += [0.0, -1.0, -1.0]
                continue
            group = [obj] if kf == "_id" else [o for o in same_type if o.fields.get(kf) == obj.fields.get(kf)]
            exposure = fired = auto = 0
            for x in group:
                nbrs = x.linked(rel)
                for ch in changed_per_seg:
                    if any(n in ch for n in nbrs):
                        exposure += 1
                        if x.id in ch:
                            fired += 1
                            auto += ch[x.id] == "auto"
            vec += [float(exposure), (fired / exposure) if exposure else -1.0,
                    (auto / fired) if fired else -1.0]
    return vec


DICT_KEYS = ["model", "mount", "series", "brand", "size"]


def dict_equalities(c: Obj, other_fields: dict) -> List[float]:
    """Key-wise equality between the object's dict-valued fields and another
    object's, over a fixed key vocabulary (1 equal, 0 different, -1 absent)."""
    mine, theirs = {}, {}
    for v in c.fields.values():
        if isinstance(v, dict):
            mine.update(v)
    for v in other_fields.values():
        if isinstance(v, dict):
            theirs.update(v)
    out = []
    for k in DICT_KEYS:
        if k in mine and k in theirs:
            out.append(1.0 if mine[k] == theirs[k] else 0.0)
        else:
            out.append(-1.0)
    return out


def _tokens(fields: dict, oid: str) -> set:
    out = {oid}
    for v in fields.values():
        if isinstance(v, (str, int)) and not isinstance(v, bool):
            out.add(str(v))
        elif isinstance(v, list):
            out.update(str(x) for x in v)
        elif isinstance(v, dict):
            out.update(str(x) for x in v.values())
    return out


def neighborhood_overlap(c: Obj, state: State, hops: int = 2) -> List[float]:
    """Token overlap between the object and its 1-hop / 2-hop neighbourhood in
    the current state: how many neighbours share >= 1 and >= 2 tokens, and the
    total overlap.  Lets a local learner see hyperedge conditions such as
    'a line of every required category with the promo's brand is present'."""
    mine = _tokens(c.fields, c.id)
    seen = {c.id}
    frontier = [c.id]
    out = []
    for _ in range(hops):
        nxt = []
        for oid in frontier:
            for targets in state.get(oid).links.values():
                for t in targets:
                    if t in state.objects and t not in seen:
                        seen.add(t)
                        nxt.append(t)
        ov = []
        for t in nxt:
            o = state.get(t)
            if o.status != "active":
                continue
            ov.append(len(mine & _tokens(o.fields, o.id)))
        out += [float(sum(1 for x in ov if x >= 1)), float(sum(1 for x in ov if x >= 2)), float(sum(ov)),
                float(len(ov))]
        frontier = nxt
    return out


def sibling_ranks(c: Obj, state: State, slots) -> List[float]:
    """For each numeric slot of the object's type: the fraction of active
    same-type siblings (objects sharing a neighbour) with a strictly larger
    value, and with a strictly smaller value.  Encodes 'the priciest optional
    line', 'the newest document in the cluster' and similar orderings."""
    sibs = set()
    for targets in c.links.values():
        for t in targets:
            if t in state.objects:
                for back in state.get(t).links.values():
                    sibs.update(x for x in back if x in state.objects)
    sibs = [state.get(x) for x in sibs if x != c.id and state.get(x).type == c.type and state.get(x).status == "active"]
    out = []
    for t, f in slots:
        if t != c.type or not isinstance(c.fields.get(f), (int, float)) or isinstance(c.fields.get(f), bool):
            out += [-1.0, -1.0]
            continue
        v = c.fields[f]
        vals = [s.fields.get(f) for s in sibs if isinstance(s.fields.get(f), (int, float))]
        if not vals:
            out += [0.0, 0.0]
            continue
        out += [sum(1 for x in vals if x > v) / len(vals), sum(1 for x in vals if x < v) / len(vals)]
    return out


def est_linked_vector(domain, est: dict, c: Obj, state: State, names: List[str], parent: Obj) -> List[float]:
    """Regime estimates for the child's parameter keys that mention the parent
    (its id or one of its field tokens): 'is this lemma sensitive to the
    definition that just changed', 'is this dependent statement-sensitive to
    the parent lemma'.  One value per parameter family (-1 if no such key)."""
    ptoks = _tokens(parent.fields, parent.id)
    keys = domain.param_keys_for(c, state)
    out = []
    for name in names:
        val = None
        for n, k in keys:
            if n != name:
                continue
            ktoks = set(str(k).replace("|", " ").split())
            if ktoks & ptoks and str(k) != c.id:
                v = est.get(name, {}).get(k)
                if v is not None:
                    val = v
                    break
        if val is None:
            out.append(-1.0)
        elif isinstance(val, str):
            out.append(float(POLICY_CODES.get(val, 2)))
        else:
            out.append(float(val))
    return out
