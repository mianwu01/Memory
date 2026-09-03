"""Shopping v3: compatibility factor graph + promotion hypergraph + global cart re-optimisation.

Objects: cart lines (base items with linked accessories), promotions, the cart.
Visible: catalog with attributes and prices, budget, priorities.  Hidden:
  compat[base|acc]      whether the (base category, accessory category) pair is constrained
                        on its attribute (model / mount / series / brand / size)
  strict_promo[promo]   the promotion also requires brand match on every required category
  auto_promo[global]    promotions are re-evaluated by the store (auto) or by the agent (txn)
  enforce_budget[global] over-budget carts must drop optional lines (most optional, then priciest)
Replacing one base item can cascade: accessory repairs change the total, the
total breaks the budget, a removal breaks a promotion, the lost discount
raises the total again.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from .core import Domain, Effect, Illegal, Obj, State, Tracker, segments, timeline

PAIR_ATTR = {"phone|case": "model", "camera|lens": "mount", "printer|cartridge": "series",
             "laptop|charger": "brand", "phone|charger": "brand", "laptop|bag": "size",
             "camera|bag": "brand"}
ACCESSORIES = {"phone": ["case", "charger"], "camera": ["lens", "bag"],
               "printer": ["cartridge"], "laptop": ["charger", "bag"]}
ATTR_VALUES = {"model": ["M1", "M2", "M3", "M4"], "mount": ["X1", "X2", "X3"],
               "series": ["S1", "S2", "S3"], "brand": ["Bx", "By", "Bz"], "size": [13, 14, 15, 16]}
CAT_ATTRS = {"phone": ["model", "brand"], "case": ["model", "brand"], "camera": ["mount", "brand"],
             "lens": ["mount", "brand"], "printer": ["series", "brand"],
             "cartridge": ["series", "brand"], "laptop": ["brand", "size"], "charger": ["brand"],
             "bag": ["size", "brand"]}
BASE_PRICE = {"phone": (400, 900), "camera": (500, 1200), "printer": (150, 400), "laptop": (700, 1500)}
ACC_PRICE = {"case": (15, 60), "charger": (20, 70), "lens": (120, 400), "bag": (30, 120),
             "cartridge": (25, 90)}


class ShoppingDomain(Domain):
    NAME = "shopping"
    PARAM_NAMES = ["compat", "strict_promo", "auto_promo", "enforce_budget"]
    OPS = {"replace_line": 15, "remove_line": 10, "apply_promo": 5, "drop_promo": 5}

    def relation_names(self):
        return ["accessories", "base", "cart", "lines", "promos"]

    def categorical_fields(self):
        return {"line": ["category", "role", "priority"], "promo": ["brand"], "cart": []}

    def numeric_fields(self):
        return {"line": ["price", "priority"], "promo": ["discount", "active"], "cart": ["budget", "total"]}

    # ------------------------------------------------------------ world
    def sample_world(self, rng: random.Random, cfg: dict):
        used = set()

        def fresh(prefix):
            while True:
                cand = f"{prefix}{rng.randint(10, 99)}"
                if cand not in used:
                    used.add(cand)
                    return cand

        catalog: Dict[str, list] = {}
        for cat in list(ACCESSORIES) + sorted({a for v in ACCESSORIES.values() for a in v}):
            lo, hi = BASE_PRICE.get(cat, ACC_PRICE.get(cat))
            variants = []
            for j in range(rng.choice([5, 6])):
                attrs = {a: rng.choice(ATTR_VALUES[a]) for a in CAT_ATTRS[cat]}
                variants.append({"sku": f"{cat[:2].upper()}-{j + 1}", "attrs": attrs,
                                 "price": rng.randint(lo, hi)})
            catalog[cat] = variants
        params = {"compat": {pair: int(rng.random() < 0.6) for pair in PAIR_ATTR},
                  "strict_promo": {}, "auto_promo": {"global": int(rng.random() < 0.5)},
                  "enforce_budget": {"global": int(rng.random() < 0.6)}}
        cart_id = fresh("CART")
        state = State(meta={"catalog": catalog}, tokens=cfg.get("tokens", 80))
        cart = Obj(cart_id, "cart", {"budget": 0, "total": 0}, {"lines": [], "promos": []})
        state.add(cart)
        bases = rng.sample(list(ACCESSORIES), 3)
        for cat in bases:
            lid = fresh("L")
            v = rng.choice(catalog[cat])
            line = Obj(lid, "line", {"category": cat, "role": "base", "sku": v["sku"],
                                     "attrs": dict(v["attrs"]), "price": v["price"], "priority": 1},
                       {"cart": [cart_id], "accessories": [], "base": []})
            state.add(line)
            cart.links["lines"].append(lid)
            for acc_cat in rng.sample(ACCESSORIES[cat], rng.choice([1, len(ACCESSORIES[cat])])):
                pair = f"{cat}|{acc_cat}"
                attr = PAIR_ATTR[pair]
                pool = catalog[acc_cat]
                if params["compat"][pair]:
                    match = [x for x in pool if x["attrs"][attr] == v["attrs"][attr]]
                    if not match:
                        continue
                    av = min(match, key=lambda x: x["price"])
                else:
                    av = rng.choice(pool)
                aid = fresh("L")
                acc = Obj(aid, "line", {"category": acc_cat, "role": "accessory", "sku": av["sku"],
                                        "attrs": dict(av["attrs"]), "price": av["price"],
                                        "priority": rng.choice([2, 3])},
                          {"cart": [cart_id], "accessories": [], "base": [lid]})
                state.add(acc)
                line.links["accessories"].append(aid)
                cart.links["lines"].append(aid)
        cats_in_cart = sorted({state.get(l).fields["category"] for l in cart.linked("lines")})
        for _ in range(rng.choice([1, 2])):
            pid = fresh("PR")
            req = rng.sample(cats_in_cart, min(len(cats_in_cart), 2))
            promo = Obj(pid, "promo", {"requires": req, "brand": rng.choice(ATTR_VALUES["brand"]),
                                       "discount": rng.choice([30, 50, 80, 120]), "active": 0},
                        {"cart": [cart_id]})
            state.add(promo)
            cart.links["promos"].append(pid)
            params["strict_promo"][pid] = int(rng.random() < 0.5)
        tr = Tracker(params)
        for pid in cart.linked("promos"):
            state.get(pid).fields["active"] = int(self._eligible(state, pid, tr))
        total = self._total(state)
        cart.fields["total"] = total
        cart.fields["budget"] = total + rng.choice([0, 20, 40, 60, 100, 150, 250])
        return params, state

    # ---------------------------------------------------------- helpers
    def _active_lines(self, state: State):
        cart = state.by_type("cart")[0]
        return [state.get(l) for l in cart.linked("lines") if state.get(l).status == "active"]

    def _eligible(self, state: State, pid: str, tr: Tracker) -> bool:
        promo = state.get(pid)
        lines = self._active_lines(state)
        strict = tr.get("strict_promo", pid)
        for cat in promo.fields["requires"]:
            cands = [l for l in lines if l.fields["category"] == cat]
            if strict:
                cands = [l for l in cands if l.fields["attrs"].get("brand") == promo.fields["brand"]]
            if not cands:
                return False
        return True

    def _total(self, state: State) -> int:
        cart = state.by_type("cart")[0]
        total = sum(l.fields["price"] for l in self._active_lines(state))
        total -= sum(state.get(p).fields["discount"] for p in cart.linked("promos")
                     if state.get(p).fields["active"])
        return total

    # ------------------------------------------------------ interventions
    def sample_intervention(self, rng, params, state, avoid=None, target_param=None):
        avoid = avoid or set()
        catalog = state.meta["catalog"]
        bases = [l for l in self._active_lines(state) if l.fields["role"] == "base" and l.id not in avoid]
        if not bases:
            return None
        pick_expensive = False
        if target_param is not None:
            name, key = target_param.split("[")
            key = key.rstrip("]")
            if name == "compat":
                b_cat, a_cat = key.split("|")
                bases = [b for b in bases if b.fields["category"] == b_cat and any(
                    state.get(a).fields["category"] == a_cat and state.get(a).status == "active"
                    for a in b.linked("accessories"))]
                if not bases:
                    return None
            elif name == "strict_promo":
                promo = state.get(key)
                bases = [b for b in bases if b.fields["category"] in promo.fields["requires"]] or bases
            elif name == "enforce_budget":
                pick_expensive = True
        base = rng.choice(bases)
        cat = base.fields["category"]
        options = [v for v in catalog[cat] if v["sku"] != base.fields["sku"]]
        if target_param and target_param.startswith("compat"):
            attr = PAIR_ATTR[target_param.split("[")[1].rstrip("]")]
            diff = [v for v in options if v["attrs"].get(attr) != base.fields["attrs"].get(attr)]
            options = diff or options
        if target_param and target_param.startswith("strict_promo"):
            diff = [v for v in options if v["attrs"]["brand"] != base.fields["attrs"]["brand"]]
            options = diff or options
        if pick_expensive:
            options = sorted(options, key=lambda v: -v["price"])[:2]
        v = rng.choice(options)
        return {"op": "replace_line", "object_id": base.id, "payload": {"sku": v["sku"]}}

    def nl_query(self, I: dict, state: State) -> str:
        line = state.get(I["object_id"])
        return f"Line {line.id} ({line.fields['category']}) is now SKU {I['payload']['sku']}."

    # ---------------------------------------------------------- mechanism
    def propagate(self, params, state: State, I: dict, tr: Tracker) -> List[Effect]:
        scratch = state.copy()
        catalog = scratch.meta["catalog"]
        base = scratch.get(I["object_id"])
        tr.read(base.id)
        self.apply_payload(scratch, base, I["op"], I["payload"])
        touched: Dict[str, str] = {}
        for aid in base.linked("accessories"):
            acc = scratch.get(aid)
            if acc.status != "active":
                continue
            tr.read(aid)
            pair = f"{base.fields['category']}|{acc.fields['category']}"
            attr = PAIR_ATTR[pair]
            if acc.fields["attrs"][attr] == base.fields["attrs"][attr]:
                continue
            if not tr.get("compat", pair):
                continue
            match = [v for v in catalog[acc.fields["category"]]
                     if v["attrs"][attr] == base.fields["attrs"][attr]]
            if match:
                v = min(match, key=lambda x: (x["price"], x["sku"]))
                self.apply_payload(scratch, acc, "replace_line", {"sku": v["sku"]})
                touched[aid] = "replace"
            else:
                acc.status = "removed"
                touched[aid] = "remove"
        cart = scratch.by_type("cart")[0]
        tr.read(cart.id)
        promo_changes: Dict[str, int] = {}

        def reevaluate_promos():
            for pid in cart.linked("promos"):
                promo = scratch.get(pid)
                tr.read(pid)
                elig = int(self._eligible(scratch, pid, tr))
                if elig != promo.fields["active"]:
                    promo.fields["active"] = elig
                    promo_changes[pid] = elig

        reevaluate_promos()
        total = self._total(scratch)
        if total > cart.fields["budget"] and tr.get("enforce_budget", "global"):
            for _ in range(12):
                total = self._total(scratch)
                if total <= cart.fields["budget"]:
                    break
                victims = [l for l in self._active_lines(scratch)
                           if l.fields["priority"] > 1 and l.id != base.id]
                if not victims:
                    break
                victim = max(victims, key=lambda l: (l.fields["priority"], l.fields["price"], l.id))
                victim.status = "removed"
                touched[victim.id] = "remove"
                reevaluate_promos()
        effects: List[Effect] = []
        for lid, what in touched.items():
            if what == "remove":
                effects.append(Effect("txn", "remove_line", lid, {}))
            else:
                effects.append(Effect("txn", "replace_line", lid, {"sku": scratch.get(lid).fields["sku"]}))
        for pid in cart.linked("promos"):
            before = state.get(pid).fields["active"]
            after = scratch.get(pid).fields["active"]
            if before != after:
                kind = "auto" if tr.get("auto_promo", "global") else "txn"
                effects.append(Effect(kind, "apply_promo" if after else "drop_promo", pid, {}))
        new_total = self._total(scratch)
        if new_total != state.by_type("cart")[0].fields["total"]:
            effects.append(Effect("auto", "recompute_total", cart.id, {"total": new_total}))
        # auto effects must precede manual ones in the receipt; the cart total is
        # recomputed by the store after the intervention and again after repairs,
        # so we report it as the final value (the store re-runs it once per event).
        auto = [e for e in effects if e.kind == "auto"]
        manual = [e for e in effects if e.kind == "txn"]
        return auto + manual

    def apply_payload(self, state: State, obj: Obj, op: str, payload: dict) -> dict:
        delta = {}
        catalog = state.meta["catalog"]
        if op == "replace_line":
            if obj.type != "line" or obj.status != "active":
                raise Illegal("replace_line needs an active line")
            sku = payload.get("sku")
            if set(payload) != {"sku"}:
                raise Illegal("replace payload must be {sku}")
            v = next((x for x in catalog[obj.fields["category"]] if x["sku"] == sku), None)
            if v is None:
                raise Illegal(f"sku {sku} not in catalog for {obj.fields['category']}")
            delta["sku"] = [obj.fields["sku"], v["sku"]]
            delta["attrs"] = [dict(obj.fields["attrs"]), dict(v["attrs"])]
            delta["price"] = [obj.fields["price"], v["price"]]
            obj.fields["sku"] = v["sku"]
            obj.fields["attrs"] = dict(v["attrs"])
            obj.fields["price"] = v["price"]
        elif op == "remove_line":
            if obj.type != "line" or obj.status != "active":
                raise Illegal("remove_line needs an active line")
            if payload:
                raise Illegal("remove takes no payload")
            delta["status"] = [obj.status, "removed"]
            obj.status = "removed"
        elif op in ("apply_promo", "drop_promo"):
            if obj.type != "promo":
                raise Illegal("promo op needs a promo")
            if payload:
                raise Illegal("promo op takes no payload")
            target = 1 if op == "apply_promo" else 0
            if obj.fields["active"] == target:
                raise Illegal(f"promo already {'active' if target else 'inactive'}")
            delta["active"] = [obj.fields["active"], target]
            obj.fields["active"] = target
        elif op == "recompute_total":
            delta["total"] = [obj.fields["total"], payload["total"]]
            obj.fields["total"] = payload["total"]
        else:
            raise Illegal(f"unknown op {op}")
        return delta

    # ------------------------------------------ runtime-history oracle
    def infer_params(self, H: List[dict], S0: State, prov: Optional[dict] = None) -> dict:
        est: Dict[str, dict] = {"compat": {}, "strict_promo": {}, "auto_promo": {}, "enforce_budget": {}}
        prov = prov if prov is not None else {}

        def note(name, key, *rids):
            prov[f"{name}[{key}]"] = sorted(set(rids))

        segs = segments(H)
        snaps = timeline(S0, H)
        cart = S0.by_type("cart")[0]
        for k, seg in enumerate(segs):
            before, after = snaps[k], snaps[k + 1]
            by_obj: Dict[str, list] = {}
            for rec in seg:
                by_obj.setdefault(rec["object_id"], []).append(rec)
            for rec in seg:
                oid = rec["object_id"]
                if oid not in S0.objects:
                    continue
                obj = S0.get(oid)
                d = rec.get("delta") or {}
                if obj.type == "line" and "attrs" in d and obj.fields["role"] == "base":
                    new_attrs = d["attrs"][1]
                    for aid in obj.linked("accessories"):
                        acc_before = before.get(aid)
                        if acc_before.status != "active":
                            continue
                        pair = f"{obj.fields['category']}|{acc_before.fields['category']}"
                        attr = PAIR_ATTR[pair]
                        if acc_before.fields["attrs"][attr] == new_attrs[attr]:
                            continue
                        repaired = any(r["op"] in ("replace_line", "remove_line") for r in by_obj.get(aid, []))
                        # a removal caused by the budget rule is not a compatibility repair;
                        # attribute it only when the replacement matches the base attribute
                        # or when removal happened with no compatible variant available
                        if repaired:
                            rr = by_obj[aid][0]
                            if rr["op"] == "replace_line":
                                if rr["delta"]["attrs"][1][attr] == new_attrs[attr]:
                                    est["compat"][pair] = 1
                                    note("compat", pair, seg[0]["rid"], rec["rid"], rr["rid"])
                            else:
                                match = [v for v in S0.meta["catalog"][acc_before.fields["category"]]
                                         if v["attrs"][attr] == new_attrs[attr]]
                                if not match:
                                    est["compat"][pair] = 1
                                    note("compat", pair, seg[0]["rid"], rec["rid"], rr["rid"])
                        else:
                            est["compat"][pair] = 0
                            note("compat", pair, seg[0]["rid"], rec["rid"])
                if obj.type == "promo" and rec["op"] in ("apply_promo", "drop_promo"):
                    est["auto_promo"]["global"] = int(rec["kind"] == "auto")
                    note("auto_promo", "global", seg[0]["rid"], rec["rid"])
                if obj.type == "line" and rec["op"] == "remove_line":
                    est["enforce_budget"]["global"] = 1
                    note("enforce_budget", "global", seg[0]["rid"], rec["rid"])
            # promo strictness from the post-segment state; budget from the post-segment total
            for pid in cart.linked("promos"):
                pol = self._strictness_from(after, pid)
                if pol is not None:
                    est["strict_promo"][pid] = pol
                    note("strict_promo", pid, seg[0]["rid"])
            if self._total(after) > cart.fields["budget"] and \
                    any(l.fields["priority"] > 1 for l in self._active_lines(after)):
                est["enforce_budget"]["global"] = 0
                note("enforce_budget", "global", seg[0]["rid"])
        for pid in cart.linked("promos"):
            if pid not in est["strict_promo"]:
                pol = self._strictness_from(S0, pid)
                if pol is not None:
                    est["strict_promo"][pid] = pol
                    prov.setdefault(f"strict_promo[{pid}]", [])
        if "global" not in est["enforce_budget"]:
            if self._total(S0) > cart.fields["budget"] and \
                    any(l.fields["priority"] > 1 for l in self._active_lines(S0)):
                est["enforce_budget"]["global"] = 0
                prov.setdefault("enforce_budget[global]", [])
        return est

    def _strictness_from(self, state: State, pid: str) -> Optional[int]:
        strict = self._eligible(state, pid, Tracker({"strict_promo": {pid: 1}}))
        lenient = self._eligible(state, pid, Tracker({"strict_promo": {pid: 0}}))
        if strict == lenient:
            return None
        active = state.get(pid).fields["active"]
        return 1 if active == int(strict) else 0

    # ------------------------------------------------ executor local rules
    def local_payload(self, scratch: State, obj: Obj, op: str, fields, tr: Tracker) -> dict:
        if op in ("remove_line", "apply_promo", "drop_promo"):
            return {}
        if op == "recompute_total":
            return {"total": self._total(scratch)}
        if op == "replace_line" and obj.type == "line":
            if not obj.linked("base"):
                raise Illegal("no compatibility rule for a base line")
            base = scratch.get(obj.linked("base")[0])
            pair = f"{base.fields['category']}|{obj.fields['category']}"
            attr = PAIR_ATTR[pair]
            match = [v for v in scratch.meta["catalog"][obj.fields["category"]]
                     if v["attrs"][attr] == base.fields["attrs"][attr]]
            if not match:
                raise Illegal("no compatible variant")
            v = min(match, key=lambda x: (x["price"], x["sku"]))
            return {"sku": v["sku"]}
        raise Illegal(f"no local rule for {obj.type}/{op}")

    def param_keys_for(self, obj: Obj, state: State) -> List[tuple]:
        keys = [("auto_promo", "global"), ("enforce_budget", "global")]
        if obj.type == "line" and obj.fields["role"] == "accessory" and obj.linked("base"):
            base = state.get(obj.linked("base")[0])
            keys.append(("compat", f"{base.fields['category']}|{obj.fields['category']}"))
        if obj.type == "promo":
            keys.append(("strict_promo", obj.id))
        return keys

    def idempotent_write(self, obj: Obj):
        if obj.type == "line" and obj.status == "active":
            return ("replace_line", {"sku": obj.fields["sku"]})
        return None
