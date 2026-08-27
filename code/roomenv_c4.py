"""RoomEnv-v3 C4: does learned structure beat recency on downstream QA?

Training phase (full state logged, as in Layer-1 discovery): K rollouts ->
  (a) per-object transition table keyed by (room, bits of INCIDENT walls) —
      the conditioning set comes from the discovered/derived local structure;
  (b) per-wall periodic pattern (canonical rotation).
Test phase (partial observation only): agent random-walks; sees co-located
objects + own room's connections. Memory policies answer "where is object o now?"
every step for every moving object:
  recency   : last room where o was sighted (never seen -> uniform random);
  tracker   : belief set propagated through the LEARNED table + LEARNED wall
              patterns with phase inferred online from local wall observations;
  oracle    : same tracker with TRUE mechanisms and TRUE phases (upper bound).
Scoring: expected accuracy (truth in belief)/|belief|; recency = exact match.

Usage: python3 code/roomenv_c4.py   [env K_TRAIN/K_TEST/T]
"""

import json
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, "benchmarks/room-env")
sys.path.insert(0, "code")
from room_env.envs.room3 import RoomEnv3  # noqa: E402

K_TRAIN = int(os.environ.get("K_TRAIN", 200))
K_TEST = int(os.environ.get("K_TEST", 50))
T = int(os.environ.get("T", 100))
ROOM = os.environ.get("ROOM", "small-01")
DIRS = ["north", "east", "south", "west"]
OPP = {"north": "south", "south": "north", "east": "west", "west": "east"}


def make_env(seed):
    random.seed(seed)
    env = RoomEnv3(terminates_at=T - 1, room_size=ROOM)
    env.reset()
    rooms = list(env.room_connections.keys())
    env.moving_locations = {o: random.choice(rooms) for o in env.moving_locations}
    for w in env.wall_configs:
        p = env.wall_configs[w]
        k = random.randrange(len(p))
        env.wall_configs[w] = p[k:] + p[:k]
    env._update_wall_layout()
    return env, rooms


def full_rollout(seed):
    env, rooms = make_env(seed)
    rec = []
    for _ in range(T):
        t = env.current_step
        rec.append({"loc": dict(env.moving_locations),
                    "walls": {"|".join(w): p[t % len(p)] for w, p in env.wall_configs.items()},
                    "conn": {r: dict(c) for r, c in env.room_connections.items()}})
        env.step(("x", "stay"))
    return rec, dict(env.movement_preferences)


def minimal_period(seq):
    for p in range(1, len(seq) + 1):
        if all(seq[i] == seq[i % p] for i in range(len(seq))):
            return seq[:p]
    return seq


def train(recs):
    walls = sorted(recs[0][0]["walls"].keys())
    objs = sorted(recs[0][0]["loc"].keys())
    # wall -> (r1, r2, direction) learned from steps where inactive
    dmap = {}
    for rec in recs:
        for step in rec:
            for wk in walls:
                if wk in dmap or step["walls"][wk] == 1:
                    continue
                r1, r2, _ = wk.split("|")
                for d in DIRS:
                    if step["conn"][r1].get(d) == r2:
                        dmap[wk] = (r1, r2, d)
    incident = defaultdict(list)
    for wk, (r1, r2, _) in dmap.items():
        incident[r1].append(wk)
        incident[r2].append(wk)
    # canonical patterns (phase differs per rollout -> learn from one rollout each)
    patterns = {wk: minimal_period([step["walls"][wk] for step in recs[0]]) for wk in walls}
    # transition table keyed by (obj, room, incident-wall bits)
    table = {}
    for rec in recs:
        for i in range(len(rec) - 1):
            for o in objs:
                r = rec[i]["loc"][o]
                key = (o, r, tuple(rec[i]["walls"][wk] for wk in sorted(incident[r])))
                nxt = rec[i + 1]["loc"][o]
                if key in table and table[key] != nxt:
                    raise RuntimeError(f"non-deterministic table entry {key}")
                table[key] = nxt
    return {"walls": walls, "objs": objs, "dmap": dmap, "incident": dict(incident),
            "patterns": patterns, "table": table}


def neighbors(conn_room):
    return [v for v in conn_room.values() if v != "wall"]


