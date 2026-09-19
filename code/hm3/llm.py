"""Full-runtime arm: an LLM receives (H, S0, I) under a selection x
serialization cell and must emit the repair transactions itself.

Selection (which memory reaches the model)      Serialization (how it is written)
  exact    the source object and its own records   verbose  pretty JSON, every field
  source   source-impact-union candidates          compact  one terse line per object / record
  graph    the learned graph's reads (objects it evaluated + witness records)
  program  the program learner's plan objects, their 1-hop neighbours, their records
  full     everything

Retry policy: one format-only repair when the reply holds no JSON array.
Wrong node sets, wrong identities, wrong values, stale revisions are terminal
semantic failures and are never retried.  The credential is read from the
environment (run through code/run_with_local_deepseek.py); it is never
written to the ledger.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from .core import Episode, State, hhmm, score_plan
from .domains import get_domain
from .generate import generate_split
from .learners import LearnedGraph, ProgramLearner, SourceUnion, all_reads
from .scaling import augment_split, bm25_topk

COST_RATES_USD_PER_MILLION = {"uncached_input": 2.5, "cached_input": 0.25, "output": 10.0}
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

OP_CARDS = {
    "travel": """Objects: flight(arrival), transfer(provider, ride, pickup), stay(hotel, late_cutoff, checkin, late_arrival),
