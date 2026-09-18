"""Episode generator.

An episode is (H, S0, I, A, S1, R).  History H is produced by running earlier
interventions through the same hidden mechanism, so every witness in H is an
outcome (what the environment and the repair transactions did), never a
declarative policy statement.  Identifiability is enforced by construction:
after the test intervention is chosen, the generator keeps adding targeted
prior interventions until the runtime-history parser recovers every hidden
parameter the oracle consulted, from H alone.
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Dict, List, Optional

from .core import (Domain, Episode, Illegal, State, Tracker, execute_intervention,
                   execute_transactions, topology_hash)

DEFAULT_CFG = {"min_prior": 2, "max_prior": 5, "p_empty": 0.08, "max_cov": 14}


def _seed_int(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def run_segment(domain: Domain, params: dict, state: State, I: dict, H: List[dict], seg: int) -> None:
    """Execute one prior intervention in place and append its records to H."""
    query = domain.nl_query(I, state)
    tracker = Tracker(params)
    receipt, txns, _ = execute_intervention(domain, params, state, I, tracker)
    receipt += execute_transactions(domain, state, txns)
    n = len(H)
    for j, e in enumerate(receipt):
        rec = {"rid": f"h{n + j}", "seg": seg, "kind": e["kind"], "op": e["op"],
               "object_id": e["object_id"], "rev": e["rev"], "fee": e["fee"],
               "delta": e["delta"]}
        if e["kind"] == "intervention":
            rec["payload"] = dict(I["payload"])
            rec["query"] = query
        elif e["kind"] == "txn":
            rec["payload"] = next(t["payload"] for t in txns if t["object_id"] == e["object_id"])
        else:
            rec["payload"] = {k: v[1] for k, v in e["delta"].items()}
        H.append(rec)


def _covered(est: dict, pk: str, params: dict) -> bool:
    name, key = pk.split("[", 1)
    key = key[:-1]
    return est.get(name, {}).get(key) == params[name][key]


def _param_lookup(params: dict, name: str, key: str):
    return params[name][key]


def generate_episode(domain: Domain, seed: int, split: str, idx: int,
                     cfg: Optional[dict] = None, params_override: Optional[dict] = None,
                     world_state: Optional[tuple] = None, fixed_I: Optional[dict] = None) -> Episode:
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    rng = random.Random(_seed_int(domain.NAME, seed, split, idx))
    for _attempt in range(40):
        if world_state is not None:
            params, state = world_state[0], world_state[1].copy()
        else:
            params, state = domain.sample_world(rng, cfg)
        if params_override:
            params = json.loads(json.dumps(params))
            for name, kv in params_override.items():
                params[name].update(kv)
        H: List[dict] = []
        seg = 0
        for _ in range(rng.randint(cfg["min_prior"], cfg["max_prior"])):
            I = domain.sample_intervention(rng, params, state)
            if I is None:
                break
            run_segment(domain, params, state, I, H, seg)
            seg += 1
        I = None
        if fixed_I is not None:
            try:
                cand = domain.refresh_intervention(fixed_I, state)
                tr = Tracker(params)
                domain.propagate(params, state.copy(), cand, tr)
                I = cand
            except (Illegal, KeyError):
                continue
        for _ in range(12 if I is None else 0):
            cand = domain.sample_intervention(rng, params, state)
            if cand is None:
                continue
            tr = Tracker(params)
            effects = domain.propagate(params, state.copy(), cand, tr)
            if any(e.kind == "txn" for e in effects) or rng.random() < cfg["p_empty"]:
                I = cand
                break
        if I is None:
            continue
        avoid = set(tr.read_objects)
        missing: List[str] = []
        for _round in range(4):
            # (1) coverage: every parameter the test consults must be recoverable from H
            for _ in range(cfg["max_cov"]):
                est = domain.infer_params(H, state)
                missing = [pk for pk in tr.consulted if not _covered(est, pk, params)]
                if not missing:
                    break
                chosen = None
                for _try in range(8):
                    trial_state = state.copy()
                    I2 = domain.sample_intervention(rng, params, trial_state, avoid=avoid,
                                                    target_param=missing[0])
                    if I2 is None:
                        continue
                    trial_H = json.loads(json.dumps(H))
                    run_segment(domain, params, trial_state, I2, trial_H, seg)
                    if _covered(domain.infer_params(trial_H, trial_state), missing[0], params):
                        chosen = (trial_state, trial_H)
                        break
                if chosen is None:
                    break
                state, H = chosen
                seg += 1
                tr = Tracker(params)
                try:
                    domain.propagate(params, state.copy(), domain.refresh_intervention(I, state), tr)
                except Illegal:
                    missing = ["invalidated"]
                    break
                avoid |= set(tr.read_objects)
            if missing:
                break
            # (2) distractor witnesses: for every hidden family the test consults, also
            # exercise another key of that family, so that episode-level aggregates
            # (how many automatic events happened, how many cancellations) do not
            # reveal the regime of the entity the query actually touches
            if cfg.get("distractors", True):
                for pk in list(tr.consulted):
                    name, key = pk.split("[", 1)
                    key = key[:-1]
                    others = [k for k in params[name] if k != key]
                    if not others:
                        continue
                    other = rng.choice(others)
                    target = f"{name}[{other}]"
                    if _covered(domain.infer_params(H, state), target, params):
                        continue
                    for _try in range(4):
                        trial_state = state.copy()
                        I2 = domain.sample_intervention(rng, params, trial_state, avoid=avoid, target_param=target)
                        if I2 is None:
                            break
                        trial_H = json.loads(json.dumps(H))
                        run_segment(domain, params, trial_state, I2, trial_H, seg)
                        if _covered(domain.infer_params(trial_H, trial_state), target, params):
                            state, H = trial_state, trial_H
                            seg += 1
                            break
            # (3) the consulted set may have moved with the shared state: re-derive it and
            # go round again until coverage is a fixpoint
            tr = Tracker(params)
            try:
                domain.propagate(params, state.copy(), domain.refresh_intervention(I, state), tr)
            except Illegal:
                missing = ["invalidated"]
                break
            avoid |= set(tr.read_objects)
            est = domain.infer_params(H, state)
            missing = [pk for pk in tr.consulted if not _covered(est, pk, params)]
            if not missing:
                break
        if missing:
            continue
        I = domain.refresh_intervention(I, state)
        # coverage segments may have moved shared state (promos, verdicts); the
        # test intervention must still carry at least one manual repair unless
        # this episode was drawn as an intentionally empty one
        tr = Tracker(params)
        effects = domain.propagate(params, state.copy(), I, tr)
        if not any(e.kind == "txn" for e in effects) and rng.random() >= cfg["p_empty"]:
            continue
        S0 = state.copy()
        post = state.copy()
        tr = Tracker(params)
        receipt, txns, tr = execute_intervention(domain, params, post, I, tr)
        receipt += execute_transactions(domain, post, txns)
        prov: Dict[str, dict] = {}
        domain.infer_params(H, S0, prov)
        records = sorted({rid for pk in tr.consulted
                          for rid in prov.get(pk, [])})
        ep = Episode(
            id=f"{domain.NAME}-s{seed}-{split}-{idx:03d}", domain=domain.NAME, seed=seed,
            split=split, params=params, H=H, S0=S0, I=I, query=domain.nl_query(I, S0),
            A=txns, S1=post, R=receipt,
            required_reads={"objects": list(tr.read_objects), "records": records},
            affected=[t["object_id"] for t in txns],
            auto_affected=[e["object_id"] for e in receipt if e["kind"] == "auto"],
            relevant_params=list(tr.consulted), topology_hash=topology_hash(S0, params),
            n_prior_segments=seg,
        )
        return ep
    raise RuntimeError(f"could not generate an identifiable episode for {domain.NAME} seed={seed} idx={idx}")


def generate_split(domain: Domain, seed: int, split: str, n: int, cfg: Optional[dict] = None) -> List[Episode]:
    return [generate_episode(domain, seed, split, i, cfg) for i in range(n)]
