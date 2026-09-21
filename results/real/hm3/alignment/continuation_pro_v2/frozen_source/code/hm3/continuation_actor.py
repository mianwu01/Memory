"""Frozen stronger-actor read-dependence diagnostic. See continuation protocol.

Every trial is a fresh API call, including identical messages. Resume keys contain
the stage and repeat. Credentials and exception bodies never enter artifacts.
"""
from __future__ import annotations

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import threading
import time

import numpy as np

from .core import Episode, score_plan, segments, timeline
from .domains import get_domain
from .generate import generate_split
from .llm import build_messages, parse_transactions
from .scaling import bm25_topk
from .structure_alignment import digest, matched_records, ordered_reads

ROOT = Path(__file__).resolve().parents[2]
MODEL = "DeepSeek-V4-Pro"
ENDPOINT = "https://www.autodl.art/api/v1"
CONFIG = dict(model=MODEL, endpoint=ENDPOINT, max_tokens=16384, temperature=0,
              extra_body={"thinking": {"type": "disabled"}, "reasoning_effort": "none"},
              trials=128, keep=.8, mask_seed=20260922, repeats=3, top_k_segments=2,
              alpha=.05, test="Gsquared", seed_panel=[70, 71, 72], episodes_per_seed=2,
              max_requests=1200, format_retries=0, infrastructure_retries=0, timeout_seconds=300,
              unit="episode; repeated API calls averaged within episode")


