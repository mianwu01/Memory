"""Shared engine for the Hidden Mechanism v3 benchmark.

Semantics that every domain inherits
  * every object carries a revision counter; a transaction must quote the
    object's current revision (``expected_revision``) or it is illegal;
  * every manual transaction is non-idempotent: it bumps the revision,
    consumes one change token, charges the op's fee and drops the price
    lock, even if the payload rewrites the existing value;
  * environment-side automatic effects ("auto") also bump the revision but
    charge nothing and consume no token;
  * the receipt is the ordered ledger of intervention + auto + txn entries.

Executable Exact Success (EES) := every transaction legal AND post-state equal
to the oracle post-state AND receipt multiset equal to the oracle receipt.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple


def ceil15(x: float) -> int:
    return int(math.ceil(x / 15.0) * 15)


def hhmm(minutes: int) -> str:
    minutes = int(minutes)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class Illegal(Exception):
    """Raised when a transaction cannot be executed."""


class Obj:
    __slots__ = ("id", "type", "fields", "links", "revision", "locked", "status")

    def __init__(self, id: str, type: str, fields: Optional[dict] = None,
                 links: Optional[dict] = None):
        self.id = id
        self.type = type
        self.fields = dict(fields or {})
        self.links = {k: list(v) for k, v in (links or {}).items()}
        self.revision = 0
        self.locked = True
        self.status = "active"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "fields": copy.deepcopy(self.fields),
            "links": {k: list(v) for k, v in self.links.items()},
            "revision": self.revision, "locked": self.locked, "status": self.status,
        }

    @staticmethod
    def from_dict(d: dict) -> "Obj":
        o = Obj(d["id"], d["type"], d["fields"], d["links"])
        o.revision = d["revision"]
        o.locked = d["locked"]
        o.status = d["status"]
        return o

    def linked(self, rel: str) -> List[str]:
        return list(self.links.get(rel, []))


class State:
    def __init__(self, objects: Iterable[Obj] = (), meta: Optional[dict] = None,
                 tokens: int = 20):
        self.objects: Dict[str, Obj] = {o.id: o for o in objects}
        self.meta: dict = dict(meta or {})
        self.tokens = tokens
        self.fees = 0

    def copy(self) -> "State":
        s = State([], copy.deepcopy(self.meta), self.tokens)
        s.objects = {k: Obj.from_dict(v.to_dict()) for k, v in self.objects.items()}
        s.fees = self.fees
        return s

    def get(self, oid: str) -> Obj:
        if oid not in self.objects:
            raise Illegal(f"unknown object {oid}")
        return self.objects[oid]

    def add(self, obj: Obj) -> None:
        self.objects[obj.id] = obj

    def by_type(self, t: str) -> List[Obj]:
        return [o for o in self.objects.values() if o.type == t]

    def to_dict(self) -> dict:
        return {
            "objects": {k: v.to_dict() for k, v in sorted(self.objects.items())},
            "meta": copy.deepcopy(self.meta), "tokens": self.tokens, "fees": self.fees,
        }

    @staticmethod
    def from_dict(d: dict) -> "State":
        s = State([], d["meta"], d["tokens"])
        s.objects = {k: Obj.from_dict(v) for k, v in d["objects"].items()}
        s.fees = d["fees"]
        return s

    def canonical(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)

    def signature(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()[:16]


# ---------------------------------------------------------------- transactions

def txn(op: str, object_id: str, expected_revision: int, payload: Optional[dict] = None) -> dict:
    return {"op": op, "object_id": object_id, "expected_revision": int(expected_revision),
            "payload": dict(payload or {})}


def canonical_txn(t: dict) -> Tuple:
    return (t["op"], t["object_id"], int(t["expected_revision"]),
            json.dumps(t.get("payload", {}), sort_keys=True, default=str))


def canonical_receipt(entries: List[dict]) -> List[Tuple]:
    return sorted(
        (e["kind"], e["op"], e["object_id"], int(e["rev"]), int(e["fee"]), int(e["token"]))
        for e in entries
    )


@dataclass
class Effect:
    """A propagation result before it is turned into a receipt entry."""
    kind: str            # "auto" | "txn"
    op: str
    object_id: str
    payload: dict = field(default_factory=dict)


class Domain:
    """Interface every DGP implements.  Subclasses set NAME, OPS (fee table),
    and implement sample_world, sample_intervention, propagate, apply_payload,
    infer_params, nl_query.  ``propagate`` is the single hidden mechanism: it
    returns the ordered auto effects and manual repair transactions implied
    by an intervention, consulting hidden params through ``Tracker``."""

    NAME = "base"
    OPS: Dict[str, int] = {}
    INTERVENTION_FEE = 0

    # ----- generation hooks
    def sample_world(self, rng, cfg: dict):
        raise NotImplementedError

    def sample_intervention(self, rng, params: dict, state: State, avoid: Optional[set] = None,
                            target_param: Optional[str] = None):
        raise NotImplementedError

    def propagate(self, params: dict, state: State, I: dict, tracker: "Tracker") -> List[Effect]:
        raise NotImplementedError

    def apply_intervention_payload(self, state: State, I: dict) -> dict:
        """Apply the intervention's own write to the state; return delta."""
        return self.apply_payload(state, state.get(I["object_id"]), I["op"], I["payload"])

    def apply_payload(self, state: State, obj: Obj, op: str, payload: dict) -> dict:
        raise NotImplementedError

    def infer_params(self, H: List[dict], S0: State, prov: Optional[dict] = None) -> dict:
        raise NotImplementedError

    def refresh_intervention(self, I: dict, state: State) -> dict:
        """Re-derive payload values that depend on the current state (default: identity)."""
        return I

    def local_payload(self, scratch: State, obj: Obj, op: str, fields, tr: "Tracker") -> dict:
        raise NotImplementedError

    def param_keys_for(self, obj: Obj, state: State) -> List[tuple]:
        """Which regime parameters (name, key) could govern effects on this object."""
        return []

    def idempotent_write(self, obj: Obj):
        """(op, payload) that legally rewrites the object's current value, or None."""
        return None

    def execution_order(self, scratch: State, items: List[dict]) -> List[dict]:
        """Default: by hop distance from the source, auto before txn, then id."""
        return sorted(items, key=lambda it: (it.get("hops", 0), it["kind"] != "auto", it["object_id"]))

    def nl_query(self, I: dict, state: State) -> str:
        raise NotImplementedError

    def param_key(self, name: str, key: Any) -> str:
        return f"{name}[{key}]"

    # ----- optional hooks used by learners
    def relation_names(self) -> List[str]:
        return []

    def categorical_fields(self) -> Dict[str, List[str]]:
        return {}

    def numeric_fields(self) -> Dict[str, List[str]]:
        return {}