class Tracker:
    """Belief tracker over object locations using learned structure."""

    def __init__(self, model, rooms, oracle=None):
        self.m = model
        self.rooms = rooms
        self.B = {o: set(rooms) for o in model["objs"]}
        # phase candidates per wall: offset k means bit(t) = pattern[(t+k) % len]
        self.phase = {wk: set(range(len(p))) for wk, p in model["patterns"].items()}
        self.oracle = oracle  # (true_prefs, true_bits_fn, true_conn_fn) or None

    def wall_bit(self, wk, t):
        p = self.m["patterns"][wk]
        bits = {p[(t + k) % len(p)] for k in self.phase[wk]}
        return bits  # set of possible bits

    def observe(self, t, agent_room, conn_agent_room, seen_objects):
        for wk in self.m["incident"].get(agent_room, []):
            r1, r2, d = self.m["dmap"][wk]
            dd = d if agent_room == r1 else OPP[d]
            bit = 1 if conn_agent_room.get(dd) == "wall" else 0
            p = self.m["patterns"][wk]
            self.phase[wk] = {k for k in self.phase[wk] if p[(t + k) % len(p)] == bit}
            if not self.phase[wk]:
                self.phase[wk] = set(range(len(p)))  # noise guard (shouldn't happen)
        for o in self.m["objs"]:
            if o in seen_objects:
                self.B[o] = {agent_room}
            else:
                self.B[o].discard(agent_room)
                if not self.B[o]:
                    self.B[o] = set(self.rooms)

    def propagate(self, t):
        for o in self.m["objs"]:
            nb = set()
            for r in self.B[o]:
                inc = sorted(self.m["incident"].get(r, []))
                combos = [()]
                for wk in inc:
                    bits = self.wall_bit(wk, t)
                    combos = [c + (b,) for c in combos for b in bits]
                hit = False
                for c in combos:
                    key = (o, r, c)
                    if key in self.m["table"]:
                        nb.add(self.m["table"][key])
                        hit = True
                if not hit:                       # unseen context: any move possible
                    nb.add(r)
                    nb |= set(self.rooms)         # conservative fallback
            self.B[o] = nb

    def answer(self, o, truth):
        return (truth in self.B[o]) / len(self.B[o])


def next_room_true(loc, conn, pref):
    for d in pref:
        if conn[loc].get(d, "wall") != "wall":
            return conn[loc][d]
    return loc


def main():
    # ---- train ----
    recs = [full_rollout(s)[0] for s in range(K_TRAIN)]
    prefs = full_rollout(0)[1]
    model = train(recs)
    print(json.dumps({"table_entries": len(model["table"]),
                      "patterns": {k: len(v) for k, v in model["patterns"].items()}}))

    # ---- test ----
    res = defaultdict(list)
    stale_bins = [(0, 0), (1, 2), (3, 5), (6, 10), (11, 10**6)]
    by_stale = {name: defaultdict(list) for name in ("recency", "tracker", "oracle")}
    for s in range(10_000, 10_000 + K_TEST):
        env, rooms = make_env(s)
        rng = random.Random(s)
        tr = Tracker(model, rooms)
        orc = Tracker(model, rooms)
        # oracle gets true phases and the full table refreshed with true mechanism
        orc.phase = {wk: {0} for wk in model["walls"]}
        orc_true_bits = {wk: env.wall_configs[tuple(wk.split("|"))]
                         if tuple(wk.split("|")) in env.wall_configs else None
                         for wk in model["walls"]}
        # env.wall_configs keys are tuples; align patterns to THIS episode's rotation
        for wk in model["walls"]:
            key = tuple(wk.split("|"))
            orcp = env.wall_configs[key]
            orc.m = dict(orc.m)
            orc.m["patterns"] = {**orc.m["patterns"], wk: list(orcp)}
        last_seen = {o: None for o in model["objs"]}
        for _ in range(T - 1):
            t = env.current_step
            agent_room = env.agent_location
            conn_agent = dict(env.room_connections[agent_room])
            seen = {o for o, r in env.moving_locations.items() if r == agent_room}
            for o in seen:
                last_seen[o] = (t, agent_room)
            tr.observe(t, agent_room, conn_agent, seen)
            orc.observe(t, agent_room, conn_agent, seen)
            # QA at time t about current locations
            for o in model["objs"]:
                truth = env.moving_locations[o]
                if last_seen[o] is None:
                    r_ans = 1.0 / len(rooms)
                    stale = 10**6
                else:
                    r_ans = 1.0 if last_seen[o][1] == truth else 0.0
                    stale = t - last_seen[o][0]
                res["recency"].append(r_ans)
                res["tracker"].append(tr.answer(o, truth))
                res["oracle"].append(orc.answer(o, truth))
                for (lo, hi) in stale_bins:
                    if lo <= stale <= hi:
                        by_stale["recency"][(lo, hi)].append(r_ans)
                        by_stale["tracker"][(lo, hi)].append(tr.answer(o, truth))
                        by_stale["oracle"][(lo, hi)].append(orc.answer(o, truth))
            tr.propagate(t)
            orc.propagate(t)
            env.step(("x", rng.choice(DIRS + ["stay"])))

    def avg(v):
        return round(sum(v) / len(v), 3) if v else None

    out = {"config": {"room": ROOM, "K_train": K_TRAIN, "K_test": K_TEST, "T": T},
           "qa_count": len(res["recency"]),
           "accuracy": {k: avg(v) for k, v in res.items()},
           "by_staleness": {k: {f"{lo}-{hi if hi < 10**6 else 'inf'}": avg(v)
                                for (lo, hi), v in sorted(d.items())}
                            for k, d in by_stale.items()}}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
