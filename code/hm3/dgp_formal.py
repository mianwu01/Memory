"""Formal v3: versioned scope binding, shadowing, and a dynamic proof DAG.

Objects: scopes (module > section > local), definitions (name, version,
scope, pending|active), lemmas (scope, uses, bound map, cert, depends).
Visible: the scope tree, every definition, each lemma's current binding.
Hidden:
  section_shadows[global]  a section-level definition shadows the module-level one
                           for lemmas inside that section (locals always shadow)
  sensitive[lemma|name]    the lemma's proof depends on that definition's version
  stmt_sensitive[lemma]    a re-check changes the lemma's statement certificate,
                           so dependents must be re-checked too
  auto_local[global]       lemmas in local blocks are re-checked by the checker daemon (auto)
A bump or an activation re-binds lemmas (auto), then certificates are recomputed
along the proof DAG; only lemmas whose certificate changes need a re-check.
"""
from __future__ import annotations

import hashlib
import random
from typing import Dict, List, Optional

from .core import Domain, Effect, Illegal, Obj, State, Tracker, segments, timeline

NAMES = ["add", "mul", "norm", "dist", "bound", "step", "comp", "inv", "lift", "pair"]


def _h(*parts) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:10]


class FormalDomain(Domain):
    NAME = "formal"
    PARAM_NAMES = ["section_shadows", "sensitive", "stmt_sensitive", "auto_local"]
    OPS = {"recheck": 20}

    def relation_names(self):
        return ["scope", "parent", "children", "defs", "lemmas", "depends", "dependents"]

    def categorical_fields(self):
        return {"scope": ["kind"], "def": ["name"], "lemma": []}

    def numeric_fields(self):
        return {"def": ["version"], "lemma": [], "scope": []}

    # ------------------------------------------------------------ world
    def sample_world(self, rng: random.Random, cfg: dict):
        used = set()

        def fresh(prefix):
            while True:
                cand = f"{prefix}{rng.randint(10, 99)}"
                if cand not in used:
                    used.add(cand)
                    return cand

        params = {"section_shadows": {"global": int(rng.random() < 0.5)}, "sensitive": {},
                  "stmt_sensitive": {}, "auto_local": {"global": int(rng.random() < 0.5)}}
        state = State(meta={}, tokens=cfg.get("tokens", 80))
        mod = Obj(fresh("M"), "scope", {"kind": "module"}, {"parent": [], "children": [], "defs": [], "lemmas": []})
        state.add(mod)
        names = rng.sample(NAMES, rng.choice([4, 5]))
        for n in names:
            d = Obj(fresh("DEF"), "def", {"name": n, "version": rng.choice([1, 2, 3])}, {"scope": [mod.id]})
            state.add(d)
            mod.links["defs"].append(d.id)
        sections = []
        locals_ = []
        for _ in range(rng.choice([2, 3])):
            sec = Obj(fresh("S"), "scope", {"kind": "section"}, {"parent": [mod.id], "children": [], "defs": [], "lemmas": []})
            state.add(sec)
            mod.links["children"].append(sec.id)
            sections.append(sec)
            for _ in range(rng.choice([0, 1, 2])):
                loc = Obj(fresh("L"), "scope", {"kind": "local"}, {"parent": [sec.id], "children": [], "defs": [], "lemmas": []})
                state.add(loc)
                sec.links["children"].append(loc.id)
                locals_.append(loc)
        # shadowing definitions: some active, some pending
        for sc in sections + locals_:
            for n in rng.sample(names, rng.choice([0, 1, 1, 2])):
                d = Obj(fresh("DEF"), "def", {"name": n, "version": rng.choice([1, 2])}, {"scope": [sc.id]})
                if rng.random() < 0.5:
                    d.status = "pending"
                state.add(d)
                sc.links["defs"].append(d.id)
        lemmas = []
        scopes_for_lemmas = sections + locals_
        for i in range(rng.choice([6, 7, 8, 9])):
            sc = rng.choice(scopes_for_lemmas)
            uses = rng.sample(names, rng.choice([2, 3]))
            # dependencies: earlier lemmas in this scope or an ancestor scope
            anc = self._ancestors(state, sc.id)
            pool = [l for l in lemmas if l.linked("scope")[0] in anc]
            deps = rng.sample(pool, min(len(pool), rng.choice([0, 1, 1, 2])))
            lem = Obj(fresh("LEM"), "lemma", {"uses": uses, "bound": {}, "cert": ""},
                      {"scope": [sc.id], "depends": [d.id for d in deps], "dependents": []})
            for d in deps:
                d.links["dependents"].append(lem.id)
            state.add(lem)
            sc.links["lemmas"].append(lem.id)
            lemmas.append(lem)
            for n in uses:
                params["sensitive"][f"{lem.id}|{n}"] = int(rng.random() < 0.6)
            params["stmt_sensitive"][lem.id] = int(rng.random() < 0.5)
        tr = Tracker(params)
        for lem in lemmas:
            lem.fields["bound"] = self._resolve(state, lem, tr)
        for lem in self._topo(state):
            lem.fields["cert"] = self._cert(state, lem, tr)
        return params, state

    # ---------------------------------------------------------- helpers
    def _ancestors(self, state: State, sid: str) -> List[str]:
        out = []
        cur = sid
        while cur:
            out.append(cur)
            parents = state.get(cur).linked("parent")
            cur = parents[0] if parents else None
        return out

    def _resolve(self, state: State, lem: Obj, tr: Tracker) -> Dict[str, str]:
        bound = {}
        chain = self._ancestors(state, lem.linked("scope")[0])
        for n in lem.fields["uses"]:
            target = None
            for sid in chain:
                sc = state.get(sid)
                defs = [state.get(d) for d in sc.linked("defs")
                        if state.get(d).fields["name"] == n and state.get(d).status == "active"]
                if not defs:
                    continue
                if sc.fields["kind"] == "section" and not tr.get("section_shadows", "global"):
                    continue
                target = max(defs, key=lambda d: d.id).id
                break
            bound[n] = target or ""
        return bound

    def _topo(self, state: State) -> List[Obj]:
        lemmas = state.by_type("lemma")
        order, seen = [], set()

        def visit(l):
            if l.id in seen:
                return
            seen.add(l.id)
            for d in l.linked("depends"):
                visit(state.get(d))
            order.append(l)

        for l in sorted(lemmas, key=lambda x: x.id):
            visit(l)
        return order

    def _stmt_cert(self, state: State, lem: Obj, tr: Tracker) -> str:
        if tr.get("stmt_sensitive", lem.id):
            return _h("stmt", lem.id, sorted(self._sensitive_bindings(state, lem, tr).items()))
        return _h("stmt", lem.id)

    def _sensitive_bindings(self, state: State, lem: Obj, tr: Tracker) -> Dict[str, tuple]:
        out = {}
        for n, did in lem.fields["bound"].items():
            if not did:
                continue
            if tr.get("sensitive", f"{lem.id}|{n}"):
                out[n] = (did, state.get(did).fields["version"])
        return out

    def _cert(self, state: State, lem: Obj, tr: Tracker) -> str:
        parents = [self._stmt_cert(state, state.get(p), tr) for p in sorted(lem.linked("depends"))]
        return _h("cert", lem.id, sorted(self._sensitive_bindings(state, lem, tr).items()), parents)

    # ------------------------------------------------------ interventions
    def sample_intervention(self, rng, params, state, avoid=None, target_param=None):
        avoid = avoid or set()
        active = [d for d in state.by_type("def") if d.status == "active" and d.id not in avoid]
        pending = [d for d in state.by_type("def") if d.status == "pending" and d.id not in avoid]
        if target_param is not None:
            name, key = target_param.split("[")
            key = key.rstrip("]")
            if name == "sensitive":
                # witnesses for a lemma's sensitivity come from bumping the very
                # definition it is bound to (possibly the test's own definition;
                # the test payload is refreshed afterwards) or from activating a
                # pending same-name definition in its scope chain
                lid, n = key.split("|")
                lem = state.get(lid)
                cands = []
                did = lem.fields["bound"].get(n)
                if did:
                    cands.append({"op": "bump_definition", "object_id": did,
                                  "payload": {"version": state.get(did).fields["version"] + 1}})
                chain = self._ancestors(state, lem.linked("scope")[0])
                for sid in chain:
                    for dd in state.get(sid).linked("defs"):
                        if state.get(dd).status == "pending" and state.get(dd).fields["name"] == n \
                                and dd not in avoid:
                            cands.append({"op": "activate_definition", "object_id": dd, "payload": {}})
                return rng.choice(cands) if cands else None
            if name == "stmt_sensitive":
                lem = state.get(key)
                cands = [state.get(d) for d in lem.fields["bound"].values() if d]
                if not cands:
                    return None
                d = rng.choice(cands)
                return {"op": "bump_definition", "object_id": d.id, "payload": {"version": d.fields["version"] + 1}}
            if name == "section_shadows":
                cands = [d for d in pending if state.get(d.linked("scope")[0]).fields["kind"] == "section"
                         and d.id not in avoid]
                if cands:
                    return {"op": "activate_definition", "object_id": rng.choice(cands).id, "payload": {}}
                return None
            if name == "auto_local":
                cands = []
                for l in state.by_type("lemma"):
                    if state.get(l.linked("scope")[0]).fields["kind"] == "local":
                        cands += [d for d in l.fields["bound"].values() if d]
                if cands:
                    did = rng.choice(cands)
                    return {"op": "bump_definition", "object_id": did,
                            "payload": {"version": state.get(did).fields["version"] + 1}}
                return None
        if pending and rng.random() < 0.3:
            return {"op": "activate_definition", "object_id": rng.choice(pending).id, "payload": {}}
        if not active:
            return None
        d = rng.choice(active)
        return {"op": "bump_definition", "object_id": d.id, "payload": {"version": d.fields["version"] + 1}}

    def refresh_intervention(self, I: dict, state: State) -> dict:
        if I["op"] == "bump_definition":
            return {"op": I["op"], "object_id": I["object_id"],
                    "payload": {"version": state.get(I["object_id"]).fields["version"] + 1}}
        return I

    def nl_query(self, I: dict, state: State) -> str:
        d = state.get(I["object_id"])
        sc = state.get(d.linked("scope")[0])
        where = f"{sc.fields['kind']} {sc.id}"
        if I["op"] == "bump_definition":
            return f"Definition {d.id} ({d.fields['name']}, {where}) is now version {I['payload']['version']}."
        return f"Definition {d.id} ({d.fields['name']}) is now active in {where}."

    # ---------------------------------------------------------- mechanism
    def propagate(self, params, state: State, I: dict, tr: Tracker) -> List[Effect]:
        scratch = state.copy()
        src = scratch.get(I["object_id"])
        tr.read(src.id)
        self.apply_payload(scratch, src, I["op"], I["payload"])
        effects: List[Effect] = []
        rebinds = []
        for lem in scratch.by_type("lemma"):
            if src.fields["name"] not in lem.fields["uses"]:
                continue
            tr.read(lem.id)
            new_bound = self._resolve(scratch, lem, tr)
            if new_bound != lem.fields["bound"]:
                lem.fields["bound"] = new_bound
                rebinds.append(Effect("auto", "rebind", lem.id, {"bound": dict(new_bound)}))
        effects.extend(rebinds)
        # certificates along the DAG; only consult sensitivity where a binding changed
        old_certs = {l.id: l.fields["cert"] for l in state.by_type("lemma")}
        for lem in self._topo(scratch):
            old = state.get(lem.id)
            changed_names = [n for n in lem.fields["uses"]
                             if self._binding_key(state, old, n) != self._binding_key(scratch, lem, n)]
            parents_changed = [p for p in lem.linked("depends") if scratch.get(p).fields["cert"] != old_certs[p]]
            if not changed_names and not parents_changed:
                continue
            tr.read(lem.id)
            new_cert = self._cert(scratch, lem, tr)
            if new_cert != lem.fields["cert"]:
                lem.fields["cert"] = new_cert
                sc = scratch.get(lem.linked("scope")[0])
                kind = "auto" if sc.fields["kind"] == "local" and tr.get("auto_local", "global") else "txn"
                effects.append(Effect(kind, "recheck", lem.id, {"cert": new_cert}))
        auto = [e for e in effects if e.kind == "auto"]
        manual = [e for e in effects if e.kind == "txn"]
        return auto + manual

    def _binding_key(self, state: State, lem: Obj, n: str):
        did = lem.fields["bound"].get(n)
        if not did:
            return None
        return (did, state.get(did).fields["version"])

    def apply_payload(self, state: State, obj: Obj, op: str, payload: dict) -> dict:
        delta = {}
        if op == "bump_definition":
            if obj.type != "def" or obj.status != "active":
                raise Illegal("bump needs an active definition")
            v = payload.get("version")
            if set(payload) != {"version"} or not isinstance(v, int):
                raise Illegal("bad bump payload")
            delta["version"] = [obj.fields["version"], v]
            obj.fields["version"] = v
        elif op == "activate_definition":
            if obj.type != "def" or obj.status != "pending":
                raise Illegal("activate needs a pending definition")
            delta["status"] = [obj.status, "active"]
            obj.status = "active"
        elif op == "rebind":
            delta["bound"] = [dict(obj.fields["bound"]), dict(payload["bound"])]
            obj.fields["bound"] = dict(payload["bound"])
        elif op == "recheck":
            if obj.type != "lemma":
                raise Illegal("recheck needs a lemma")
            c = payload.get("cert")
            if set(payload) != {"cert"} or not isinstance(c, str):
                raise Illegal("bad recheck payload")
            delta["cert"] = [obj.fields["cert"], c]
            obj.fields["cert"] = c
        else:
            raise Illegal(f"unknown op {op}")
        return delta

    # ------------------------------------------ runtime-history oracle
    def infer_params(self, H: List[dict], S0: State, prov: Optional[dict] = None) -> dict:
        est: Dict[str, dict] = {"section_shadows": {}, "sensitive": {}, "stmt_sensitive": {}, "auto_local": {}}
        prov = prov if prov is not None else {}
        seg_members: Dict[str, List[str]] = {}
        for seg0 in segments(H):
            ids = [r["rid"] for r in seg0]
            for rid in ids:
                seg_members[rid] = ids

        def note(name, key, *rids):
            # a Formal witness is the whole segment: which lemmas were (not) re-checked
            # after a bump is only meaningful together with everything else that moved
            full = set()
            for rid in rids:
                full.update(seg_members.get(rid, [rid]))
            prov[f"{name}[{key}]"] = sorted(full)

        # shadowing policy from any lemma whose section has an active definition of a used name
        for lem in S0.by_type("lemma"):
            chain = self._ancestors(S0, lem.linked("scope")[0])
            for n in lem.fields["uses"]:
                local_def = section_def = None
                for sid in chain:
                    sc = S0.get(sid)
                    defs = [d for d in sc.linked("defs") if S0.get(d).fields["name"] == n and S0.get(d).status == "active"]
                    if defs and sc.fields["kind"] == "local" and local_def is None:
                        local_def = defs[0]
                    if defs and sc.fields["kind"] == "section" and section_def is None:
                        section_def = max(defs)
                if section_def and not local_def:
                    est["section_shadows"]["global"] = int(lem.fields["bound"].get(n) == section_def)
                    prov.setdefault("section_shadows[global]", [])
        segs = segments(H)
        snaps = timeline(S0, H)
        facts = []  # (lemma, changed names, parents rechecked, rechecked?, rids)
        for k, seg in enumerate(segs):
            before, after = snaps[k], snaps[k + 1]
            rechecked = {r["object_id"] for r in seg if r["op"] == "recheck"}
            for rec in seg:
                if rec["op"] == "recheck" and rec["object_id"] in S0.objects:
                    sc = S0.get(S0.get(rec["object_id"]).linked("scope")[0])
                    if sc.fields["kind"] == "local":
                        est["auto_local"]["global"] = int(rec["kind"] == "auto")
                        note("auto_local", "global", seg[0]["rid"], rec["rid"])
            for lem in S0.by_type("lemma"):
                lb, la = before.get(lem.id), after.get(lem.id)
                changed = [n for n in lem.fields["uses"]
                           if self._binding_key(before, lb, n) != self._binding_key(after, la, n)]
                parents = [p for p in lem.linked("depends") if p in rechecked]
                if not changed and not parents:
                    continue
                related = {lem.id, *lem.linked("depends")}
                rids = [seg[0]["rid"]] + [r["rid"] for r in seg if r["object_id"] in related]
                facts.append((lem.id, changed, parents, lem.id in rechecked, rids))
        # a lemma that was not re-checked rules out every candidate cause; a
        # re-checked lemma with exactly one candidate cause (after removing
        # causes already known to be inactive) identifies that cause
        for _pass in range(4):
            for lid, changed, parents, was, rids in facts:
                if not was:
                    for n in changed:
                        est["sensitive"][f"{lid}|{n}"] = 0
                        note("sensitive", f"{lid}|{n}", *rids)
                    for p in parents:
                        est["stmt_sensitive"][p] = 0
                        note("stmt_sensitive", p, *rids)
                    continue
                cands = [("s", n) for n in changed] + [("p", p) for p in parents]
                live, support = [], list(rids)
                for c in cands:
                    pk = f"sensitive[{lid}|{c[1]}]" if c[0] == "s" else f"stmt_sensitive[{c[1]}]"
                    dead = (est["sensitive"].get(f"{lid}|{c[1]}") == 0) if c[0] == "s" \
                        else (est["stmt_sensitive"].get(c[1]) == 0)
                    if dead:
                        support += prov.get(pk, [])
                    else:
                        live.append(c)
                if len(live) == 1:
                    kind, key = live[0]
                    if kind == "s":
                        est["sensitive"][f"{lid}|{key}"] = 1
                        note("sensitive", f"{lid}|{key}", *support)
                    else:
                        est["stmt_sensitive"][key] = 1
                        note("stmt_sensitive", key, *support)
        return est

    # ------------------------------------------------ executor local rules
    def local_payload(self, scratch: State, obj: Obj, op: str, fields, tr: Tracker) -> dict:
        if op == "rebind":
            return {"bound": self._resolve(scratch, obj, tr)}
        if op == "recheck":
            return {"cert": self._cert(scratch, obj, tr)}
        raise Illegal(f"no local rule for {obj.type}/{op}")

    def execution_order(self, scratch: State, items: List[dict]) -> List[dict]:
        topo = {l.id: i for i, l in enumerate(self._topo(scratch))}
        return sorted(items, key=lambda it: (topo.get(it["object_id"], -1), it["kind"] != "auto", it["object_id"]))

    def param_keys_for(self, obj: Obj, state: State) -> List[tuple]:
        keys = [("section_shadows", "global"), ("auto_local", "global")]
        if obj.type == "lemma":
            keys += [("sensitive", f"{obj.id}|{n}") for n in obj.fields["uses"]]
            keys.append(("stmt_sensitive", obj.id))
            keys += [("stmt_sensitive", p) for p in obj.linked("depends")]
        return keys

    def idempotent_write(self, obj: Obj):
        if obj.type == "lemma":
            return ("recheck", {"cert": obj.fields["cert"]})
        return None