class Tracker:
    """Records which hidden params and which state objects the oracle consulted."""

    def __init__(self, params: Optional[dict] = None):
        self.params = params or {}
        self.consulted: List[str] = []
        self.read_objects: List[str] = []

    def get(self, name: str, key: Any):
        pk = f"{name}[{key}]"
        if pk not in self.consulted:
            self.consulted.append(pk)
        return self.params[name][key]

    def read(self, *oids: str) -> None:
        for oid in oids:
            if oid not in self.read_objects:
                self.read_objects.append(oid)


# ----------------------------------------------------------------- execution

def execute_intervention(domain: Domain, params: dict, state: State, I: dict,
                         tracker: Optional[Tracker] = None) -> Tuple[List[dict], List[dict], Tracker]:
    """Mutates ``state``: applies the intervention write and every auto effect.
    Returns (receipt entries, manual transactions with expected revisions, tracker)."""
    tracker = tracker or Tracker(params)
    effects = domain.propagate(params, state, I, tracker)
    receipt: List[dict] = []
    obj = state.get(I["object_id"])
    delta = domain.apply_intervention_payload(state, I)
    obj.revision += 1
    receipt.append({"kind": "intervention", "op": I["op"], "object_id": obj.id,
                    "rev": obj.revision, "fee": domain.INTERVENTION_FEE, "token": 0,
                    "delta": delta})
    manual: List[Effect] = []
    for eff in effects:
        if eff.kind == "auto":
            o = state.get(eff.object_id)
            d = domain.apply_payload(state, o, eff.op, eff.payload)
            o.revision += 1
            receipt.append({"kind": "auto", "op": eff.op, "object_id": o.id,
                            "rev": o.revision, "fee": 0, "token": 0, "delta": d})
        else:
            manual.append(eff)
    txns = []
    seen = set()
    for eff in manual:
        if eff.object_id in seen:
            raise RuntimeError(f"domain {domain.NAME} emitted two manual txns on {eff.object_id}")
        seen.add(eff.object_id)
        txns.append(txn(eff.op, eff.object_id, state.get(eff.object_id).revision, eff.payload))
    return receipt, txns, tracker


