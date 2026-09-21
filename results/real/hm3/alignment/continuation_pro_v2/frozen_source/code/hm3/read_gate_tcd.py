"""Established TCD on randomized read gates of a fixed HM3 executor.

This is a new, explicitly interventional input representation, not the old write
indicator bridge. At step t each visibility gate G_i(t) is randomized independently;
Y(t+1) is correctness of replaying that fixed episode under G(t). The fixed-state
replay resets between trials. No instance links or parser-derived graph restrict
candidate edges. The executor still uses the same domain parser inside the policy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np

from .domains import get_domain
from .generate import generate_split
from .grace_logs import fit_grace
from .replay import ExecutorOracle
from .structure_alignment import matched_records
from .tcd_logs import fit_pcmci


def panel(oracle, records, n, seed, keep=.8):
    rng = np.random.default_rng(seed)
    gates = (rng.random((n, len(records))) < keep).astype(float)
    outcomes = np.array([oracle([r for r, g in zip(records, mask) if g]) for mask in gates], float)
    X = np.zeros((n, len(records)+1))
    X[:, :-1] = gates
    X[1:, -1] = outcomes[:-1]
    return X, gates, outcomes


def empirical_effects(oracle, records, masks):
    """Held-out randomized-context flip effects, not an asserted complete oracle DAG."""
    effects = []
    for j, _ in enumerate(records):
        changed = 0
        for mask in masks:
            base = [r for i, r in enumerate(records) if i != j and mask[i]]
            changed += oracle(base) != oracle(base+[records[j]])
        effects.append(changed / len(masks))
    return effects


def incoming(fit, names):
    y = names[-1]
    return sorted({key.split("->")[0] for key in fit.get("edges", {})
                   if key.endswith(f"->{y}@1")})


def run(args):
    import tiktoken
    encoding = tiktoken.get_encoding("cl100k_base")
    domain = get_domain(args.domain)
    episodes = generate_split(domain, args.seed, args.split, args.episodes)
    result = {"config": vars(args), "interpretation": "interventional fixed-executor read-gate structure; not observational write causality or LLM evidence", "episodes": []}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for index, ep in enumerate(episodes):
        t0 = time.monotonic()
        records = [r["rid"] for r in ep.H]
        oracle = ExecutorOracle(domain, ep)
        X, masks, outcomes = panel(oracle, records, args.trials, args.mask_seed+index)
        names = [f"g{i}" for i in range(len(records))] + ["decision_correct"]
        trials = [(X, np.zeros(len(X), dtype=bool))]
        # Discard the initialized first Y row; all retained Y values are actual replays.
        trials = [(X[1:], np.zeros(len(X)-1, dtype=bool))]
        pcmci = fit_pcmci(trials, names, max_lag=1, alpha=.01)
        fits = {"pcmci_parcorr": pcmci}
        if not args.no_grace:
            fits["grace_pcmci_g2"] = fit_grace(trials, names, max_lag=1, skeleton_mode="pcmci_g2", seed=0,
                                               max_epochs=150, patience=30, lambda_scale=1)
        rng = np.random.default_rng(args.mask_seed+10000+index)
        heldout = rng.random((args.effect_contexts, len(records))) < .8
        effects = empirical_effects(oracle, records, heldout)
        empirical = {names[j] for j, value in enumerate(effects) if value > 0}
        summaries = {}
        for method, fit in fits.items():
            recovered = set(incoming(fit, names))
            selected = [records[names.index(g)] for g in sorted(recovered)]
            reference = {"objects": sorted(ep.S0.objects), "records": selected}
            controls = {}
            for random_seed in (17, 29, 43):
                reads, matching = matched_records(ep, reference, [], random_seed, encoding)
                controls[str(random_seed)] = {"correct": bool(oracle(reads["records"])), "records": reads["records"], **matching}
            summaries[method] = {"parents": sorted(recovered), "empirical_flip_precision": len(recovered & empirical)/len(recovered) if recovered else None,
                                 "empirical_flip_recall": len(recovered & empirical)/len(empirical) if empirical else None,
                                 "full_read_after_selection": bool(oracle(selected)),
                                 "selected_records": selected, "matched_random": controls}
        row = {"episode": ep.id, "n_records": len(records), "gate_to_record": dict(zip(names[:-1], records)),
               "train_success_rate": float(outcomes.mean()), "heldout_flip_effects": dict(zip(names[:-1], effects)),
               "empirical_effect_parents": sorted(empirical), "methods": summaries, "fits": fits,
               "unique_replay_contexts": len(oracle.cache), "seconds": time.monotonic()-t0}
        result["episodes"].append(row)
        out.write_text(json.dumps(result, indent=1))
        print(json.dumps({k: row[k] for k in ("episode", "n_records", "train_success_rate", "empirical_effect_parents", "methods", "seconds")}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--domain", default="travel")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--episodes", type=int, default=3)
    p.add_argument("--trials", type=int, default=512)
    p.add_argument("--effect-contexts", type=int, default=64)
    p.add_argument("--mask-seed", type=int, default=20260921)
    p.add_argument("--no-grace", action="store_true")
    p.add_argument("--out", default="results/development/hm3/alignment/read_gate_tcd.json")
    run(p.parse_args())
