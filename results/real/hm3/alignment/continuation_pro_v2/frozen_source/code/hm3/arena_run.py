"""Substrate port, actor layer: HM3 Travel on MemoryArena's real entities, with memory routed through
MemoryArena's own memory-system interface (add_chunk / wrap_user_prompt).

Every history record is written to the memory system as one chunk (the compact record line); at
query time the system's wrap_user_prompt(query) returns its <memory_context>; the record ids found in
that context are the records the actor receives, in the same verbose serialization for every system.
Systems (MemoryArena implementations loaded file-by-file from benchmarks/MemoryArena/memory/memory_systems,
unmodified; their tree stays pristine):
  bm25          RAGMemorySystem(retrieval_method="bm25")   MemoryArena default top_k = 3
  bm25_k16      the same with top_k = 16 (read-budget matched to our other fixed-K arms)
  long_context  LongContextMemorySystem                    everything, up to its 120k-token budget
  amem          AMemMemorySystem                           A-Mem note construction + evolution, k = 5 (its default),
                                                           LLM = the actor's endpoint/model, write tokens recorded
  causal        HM3 learned graph (graph_seg selection) behind the same two-method interface
State block for the actor: the objects referenced by the selected records plus their 1-hop neighbours and
the source (long_context: every object).  Selections are cached per (system, episode, condition) so both
prompt versions reuse one memory build.

Usage: OPENAI_API_KEY=... OPENAI_BASE_URL=... PYTHONPATH=<pylib>:<A-mem>:. python3 -m hm3.arena_run \
    --domain travel_arena --seed 30 --n_eval 64 --ep_start 0 --ep_end 16 --history 100:abcd \
    --systems causal bm25 bm25_k16 long_context amem --prompt v1 --max_tokens 16384 --out_dir <dir>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from .core import Episode, score_plan
from .domains import get_domain
from .generate import generate_split
from . import llm as L
from .scaling import augment_split, query_text, record_text

ROOT = Path(__file__).resolve().parents[2]
ARENA_MS = ROOT / "benchmarks" / "MemoryArena" / "memory" / "memory_systems"
RID_RE = re.compile(r"\bh\d+\b")
WRITE_USAGE = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
_ACCOUNT = {"on": False}


def _load(name: str):
    """Load one MemoryArena memory-system module by file, bypassing the package __init__ (which imports
    every optional SDK)."""
    spec = importlib.util.spec_from_file_location(f"arena_{name}", ARENA_MS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _openai_patch():
    from openai.resources.chat import completions as oc
    if getattr(oc.Completions, "_hm3_arena_patched", False):
        return
    orig = oc.Completions.create

    def create(self, *a, **kw):
        eb = dict(kw.get("extra_body") or {})
        eb.setdefault("thinking", {"type": "disabled"}); eb.setdefault("reasoning_effort", "none")
        kw["extra_body"] = eb
        r = orig(self, *a, **kw)
        if _ACCOUNT["on"] and getattr(r, "usage", None) is not None:
            WRITE_USAGE["calls"] += 1
            WRITE_USAGE["input_tokens"] += int(r.usage.prompt_tokens or 0)
            WRITE_USAGE["output_tokens"] += int(r.usage.completion_tokens or 0)
        return r
    oc.Completions.create = create
    oc.Completions._hm3_arena_patched = True


class CausalMemorySystem:
    """Our learned graph behind MemoryArena's interface.  add_chunk stores the record lines; wrap_user_prompt
    returns the graph_seg read set (objects along the learned skeleton, the witnesses attributed to their
    policy keys, and the whole segment of each witness).  The selector needs the current state and the
    intervention, which MemoryArena passes to a memory system only through the prompt; here they are given
    at construction, like ReasoningBank receives its user_id."""

    def __init__(self, domain, ep: Episode, selector: L.Selector):
        self.domain, self.ep, self.selector = domain, ep, selector
        self.chunks: List[str] = []
        self.last_sel: Optional[dict] = None

    def add_chunk(self, chunk: str):
        self.chunks.append(chunk)

    def wrap_user_prompt(self, prompt: str) -> str:
        sel = self.selector.select(self.domain, self.ep, "graph_seg")
        self.last_sel = sel   # the graph's own object reads (the state block), as in the synthetic graph_seg arm
        keep = set(sel["records"])
        lines = ["<memory_context>"] + [c for c in self.chunks if (RID_RE.search(c) or [None])[0] in keep] + ["</memory_context>", f"User: {prompt}"]
        return "\n".join(lines)


def make_system(name: str, domain, ep: Episode, selector: Optional[L.Selector], model: str):
    if name == "causal":
        return CausalMemorySystem(domain, ep, selector)
    if name in ("bm25", "bm25_k16"):
        rag = _load("rag")
        return rag.RAGMemorySystem(retrieval_method="bm25", top_k=3 if name == "bm25" else 16)
    if name == "long_context":
        return _load("long_context").LongContextMemorySystem()
    if name == "amem":
        from .memsys_llm import _patch_amem_controller
        _patch_amem_controller(model)
        amem = _load("amem")
        return amem.AMemMemorySystem(llm_model=model, api_key=os.environ["OPENAI_API_KEY"])
    raise KeyError(name)


def select_with(system_name: str, system, domain, ep: Episode) -> dict:
    """Write the history through add_chunk, read through wrap_user_prompt, recover the record ids."""
    _ACCOUNT["on"] = system_name == "amem"
    before = dict(WRITE_USAGE)
    t0 = time.time()
    try:
        for r in ep.H:
            system.add_chunk(record_text(r))
        wrapped = system.wrap_user_prompt(query_text(ep))
    finally:
        _ACCOUNT["on"] = False
    ctx = wrapped.split("</memory_context>")[0]
    valid = {r["rid"] for r in ep.H}
    rids: List[str] = []
    for m in RID_RE.findall(ctx):
        if m in valid and m not in rids:
            rids.append(m)
    src = ep.I["object_id"]
    own = getattr(system, "last_sel", None)
    if own is not None:
        # our system: state block = the graph's object reads; the records must be exactly what the
        # interface returned (checked), so the interface is genuinely in the loop
        assert set(own["records"]) == set(rids), "causal: interface records differ from the selector's"
        objects = sorted(own["objects"])
    elif system_name == "long_context":
        objects = sorted(ep.S0.objects)
    else:
        referents = {r["object_id"] for r in ep.H if r["rid"] in set(rids) and r["object_id"] in ep.S0.objects}
        objects = set(referents) | {src}
        for oid in list(referents) + [src]:
            for targets in ep.S0.get(oid).links.values():
                objects.update(t for t in targets if t in ep.S0.objects)
        objects = sorted(objects)
    order = {r["rid"]: i for i, r in enumerate(ep.H)}
    cost = {k: WRITE_USAGE[k] - before[k] for k in WRITE_USAGE}
    cost.update({"seconds": time.time() - t0, "context_chars": len(ctx), "n_context_rids": len(rids)})
    return {"objects": objects, "records": sorted(rids, key=lambda r: order[r])}, cost


def run(a):
    out_dir = Path(a.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    domain = get_domain(a.domain)
    L.PROMPT_VERSION = a.prompt
    _openai_patch()
    train = generate_split(domain, a.seed + a.train_seed_offset, "train", a.n_train)
    evals = generate_split(domain, a.seed, "test", a.n_eval)[a.ep_start:a.ep_end]
    if a.history and a.history != "native":
        target, mix = a.history.split(":")
        evals, st = augment_split(domain, evals, int(target), mix, f"test{a.seed}")
        json.dump(st, open(out_dir / "augment_stats.json", "w"), indent=1)
    selector = L.Selector(domain, train) if "causal" in a.systems else None
    json.dump({"domain": a.domain, "seed": a.seed, "history": a.history or "native", "systems": a.systems, "model": a.model,
               "prompt_version": a.prompt, "max_tokens": a.max_tokens, "serialization": "verbose",
               "memory_interface": "MemoryArena add_chunk/wrap_user_prompt, classes loaded from benchmarks/MemoryArena/memory/memory_systems unmodified",
               "bm25_top_k": {"bm25": 3, "bm25_k16": 16}, "amem_k": 5, "budget_usd": a.budget_usd}, open(out_dir / "llm_protocol.json", "w"), indent=1)
    ledger = out_dir / "llm_ledger.jsonl"
    sel_cache_path = out_dir.parent / "selections.json"   # shared across prompt versions in sibling dirs
    sel_cache: Dict[str, dict] = json.load(open(sel_cache_path)) if sel_cache_path.exists() else {}
    done = set(); spent = 0.0
    if ledger.exists():
        for l in open(ledger):
            r = json.loads(l)
            if r.get("event") == "cell":
                done.add(r["cell"]); spent += r["cost"]
    client = L.Client(a.model)
    for ep in evals:
        for name in a.systems:
            cell = f"{a.domain}/{ep.id}/{name}/verbose"
            if cell in done:
                continue
            if spent >= a.budget_usd:
                print(f"budget {a.budget_usd} reached; stopping", flush=True); return
            key = f"{a.history or 'native'}/{ep.id}/{name}"
            if key in sel_cache:
                sel, wcost = sel_cache[key]["sel"], sel_cache[key]["write"]
            else:
                try:
                    system = make_system(name, domain, ep, selector, a.model)
                    sel, wcost = select_with(name, system, domain, ep)
                except Exception as exc:
                    with open(ledger, "a") as f:
                        f.write(json.dumps({"event": "infrastructure_failure", "cell": cell, "stage": "memory", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}) + "\n")
                    print(f"{cell:56s} MEMORY FAILURE {type(exc).__name__}: {str(exc)[:80]}", flush=True)
                    continue
                sel_cache[key] = {"sel": sel, "write": wcost}
                json.dump(sel_cache, open(sel_cache_path, "w"))
            messages = L.build_messages(domain, ep, sel, "verbose")
            try:
                r = client.chat(messages, max_tokens=a.max_tokens)
            except Exception as exc:
                with open(ledger, "a") as f:
                    f.write(json.dumps({"event": "infrastructure_failure", "cell": cell, "stage": "actor", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}) + "\n")
                print(f"{cell:56s} ACTOR FAILURE {type(exc).__name__}", flush=True)
                continue
            attempts = [r]
            txns = L.parse_transactions(r["text"])
            repair = False
            if txns is None:
                repair = True
                r2 = client.chat(messages + [{"role": "assistant", "content": r["text"]},
                                             {"role": "user", "content": "Return the final answer now as a fenced ```json block containing only the array of transactions."}], max_tokens=a.max_tokens)
                attempts.append(r2); txns = L.parse_transactions(r2["text"])
            score = score_plan(domain, ep, txns or [], sel)
            rec = {"event": "cell", "cell": cell, "domain": a.domain, "episode": ep.id, "selection": name, "serialization": "verbose",
                   "system": name, "n_objects": len(sel["objects"]), "n_records": len(sel["records"]), "write": wcost,
                   "input_tokens": sum(x["input_tokens"] for x in attempts), "output_tokens": sum(x["output_tokens"] for x in attempts),
                   "output_tokens_per_attempt": [x["output_tokens"] for x in attempts], "finish_reasons": [x["finish_reason"] for x in attempts],
                   "cost": sum(x["cost"] for x in attempts), "n_attempts": len(attempts), "format_repair": repair, "parse_ok": txns is not None,
                   "max_tokens": a.max_tokens, "raw_reply": attempts[-1]["text"][:4000], "txns": txns,
                   "score": {k: v for k, v in score.items() if k != "error"}, "error": score["error"]}
            spent += rec["cost"]
            with open(ledger, "a") as f:
                f.write(json.dumps(rec) + "\n")
            done.add(cell)
            print(f"{cell:56s} EES={int(score['ees'])} legal={int(score['legal'])} F1={score['affected_f1']:.2f} recs={len(sel['records'])} "
                  f"in={rec['input_tokens']} out={rec['output_tokens']} write={wcost.get('calls', 0)}calls ${spent:.3f}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="travel_arena")
    ap.add_argument("--seed", type=int, default=30)
    ap.add_argument("--n_eval", type=int, default=64)
    ap.add_argument("--ep_start", type=int, default=0)
    ap.add_argument("--ep_end", type=int, default=None)
    ap.add_argument("--n_train", type=int, default=200)
    ap.add_argument("--train_seed_offset", type=int, default=100)
    ap.add_argument("--history", default=None)
    ap.add_argument("--systems", nargs="+", default=["causal", "bm25", "bm25_k16", "long_context", "amem"])
    ap.add_argument("--prompt", default="v1", choices=["v1", "v2", "v3"])
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--max_tokens", type=int, default=16384)
    ap.add_argument("--budget_usd", type=float, default=20.0)
    ap.add_argument("--out_dir", required=True)
    run(ap.parse_args())