def execute_transactions(domain: Domain, state: State, txns: List[dict]) -> List[dict]:
    """Mutates ``state``.  Raises Illegal on the first illegal transaction."""
    receipt = []
    for t in txns:
        if t["op"] not in domain.OPS:
            raise Illegal(f"unknown op {t['op']}")
        obj = state.get(t["object_id"])
        if int(t["expected_revision"]) != obj.revision:
            raise Illegal(f"stale revision on {obj.id}: expected {t['expected_revision']} actual {obj.revision}")
        if state.tokens <= 0:
            raise Illegal("no change tokens left")
        delta = domain.apply_payload(state, obj, t["op"], t.get("payload", {}))
        obj.revision += 1
        obj.locked = False
        state.tokens -= 1
        fee = domain.OPS[t["op"]]
        state.fees += fee
        receipt.append({"kind": "txn", "op": t["op"], "object_id": obj.id, "rev": obj.revision,
                        "fee": fee, "token": 1, "delta": delta})
    return receipt


# ------------------------------------------------------------------ episodes

@dataclass
class Episode:
    id: str
    domain: str
    seed: int
    split: str
    params: dict
    H: List[dict]
    S0: State
    I: dict
    query: str
    A: List[dict]
    S1: State
    R: List[dict]
    required_reads: dict
    affected: List[str]
    auto_affected: List[str]
    relevant_params: List[str]
    topology_hash: str
    n_prior_segments: int

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["S0"] = self.S0.to_dict()
        d["S1"] = self.S1.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> "Episode":
        d = dict(d)
        d["S0"] = State.from_dict(d["S0"])
        d["S1"] = State.from_dict(d["S1"])
        return Episode(**d)

    def test_view(self) -> dict:
        """What a test method is allowed to see."""
        return {"H": self.H, "S0": self.S0, "I": self.I, "query": self.query}


