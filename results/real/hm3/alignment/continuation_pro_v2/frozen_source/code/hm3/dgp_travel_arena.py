"""Travel on MemoryArena's real entities (the substrate port, 2026-09-20).

Same hidden mechanism, same visible rules, same parser and executor as ``dgp_travel.TravelDomain``.
What changes is the vocabulary: every world is set in one real destination city from MemoryArena's
travel database; flights are real flight numbers with their real arrival times and origin cities,
stays are real accommodations of that city, dinners are real restaurants of that city.  The hidden
policies are keyed by those real names (enforce_late[<hotel name>], late_seating[<restaurant name>]).
Ground-transfer providers and activity bundles have no counterpart in the database and keep
generated ids, which the paper states.

The vocabulary is cached once in results/real/hm3/arena_vocab.json (build_vocab); worlds are sampled
from it deterministically.  Only cities with >= 4 accommodations, >= 4 restaurants and >= 12 arriving
flights landing between 10:00 and 20:30 are used, so the mechanism's time arithmetic stays in range.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Dict, List

from .core import Obj, State, ceil15, hhmm
from .dgp_travel import NAMES, TravelDomain

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "benchmarks" / "MemoryArena" / "env" / "env_systems" / "travel_planner_env" / "database"
VOCAB_PATH = ROOT / "results" / "real" / "hm3" / "arena_vocab.json"


def _minutes(hhmm_str: str) -> int:
    h, m = hhmm_str.split(":")
    return int(h) * 60 + int(m)


def build_vocab(max_flights_per_city: int = 60, min_hotels: int = 4, min_restaurants: int = 4, min_flights: int = 12) -> dict:
    import pandas as pd
    acc = pd.read_csv(DB / "accommodations" / "clean_accommodations_2022.csv").dropna(subset=["NAME", "city"])
    res = pd.read_csv(DB / "restaurants" / "clean_restaurant_2022.csv").dropna(subset=["Name", "City"])
    def ok(x) -> bool:
        # policy keys are written name[key]; Shopping's compound keys use "|": names with those characters are excluded
        x = str(x).strip()
        return bool(x) and not any(ch in x for ch in "[]|") and len(x) <= 60
    hotels: Dict[str, List[str]] = {str(c): sorted({str(x).strip() for x in g["NAME"] if ok(x)}) for c, g in acc.groupby("city")}
    rests: Dict[str, List[str]] = {str(c): sorted({str(x).strip() for x in g["Name"] if ok(x)}) for c, g in res.groupby("City")}
    flights: Dict[str, List[dict]] = {}
    seen: Dict[str, set] = {}
    cols = ["Flight Number", "ArrTime", "FlightDate", "OriginCityName", "DestCityName"]
    for chunk in pd.read_csv(DB / "flights" / "clean_Flights_2022.csv", usecols=cols, chunksize=500_000):
        chunk = chunk[cols].dropna()
        for fn, arr_s, date, origin, city in chunk.itertuples(index=False, name=None):
            city = str(city)
            if city not in hotels or city not in rests:
                continue
            lst = flights.setdefault(city, [])
            if len(lst) >= max_flights_per_city:
                continue
            try:
                arr = _minutes(str(arr_s))
            except ValueError:
                continue
            if not (600 <= arr <= 1230):
                continue
            fn = str(fn)
            if fn in seen.setdefault(city, set()):
                continue
            seen[city].add(fn)
            lst.append({"number": fn, "arrival": arr, "origin": str(origin), "date": str(date)})
    cities = sorted(c for c in flights if len(flights[c]) >= min_flights and len(hotels[c]) >= min_hotels and len(rests[c]) >= min_restaurants)
    vocab = {"cities": {c: {"hotels": hotels[c][:40], "restaurants": rests[c][:40], "flights": flights[c]} for c in cities},
             "source": "MemoryArena travel database (clean_*_2022.csv)", "n_cities": len(cities)}
    VOCAB_PATH.parent.mkdir(parents=True, exist_ok=True)
    json.dump(vocab, open(VOCAB_PATH, "w"))
    return vocab


_VOCAB = None


def vocab() -> dict:
    global _VOCAB
    if _VOCAB is None:
        if not VOCAB_PATH.exists():
            build_vocab()
        _VOCAB = json.load(open(VOCAB_PATH))
    return _VOCAB


class ArenaTravelDomain(TravelDomain):
    NAME = "travel_arena"

    def sample_world(self, rng: random.Random, cfg: dict):
        v = vocab()
        n_trav = cfg.get("n_travelers", 3)
        n_days = cfg.get("n_days", 2)
        city = rng.choice(sorted(v["cities"]))
        cv = v["cities"][city]
        used = set()

        def fresh(prefix):
            while True:
                cand = f"{prefix}{rng.randint(10, 99)}"
                if cand not in used:
                    used.add(cand)
                    return cand

        providers = [fresh("P") for _ in range(rng.choice([2, 3]))]
        hotels = rng.sample(cv["hotels"], rng.choice([2, 3]))
        restaurants = rng.sample(cv["restaurants"], rng.choice([2, 3]))
        vendors = [fresh("V") for _ in range(2)]
        params = {
            "auto_rebook": {p: int(rng.random() < 0.5) for p in providers},
            "buffer": {p: rng.choice([20, 25, 30, 35, 40, 45, 50, 55, 60]) for p in providers},
            "enforce_late": {h: int(rng.random() < 0.5) for h in hotels},
            "late_seating": {r: int(rng.random() < 0.5) for r in restaurants},
            "linked": {v: int(rng.random() < 0.5) for v in vendors},
        }
        travelers = rng.sample(NAMES, n_trav)
        flight_pool = list(cv["flights"])
        rng.shuffle(flight_pool)
        state = State(meta={"trip": fresh("TRIP"), "city": city, "days": n_days}, tokens=cfg.get("tokens", 80))
        for name in travelers:
            for day in range(1, n_days + 1):
                fl = flight_pool.pop() if flight_pool else {"number": fresh("F"), "arrival": rng.choice(range(600, 1230, 15)), "origin": "unknown", "date": ""}
                fid = fl["number"]
                used.add(fid)
                tid, sid, did, aid = (fresh("T"), fresh("S"), fresh("D"), fresh("A"))
                p = rng.choice(providers)
                h = rng.choice(hotels)
                r = rng.choice(restaurants)
                arrival = int(fl["arrival"])
                ride = rng.choice([20, 30, 40, 50])
                pickup = arrival + rng.choice(range(15, 80, 5))
                checkin = pickup + ride
                cutoff = rng.choice([1230, 1260, 1290, 1320, 1350, 1380])
                late = int(params["enforce_late"][h] and checkin > cutoff)
                dinner_start = max(ceil15(checkin + 45), rng.choice(range(1140, 1320, 15)))
                dinner_start += rng.choice([0, 15, 30, 45, 60])
                min_rest = rng.choice([480, 540, 600])
                act_start = max(ceil15(checkin + min_rest), 1440 + rng.choice(range(480, 660, 15)))
                act_start += rng.choice([0, 15, 30])
                flight = Obj(fid, "flight", {"traveler": name, "day": day, "arrival": arrival, "origin": fl["origin"], "dest": city}, {"transfer": [tid]})
                transfer = Obj(tid, "transfer", {"traveler": name, "day": day, "provider": p, "ride": ride, "pickup": pickup}, {"flight": [fid], "stay": [sid]})
                stay = Obj(sid, "stay", {"traveler": name, "day": day, "hotel": h, "late_cutoff": cutoff, "checkin": checkin, "late_arrival": late},
                           {"transfer": [tid], "dinner": [did], "activity": [aid]})
                dinner = Obj(did, "dinner", {"traveler": name, "day": day, "restaurant": r, "start": dinner_start}, {"stay": [sid]})
                activity = Obj(aid, "activity", {"traveler": name, "day": day, "start": act_start, "min_rest": min_rest}, {"stay": [sid]})
                for o in (flight, transfer, stay, dinner, activity):
                    state.add(o)
                if rng.random() < 0.75:
                    bid = fresh("B")
                    vv = rng.choice(vendors)
                    bundle = Obj(bid, "bundle", {"traveler": name, "day": day, "vendor": vv, "rebooked": 0}, {"stay": [sid], "dinner": [did]})
                    stay.links["bundle"] = [bid]
                    dinner.links["bundle"] = [bid]
                    state.add(bundle)
        return params, state

    def numeric_fields(self):
        return super().numeric_fields()

    def nl_query(self, I: dict, state: State) -> str:
        o = state.get(I["object_id"])
        who = f"{o.fields['traveler']}, day {o.fields['day']}"
        if o.type == "flight":
            route = f", {o.fields.get('origin', '?')} → {o.fields.get('dest', '?')}" if o.fields.get("origin") else ""
            return f"Flight {o.id} ({who}{route}) now arrives at {hhmm(I['payload']['arrival'])}."
        return f"Transfer {o.id} ({who}) will now pick up at {hhmm(I['payload']['pickup'])}."
