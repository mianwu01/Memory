"""Search v3: non-monotone evidence aggregation under trust / window / dedup gates.

Objects: documents (class, cluster, stance, timestamp) attached to base claims;
composite claims combine children with AND / OR.  Visible policy: now, window,
margin.  Hidden (per episode):
  trust[class]    weight 0/1/2 of a source class (0 = ignored)
  dedup[global]   within a cluster only the newest in-window document counts
  policy[global]  how unresolved children enter a composite ("propagate" | "ignore")
  auto_base[global] base-claim verdicts are maintained by the environment (auto) or by the agent (txn)
A publication is non-monotone: a newer document silences an older one in its
cluster under dedup; a retraction can un-silence one.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from .core import Domain, Effect, Illegal, Obj, State, Tracker, segments, timeline

CLASSES = ["wire", "gov", "blog", "forum", "paper", "wiki"]
VERDICTS = ("supported", "refuted", "unresolved")


class SearchDomain(Domain):
    NAME = "search"
    PARAM_NAMES = ["trust", "dedup", "policy", "auto_base"]
    OPS = {"set_verdict": 20}

    def relation_names(self):
        return ["claims", "docs", "children", "parents"]

    def categorical_fields(self):
        return {"doc": ["cls", "cluster"], "claim": ["kind", "combinator"]}

    def numeric_fields(self):
        return {"doc": ["ts", "stance"], "claim": []}

    # ------------------------------------------------------------ world
    def sample_world(self, rng: random.Random, cfg: dict):
        used = set()

        def fresh(prefix):
            while True:
                cand = f"{prefix}{rng.randint(10, 99)}"
                if cand not in used:
                    used.add(cand)
                    return cand

        classes = rng.sample(CLASSES, 4)
        trust = {c: rng.choice([0, 1, 2]) for c in classes}
        if all(v == 0 for v in trust.values()):
            trust[classes[0]] = 1
        params = {"trust": trust, "dedup": {"global": int(rng.random() < 0.5)},
                  "policy": {"global": rng.choice(["propagate", "ignore"])},
                  "auto_base": {"global": int(rng.random() < 0.5)}}
        now = 1000
        state = State(meta={"now": now, "window": rng.choice([30, 60, 90]),
                            "margin": rng.choice([1, 2]), "classes": classes},
                      tokens=cfg.get("tokens", 80))
        n_base = rng.choice([4, 5, 6])
        base_ids = [fresh("C") for _ in range(n_base)]
        for cid in base_ids:
            state.add(Obj(cid, "claim", {"kind": "base", "combinator": "", "verdict": "unresolved"},
                          {"docs": [], "parents": [], "children": []}))
            clusters = [fresh("K") for _ in range(rng.choice([2, 3]))]
            used_ts = set()
            for _ in range(rng.choice([1, 2, 3])):
                ts = rng.choice(range(now - 120, now - 1))
                while ts in used_ts:
                    ts = rng.choice(range(now - 120, now - 1))
                used_ts.add(ts)
                did = fresh("D")
                state.add(Obj(did, "doc", {"cls": rng.choice(classes), "cluster": rng.choice(clusters),
                                           "stance": rng.choice([1, -1]), "ts": ts,
                                           "counted": None, "weight": None, "reason": ""},
                              {"claims": [cid]}))
                state.get(cid).links["docs"].append(did)
            # pending arrivals
            for _ in range(rng.choice([0, 1, 1, 2])):
                ts = rng.choice(range(now - 100, now + 1))
                while ts in used_ts:
                    ts = rng.choice(range(now - 100, now + 1))
                used_ts.add(ts)
                did = fresh("D")
                d = Obj(did, "doc", {"cls": rng.choice(classes), "cluster": rng.choice(clusters),
                                     "stance": rng.choice([1, -1]), "ts": ts,
                                     "counted": None, "weight": None, "reason": ""},
                        {"claims": [cid]})
                d.status = "pending"
                state.add(d)
                state.get(cid).links["docs"].append(did)
        comp_ids = []
        for level in range(2):
            for _ in range(rng.choice([1, 2])):
                pool = base_ids + (comp_ids if level == 1 else [])
                kids = rng.sample(pool, min(len(pool), rng.choice([2, 3])))
                cid = fresh("C")
                state.add(Obj(cid, "claim", {"kind": "composite", "combinator": rng.choice(["AND", "OR"]),
                                             "verdict": "unresolved"},
                              {"docs": [], "children": kids, "parents": []}))
                for k in kids:
                    state.get(k).links["parents"].append(cid)
                comp_ids.append(cid)
        # consistent initial verdicts
        tr = Tracker(params)
        for cid in base_ids:
            state.get(cid).fields["verdict"] = self._base_verdict(params, state, cid, tr)
        for cid in comp_ids:
            state.get(cid).fields["verdict"] = self._composite_verdict(params, state, cid, tr)
        return params, state

    # ------------------------------------------------------ aggregation
    def _counted_docs(self, params, state: State, cid: str, tr: Tracker):
        claim = state.get(cid)
        now, window = state.meta["now"], state.meta["window"]
        active = [state.get(d) for d in claim.linked("docs") if state.get(d).status == "active"]
        in_window = [d for d in active if d.fields["ts"] >= now - window]
        by_cluster: Dict[str, list] = {}
        for d in in_window:
            by_cluster.setdefault(d.fields["cluster"], []).append(d)
        counted = []
        for cluster, docs in by_cluster.items():
            if len(docs) >= 2 and tr.get("dedup", "global"):
                docs = [max(docs, key=lambda d: d.fields["ts"])]
            counted.extend(docs)
        return counted

    def _base_verdict(self, params, state: State, cid: str, tr: Tracker) -> str:
        score = 0
        for d in self._counted_docs(params, state, cid, tr):
            tr.read(d.id)
            score += d.fields["stance"] * tr.get("trust", d.fields["cls"])
        m = state.meta["margin"]
        return "supported" if score >= m else ("refuted" if score <= -m else "unresolved")

    def _composite_verdict(self, params, state: State, cid: str, tr: Tracker) -> str:
        claim = state.get(cid)
        kids = [state.get(k).fields["verdict"] for k in claim.linked("children")]
        tr.read(*claim.linked("children"))
        comb = claim.fields["combinator"]
        if comb == "AND":
            if "refuted" in kids:
                return "refuted"
            if all(k == "supported" for k in kids):
                return "supported"
            if tr.get("policy", "global") == "propagate":
                return "unresolved"
            return "supported" if "supported" in kids else "unresolved"
        if "supported" in kids:
            return "supported"
        if all(k == "refuted" for k in kids):
            return "refuted"
        if tr.get("policy", "global") == "propagate":
            return "unresolved"
        return "refuted" if "refuted" in kids else "unresolved"

    # ------------------------------------------------------ interventions
    def sample_intervention(self, rng, params, state, avoid=None, target_param=None):
        avoid = avoid or set()
        pending = [d for d in state.by_type("doc") if d.status == "pending" and d.id not in avoid]
        active = [d for d in state.by_type("doc") if d.status == "active" and d.id not in avoid]
        if target_param is not None:
            name, key = target_param.split("[")
            key = key.rstrip("]")
            if name == "trust":
                cands = [d for d in pending if d.fields["cls"] == key]
                if not cands:
                    return self._new_pending(rng, state, cls=key)
                return {"op": "publish_document", "object_id": rng.choice(cands).id, "payload": {}}
            if name == "dedup":
                return self._new_pending(rng, state, occupied=True)
            if name == "auto_base":
                return self._new_pending(rng, state, decisive=True)
            if name == "policy":
                return self._new_pending(rng, state, under_composite=True)
        if pending and (rng.random() < 0.75 or not active):
            return {"op": "publish_document", "object_id": rng.choice(pending).id, "payload": {}}
        if active:
            return {"op": "retract_document", "object_id": rng.choice(active).id, "payload": {}}
        return self._new_pending(rng, state)

    def _new_pending(self, rng, state: State, cls=None, occupied=False, decisive=False,
                     under_composite=False):
        """Queue a fresh arrival (it becomes part of the visible pending queue)
        and return the intervention that publishes it."""
        bases = [c for c in state.by_type("claim") if c.fields["kind"] == "base"]
        if under_composite:
            bases = [c for c in bases if c.linked("parents")] or bases
        claim = rng.choice(bases)
        docs = [state.get(d) for d in claim.linked("docs")]
        clusters = sorted({d.fields["cluster"] for d in docs}) or [f"K{rng.randint(10, 99)}"]
        if occupied:
            act = [d.fields["cluster"] for d in docs if d.status == "active"]
            clusters = sorted(set(act)) or clusters
        used_ts = {d.fields["ts"] for d in docs}
        ts = state.meta["now"]
        while ts in used_ts:
            ts -= 1
        used = set(state.objects)
        did = f"D{rng.randint(10, 99)}"
        while did in used:
            did = f"D{rng.randint(10, 99)}"
        stance = rng.choice([1, -1])
        if decisive:
            stance = -1 if claim.fields["verdict"] == "supported" else 1
        d = Obj(did, "doc", {"cls": cls or rng.choice(state.meta["classes"]),
                             "cluster": rng.choice(clusters), "stance": stance, "ts": ts,
                             "counted": None, "weight": None, "reason": ""},
                {"claims": [claim.id]})
        d.status = "pending"
        state.add(d)
        claim.links["docs"].append(did)
        return {"op": "publish_document", "object_id": did, "payload": {}}

    def nl_query(self, I: dict, state: State) -> str:
        if I["op"] == "publish_document":
            return f"Document {I['object_id']} is now published."
        return f"Document {I['object_id']} has been retracted."

    # ---------------------------------------------------------- mechanism
    def propagate(self, params, state: State, I: dict, tr: Tracker) -> List[Effect]:
        effects: List[Effect] = []
        scratch = state.copy()
        doc = scratch.get(I["object_id"])
        tr.read(doc.id)
        if I["op"] == "publish_document":
            if doc.status != "pending":
                raise Illegal("only pending documents can be published")
            doc.status = "active"
            now, window = scratch.meta["now"], scratch.meta["window"]
            cls = doc.fields["cls"]
            w = tr.get("trust", cls)
            if w == 0:
                eff = {"counted": 0, "weight": 0, "reason": "untrusted"}
            elif doc.fields["ts"] < now - window:
                eff = {"counted": 0, "weight": 0, "reason": "expired"}
            else:
                others = [scratch.get(x) for c in doc.linked("claims")
                          for x in scratch.get(c).linked("docs")]
                same_cluster = [o for o in others if o.id != doc.id and o.status == "active"
                                and o.fields["cluster"] == doc.fields["cluster"]
                                and o.fields["ts"] >= now - window]
                if same_cluster and tr.get("dedup", "global"):
                    newest = max(same_cluster, key=lambda o: o.fields["ts"])
                    if newest.fields["ts"] > doc.fields["ts"]:
                        eff = {"counted": 0, "weight": 0, "reason": "deduped"}
                    else:
                        eff = {"counted": 1, "weight": w, "reason": "counted"}
                else:
                    eff = {"counted": 1, "weight": w, "reason": "counted"}
            effects.append(Effect("auto", "evidence_effect", doc.id, eff))
            for k, v in eff.items():
                doc.fields[k] = v
        elif I["op"] == "retract_document":
            if doc.status != "active":
                raise Illegal("only active documents can be retracted")
            doc.status = "retracted"
        else:
            raise Illegal("unsupported intervention")
        changed = []
        for cid in doc.linked("claims"):
            claim = scratch.get(cid)
            tr.read(cid)
            new = self._base_verdict(params, scratch, cid, tr)
            if new != claim.fields["verdict"]:
                claim.fields["verdict"] = new
                kind = "auto" if tr.get("auto_base", "global") else "txn"
                effects.append(Effect(kind, "set_verdict", cid, {"verdict": new}))
                changed.append(cid)
        frontier = list(changed)
        done = set()
        while frontier:
            cid = frontier.pop(0)
            for pid in scratch.get(cid).linked("parents"):
                if pid in done:
                    continue
                done.add(pid)
                parent = scratch.get(pid)
                tr.read(pid)
                new = self._composite_verdict(params, scratch, pid, tr)
                if new != parent.fields["verdict"]:
                    parent.fields["verdict"] = new
                    effects.append(Effect("txn", "set_verdict", pid, {"verdict": new}))
                    frontier.append(pid)
        return effects

    def apply_payload(self, state: State, obj: Obj, op: str, payload: dict) -> dict:
        delta = {}
        if op == "publish_document":
            if obj.type != "doc" or obj.status != "pending":
                raise Illegal("publish needs a pending document")
            delta["status"] = [obj.status, "active"]
            obj.status = "active"
        elif op == "retract_document":
            if obj.type != "doc" or obj.status != "active":
                raise Illegal("retract needs an active document")
            delta["status"] = [obj.status, "retracted"]
            obj.status = "retracted"
        elif op == "evidence_effect":
            for k in ("counted", "weight", "reason"):
                delta[k] = [obj.fields[k], payload[k]]
                obj.fields[k] = payload[k]
        elif op == "set_verdict":
            if obj.type != "claim":
                raise Illegal("set_verdict needs a claim")
            v = payload.get("verdict")
            if set(payload) != {"verdict"} or v not in VERDICTS:
                raise Illegal(f"bad verdict payload {payload}")
            delta["verdict"] = [obj.fields["verdict"], v]
            obj.fields["verdict"] = v
        else:
            raise Illegal(f"unknown op {op}")
        return delta

    # ------------------------------------------ runtime-history oracle
    def infer_params(self, H: List[dict], S0: State, prov: Optional[dict] = None) -> dict:
        est: Dict[str, dict] = {"trust": {}, "dedup": {}, "policy": {}, "auto_base": {}}
        prov = prov if prov is not None else {}

        def note(name, key, *rids):
            prov[f"{name}[{key}]"] = sorted(set(rids))

        segs = segments(H)
        snaps = timeline(S0, H)
        now, window = S0.meta["now"], S0.meta["window"]
        for k, seg in enumerate(segs):
            before = snaps[k]
            after = snaps[k + 1]
            for rec in seg:
                oid = rec["object_id"]
                if oid not in S0.objects:
                    continue
                obj = S0.get(oid)
                if rec["kind"] == "auto" and rec["op"] == "evidence_effect":
                    eff = rec["payload"]
                    cls = obj.fields["cls"]
                    if eff["reason"] == "untrusted":
                        est["trust"][cls] = 0
                        note("trust", cls, seg[0]["rid"], rec["rid"])
                    elif eff["reason"] == "counted":
                        est["trust"][cls] = eff["weight"]
                        note("trust", cls, seg[0]["rid"], rec["rid"])
                    if eff["reason"] == "deduped":
                        est["dedup"]["global"] = 1
                        note("dedup", "global", seg[0]["rid"], rec["rid"])
                    elif eff["reason"] == "counted":
                        # was the cluster already occupied by an older in-window active doc?
                        occupied = False
                        for c in obj.linked("claims"):
                            for x in S0.get(c).linked("docs"):
                                if x == oid or x not in before.objects:
                                    continue
                                o = before.get(x)
                                if o.status == "active" and o.fields["cluster"] == obj.fields["cluster"] \
                                        and o.fields["ts"] >= now - window:
                                    occupied = True
                        if occupied:
                            est["dedup"]["global"] = 0
                            note("dedup", "global", seg[0]["rid"], rec["rid"])
                if rec["op"] == "set_verdict" and obj.fields["kind"] == "base":
                    est["auto_base"]["global"] = int(rec["kind"] == "auto")
                    note("auto_base", "global", seg[0]["rid"], rec["rid"])
                if rec["op"] == "set_verdict" and obj.fields["kind"] == "composite":
                    kids = [after.get(c).fields["verdict"] for c in obj.linked("children")]
                    pol = self._policy_from(obj.fields["combinator"], kids, rec["delta"]["verdict"][1])
                    if pol:
                        est["policy"]["global"] = pol
                        note("policy", "global", seg[0]["rid"], rec["rid"])
        # the current state is itself consistent with the hidden policy
        if "global" not in est["policy"]:
            for c in S0.by_type("claim"):
                if c.fields["kind"] != "composite":
                    continue
                kids = [S0.get(x).fields["verdict"] for x in c.linked("children")]
                pol = self._policy_from(c.fields["combinator"], kids, c.fields["verdict"])
                if pol:
                    est["policy"]["global"] = pol
                    prov.setdefault("policy[global]", [])
                    break
        return est

    @staticmethod
    def _policy_from(comb: str, kids: List[str], verdict: str) -> Optional[str]:
        if comb == "AND":
            if "refuted" in kids or all(k == "supported" for k in kids) or "supported" not in kids:
                return None
            return "ignore" if verdict == "supported" else "propagate"
        if "supported" in kids or all(k == "refuted" for k in kids) or "refuted" not in kids:
            return None
        return "ignore" if verdict == "refuted" else "propagate"

    # ------------------------------------------------ executor local rules
    def local_payload(self, scratch: State, obj: Obj, op: str, fields, tr: Tracker) -> dict:
        if op == "evidence_effect":
            # the store's own bookkeeping on the published document
            now, window = scratch.meta["now"], scratch.meta["window"]
            w = tr.get("trust", obj.fields["cls"])
            if w == 0:
                return {"counted": 0, "weight": 0, "reason": "untrusted"}
            if obj.fields["ts"] < now - window:
                return {"counted": 0, "weight": 0, "reason": "expired"}
            return {"counted": 1, "weight": w, "reason": "counted"}
        if op == "set_verdict" and obj.type == "claim":
            if obj.fields["kind"] == "base":
                return {"verdict": self._base_verdict(None, scratch, obj.id, tr)}
            return {"verdict": self._composite_verdict(None, scratch, obj.id, tr)}
        raise Illegal(f"no local rule for {obj.type}/{op}")

    def execution_order(self, scratch: State, items: List[dict]) -> List[dict]:
        depth = {}

        def dep(cid):
            if cid in depth:
                return depth[cid]
            c = scratch.get(cid)
            depth[cid] = 0 if c.fields["kind"] == "base" else 1 + max(dep(k) for k in c.linked("children"))
            return depth[cid]

        def key(it):
            oid = it["object_id"]
            d = dep(oid) if scratch.get(oid).type == "claim" else -1
            return (d, it["kind"] != "auto", oid)

        return sorted(items, key=key)

    def param_keys_for(self, obj: Obj, state: State) -> List[tuple]:
        keys = [("dedup", "global"), ("policy", "global"), ("auto_base", "global")]
        if obj.type == "doc":
            keys.append(("trust", obj.fields["cls"]))
        if obj.type == "claim":
            for did in obj.linked("docs"):
                keys.append(("trust", state.get(did).fields["cls"]))
        return keys

    def idempotent_write(self, obj: Obj):
        if obj.type == "claim":
            return ("set_verdict", {"verdict": obj.fields["verdict"]})
        return None
