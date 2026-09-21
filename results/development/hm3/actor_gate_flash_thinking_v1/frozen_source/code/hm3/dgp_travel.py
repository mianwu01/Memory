"""Travel v3: a time / resource / provider-policy / bundle-commitment network.

Chain per (traveler, day):  flight --transfer--> stay --> {dinner, activity}, dinner --bundle--> bundle
Visible mechanism:  stay.checkin = transfer.pickup + transfer.ride;
                    activity shifts when checkin + min_rest > activity.start.
Hidden mechanism (per episode, keyed by visible provider/hotel/restaurant/vendor ids):
  auto_rebook[provider]   transfer follows the flight automatically (auto) or needs a manual shift (txn)
  buffer[provider]        pickup = arrival + buffer (continuous, identified by subtraction from one witness)
  enforce_late[hotel]     late-arrival flag is maintained when checkin crosses the visible late_cutoff
  late_seating[restaurant] a dinner conflict is resolved by shifting (1) or cancelling (0)
  linked[vendor]          a bundle must be re-booked when its dinner changes
The query names only the source reservation and its new time.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from .core import Domain, Effect, Illegal, Obj, State, Tracker, ceil15, hhmm, segments

NAMES = ["Alice", "Bob", "Chen", "Dana", "Eli", "Fatima", "Gao", "Hana", "Ivan", "Jun",
         "Kai", "Lena", "Mateo", "Nia", "Omar", "Priya", "Quinn", "Rosa", "Sam", "Tara"]
DINNER_LEAD = 45


class TravelDomain(Domain):
    NAME = "travel"
    PARAM_NAMES = ["auto_rebook", "buffer", "enforce_late", "late_seating", "linked"]
    OPS = {"shift_reservation": 25, "cancel_reservation": 40, "rebook_bundle": 30}
    SHIFT_FIELDS = {"transfer": {"pickup"}, "stay": {"checkin", "late_arrival"},
                    "dinner": {"start"}, "activity": {"start"}, "flight": {"arrival"}}

    def relation_names(self):
        return ["transfer", "flight", "stay", "dinner", "activity", "bundle"]

    def categorical_fields(self):
        return {"transfer": ["provider"], "stay": ["hotel"], "dinner": ["restaurant"],
                "bundle": ["vendor"], "flight": [], "activity": []}

    def numeric_fields(self):
        return {"flight": ["arrival"], "transfer": ["pickup", "ride"],
                "stay": ["checkin", "late_cutoff", "late_arrival"], "dinner": ["start"],
                "activity": ["start", "min_rest"], "bundle": []}

    # ------------------------------------------------------------ world
    def sample_world(self, rng: random.Random, cfg: dict):
        n_trav = cfg.get("n_travelers", 3)
        n_days = cfg.get("n_days", 2)
        used = set()

        def fresh(prefix):
            while True:
                cand = f"{prefix}{rng.randint(10, 99)}"
                if cand not in used:
                    used.add(cand)
                    return cand

        providers = [fresh("P") for _ in range(rng.choice([2, 3]))]
        hotels = [fresh("H") for _ in range(rng.choice([2, 3]))]
        restaurants = [fresh("R") for _ in range(rng.choice([2, 3]))]
        vendors = [fresh("V") for _ in range(2)]
        params = {
            "auto_rebook": {p: int(rng.random() < 0.5) for p in providers},
            "buffer": {p: rng.choice([20, 25, 30, 35, 40, 45, 50, 55, 60]) for p in providers},
            "enforce_late": {h: int(rng.random() < 0.5) for h in hotels},
            "late_seating": {r: int(rng.random() < 0.5) for r in restaurants},
            "linked": {v: int(rng.random() < 0.5) for v in vendors},
        }
        travelers = rng.sample(NAMES, n_trav)
        state = State(meta={"trip": fresh("TRIP"), "days": n_days}, tokens=cfg.get("tokens", 80))
        for name in travelers:
            for day in range(1, n_days + 1):
                fid, tid, sid, did, aid = (fresh("F"), fresh("T"), fresh("S"), fresh("D"), fresh("A"))
                p = rng.choice(providers)
                h = rng.choice(hotels)
                r = rng.choice(restaurants)
                arrival = rng.choice(range(600, 1230, 15))
                ride = rng.choice([20, 30, 40, 50])
                # the booked pickup is a manual booking; the provider's buffer rule
                # only shows itself when a flight moves, so S0 does not leak it
                pickup = arrival + rng.choice(range(15, 80, 5))
                checkin = pickup + ride
                cutoff = rng.choice([1230, 1260, 1290, 1320, 1350, 1380])
                late = int(params["enforce_late"][h] and checkin > cutoff)
                dinner_start = max(ceil15(checkin + DINNER_LEAD), rng.choice(range(1140, 1320, 15)))
                dinner_start += rng.choice([0, 15, 30, 45, 60])
                min_rest = rng.choice([480, 540, 600])
                act_start = max(ceil15(checkin + min_rest), 1440 + rng.choice(range(480, 660, 15)))
                act_start += rng.choice([0, 15, 30])
                flight = Obj(fid, "flight", {"traveler": name, "day": day, "arrival": arrival},
                             {"transfer": [tid]})
                transfer = Obj(tid, "transfer", {"traveler": name, "day": day, "provider": p,
                                                 "ride": ride, "pickup": pickup},
                               {"flight": [fid], "stay": [sid]})
                stay = Obj(sid, "stay", {"traveler": name, "day": day, "hotel": h,
                                         "late_cutoff": cutoff, "checkin": checkin,
                                         "late_arrival": late},
                           {"transfer": [tid], "dinner": [did], "activity": [aid]})
                dinner = Obj(did, "dinner", {"traveler": name, "day": day, "restaurant": r,
                                             "start": dinner_start}, {"stay": [sid]})
                activity = Obj(aid, "activity", {"traveler": name, "day": day, "start": act_start,
                                                 "min_rest": min_rest}, {"stay": [sid]})
                for o in (flight, transfer, stay, dinner, activity):
                    state.add(o)
                if rng.random() < 0.75:
                    bid = fresh("B")
                    v = rng.choice(vendors)
                    bundle = Obj(bid, "bundle", {"traveler": name, "day": day, "vendor": v,
                                                 "rebooked": 0}, {"stay": [sid], "dinner": [did]})
                    stay.links["bundle"] = [bid]
                    dinner.links["bundle"] = [bid]
                    state.add(bundle)
        return params, state

    # ------------------------------------------------------ interventions
    def _chains(self, state: State):
        return [(f, state.get(f.linked("transfer")[0])) for f in state.by_type("flight")]

    def sample_intervention(self, rng, params, state, avoid=None, target_param=None):
        avoid = avoid or set()
        chains = [(f, t) for f, t in self._chains(state) if f.id not in avoid and t.id not in avoid]
        if target_param is not None:
            name, key = target_param.split("[")
            key = key.rstrip("]")
            cands = []
            for f, t in chains:
                stay = state.get(t.linked("stay")[0])
                dinner = state.get(stay.linked("dinner")[0])
                if name in ("buffer", "auto_rebook") and t.fields["provider"] == key:
                    cands.append((f, t, "any"))
                elif name == "enforce_late" and stay.fields["hotel"] == key:
                    cands.append((f, t, "cross_cutoff"))
                elif name == "late_seating" and dinner.fields["restaurant"] == key and dinner.status == "active":
                    cands.append((f, t, "dinner_conflict"))
                elif name == "linked" and dinner.linked("bundle") and dinner.status == "active" \
                        and state.get(dinner.linked("bundle")[0]).fields["vendor"] == key:
                    cands.append((f, t, "dinner_conflict"))
            if not cands:
                return None
            f, t, mode = rng.choice(cands)
        else:
            if not chains:
                return None
            f, t = rng.choice(chains)
            mode = rng.choice(["any", "cross_cutoff", "dinner_conflict", "dinner_conflict", "late"])
        stay = state.get(t.linked("stay")[0])
        dinner = state.get(stay.linked("dinner")[0])
        buf = params["buffer"][t.fields["provider"]]
        ride = t.fields["ride"]
        if mode == "cross_cutoff":
            cutoff = stay.fields["late_cutoff"]
            if stay.fields["late_arrival"]:
                # currently late: move earlier so the flag would clear
                arrival = cutoff - buf - ride - rng.choice([15, 30, 45, 60])
            else:
                arrival = cutoff - buf - ride + rng.choice([15, 30, 45, 60, 90])
        elif mode == "dinner_conflict":
            arrival = dinner.fields["start"] - DINNER_LEAD - buf - ride + rng.choice([15, 30, 45, 60, 90])
        elif mode == "late":
            arrival = f.fields["arrival"] + rng.choice([120, 180, 240, 300, 360])
        else:
            arrival = f.fields["arrival"] + rng.choice([-180, -120, -90, -60, -30, 30, 60, 90, 120, 180, 240])
        arrival = max(540, min(1410, int(round(arrival / 15.0)) * 15))
        if mode == "any" and rng.random() < 0.3:
            pickup = arrival + buf + rng.choice([-10, -5, 5, 10, 15])
            if pickup == t.fields["pickup"]:
                pickup += 15
            return {"op": "shift_reservation", "object_id": t.id, "payload": {"pickup": int(pickup)}}
        if arrival == f.fields["arrival"]:
            arrival = arrival + 30 if arrival + 30 <= 1410 else arrival - 30
        return {"op": "shift_reservation", "object_id": f.id, "payload": {"arrival": int(arrival)}}

    def nl_query(self, I: dict, state: State) -> str:
        o = state.get(I["object_id"])
        who = f"{o.fields['traveler']}, day {o.fields['day']}"
        if o.type == "flight":
            return f"Flight {o.id} ({who}) now arrives at {hhmm(I['payload']['arrival'])}."
        return f"Transfer {o.id} ({who}) will now pick up at {hhmm(I['payload']['pickup'])}."

    # ---------------------------------------------------------- mechanism
    def propagate(self, params, state: State, I: dict, tr: Tracker) -> List[Effect]:
        effects: List[Effect] = []
        src = state.get(I["object_id"])
        tr.read(src.id)
        if src.type == "flight":
            arrival = int(I["payload"]["arrival"])
            transfer = state.get(src.linked("transfer")[0])
            tr.read(transfer.id)
            p = transfer.fields["provider"]
            pickup = arrival + tr.get("buffer", p)
            kind = "auto" if tr.get("auto_rebook", p) else "txn"
            effects.append(Effect(kind, "shift_reservation", transfer.id, {"pickup": pickup}))
        elif src.type == "transfer":
            transfer = src
            pickup = int(I["payload"]["pickup"])
        else:
            raise Illegal("unsupported intervention source")
        stay = state.get(transfer.linked("stay")[0])
        tr.read(stay.id)
        checkin = pickup + transfer.fields["ride"]
        payload = {"checkin": checkin}
        would = 1 if checkin > stay.fields["late_cutoff"] else 0
        if would != stay.fields["late_arrival"]:
            if tr.get("enforce_late", stay.fields["hotel"]):
                payload["late_arrival"] = would
        effects.append(Effect("txn", "shift_reservation", stay.id, payload))
        dinner = state.get(stay.linked("dinner")[0])
        tr.read(dinner.id)
        dinner_changed = False
        if dinner.status == "active" and checkin + DINNER_LEAD > dinner.fields["start"]:
            if tr.get("late_seating", dinner.fields["restaurant"]):
                effects.append(Effect("txn", "shift_reservation", dinner.id,
                                      {"start": ceil15(checkin + DINNER_LEAD)}))
            else:
                effects.append(Effect("txn", "cancel_reservation", dinner.id, {}))
            dinner_changed = True
        if dinner_changed and dinner.linked("bundle"):
            bundle = state.get(dinner.linked("bundle")[0])
            tr.read(bundle.id)
            if tr.get("linked", bundle.fields["vendor"]):
                effects.append(Effect("txn", "rebook_bundle", bundle.id, {}))
        activity = state.get(stay.linked("activity")[0])
        tr.read(activity.id)
        if checkin + activity.fields["min_rest"] > activity.fields["start"]:
            effects.append(Effect("txn", "shift_reservation", activity.id,
                                  {"start": ceil15(checkin + activity.fields["min_rest"])}))
        return effects

    def apply_payload(self, state: State, obj: Obj, op: str, payload: dict) -> dict:
        delta = {}
        if op == "shift_reservation":
            allowed = self.SHIFT_FIELDS.get(obj.type, set())
            if not payload or any(k not in allowed for k in payload):
                raise Illegal(f"bad shift payload for {obj.type}: {sorted(payload)}")
            if obj.status != "active":
                raise Illegal(f"{obj.id} is {obj.status}")
            for k, v in payload.items():
                if not isinstance(v, int) or isinstance(v, bool):
                    raise Illegal(f"non-integer value for {k}")
                delta[k] = [obj.fields[k], v]
                obj.fields[k] = v
        elif op == "cancel_reservation":
            if obj.type != "dinner":
                raise Illegal("only dinners can be cancelled")
            if obj.status != "active":
                raise Illegal(f"{obj.id} is already {obj.status}")
            if payload:
                raise Illegal("cancel takes no payload")
            delta["status"] = [obj.status, "cancelled"]
            obj.status = "cancelled"
        elif op == "rebook_bundle":
            if obj.type != "bundle":
                raise Illegal("rebook_bundle needs a bundle")
            if payload:
                raise Illegal("rebook takes no payload")
            delta["rebooked"] = [obj.fields["rebooked"], obj.fields["rebooked"] + 1]
            obj.fields["rebooked"] += 1
        else:
            raise Illegal(f"unknown op {op}")
        return delta

    # ------------------------------------------ runtime-history oracle
    def infer_params(self, H: List[dict], S0: State, prov: Optional[dict] = None) -> dict:
        est: Dict[str, dict] = {"auto_rebook": {}, "buffer": {}, "enforce_late": {},
                                "late_seating": {}, "linked": {}}
        prov = prov if prov is not None else {}

        def note(name, key, *rids):
            prov[f"{name}[{key}]"] = sorted(set(rids))
        # reconstruct late flags before each segment by reverse-applying deltas
        flags = {s.id: s.fields["late_arrival"] for s in S0.by_type("stay")}
        for rec in reversed(H):
            d = rec.get("delta") or {}
            if "late_arrival" in d and rec["object_id"] in flags:
                flags[rec["object_id"]] = d["late_arrival"][0]
        for seg in segments(H):
            by_obj = {}
            for rec in seg:
                by_obj.setdefault(rec["object_id"], []).append(rec)
            for rec in seg:
                d = rec.get("delta") or {}
                oid = rec["object_id"]
                if oid not in S0.objects:
                    continue
                obj = S0.get(oid)
                if obj.type == "flight" and "arrival" in d:
                    tid = obj.linked("transfer")[0]
                    if tid in by_obj:
                        trec = by_obj[tid][0]
                        td = trec.get("delta") or {}
                        if "pickup" in td:
                            p = S0.get(tid).fields["provider"]
                            est["buffer"][p] = td["pickup"][1] - d["arrival"][1]
                            est["auto_rebook"][p] = int(trec["kind"] == "auto")
                            note("buffer", p, seg[0]["rid"], rec["rid"], trec["rid"])
                            note("auto_rebook", p, seg[0]["rid"], rec["rid"], trec["rid"])
                if obj.type == "stay" and "checkin" in d:
                    h = obj.fields["hotel"]
                    would = 1 if d["checkin"][1] > obj.fields["late_cutoff"] else 0
                    if "late_arrival" in d:
                        est["enforce_late"][h] = 1
                        flags[oid] = d["late_arrival"][1]
                        note("enforce_late", h, seg[0]["rid"], rec["rid"])
                    elif would != flags[oid]:
                        est["enforce_late"][h] = 0
                        note("enforce_late", h, seg[0]["rid"], rec["rid"])
                if obj.type == "dinner" and rec["kind"] == "txn":
                    r = obj.fields["restaurant"]
                    if rec["op"] == "shift_reservation":
                        est["late_seating"][r] = 1
                        note("late_seating", r, seg[0]["rid"], rec["rid"])
                    elif rec["op"] == "cancel_reservation":
                        est["late_seating"][r] = 0
                        note("late_seating", r, seg[0]["rid"], rec["rid"])
                    if obj.linked("bundle"):
                        b = S0.get(obj.linked("bundle")[0])
                        est["linked"][b.fields["vendor"]] = int(b.id in by_obj)
                        note("linked", b.fields["vendor"], seg[0]["rid"], rec["rid"],
                             *[x["rid"] for x in by_obj.get(b.id, [])])
        # a visible late flag implies enforcement
        for s in S0.by_type("stay"):
            if s.fields["late_arrival"] == 1 and s.fields["hotel"] not in est["enforce_late"]:
                est["enforce_late"][s.fields["hotel"]] = 1
                prov.setdefault(f"enforce_late[{s.fields['hotel']}]", [])
        return est

    # ------------------------------------------------ executor local rules
    def local_payload(self, scratch: State, obj: Obj, op: str, fields, tr: Tracker) -> dict:
        """Value of a repair given the structural decision (object, op, fields),
        computed from the current scratch state and whatever regime parameters
        the caller managed to read from history."""
        if op in ("cancel_reservation", "rebook_bundle"):
            return {}
        if obj.type == "transfer":
            flight = scratch.get(obj.linked("flight")[0])
            return {"pickup": flight.fields["arrival"] + tr.get("buffer", obj.fields["provider"])}
        if obj.type == "stay":
            transfer = scratch.get(obj.linked("transfer")[0])
            checkin = transfer.fields["pickup"] + transfer.fields["ride"]
            out = {"checkin": checkin}
            if fields and "late_arrival" in fields:
                out["late_arrival"] = 1 if checkin > obj.fields["late_cutoff"] else 0
            return out
        if obj.type == "dinner":
            stay = scratch.get(obj.linked("stay")[0])
            return {"start": ceil15(stay.fields["checkin"] + DINNER_LEAD)}
        if obj.type == "activity":
            stay = scratch.get(obj.linked("stay")[0])
            return {"start": ceil15(stay.fields["checkin"] + obj.fields["min_rest"])}
        raise Illegal(f"no local rule for {obj.type}/{op}")

    def param_keys_for(self, obj: Obj, state: State) -> List[tuple]:
        if obj.type == "transfer":
            return [("auto_rebook", obj.fields["provider"]), ("buffer", obj.fields["provider"])]
        if obj.type == "stay":
            return [("enforce_late", obj.fields["hotel"])]
        if obj.type == "dinner":
            return [("late_seating", obj.fields["restaurant"])]
        if obj.type == "bundle":
            return [("linked", obj.fields["vendor"])]
        return []

    def idempotent_write(self, obj: Obj):
        """A legal transaction that rewrites the object's current value."""
        if obj.status != "active":
            return None
        if obj.type in ("transfer", "stay", "dinner", "activity"):
            f = {"transfer": "pickup", "stay": "checkin", "dinner": "start", "activity": "start"}[obj.type]
            return ("shift_reservation", {f: obj.fields[f]})
        if obj.type == "bundle":
            return ("rebook_bundle", {})
        return None