dinner(restaurant, start), activity(start, min_rest), bundle(vendor, rebooked). Times are minutes after midnight
(next-day activities use 1440+).
Ops you may emit: shift_reservation(payload = changed time fields only: pickup | checkin[, late_arrival] | start),
cancel_reservation (dinner only, empty payload), rebook_bundle (bundle only, empty payload).
Known visible rules: a stay's checkin = its transfer's pickup + ride; an activity must start >= checkin + min_rest
(shift to the next 15-min slot); a dinner must start >= checkin + 45 (shift to the next 15-min slot, or cancel).
Whether the transfer follows the flight automatically, by how many minutes, whether the hotel maintains the late-arrival
flag past late_cutoff, whether a restaurant accepts a later seating or cancels, and whether a bundle must be re-booked
when its dinner changes, all depend on the provider / hotel / restaurant / vendor and are only visible in the history.""",
    "shopping": """Objects: cart(budget, total; links lines, promos), line(category, role base|accessory, sku, attrs, price, priority;
links cart, base, accessories; status active|removed), promo(requires [categories], brand, discount, active 0|1).
The catalog (per category: sku, attrs, price) is given in the policy block.
Ops you may emit: replace_line(payload {"sku": ...}) on an active line, remove_line (active line, empty payload),
apply_promo / drop_promo (promo, empty payload). The cart total is recomputed automatically (never write to the cart).
Known visible rules: an accessory whose constrained attribute no longer matches its base must be replaced by the cheapest
compatible variant of its category (or removed when none exists); a promotion is eligible when the cart has an active line in
every required category (a strict promotion also requires the promotion's brand on those lines); when the total exceeds the
budget, optional lines (priority > 1) are dropped, most optional first, then priciest.
Whether a (base category, accessory category) pair is constrained, whether each promotion is strict, whether the store
re-evaluates promotions itself (automatic) or the agent must apply/drop them, and whether the budget rule is enforced,
depend on the store and are only visible in the history.""",
    "search": """Objects: doc(cls, cluster, stance, ts, status pending|active|retracted) attached to base claims; claim(kind base|composite,
combinator AND|OR, verdict supported|refuted|unresolved). Policy: now, window (docs older than now-window are ignored),
margin (score >= margin supported, <= -margin refuted).
Op you may emit: set_verdict(payload {"verdict": ...}) on a claim whose verdict changes.
A base claim's score is the sum of stance x trust(cls) over counted active documents; the trust weight of each source
class (0 = ignored), whether only the newest document per cluster counts (dedup), how unresolved children enter a
composite, and whether the store updates base-claim verdicts itself (automatic) are only visible in the history
(evidence_effect records show counted/weight/reason for past publications). Composite claims are always your job.""",
}

SYSTEM_V2_SUFFIX = """
Method (follow it literally):
STEP A - POLICY LEDGER. For every entity whose policy matters here (each provider, hotel, restaurant, vendor, source
class, store rule that the linked objects refer to), quote the history record ids that reveal its policy and state the
policy with its number, e.g. "P82: transfer moved by txn (h19), so manual, buffer = 1325-1305 = 20". If the history has
no record for an entity, say "no evidence" and treat the object as unchanged.
STEP B - PROPAGATE. Starting at the intervention source, recompute each linked object in dependency order with the
visible rules and the ledger from step A, using the NEW upstream values. Write the arithmetic. Mark each object stale
(needs a transaction), automatic (the environment updates it; never write to it; its revision is +1 when your
transactions run, which only matters if a later object depends on it) or unchanged (the recomputed value equals the
current value; do not write it).
STEP C - CHECK. Every transaction quotes expected_revision = the object's current rev shown in the state. Objects
that are cancelled cannot be shifted. Empty-payload ops (cancel, rebook) carry {} as payload.
Then the fenced json block."""

SYSTEM = """You maintain a transactional memory. An intervention has just been applied to one object. Decide which OTHER
objects are now stale and emit the minimal set of repair transactions that brings the memory to the correct post-state.
Rules:
- Every transaction is non-idempotent: it increments the object's revision, consumes a change token, charges a fee and
  drops the price lock, even when it rewrites the same value. Writing to an object that did not need a change is a
  collateral write and fails the task. Missing a needed change also fails the task.
- Each transaction must quote expected_revision equal to the object's revision at execution time. The environment may
  update some objects automatically after the intervention (their revision increments before your transactions run);
  do not write to those objects, but do use their new values when computing what depends on them.
- The visible rules are deterministic: whenever an upstream value changes, every value defined from it by a visible rule
  is stale and must be recomputed. The hidden policies of the entities involved (whether an update is automatic, by
  how much, whether a threshold is enforced, how a conflict is resolved) must be inferred from the history: earlier
  interventions and what followed them are your evidence. Entities with the same id share the same policy.
Answer in two parts.
PART 1 - ANALYSIS: walk outward from the intervention source through the linked objects. One line per object:
  <id>: stale | unchanged | automatic - <the rule or history evidence, with the numbers>.
PART 2 - the final answer as a fenced json block containing ONLY the array of transactions:
```json
[{"op": ..., "object_id": ..., "expected_revision": <int>, "payload": {...}}]
```
An empty array [] is a valid answer when nothing else needs to change."""


# ---------------------------------------------------------------- serialize

def _fmt(v):
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}:{_fmt(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ",".join(_fmt(x) for x in v) + "]"
    return str(v)


def serialize_state(domain, S0: State, oids: List[str], mode: str) -> str:
    objs = [S0.get(o) for o in sorted(oids) if o in S0.objects]
    catalog = S0.meta.get("catalog")
    if mode == "verbose":
        out = {"policy": {k: v for k, v in S0.meta.items() if k != "catalog"},
               "objects": [o.to_dict() for o in objs]}
        if catalog:
            out["catalog"] = catalog
        return json.dumps(out, indent=1)
    lines = ["policy " + " ".join(f"{k}={_fmt(v)}" for k, v in S0.meta.items() if k != "catalog")]
    if catalog:
        for cat, variants in catalog.items():
            lines.append(f"catalog {cat}: " + "; ".join(f"{v['sku']} {_fmt(v['attrs'])} price={v['price']}" for v in variants))
    for o in objs:
        fields = " ".join(f"{k}={_fmt(v)}" for k, v in o.fields.items())
        links = " ".join(f"{k}->{','.join(v)}" for k, v in o.links.items() if v)
        lines.append(f"{o.id} {o.type} {fields} {links} rev={o.revision} {o.status}")
    return "\n".join(lines)


def serialize_history(H: List[dict], rids: List[str], mode: str) -> str:
    recs = [r for r in H if r["rid"] in set(rids)]
    if mode == "verbose":
        return json.dumps(recs, indent=1)
    lines = []
    for r in recs:
        delta = " ".join(f"{k}:{_fmt(a)}->{_fmt(b)}" for k, (a, b) in (r.get("delta") or {}).items())
        head = f"{r['rid']} seg{r['seg']} {r['kind']} {r['op']} {r['object_id']} rev={r['rev']}"
        if r["kind"] == "intervention":
            head += f" query=\"{r.get('query', '')}\""
        lines.append(f"{head} {delta}".strip())
    return "\n".join(lines)


# ----------------------------------------------------------------- selection

class Selector:
    """Learners are fitted lazily, only for the selection modes actually requested."""

    def __init__(self, domain, train: List[Episode]):
        self.domain = domain
        self.train = train
        self._fitted: Dict[str, object] = {}

    def _get(self, name: str):
        if name not in self._fitted:
            t0 = time.time()
            learner = {"union": SourceUnion, "graph": LearnedGraph, "program": lambda: ProgramLearner(3)}[name]()
            learner.fit(self.domain, self.train)
            print(f"selector fit {name} on {len(self.train)} episodes: {time.time() - t0:.1f}s", flush=True)
            self._fitted[name] = learner
        return self._fitted[name]

    @property
    def union(self):
        return self._get("union")

    @property
    def graph(self):
        return self._get("graph")

    @property
    def program(self):
        return self._get("program")

    def select(self, domain, ep: Episode, mode: str) -> dict:
        src = ep.I["object_id"]
        if mode == "full":
            return all_reads(ep)
        if mode == "exact":
            return {"objects": [src], "records": [r["rid"] for r in ep.H if r["object_id"] == src]}
        if mode == "source":
            out = self.union.predict(domain, ep)
            objs = set(out["reads"]["objects"]) | {src}
            return {"objects": sorted(objs), "records": [r["rid"] for r in ep.H if r["object_id"] in objs]}
        if mode == "graph":
            out = self.graph.predict(domain, ep)
            return {"objects": sorted(set(out["reads"]["objects"]) | {src}), "records": out["reads"]["records"]}
        if mode == "graph_closed":
            # round 4: the graph's reads plus the referents of every selected history record
            # and their 1-hop neighbours, so that a witness such as "T58 pickup 860->1045"
            # arrives together with T58's provider and its flight; without them the model
            # cannot key the policy the witness reveals
            out = self.graph.predict(domain, ep)
            objs = set(out["reads"]["objects"]) | {src}
            recs = set(out["reads"]["records"])
            referents = {r["object_id"] for r in ep.H if r["rid"] in recs and r["object_id"] in ep.S0.objects}
            closure = set(referents)
            for oid in referents:
                for targets in ep.S0.get(oid).links.values():
                    closure.update(t for t in targets if t in ep.S0.objects)
            return {"objects": sorted(objs | closure), "records": sorted(recs)}
        if mode.startswith("bm25_k") or mode.startswith("recency_k"):
            k = int(mode.split("_k")[1])
            if mode.startswith("bm25"):
                recs = bm25_topk(ep, k)
            else:
                recs = [r["rid"] for r in ep.H[-k:]]
            rs = set(recs)
            referents = {r["object_id"] for r in ep.H if r["rid"] in rs and r["object_id"] in ep.S0.objects}
            closure = set(referents) | {src}
            for oid in list(referents) + [src]:
                for targets in ep.S0.get(oid).links.values():
                    closure.update(t for t in targets if t in ep.S0.objects)
            return {"objects": sorted(closure), "records": sorted(rs, key=lambda r: [x["rid"] for x in ep.H].index(r))}
        if mode == "program":
            out = self.program.predict(domain, ep)
            objs = {src} | {it["object_id"] for it in out["plan"]}
            for oid in list(objs):
                for targets in ep.S0.get(oid).links.values():
                    objs.update(t for t in targets if t in ep.S0.objects)
            segs = {r["seg"] for r in ep.H if r["object_id"] in objs}
            return {"objects": sorted(objs), "records": [r["rid"] for r in ep.H if r["seg"] in segs]}
        raise KeyError(mode)


# ------------------------------------------------------------------- client

def parse_transactions(text: str) -> Optional[List[dict]]:
    """Take the last fenced json block; otherwise the last parsable JSON array."""
    candidates = re.findall(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    arr = None
    for cand in reversed(candidates):
        try:
            arr = json.loads(cand)
            break
        except json.JSONDecodeError:
            continue
    if arr is None:
        starts = [m.start() for m in re.finditer(r"\[", text)]
        for st in reversed(starts):
            depth = 0
            for i in range(st, len(text)):
                if text[i] == "[":
                    depth += 1
                elif text[i] == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            cand = json.loads(text[st:i + 1])
                            if isinstance(cand, list) and all(isinstance(t, dict) for t in cand):
                                arr = cand
                        except json.JSONDecodeError:
                            pass
                        break
            if arr is not None:
                break
    if not isinstance(arr, list):
        return None
    out = []
    for t in arr:
        if not isinstance(t, dict) or "op" not in t or "object_id" not in t:
            return None
        rev = t.get("expected_revision", -1)
        out.append({"op": str(t["op"]), "object_id": str(t["object_id"]),
                    "expected_revision": int(rev) if isinstance(rev, int) and not isinstance(rev, bool) else -1,
                    "payload": t.get("payload") if isinstance(t.get("payload"), dict) else {}})
    return out


class Client:
    def __init__(self, model: str, thinking: bool = False):
        from openai import OpenAI
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"],
                             base_url=os.environ.get("OPENAI_BASE_URL", DEEPSEEK_BASE_URL))
        self.model = model
        self.thinking = thinking

    def chat(self, messages: List[dict], max_tokens: int = 4096) -> dict:
        t0 = time.time()
        # AutoDL / DeepSeek reasoning models think by default; the MINJA AutoDL campaign
        # disabled it with exactly these two fields, so the non-thinking arm stays comparable
        extra = {"thinking": {"type": "enabled"}} if self.thinking else \
            {"thinking": {"type": "disabled"}, "reasoning_effort": "none"}
        resp = None
        for attempt in range(12):
            try:
                resp = self.client.chat.completions.create(model=self.model, messages=messages, temperature=0,
                                                           max_tokens=max_tokens * (2 if self.thinking else 1),
                                                           extra_body=extra)
                break
            except Exception as exc:  # transient network / proxy / rate-limit errors: back off and retry
                if attempt == 11:
                    raise
                time.sleep(min(120, 5 * 2 ** attempt))
        dt = time.time() - t0
        u = resp.usage
        cached = int(getattr(u, "prompt_cache_hit_tokens", 0) or 0)
        details = getattr(u, "prompt_tokens_details", None)
        if details is not None:
            cached = max(cached, int(getattr(details, "cached_tokens", 0) or 0))
        inp, out = int(u.prompt_tokens), int(u.completion_tokens)
        cost = ((inp - cached) * COST_RATES_USD_PER_MILLION["uncached_input"] +
                cached * COST_RATES_USD_PER_MILLION["cached_input"] +
                out * COST_RATES_USD_PER_MILLION["output"]) / 1_000_000
        choice = resp.choices[0]
        return {"text": choice.message.content or "", "input_tokens": inp, "output_tokens": out,
                "cached_tokens": cached, "cost": cost, "duration": dt,
                "finish_reason": choice.finish_reason, "returned_model": resp.model}


# --------------------------------------------------------------------- runner

PROMPT_VERSION = "v1"


def build_messages(domain, ep: Episode, sel: dict, ser: str) -> List[dict]:
    card = OP_CARDS.get(domain.NAME) or OP_CARDS[domain.NAME.rstrip("0123456789")]
    user = (f"DOMAIN: {domain.NAME}\n{card}\n\n"
            f"### HISTORY (earlier interventions and what followed; {ser} form)\n"
            f"{serialize_history(ep.H, sel['records'], ser)}\n\n"
            f"### CURRENT STATE before the intervention ({ser} form)\n"
            f"{serialize_state(domain, ep.S0, sel['objects'], ser)}\n\n"
            f"### INTERVENTION (already applied to {ep.I['object_id']})\n{ep.query}\n{json.dumps(ep.I)}\n\n"
            "Return the JSON array of repair transactions.")
    system = SYSTEM + (SYSTEM_V2_SUFFIX if PROMPT_VERSION == "v2" else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def run(domains: List[str], seed: int, n_eval: int, selections: List[str], serializations: List[str],
        model: str, out_dir: Path, budget_usd: float, n_train: int = 200, train_seed_offset: int = 100,
        dry_run: bool = False, ep_start: int = 0, ep_end: Optional[int] = None,
        resume_from: Optional[List[str]] = None, thinking: bool = False, history: Optional[str] = None):
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = out_dir / "llm_ledger.jsonl"
    done = set()
    spent = 0.0
    for lp in [ledger_path] + [Path(x) for x in (resume_from or [])]:
        if lp.exists():
            for line in open(lp):
                rec = json.loads(line)
                if rec.get("event") == "cell" and not rec.get("dry_run"):
                    done.add(rec["cell"])
                    spent += rec["cost"]
    client = None if dry_run else Client(model, thinking=thinking)
    protocol = {"domains": domains, "seed": seed, "n_eval": n_eval, "selections": selections,
                "serializations": serializations, "model": model, "n_train": n_train,
                "train_seed_offset": train_seed_offset, "budget_usd": budget_usd,
                "retry_policy": "one format-only repair; semantic failures terminal", "thinking": thinking,
                "prompt_version": PROMPT_VERSION, "history": history or "native",
                "base_url": os.environ.get("OPENAI_BASE_URL", DEEPSEEK_BASE_URL),
                "cost_rates_usd_per_million": COST_RATES_USD_PER_MILLION}
    json.dump(protocol, open(out_dir / "llm_protocol.json", "w"), indent=1)
    for dname in domains:
        domain = get_domain(dname)
        train = generate_split(domain, seed + train_seed_offset, "train", n_train)
        evals = generate_split(domain, seed, "test", n_eval)[ep_start:ep_end]
        if history and history != "native":
            target, mix = history.split(":")
            train, st_tr = augment_split(domain, train, int(target), mix, f"train{seed}")
            evals, st_ev = augment_split(domain, evals, int(target), mix, f"test{seed}")
            with open(out_dir / "augment_stats.json", "w") as f:
                json.dump({"domain": dname, "history": history, "train": st_tr, "eval": st_ev}, f, indent=1)
        selector = Selector(domain, train)
        for ep in evals:
            for sel_mode in selections:
                sel = selector.select(domain, ep, sel_mode)
                for ser in serializations:
                    cell = f"{dname}/{ep.id}/{sel_mode}/{ser}"
                    if cell in done:
                        continue
                    if spent >= budget_usd:
                        print(f"budget {budget_usd} reached at {spent:.3f}; stopping", flush=True)
                        return
                    messages = build_messages(domain, ep, sel, ser)
                    if dry_run:
                        rec = {"event": "cell", "cell": cell, "dry_run": True,
                               "prompt_chars": sum(len(m["content"]) for m in messages),
                               "n_objects": len(sel["objects"]), "n_records": len(sel["records"]), "cost": 0.0}
                        with open(ledger_path, "a") as f:
                            f.write(json.dumps(rec) + "\n")
                        continue
                    attempts = []
                    try:
                        r = client.chat(messages)
                    except Exception as exc:
                        rec = {"event": "infrastructure_failure", "cell": cell, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
                        with open(ledger_path, "a") as f:
                            f.write(json.dumps(rec) + "\n")
                        print(f"{cell:48s} INFRASTRUCTURE FAILURE {type(exc).__name__}", flush=True)
                        continue
                    attempts.append(r)
                    txns = parse_transactions(r["text"])
                    repair = False
                    if txns is None:
                        repair = True
                        r2 = client.chat(messages + [{"role": "assistant", "content": r["text"]},
                                                     {"role": "user", "content": "Return the final answer now as a fenced ```json block containing only the array of transactions."}])
                        attempts.append(r2)
                        txns = parse_transactions(r2["text"])
                    parse_ok = txns is not None
                    score = score_plan(domain, ep, txns or [], sel)
                    rec = {"event": "cell", "cell": cell, "domain": dname, "episode": ep.id, "selection": sel_mode,
                           "serialization": ser, "n_objects": len(sel["objects"]), "n_records": len(sel["records"]),
                           "prompt_chars": sum(len(m["content"]) for m in messages),
                           "input_tokens": sum(a["input_tokens"] for a in attempts),
                           "output_tokens": sum(a["output_tokens"] for a in attempts),
                           "cached_tokens": sum(a["cached_tokens"] for a in attempts),
                           "cost": sum(a["cost"] for a in attempts), "duration": sum(a["duration"] for a in attempts),
                           "n_attempts": len(attempts), "format_repair": repair, "parse_ok": parse_ok,
                           "finish_reason": attempts[-1]["finish_reason"], "returned_model": attempts[-1]["returned_model"],
                           "raw_reply": attempts[-1]["text"][:4000], "txns": txns,
                           "score": {k: v for k, v in score.items() if k != "error"}, "error": score["error"]}
                    spent += rec["cost"]
                    with open(ledger_path, "a") as f:
                        f.write(json.dumps(rec) + "\n")
                    done.add(cell)
                    print(f"{cell:48s} EES={int(score['ees'])} legal={int(score['legal'])} F1={score['affected_f1']:.2f} "
                          f"in={rec['input_tokens']} out={rec['output_tokens']} ${spent:.3f}", flush=True)


def summarize(out_dir: Path) -> dict:
    cells = []
    seen = set()
    for lp in sorted(out_dir.rglob("llm_ledger.jsonl")):
        for l in open(lp):
            rec = json.loads(l)
            if rec.get("event") == "cell" and not rec.get("dry_run") and rec["cell"] not in seen:
                seen.add(rec["cell"])
                cells.append(rec)
    import numpy as np
    by = {}
    for c in cells:
        key = (c["domain"], c["selection"], c["serialization"])
        by.setdefault(key, []).append(c)
    table = {}
    for (d, s, z), rows in sorted(by.items()):
        sc = [r["score"] for r in rows]
        table[f"{d}/{s}/{z}"] = {
            "n": len(rows), "ees": float(np.mean([x["ees"] for x in sc])),
            "legal": float(np.mean([x["legal"] for x in sc])),
            "exact_action_set": float(np.mean([x["exact_action_set"] for x in sc])),
            "affected_f1": float(np.mean([x["affected_f1"] for x in sc])),
            "collateral_txns": float(np.mean([x["collateral_txns"] for x in sc])),
            "value_accuracy": float(np.mean([x["value_accuracy"] for x in sc])),
            "required_read_recall": float(np.mean([x["required_read_recall"] for x in sc])),
            "input_tokens": int(sum(r["input_tokens"] for r in rows)),
            "output_tokens": int(sum(r["output_tokens"] for r in rows)),
            "cost": float(sum(r["cost"] for r in rows)), "duration": float(sum(r["duration"] for r in rows)),
            "parse_ok": float(np.mean([r["parse_ok"] for r in rows])),
            "format_repairs": int(sum(r["format_repair"] for r in rows)),
            "returned_models": sorted({r["returned_model"] for r in rows}),
        }
    total = {"cells": len(cells), "cost": float(sum(c["cost"] for c in cells)),
             "input_tokens": int(sum(c["input_tokens"] for c in cells)),
             "output_tokens": int(sum(c["output_tokens"] for c in cells))}
    out = {"cells": table, "total": total}
    json.dump(out, open(out_dir / "llm_summary.json", "w"), indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="+", default=["travel", "search"])
    ap.add_argument("--seed", type=int, default=10)
    ap.add_argument("--n_eval", type=int, default=20)
    ap.add_argument("--selections", nargs="+", default=["exact", "source", "graph", "program", "full"])
    ap.add_argument("--serializations", nargs="+", default=["verbose", "compact"])
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--out_dir", default="results/real/hm3")
    ap.add_argument("--budget_usd", type=float, default=15.0)
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--ep_start", type=int, default=0)
    ap.add_argument("--ep_end", type=int, default=None)
    ap.add_argument("--resume_from", nargs="*", default=None)
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument("--prompt", default="v1", choices=["v1", "v2"])
    ap.add_argument("--history", default=None, help="e.g. 500:abcd (docs/hm3-history-scaling-design-2026-09-18.md)")
    ap.add_argument("--base_url", default=None)
    a = ap.parse_args()
    PROMPT_VERSION = a.prompt
    if a.base_url:
        os.environ["OPENAI_BASE_URL"] = a.base_url
    if a.summarize:
        print(json.dumps(summarize(Path(a.out_dir))["total"]))
    else:
        run(a.domains, a.seed, a.n_eval, a.selections, a.serializations, a.model, Path(a.out_dir), a.budget_usd,
            dry_run=a.dry_run, ep_start=a.ep_start, ep_end=a.ep_end, resume_from=a.resume_from,
            thinking=a.thinking, history=a.history)
