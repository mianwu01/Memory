"""Reproducible discovery-vs-link/parser audit, with no model-service calls.

All task labels are used only by score_plan, never by selectors or budget matching.
Historical GRACE artifacts are frozen. Complete adjacency removes learned type
filtering but retains instance links. This is deliberately a strong control.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
from pathlib import Path

import numpy as np

from .core import FallbackTracker, execute_intervention, restricted_est, score_plan, segments
from .domains import get_domain
from .generate import generate_split
from .keysel import _neighbours, key_precedent_records
from .llm import build_messages, serialize_history
from .scaling import augment_split, bm25_topk
from .tcd_logs import TCDSelect, adjacency_reads, compare, type_edges_with_lag, type_vocab

PERMUTATION_SEEDS = (17, 29, 43)
CONDITIONS = {"native": (None, ""), "100": (100, "abcd"),
              "c100": (100, "c"), "500": (500, "abcd")}
TRAVEL_MECHANISM = {("flight", "transfer"), ("transfer", "stay"),
                    ("stay", "dinner"), ("stay", "activity"), ("dinner", "bundle")}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def permutations(types):
    """Three distinct nonidentity permutations fixed without outcome information."""
    choices = [p for p in itertools.permutations(types) if list(p) != types]
    used, out = set(), {}
    for seed in PERMUTATION_SEEDS:
        available = [p for p in choices if p not in used]
        if not available:
            raise ValueError("fewer than three nonidentity type permutations")
        p = random.Random(seed).choice(available)
        used.add(p)
        out[seed] = dict(zip(types, p))
    return out


def response_precedent_records(domain, ep, objects, n_prec=2):
    """Latest same-key *responses to linked upstream interventions*, whole segment.

    Generic link/event metadata only; no parameter parser, learned graph, gold
    fields or domain arithmetic. This is an explicitly non-CD retrieval baseline.
    A target absent from an upstream segment can also be an informative response.
    """
    S0 = ep.S0
    segs = segments(ep.H)
    cats = domain.categorical_fields()
    chosen = set()
    for oid in objects:
        obj = S0.get(oid)
        for field in cats.get(obj.type, []):
            value = obj.fields.get(field)
            if value is None:
                continue
            same = {o.id for o in S0.objects.values()
                    if o.type == obj.type and o.fields.get(field) == value}
            near = {x: _neighbours(S0, x) for x in same}
            hits = []
            for si, seg in enumerate(segs):
                if not seg or seg[0]["kind"] != "intervention":
                    continue
                src = seg[0]["object_id"]
                if any(src != x and src in near[x] for x in same):
                    hits.append(si)
            if hits:
                for si in hits[-n_prec:]:
                    chosen.update(r["rid"] for r in segs[si])
            else:
                chosen.update(key_precedent_records(domain, ep, [oid], n_prec))
    return [r["rid"] for r in ep.H if r["rid"] in chosen]


def execute_reads(domain, ep, reads):
    est = restricted_est(domain, ep.H, ep.S0, reads["records"])
    tr = FallbackTracker(est)
    error = None
    try:
        _, txns, _ = execute_intervention(domain, est, ep.S0.copy(), ep.I, tr)
    except Exception as exc:
        txns, error = [], type(exc).__name__
    result = score_plan(domain, ep, txns, reads)
    result["execution_error"] = error
    result["unknown_parameters"] = len(tr.unknown)
    return result


def ordered_reads(ep, objects, records):
    rs = set(records)
    return {"objects": sorted(set(objects)), "records": [r["rid"] for r in ep.H if r["rid"] in rs]}


def matched_records(ep, reference, preferred, seed, encoding, eligible=None):
    """Match K and proxy token budget using label-blind length swaps.

    Objects remain exactly the reference objects. A preferred ordering is provided
    by a permuted graph or shuffled record order. Up to 100 swaps reduce the token
    residual; all departures from the initial selection are recorded.
    """
    order = {r["rid"]: i for i, r in enumerate(ep.H)}
    pool = set(order) if eligible is None else set(eligible)
    if not set(reference["records"]).issubset(pool):
        raise ValueError("matching pool must contain the reference records")
    all_ids = [r for r in order if r in pool]
    k = len(reference["records"])
    rng = random.Random(int(digest([ep.id, seed])[:12], 16))
    fallback = all_ids[:]
    rng.shuffle(fallback)
    ranked = list(dict.fromkeys([r for r in preferred if r in pool] + fallback))
    chosen = ranked[:k]
    target = len(encoding.encode(serialize_history(ep.H, reference["records"], "verbose")))
    lengths = {r["rid"]: len(encoding.encode(json.dumps(r, indent=2))) for r in ep.H}

    def tokens(ids):
        return len(encoding.encode(serialize_history(ep.H, sorted(ids, key=order.get), "verbose")))

    current = tokens(chosen)
    swaps = 0
    for _ in range(100):
        residual = target - current
        if residual == 0 or not chosen or k == len(all_ids):
            break
        chosen_set = set(chosen)
        outside = [r for r in ranked if r not in chosen_set]
        candidates = sorted(((abs(residual - (lengths[b] - lengths[a])), i, b)
                             for i, a in enumerate(chosen) for b in outside))[:12]
        best = None
        for _, i, b in candidates:
            trial = chosen[:]
            trial[i] = b
            size = tokens(trial)
            if abs(target-size) < abs(target-current) and (best is None or abs(target-size) < best[0]):
                best = (abs(target-size), trial, size)
        if best is None:
            break
        _, chosen, current = best
        swaps += 1
    assert len(set(chosen)) == k
    reads = ordered_reads(ep, reference["objects"], chosen)
    return reads, {"target_history_proxy_tokens": target, "history_proxy_tokens": current,
                   "token_residual": current-target, "exact_record_count": True,
                   "exact_object_context": True, "length_matching_swaps": swaps}


def selections(domain, ep, graphs, include_matched, encoding):
    out = {}
    selection_cache = {}
    for name, adjacency in graphs.items():
        object_key = tuple(sorted(adjacency_reads(ep, adjacency)))
        for reader in ("parser", "key2"):
            cache_key = (object_key, reader)
            if cache_key not in selection_cache:
                selector = TCDSelect("parser" if reader == "parser" else "key", n_prec=2, lag_aware=True)
                selector.adj = adjacency
                selection_cache[cache_key] = selector.select(domain, ep)
            out[f"{name}/{reader}"] = (selection_cache[cache_key], {})
    complete = out["complete/parser"][0]
    response = response_precedent_records(domain, ep, complete["objects"])
    out["complete/response2"] = (ordered_reads(ep, complete["objects"], response), {})
    out["full"] = (ordered_reads(ep, ep.S0.objects, [r["rid"] for r in ep.H]), {})
    for name, ids in (("bm25_16", bm25_topk(ep, 16)), ("recency_16", [r["rid"] for r in ep.H[-16:]])):
        # Same object context isolates record retrieval from object visibility.
        out[name] = (ordered_reads(ep, complete["objects"], ids), {})
    if include_matched:
        ref = out["grace_open_x3/parser"][0]
        for seed in PERMUTATION_SEEDS:
            preferred = out[f"permuted_{seed}/parser"][0]["records"]
            out[f"permuted_{seed}/matched"] = matched_records(ep, ref, preferred, seed, encoding)
            out[f"random_{seed}/matched"] = matched_records(ep, ref, [], seed, encoding)
    return out


def summarize_rows(rows):
    metrics = ("ees", "required_read_recall", "n_records", "n_objects", "input_proxy_tokens",
               "same_reads_as_complete", "same_prompt_as_complete", "unknown_parameters")
    return {"n": len(rows), **{k: float(np.mean([r[k] for r in rows])) for k in metrics},
            "max_abs_token_residual": max((abs(r.get("token_residual", 0)) for r in rows), default=0)}


def run(args):
    import tiktoken
    encoding = tiktoken.get_encoding("cl100k_base")
    graph_bytes = Path(args.graphs).read_bytes()
    fitted = json.loads(graph_bytes)["runs"]
    config = vars(args).copy()
    config.update({"graph_artifact_sha256": hashlib.sha256(graph_bytes).hexdigest(),
                   "tokenizer_proxy": "cl100k_base; not DeepSeek's tokenizer",
                   "actor_called": False, "permutation_seeds": PERMUTATION_SEEDS})
    result = {"config": config, "runs": {}}
    out = Path(args.out)
    if out.exists():
        old = json.loads(out.read_text())
        if old["config"] != json.loads(json.dumps(config)):
            raise ValueError("output exists with a different protocol; choose a new output")
        result = old
    for dname in args.domains:
        domain = get_domain(dname)
        for seed in args.seeds:
            native = generate_split(domain, seed, args.split, args.n_eval)
            types = type_vocab(native)
            complete = {(a, b): 1 for a in types for b in types if a != b}
            graph_seed = seed if args.graph_seed is None else args.graph_seed
            entry = fitted[f"{dname}/seed{graph_seed}"]
            graphs = {"complete": complete, "query_only": {}}
            for mode in ("grace_open", "grace_open_x3", "grace_pcmci_g2"):
                graphs[mode] = type_edges_with_lag(entry["encodings"]["event"][mode])
            perms = permutations(types)
            for pseed, p in perms.items():
                graphs[f"permuted_{pseed}"] = {(p[a], p[b]): lag for (a, b), lag in graphs["grace_open_x3"].items()}
            for condition in args.conditions:
                key = f"{dname}/seed{seed}/{condition}"
                if key in result["runs"]:
                    continue
                target, mix = CONDITIONS[condition]
                eps, aug = (native, {}) if condition == "native" else augment_split(domain, native, target, mix, f"{args.split}{seed}")
                rows = {}
                for ep in eps:
                    arms = selections(domain, ep, graphs, not args.no_matched, encoding)
                    ref = arms["complete/parser"][0]
                    ref_hash = digest(build_messages(domain, ep, ref, "verbose"))
                    evaluation_cache = {}
                    for arm, (reads, match) in arms.items():
                        read_hash = digest(reads)
                        if read_hash not in evaluation_cache:
                            score = execute_reads(domain, ep, reads)
                            messages = build_messages(domain, ep, reads, "verbose")
                            tokens = sum(len(encoding.encode(m["content"])) for m in messages)
                            evaluation_cache[read_hash] = (score, digest(messages), tokens)
                        score, prompt_hash, tokens = evaluation_cache[read_hash]
                        row = {"episode": ep.id, "ees": bool(score["ees"]),
                               "required_read_recall": score["required_read_recall"],
                               "n_records": len(reads["records"]), "n_objects": len(reads["objects"]),
                               "unknown_parameters": score["unknown_parameters"],
                               "input_proxy_tokens": tokens,
                               "same_reads_as_complete": reads == ref,
                               "same_prompt_as_complete": prompt_hash == ref_hash,
                               "reads": reads, "prompt_sha256": prompt_hash, **match}
                        rows.setdefault(arm, []).append(row)
                refs = {"template_reference": entry["skeleton_type_edges"]}
                if dname == "travel":
                    refs["mechanism_reference"] = sorted(f"{a}->{b}" for a, b in TRAVEL_MECHANISM)
                    refs["vs_mechanism"] = {name: compare(set(g), TRAVEL_MECHANISM) for name, g in graphs.items()}
                result["runs"][key] = {"augmentation": aug, "n_requested": args.n_eval, "n": len(eps),
                                        "references": refs, "type_permutations": perms,
                                        "arms": {name: {"summary": summarize_rows(rs), "rows": rs} for name, rs in rows.items()}}
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(result, indent=1))
                short = {a: {k: v["summary"][k] for k in ("ees", "n_records", "same_reads_as_complete")}
                         for a, v in result["runs"][key]["arms"].items()
                         if a in ("complete/parser", "complete/key2", "complete/response2", "grace_open_x3/parser", "query_only/parser")}
                print(json.dumps({"cell": key, "n": len(eps), "summary": short}), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domains", nargs="+", default=["travel", "shopping32"])
    parser.add_argument("--seeds", nargs="+", type=int, default=[30, 31, 32])
    parser.add_argument("--graph-seed", type=int, default=None)
    parser.add_argument("--split", default="test")
    parser.add_argument("--n-eval", type=int, default=64)
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    parser.add_argument("--graphs", default="results/real/hm3/tcd/grace_graphs_test.json")
    parser.add_argument("--no-matched", action="store_true")
    parser.add_argument("--out", required=True)
    run(parser.parse_args())