def write_once(path, value):
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text() != text:
            raise ValueError(f"Frozen artifact mismatch: {path.name}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def state_diagnostic(ep):
    """Observable numeric fields at real segment boundaries; no hidden params."""
    snaps = timeline(ep.S0, ep.H)
    names = [(oid, field) for oid, obj in sorted(ep.S0.objects.items())
             for field, value in sorted(obj.fields.items())
             if isinstance(value, (int, float)) and field not in ("day",)]
    data = np.array([[s.get(oid).fields[field] for oid, field in names] for s in snaps])
    changes = np.count_nonzero(np.diff(data, axis=0), axis=0)
    return dict(episode=ep.id, names=[f"{o}.{f}" for o, f in names], values=data.tolist(),
                n_boundaries=len(data), n_fields=len(names), changes=changes.tolist(),
                changing_fields=int(np.count_nonzero(changes)),
                interpretation="Observable synthetic environment states; not LLM hidden states. "
                "Few segment transitions and many constant fields; no reliable full-SCM fit asserted.")


def fit_dependence(masks, outcomes):
    """Known randomized-input DAG restrictions, not a discovered full time graph."""
    from tigramite import data_processing as pp
    from tigramite.pcmci import PCMCI
    from tigramite.independence_tests.gsquared import Gsquared
    masks = np.asarray(masks, dtype=int)
    outcomes = np.asarray(outcomes, dtype=int)
    n, d = masks.shape
    # Add a trailing row so Y(t+1) is available for the final actual gate trial.
    # cut_off='2xtau_max' in PCMCI discards its standard initial boundary rows.
    panel = np.zeros((n+1, d+1), dtype=int)
    panel[:-1, :d] = masks
    panel[1:, d] = outcomes
    names = [f"segment_{i}" for i in range(d)] + ["correct"]
    assumptions = {i: {} for i in range(d+1)}
    assumptions[d] = {(i, -1): "-?>" for i in range(d)}
    df = pp.DataFrame(panel, var_names=names, data_type=np.ones_like(panel))
    fit = PCMCI(dataframe=df, cond_ind_test=Gsquared(significance="analytic"), verbosity=0)
    result = fit.run_pcmciplus(tau_min=1, tau_max=1, pc_alpha=.05,
                              link_assumptions=assumptions)
    p = result["p_matrix"][:d, d, 1]
    val = result["val_matrix"][:d, d, 1]
    ranking = sorted(range(d), key=lambda i: (float(p[i]), -float(val[i]), i))
    return dict(p_values=p.tolist(), statistics=val.tolist(), ranking=ranking,
                threshold_parents=[i for i in range(d) if result["graph"][i, d, 1] == "-->"],
                graph=result["graph"].tolist(), candidate_edges=d,
                known_design_constraint="only independent randomized gates -> correctness",
                outcome_constant=bool(len(set(outcomes)) == 1),
                train_success=float(outcomes.mean()), usable_lag_rows=n-1)


class Actor:
    def __init__(self, directory, key_file, max_requests=1200):
        from openai import OpenAI
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        keys = [x.strip() for x in Path(key_file).read_text().splitlines()
                if x.strip() and not x.strip().startswith("#")]
        self.clients = [OpenAI(api_key=k, base_url=ENDPOINT, timeout=CONFIG["timeout_seconds"], max_retries=0) for k in keys]
        self.lock = threading.Lock()
        self.ledger = self.directory / "ledger.jsonl"
        self.done = {}
        if self.ledger.exists():
            for line in self.ledger.read_text().splitlines():
                r = json.loads(line)
                self.done[r["job_id"]] = r
        self.started = len(self.done)
        self.max_requests = max_requests

    def ask(self, ep, reads, stage, repeat, *, visible_ep=None, memory_text=None, metadata=None):
        domain = get_domain(ep.domain)
        messages = build_messages(domain, visible_ep or ep, reads, "verbose")
        if memory_text is not None:
            prefix, rest = messages[1]["content"].split("### HISTORY", 1)
            _, suffix = rest.split("### CURRENT STATE", 1)
            messages[1]["content"] = (prefix + "### HISTORY (earlier interventions and what followed; verbose form)\n"
                                       + memory_text + "\n\n### CURRENT STATE" + suffix)
        sha = digest(messages)
        ident = digest([ep.id, stage, repeat, sha, MODEL])
        base = dict(job_id=ident, episode=ep.id, seed=ep.seed, stage=stage, repeat=repeat,
                    prompt_sha256=sha, reads=reads, metadata=metadata or {}, requested_model=MODEL)
        with self.lock:
            if ident in self.done:
                return self.done[ident]
            if self.started >= self.max_requests:
                raise RuntimeError("Frozen request bound exhausted")
            self.started += 1
            index = self.started
            write_once(self.directory / "inputs" / f"{sha}.json", messages)
            # Persist intent before network I/O, so interrupted in-flight calls are visible.
            with (self.directory / "requests.jsonl").open("a") as handle:
                handle.write(json.dumps({**base, "time": time.time()}) + "\n")
        start = time.monotonic()
        try:
            r = self.clients[index % len(self.clients)].chat.completions.create(
                model=MODEL, messages=messages, temperature=0, max_tokens=16384,
                extra_body=CONFIG["extra_body"])
            choice = r.choices[0]
            text = choice.message.content or ""
            txns = parse_transactions(text)
            try:
                score = score_plan(domain, ep, txns or [], reads)
                correct = bool(txns is not None and score["ees"])
                score_error = None
            except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
                score, correct, score_error = {}, False, type(exc).__name__
            usage = r.usage.model_dump() if r.usage else None
            if usage is None:
                raise ValueError("No usage in provider response")
            row = dict(**base, event="result", correct=correct, score=score,
                       score_error=score_error, parse_ok=txns is not None, txns=txns,
                       response=text, finish_reason=choice.finish_reason, usage=usage,
                       returned_model=r.model, seconds=time.monotonic()-start,
                       provider_cost_cny=getattr(r, "cost_cny", None),
                       legacy_rate_estimate_usd=(r.usage.prompt_tokens*2.5+r.usage.completion_tokens*10)/1e6,
                       cost_note="Legacy-rate scenario only; NOT Pro pricing or provider invoice")
        except Exception as exc:
            row = dict(**base, event="infrastructure_failure", error_type=type(exc).__name__,
                       status=getattr(exc, "status_code", None), seconds=time.monotonic()-start)
        with self.lock:
            with self.ledger.open("a") as handle:
                handle.write(json.dumps(row) + "\n")
            self.done[ident] = row
            if index % 16 == 0 or stage != "train":
                print(json.dumps(dict(call=index, episode=ep.id, stage=stage,
                                      correct=row.get("correct"), event=row["event"])), flush=True)
        return row


def prepare(directory, smoke=False):
    directory = Path(directory)
    source_hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                     ["code/hm3/continuation_actor.py", "code/hm3/llm.py", "code/hm3/core.py",
                      "code/hm3/generate.py", "code/hm3/dgp_travel.py",
                      "docs/continuation-protocol-2026-09-22.md"]}
    config = {**CONFIG, "source_hashes": source_hashes, "smoke": smoke}
    write_once(directory / "protocol.json", config)
    domain = get_domain("travel")
    eps = generate_split(domain, 2, "dev", 1) if smoke else [
        ep for seed in CONFIG["seed_panel"] for ep in generate_split(domain, seed, "test", 2)]
    write_once(directory / "episodes.json", [ep.to_dict() for ep in eps])
    write_once(directory / "state_panels.json", [state_diagnostic(ep) for ep in eps])
    manifests = []
    for index, ep in enumerate(eps):
        groups = [[r["rid"] for r in s] for s in segments(ep.H)]
        masks = (np.random.default_rng(CONFIG["mask_seed"]+index).random((128, len(groups))) < .8).astype(int)
        manifests.append(dict(episode=ep.id, groups=groups, masks=masks.tolist(),
                              source_labels={r: ("disallowed_external_cache" if j == 0 else "authorized_event_log")
                                             for j, group in enumerate(groups) for r in group}))
    write_once(directory / "manifests.json", manifests)
    return eps, manifests