def topology_hash(state: State, params: dict) -> str:
    skeleton = sorted((o.type, tuple(sorted((r, len(v)) for r, v in o.links.items())))
                      for o in state.objects.values())
    blob = json.dumps([skeleton, params], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ------------------------------------------------------------------- scoring

def score_plan(domain: Domain, ep: Episode, plan: List[dict], reads: Optional[dict] = None) -> dict:
    """Execute ``plan`` on the post-intervention state and compare with the oracle."""
    state = ep.S0.copy()
    params = ep.params
    receipt, _oracle_txns, _ = execute_intervention(domain, params, state, ep.I)
    legal = True
    error = None
    try:
        receipt += execute_transactions(domain, state, plan)
    except Illegal as exc:
        legal = False
        error = str(exc)
    post_ok = legal and state.canonical() == ep.S1.canonical()
    receipt_ok = legal and canonical_receipt(receipt) == canonical_receipt(ep.R)
    ees = bool(legal and post_ok and receipt_ok)

    oracle_set = {canonical_txn(t) for t in ep.A}
    plan_set = {canonical_txn(t) for t in plan}
    oracle_objs = {t["object_id"] for t in ep.A}
    plan_objs = [t["object_id"] for t in plan]
    plan_obj_set = set(plan_objs)
    tp = len(oracle_objs & plan_obj_set)
    prec = tp / len(plan_obj_set) if plan_obj_set else (1.0 if not oracle_objs else 0.0)
    rec = tp / len(oracle_objs) if oracle_objs else 1.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    collateral = sum(1 for o in plan_objs if o not in oracle_objs)
    duplicates = len(plan_objs) - len(plan_obj_set)
    # value accuracy on affected objects the plan touched
    oracle_by_obj = {t["object_id"]: t for t in ep.A}
    val_hits = 0
    val_total = 0
    for t in plan:
        if t["object_id"] in oracle_by_obj:
            val_total += 1
            o = oracle_by_obj[t["object_id"]]
            if o["op"] == t["op"] and json.dumps(o["payload"], sort_keys=True, default=str) == \
                    json.dumps(t.get("payload", {}), sort_keys=True, default=str):
                val_hits += 1
    value_acc = val_hits / val_total if val_total else (1.0 if not oracle_objs else 0.0)
    # required-read recall
    req_objs = set(ep.required_reads.get("objects", []))
    req_recs = set(ep.required_reads.get("records", []))
    reads = reads or {"objects": [], "records": []}
    r_objs = set(reads.get("objects", []))
    r_recs = set(reads.get("records", []))
    req_total = len(req_objs) + len(req_recs)
    read_recall = ((len(req_objs & r_objs) + len(req_recs & r_recs)) / req_total) if req_total else 1.0
    # utility / regret: fees + tokens spent relative to the oracle
    oracle_cost = sum(e["fee"] + 5 * e["token"] for e in ep.R)
    plan_cost = sum(e["fee"] + 5 * e["token"] for e in receipt) if legal else None
    regret = (plan_cost - oracle_cost) if legal else None
    return {
        "legal": legal, "ees": ees, "post_state_ok": post_ok, "receipt_ok": receipt_ok,
        "exact_action_set": plan_set == oracle_set, "affected_precision": prec,
        "affected_recall": rec, "affected_f1": f1, "collateral_txns": collateral,
        "duplicate_txns": duplicates, "value_accuracy": value_acc,
        "required_read_recall": read_recall, "n_reads": len(r_objs) + len(r_recs),
        "regret": regret, "n_plan": len(plan), "n_oracle": len(ep.A), "error": error,
    }


def segments(H: List[dict]) -> List[List[dict]]:
    """Split the flat history log into intervention-anchored segments."""
    out: List[List[dict]] = []
    for rec in H:
        if rec["kind"] == "intervention":
            out.append([rec])
        elif out:
            out[-1].append(rec)
        else:
            out.append([rec])
    return out


def timeline(S0: State, H: List[dict]) -> List[State]:
    """Reconstruct the state before each history segment by reverse-applying
    deltas from S0.  Returns snaps[k] = state before segment k for k in
    0..n_segments, with snaps[n_segments] = S0."""
    segs = segments(H)
    snaps: List[State] = [None] * (len(segs) + 1)  # type: ignore
    cur = S0.copy()
    snaps[len(segs)] = cur.copy()
    for k in range(len(segs) - 1, -1, -1):
        for rec in reversed(segs[k]):
            oid = rec["object_id"]
            if oid not in cur.objects:
                continue
            obj = cur.objects[oid]
            for fld, (old, _new) in (rec.get("delta") or {}).items():
                if fld == "status":
                    obj.status = old
                else:
                    obj.fields[fld] = old
            obj.revision = rec["rev"] - 1
        snaps[k] = cur.copy()
    return snaps


class FallbackTracker(Tracker):
    """Parameter access for learners: values come from what was parsed out of
    the history records the method actually read; unknown parameters fall
    back to a fixed default and are recorded as ``unknown``."""

    DEFAULTS = {"policy": "propagate"}

    def __init__(self, est: dict):
        super().__init__(est)
        self.unknown: List[str] = []

    def get(self, name: str, key: Any):
        pk = f"{name}[{key}]"
        if pk not in self.consulted:
            self.consulted.append(pk)
        try:
            return self.params[name][key]
        except KeyError:
            if pk not in self.unknown:
                self.unknown.append(pk)
            return self.DEFAULTS.get(name, 0)


def hop_distances(state: State, source: str, max_hops: int = 6) -> Dict[str, int]:
    dist = {source: 0}
    frontier = [source]
    while frontier:
        nxt = []
        for oid in frontier:
            for rel, targets in state.get(oid).links.items():
                for t in targets:
                    if t in state.objects and t not in dist:
                        dist[t] = dist[oid] + 1
                        nxt.append(t)
        frontier = nxt
    return dist


def plan_to_txns(domain: Domain, S0: State, I: dict, plan: List[dict], est: dict) -> Tuple[List[dict], dict]:
    """Turn a structural plan [{object_id, op, kind, fields}] into executable
    transactions.  Values are computed by the domain's local rules on a scratch
    copy that reflects the intervention and every planned effect executed so
    far, so a wrong or missing upstream decision corrupts downstream values."""
    scratch = S0.copy()
    src = scratch.get(I["object_id"])
    domain.apply_intervention_payload(scratch, I)
    src.revision += 1
    tr = FallbackTracker(est)
    dist = hop_distances(scratch, I["object_id"])
    items = []
    for it in plan:
        it = dict(it)
        it["hops"] = dist.get(it["object_id"], 99)
        items.append(it)
    txns: List[dict] = []
    info = {"unknown_params": [], "errors": []}
    for it in domain.execution_order(scratch, items):
        try:
            obj = scratch.get(it["object_id"])
            payload = domain.local_payload(scratch, obj, it["op"], it.get("fields"), tr)
            if it["kind"] == "auto":
                domain.apply_payload(scratch, obj, it["op"], payload)
                obj.revision += 1
            else:
                txns.append(txn(it["op"], obj.id, obj.revision, payload))
                domain.apply_payload(scratch, obj, it["op"], payload)
                obj.revision += 1
        except Illegal as exc:
            info["errors"].append(f"{it['object_id']}/{it['op']}: {exc}")
            if it["kind"] != "auto":
                # keep the write so that the structural mistake is visible in the ledger
                txns.append(txn(it["op"], it["object_id"], scratch.get(it["object_id"]).revision
                                if it["object_id"] in scratch.objects else 0, {}))
    info["unknown_params"] = list(tr.unknown)
    return txns, info


def restricted_est(domain: Domain, H: List[dict], S0: State, record_ids) -> dict:
    """Regime parameters recoverable from the history records that were read."""
    keep = set(record_ids)
    sub = [r for r in H if r["rid"] in keep]
    return domain.infer_params(sub, S0)
