"""RoomEnv-v3 Oracle-C4: budgeted memory selection with a SHARED answerer.

Record stream per test step: sighting records (t, o, room) for co-located objects,
wall records (t, wall, bit) for the agent's room. One belief-propagation answerer
consumes whatever record subset a policy retains; policies differ ONLY in
which k records they keep for a query about object o at time t_q:

  full        : all records (upper bound for this answerer)
  recency@k   : k most recent records of any type
  random@k    : k uniform random records
  ledger@k    : k most recent sightings of o (object-specific, no walls)
  ancestor@k  : latest sighting of o + wall records of STRUCTURALLY RELEVANT
                walls (incident to o's reachable cone since the sighting,
                derived from the learned transition table = gold-equivalent
                structure at this scale), round-robin most-recent-first,
                then earlier sightings of o if budget remains.

Question: does ancestor@small-k approach full and beat same-budget non-causal
policies? (GPT go/no-go for "causal memory", not just "causal discovery".)

Usage: python3 code/roomenv_oracle_c4.py   [env K_TRAIN/K_TEST/T/ROOM]
"""

import json
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, "benchmarks/room-env")
sys.path.insert(0, "code")
from roomenv_c4 import DIRS, OPP, T, full_rollout, make_env, train  # noqa: E402

K_TRAIN = int(os.environ.get("K_TRAIN", 200))
K_TEST = int(os.environ.get("K_TEST", 20))
BUDGETS = [2, 4, 8, 16, 32]


def possible_next(table, o, r):
    out = {v for (oo, rr, _), v in table.items() if oo == o and rr == r}
    return out or {r}


def answer(records, o, t_q, model, rooms):
    """Shared answerer: phases from retained wall records, belief from latest
    retained sighting of o, propagated via the learned table."""
    pats = model["patterns"]
    phase = {wk: set(range(len(p))) for wk, p in pats.items()}
    for (kind, t, a, b) in records:
        if kind == "wall" and t <= t_q:
            p = pats[a]
            phase[a] = {k for k in phase[a] if p[(t + k) % len(p)] == b} or phase[a]
    sights = [(t, b) for (kind, t, a, b) in records if kind == "sight" and a == o and t <= t_q]
    if not sights:
        return 1.0 / len(rooms) if True else 0.0, len(rooms)
    t_s, room_s = max(sights)
    B = {room_s}
    for s in range(t_s, t_q):
        nb = set()
        for r in B:
            inc = sorted(model["incident"].get(r, []))
            combos = [()]
            for wk in inc:
                p = pats[wk]
                bits = {p[(s + k) % len(p)] for k in phase[wk]}
                combos = [c + (bb,) for c in combos for bb in bits]
            hit = False
            for c in combos:
                key = (o, r, c)
                if key in model["table"]:
                    nb.add(model["table"][key])
                    hit = True
            if not hit:
                nb |= possible_next(model["table"], o, r)
        B = nb
    return None, B


def score(B, truth, rooms):
    if isinstance(B, set):
        return (truth in B) / len(B)
    return B  # never-seen prior case already a float


def reachable_walls(model, o, room_s, horizon):
    R = {room_s}
    for _ in range(min(horizon, len(model["incident"]) + 8)):
        R = R | {v for r in R for v in possible_next(model["table"], o, r)}
    return R, {wk for r in R for wk in model["incident"].get(r, [])}


def select(policy, records, o, t_q, k, model, rng):
    past = [rec for rec in records if rec[1] <= t_q]
    if policy == "full":
        return past
    if policy == "recency":
        return past[-k:]
    if policy == "random":
        return rng.sample(past, min(k, len(past)))
    if policy == "ledger":
        s = [rec for rec in past if rec[0] == "sight" and rec[2] == o]
        return s[-k:]
    if policy == "ancestor":
        s = [rec for rec in past if rec[0] == "sight" and rec[2] == o]
        if not s:
            return []
        chosen = [s[-1]]
        t_s, room_s = s[-1][1], s[-1][3]
        _, rel = reachable_walls(model, o, room_s, t_q - t_s)
        per_wall = defaultdict(list)
        for rec in past:
            if rec[0] == "wall" and rec[2] in rel:
                per_wall[rec[2]].append(rec)
        queues = [list(reversed(v)) for v in per_wall.values()]
        qi = 0
        while len(chosen) < k and any(queues):
            q = queues[qi % len(queues)]
            if q:
                chosen.append(q.pop(0))
            qi += 1
            if all(not q for q in queues):
                break
        for rec in reversed(s[:-1]):
            if len(chosen) >= k:
                break
            chosen.append(rec)
        return chosen
    raise ValueError(policy)


def main():
    recs = [full_rollout(s)[0] for s in range(K_TRAIN)]
    model = train(recs)
    acc = defaultdict(list)
    used = defaultdict(list)
    for s in range(20_000, 20_000 + K_TEST):
        env, rooms = make_env(s)
        rng = random.Random(s)
        records, truth_log = [], []
        for _ in range(T - 1):
            t = env.current_step
            ar = env.agent_location
            seen = {o for o, r in env.moving_locations.items() if r == ar}
            for o in seen:
                records.append(("sight", t, o, ar))
            for wk in model["incident"].get(ar, []):
                r1, r2, d = model["dmap"][wk]
                dd = d if ar == r1 else OPP[d]
                bit = 1 if env.room_connections[ar].get(dd) == "wall" else 0
                records.append(("wall", t, wk, bit))
            truth_log.append((t, dict(env.moving_locations)))
            env.step(("x", rng.choice(DIRS + ["stay"])))
        qrng = random.Random(s + 1)
        for (t_q, locs) in truth_log[5::5]:          # query every 5 steps after warmup
            for o in model["objs"]:
                truth = locs[o]
                for pol in ("full", "recency", "random", "ledger", "ancestor"):
                    for k in ([None] if pol == "full" else BUDGETS):
                        sel = select(pol, records, o, t_q, k or 0, model, qrng)
                        prior, B = answer(sel, o, t_q, model, rooms)
                        v = prior if prior is not None else score(B, truth, rooms)
                        key = pol if pol == "full" else f"{pol}@{k}"
                        acc[key].append(v)
                        used[key].append(len(sel))

    def avg(v):
        return round(sum(v) / len(v), 3)

    out = {"config": {"K_train": K_TRAIN, "K_test": K_TEST, "T": T},
           "queries": len(acc["full"]),
           "accuracy": {k: avg(v) for k, v in sorted(acc.items())},
           "avg_records_used": {k: round(sum(v) / len(v), 1) for k, v in sorted(used.items())}}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