def validation_arms(ep, groups, fitted):
    import tiktoken
    encoder = tiktoken.get_encoding("cl100k_base")
    full = [r["rid"] for r in ep.H]
    chosen = fitted["ranking"][:2]
    selected = [r for j in chosen for r in groups[j]]
    reference = ordered_reads(ep, sorted(ep.S0.objects), selected)
    k = len(selected)
    arms = {"learned_top2": (reference, {}), "full": (ordered_reads(ep, ep.S0.objects, full), {}),
            "query_only": (ordered_reads(ep, ep.S0.objects, []), {}),
            "recency_matched": (ordered_reads(ep, ep.S0.objects, full[-k:] if k else []), {}),
            "bm25_matched": (ordered_reads(ep, ep.S0.objects, bm25_topk(ep, k)), {})}
    for seed in (17, 29, 43):
        perm = np.random.default_rng(seed).permutation(len(groups)).tolist()
        preferred = [r for j in chosen for r in groups[perm[j]]]
        arms[f"wrong_{seed}"] = matched_records(ep, reference, preferred, seed, encoder)
        arms[f"random_{seed}"] = matched_records(ep, reference, [], seed, encoder)
    suspect, neutral = set(groups[0]), set(groups[-1])
    arms["source_blocked"] = (ordered_reads(ep, ep.S0.objects, [r for r in full if r not in suspect]), {})
    arms["neutral_blocked"] = (ordered_reads(ep, ep.S0.objects, [r for r in full if r not in neutral]), {})
    arms["source_changed"] = arms["full"]
    changed = copy.deepcopy(ep)
    time_fields = {"arrival", "pickup", "checkin", "start"}
    for r in changed.H:
        if r["rid"] not in suspect:
            continue
        for field, pair in r.get("delta", {}).items():
            if field in time_fields:
                r["delta"][field] = [v+15 for v in pair]
                if field in r.get("payload", {}):
                    r["payload"][field] += 15
        if "query" in r:
            # Re-render the visible historical intervention to avoid internal text contradictions.
            event = dict(object_id=r["object_id"], op=r["op"], payload=r["payload"])
            r["query"] = get_domain(ep.domain).nl_query(event, changed.S0)
    return arms, changed


def run(args):
    out = Path(args.out)
    eps, manifests = prepare(out, args.stage == "smoke")
    if args.stage == "prepare":
        print(json.dumps({"episodes": len(eps), "state_panels": str(out / "state_panels.json")}))
        return
    actor = Actor(out, args.key_file)
    if args.stage == "smoke":
        ep = eps[0]
        row = actor.ask(ep, ordered_reads(ep, ep.S0.objects, [r["rid"] for r in ep.H]), "smoke", 0)
        print(json.dumps({k: row.get(k) for k in ["event", "returned_model", "correct", "finish_reason", "usage"]}))
        return
    for ep, manifest in zip(eps, manifests):
        groups = manifest["groups"]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(actor.ask, ep,
                                ordered_reads(ep, ep.S0.objects, [r for g, bit in zip(groups, mask) if bit for r in g]),
                                "train", i, metadata={"mask": mask})
                    for i, mask in enumerate(manifest["masks"])]
            train = [f.result() for f in jobs]
        if any(r["event"] != "result" for r in train):
            write_once(out / f"{ep.id}_incomplete.json", {"status": "training infrastructure failures; fit withheld"})
            continue
        fitted = fit_dependence(manifest["masks"], [r["correct"] for r in train])
        write_once(out / f"{ep.id}_fit.json", fitted)
        arms, changed = validation_arms(ep, groups, fitted)
        write_once(out / f"{ep.id}_arms.json", arms)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(actor.ask, ep, reads, name, repeat,
                                visible_ep=changed if name == "source_changed" else None, metadata=meta)
                    for name, (reads, meta) in arms.items() for repeat in range(3)]
            for job in jobs:
                job.result()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument("--stage", choices=["prepare", "smoke", "run"], default="prepare")
    p.add_argument("--key-file", default="api/api.txt")
    p.add_argument("--workers", type=int, default=8)
    run(p.parse_args())
