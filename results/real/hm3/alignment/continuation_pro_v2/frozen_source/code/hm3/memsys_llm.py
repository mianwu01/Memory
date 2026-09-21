"""Modern agent-memory systems as selectors in the HM3 actor matrix (three-layer plan, layer 1/3).

A-Mem (agiresearch/A-mem, benchmarks/A-mem): every history record is written as a note in
history order with A-Mem's own LLM note construction and evolution; the query retrieves the
top-K notes by A-Mem's embedding search; the retrieved records go to the same actor prompt and
serialization as the other fixed-K arms (referents + one-hop closure), so the comparison is
read-budget matched.  Write-side LLM tokens are recorded per episode and reported separately.
The LLM used inside A-Mem is the same endpoint/model as the actor, thinking disabled.

Usage: OPENAI_API_KEY=... OPENAI_BASE_URL=https://www.autodl.art/api/v1 \
  PYTHONPATH=<pylib2>:benchmarks/A-mem:. python3 -m hm3.memsys_llm --system amem --domains travel \
  --seed 30 --n_eval 64 --ep_start 0 --ep_end 16 --history native --k 16 --out_dir results/real/hm3/memsys/amem/travel_native
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from .core import score_plan
from .domains import get_domain
from .generate import generate_split
from .llm import Client, build_messages, parse_transactions
from . import llm as llm_mod
from .scaling import augment_split, record_text, query_text

logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("agentic_memory").setLevel(logging.ERROR)

WRITE_USAGE = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
_ACCOUNT = {"on": False}


def _global_openai_patch():
    """Every chat call from inside a memory system goes to the same endpoint with thinking
    disabled, and its usage is accumulated while _ACCOUNT['on'] is set."""
    from openai.resources.chat import completions as oc
    if getattr(oc.Completions, "_hm3_patched", False):
        return
    orig = oc.Completions.create

    def create(self, *args, **kwargs):
        eb = dict(kwargs.get("extra_body") or {})
        eb.setdefault("thinking", {"type": "disabled"}); eb.setdefault("reasoning_effort", "none")
        kwargs["extra_body"] = eb
        r = orig(self, *args, **kwargs)
        if _ACCOUNT["on"] and getattr(r, "usage", None) is not None:
            WRITE_USAGE["calls"] += 1
            WRITE_USAGE["input_tokens"] += int(r.usage.prompt_tokens or 0)
            WRITE_USAGE["output_tokens"] += int(r.usage.completion_tokens or 0)
        return r

    oc.Completions.create = create
    oc.Completions._hm3_patched = True


RID_RE = __import__("re").compile(r"\bh\d+\b")


def _closure(ep, rids: List[str]) -> dict:
    src = ep.I["object_id"]
    rs = set(rids)
    referents = {r["object_id"] for r in ep.H if r["rid"] in rs and r["object_id"] in ep.S0.objects}
    closure = set(referents) | {src}
    for oid in list(referents) + [src]:
        for targets in ep.S0.get(oid).links.values():
            closure.update(t for t in targets if t in ep.S0.objects)
    order = {r["rid"]: i for i, r in enumerate(ep.H)}
    return {"objects": sorted(closure), "records": sorted(rs, key=lambda r: order[r])}


def mem0_select(domain, ep, k: int, model: str, infer: bool = True) -> dict:
    """Mem0 OSS: each record added as a user message, then search.  infer=True runs Mem0's LLM fact
    extraction and memory-update pipeline (with DeepSeek-V4-Flash it keeps 0-40 % of the records of an
    episode and sometimes nothing: documented negative); infer=False (system 'mem0_raw') stores the
    record verbatim and retrieves with Mem0's embedding search.  Record ids travel in the metadata."""
    import shutil
    import tempfile
    # Mem0 also opens a process-wide local Qdrant under $MEM0_DIR/migrations_qdrant (default ~/.mem0), which
    # only one process may hold: give every process its own MEM0_DIR before mem0 is first imported
    if "MEM0_DIR" not in os.environ:
        os.environ["MEM0_DIR"] = tempfile.mkdtemp(prefix="hm3_mem0_home_")
    from mem0 import Memory
    before = dict(WRITE_USAGE)
    t0 = time.time()
    # Mem0's local Qdrant defaults to the persistent path /tmp/qdrant even with on_disk=False, so a
    # collection from an earlier run of the same episode would be reused; every episode gets its own
    # store directory, removed afterwards
    store = tempfile.mkdtemp(prefix="hm3_mem0_")
    cfg = {"llm": {"provider": "openai", "config": {"model": model, "temperature": 0.0, "max_tokens": 1000,
                                                     "api_key": os.environ["OPENAI_API_KEY"],
                                                     "openai_base_url": os.environ.get("OPENAI_BASE_URL")}},
           "embedder": {"provider": "huggingface", "config": {"model": "all-MiniLM-L6-v2", "embedding_dims": 384}},
           "vector_store": {"provider": "qdrant", "config": {"collection_name": "hm3_" + ep.id.replace("-", "_"),
                                                             "embedding_model_dims": 384, "on_disk": False,
                                                             "path": store}},
           # Mem0 2.x also keeps a per-user message history (default ~/.mem0/history.db) and asks the LLM
           # only for memories that are new relative to it; an earlier run of the same episode id would
           # make every record "already seen" and the store stays empty -- isolate it per episode too
           "history_db_path": os.path.join(store, "history.db")}
    _ACCOUNT["on"] = True
    n_stored = None
    try:
        mem = Memory.from_config(cfg)
        uid = ep.id
        for r in ep.H:
            # the record id travels in the metadata: Mem0's fact extraction rewrites the text and
            # drops the "h17" token, so the id cannot be recovered from the memory text alone
            mem.add(messages=[{"role": "user", "content": record_text(r)}], user_id=uid, infer=infer,
                    metadata={"rid": r["rid"], "object_id": r["object_id"], "seg": r["seg"]})
        res = mem.search(query_text(ep), filters={"user_id": uid}, limit=k)
        try:
            allm = mem.get_all(filters={"user_id": uid})
            allm = allm.get("results", allm) if isinstance(allm, dict) else allm
            n_stored = len(allm)
        except Exception:
            n_stored = None
    finally:
        _ACCOUNT["on"] = False
        shutil.rmtree(store, ignore_errors=True)
    items = res.get("results", res) if isinstance(res, dict) else res
    texts = [it.get("memory", "") for it in items]
    valid = {r["rid"] for r in ep.H}
    rids: List[str] = []
    n_meta = 0
    for it in items:
        rid = (it.get("metadata") or {}).get("rid")
        if rid in valid and rid not in rids:
            rids.append(rid)
            n_meta += 1
    for t in texts:
        for m in RID_RE.findall(t):
            if m in valid and m not in rids:
                rids.append(m)
    rids = rids[:k]
    sel = _closure(ep, rids)
    cost = {kk: WRITE_USAGE[kk] - before[kk] for kk in WRITE_USAGE}
    cost.update({"seconds": time.time() - t0, "n_notes": len(ep.H), "n_retrieved_items": len(texts),
                 "n_recovered_ids": len(rids), "n_recovered_from_metadata": n_meta, "n_stored_memories": n_stored,
                 "sample_items": texts[:3]})
    return sel, cost


def _patch_amem_controller(model: str):
    """A-Mem's OpenAI controller: same endpoint, thinking disabled, usage captured."""
    from agentic_memory import llm_controller as lc
    from openai import OpenAI

    class PatchedOpenAIController(lc.BaseLLMController):
        def __init__(self, model_name: str = model, api_key: Optional[str] = None):
            self.model = model
            self.client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"],
                                 base_url=os.environ.get("OPENAI_BASE_URL"))

        def get_completion(self, prompt: str, response_format: dict, temperature: float = 0.7) -> str:
            last = None
            for attempt in range(6):
                try:
                    r = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "system", "content": "You must respond with a JSON object."},
                                  {"role": "user", "content": prompt}],
                        response_format=response_format, temperature=temperature, max_tokens=1000,
                        extra_body={"thinking": {"type": "disabled"}, "reasoning_effort": "none"})
                    WRITE_USAGE["calls"] += 1
                    WRITE_USAGE["input_tokens"] += int(r.usage.prompt_tokens)
                    WRITE_USAGE["output_tokens"] += int(r.usage.completion_tokens)
                    return r.choices[0].message.content
                except Exception as exc:
                    last = exc
                    time.sleep(min(60, 3 * 2 ** attempt))
            raise last

    lc.OpenAIController = PatchedOpenAIController
    # LLMController picks the class at construction time
    orig_init = lc.LLMController.__init__

    def _init(self, backend: str = "openai", model: str = model, api_key: Optional[str] = None):
        self.llm = PatchedOpenAIController(model, api_key)

    lc.LLMController.__init__ = _init


def amem_select(domain, ep, k: int, model: str) -> dict:
    """Write the history into a fresh A-Mem store, query it, return the selection and write cost."""
    from agentic_memory.memory_system import AgenticMemorySystem
    before = dict(WRITE_USAGE)
    t0 = time.time()
    mem = AgenticMemorySystem(model_name="all-MiniLM-L6-v2", llm_backend="openai", llm_model=model)
    id_to_rid: Dict[str, str] = {}
    for r in ep.H:
        nid = mem.add_note(record_text(r), time=f"seg{r['seg']:04d}")
        id_to_rid[nid] = r["rid"]
    results = mem.search(query_text(ep), k=k)
    rids = [id_to_rid[x["id"]] for x in results if x["id"] in id_to_rid][:k]
    src = ep.I["object_id"]
    rs = set(rids)
    referents = {r["object_id"] for r in ep.H if r["rid"] in rs and r["object_id"] in ep.S0.objects}
    closure = set(referents) | {src}
    for oid in list(referents) + [src]:
        for targets in ep.S0.get(oid).links.values():
            closure.update(t for t in targets if t in ep.S0.objects)
    order = {r["rid"]: i for i, r in enumerate(ep.H)}
    sel = {"objects": sorted(closure), "records": sorted(rs, key=lambda r: order[r])}
    cost = {kk: WRITE_USAGE[kk] - before[kk] for kk in WRITE_USAGE}
    cost["seconds"] = time.time() - t0
    cost["n_notes"] = len(ep.H)
    return sel, cost


def run(system: str, domain_name: str, seed: int, n_eval: int, ep_start: int, ep_end: Optional[int], history: Optional[str],
        k: int, model: str, out_dir: Path, budget_usd: float, serialization: str = "compact",
        n_train: int = 200, train_seed_offset: int = 100, max_tokens: int = 4096):
    out_dir.mkdir(parents=True, exist_ok=True)
    domain = get_domain(domain_name)
    evals = generate_split(domain, seed, "test", n_eval)[ep_start:ep_end]
    if history and history != "native":
        target, mix = history.split(":")
        evals, st = augment_split(domain, evals, int(target), mix, f"test{seed}")
        json.dump({"eval": st}, open(out_dir / "augment_stats.json", "w"), indent=1)
    ledger = out_dir / "llm_ledger.jsonl"
    done = set(); spent = 0.0
    if ledger.exists():
        for l in open(ledger):
            r = json.loads(l)
            if r.get("event") == "cell":
                done.add(r["cell"]); spent += r["cost"]
    json.dump({"system": system, "domain": domain_name, "seed": seed, "history": history or "native", "k": k, "model": model,
               "serialization": serialization, "prompt_version": llm_mod.PROMPT_VERSION, "budget_usd": budget_usd,
               "max_tokens": max_tokens,
               "write_llm": "same endpoint and model, thinking disabled; write tokens recorded per cell"},
              open(out_dir / "llm_protocol.json", "w"), indent=1)
    _global_openai_patch()
    if system == "amem":
        _patch_amem_controller(model)
    elif system in ("mem0", "mem0_raw"):
        pass
    else:
        raise SystemExit(f"unknown system {system}")
    select_fn = {"amem": amem_select, "mem0": mem0_select,
                 "mem0_raw": lambda d, e, kk, m: mem0_select(d, e, kk, m, infer=False)}[system]
    client = Client(model)
    sel_name = f"{system}_k{k}"
    for ep in evals:
        cell = f"{domain_name}/{ep.id}/{sel_name}/{serialization}"
        if cell in done:
            continue
        if spent >= budget_usd:
            print(f"budget {budget_usd} reached at {spent:.3f}", flush=True); return
        try:
            sel, wcost = select_fn(domain, ep, k, model)
        except Exception as exc:
            open(ledger, "a").write(json.dumps({"event": "infrastructure_failure", "cell": cell, "stage": "write", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}) + "\n")
            print(f"{cell:48s} WRITE FAILURE {type(exc).__name__}", flush=True); continue
        messages = build_messages(domain, ep, sel, serialization)
        try:
            r = client.chat(messages, max_tokens=max_tokens)
        except Exception as exc:
            open(ledger, "a").write(json.dumps({"event": "infrastructure_failure", "cell": cell, "stage": "actor", "error": str(exc)[:200]}) + "\n"); continue
        attempts = [r]; txns = parse_transactions(r["text"]); repair = False
        if txns is None:
            repair = True
            r2 = client.chat(max_tokens=max_tokens, messages=messages + [{"role": "assistant", "content": r["text"]},
                                         {"role": "user", "content": "Return the final answer now as a fenced ```json block containing only the array of transactions."}])
            attempts.append(r2); txns = parse_transactions(r2["text"])
        score = score_plan(domain, ep, txns or [], sel)
        write_cost_usd = (wcost["input_tokens"] * llm_mod.COST_RATES_USD_PER_MILLION["uncached_input"] +
                          wcost["output_tokens"] * llm_mod.COST_RATES_USD_PER_MILLION["output"]) / 1e6
        rec = {"event": "cell", "cell": cell, "domain": domain_name, "episode": ep.id, "selection": sel_name, "serialization": serialization,
               "n_objects": len(sel["objects"]), "n_records": len(sel["records"]),
               "prompt_chars": sum(len(m["content"]) for m in messages),
               "input_tokens": sum(a["input_tokens"] for a in attempts), "output_tokens": sum(a["output_tokens"] for a in attempts),
               "cached_tokens": sum(a["cached_tokens"] for a in attempts),
               "cost": sum(a["cost"] for a in attempts) + write_cost_usd, "actor_cost": sum(a["cost"] for a in attempts),
               "write": wcost, "write_cost_usd": write_cost_usd,
               "duration": sum(a["duration"] for a in attempts), "n_attempts": len(attempts), "format_repair": repair,
               "parse_ok": txns is not None, "finish_reason": attempts[-1]["finish_reason"], "returned_model": attempts[-1]["returned_model"],
               "raw_reply": attempts[-1]["text"][:4000], "txns": txns, "score": {kk: v for kk, v in score.items() if kk != "error"}, "error": score["error"]}
        spent += rec["cost"]
        open(ledger, "a").write(json.dumps(rec) + "\n"); done.add(cell)
        print(f"{cell:48s} EES={int(score['ees'])} legal={int(score['legal'])} F1={score['affected_f1']:.2f} recs={len(sel['records'])} "
              f"write_calls={wcost['calls']} write_tok={wcost['input_tokens']}+{wcost['output_tokens']} ${spent:.3f}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="amem")
    ap.add_argument("--domains", nargs="+", default=["travel"])
    ap.add_argument("--seed", type=int, default=30)
    ap.add_argument("--n_eval", type=int, default=64)
    ap.add_argument("--ep_start", type=int, default=0)
    ap.add_argument("--ep_end", type=int, default=None)
    ap.add_argument("--history", default=None)
    ap.add_argument("--k", type=int, default=16)
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--serialization", default="compact")
    ap.add_argument("--prompt", default="v2", choices=["v1", "v2", "v3"])
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--budget_usd", type=float, default=10.0)
    ap.add_argument("--max_tokens", type=int, default=4096, help="actor completion cap per attempt (A-Mem rounds before 2026-09-20 used 4096)")
    a = ap.parse_args()
    llm_mod.PROMPT_VERSION = a.prompt
    for d in a.domains:
        run(a.system, d, a.seed, a.n_eval, a.ep_start, a.ep_end, a.history, a.k, a.model, Path(a.out_dir), a.budget_usd, a.serialization,
            max_tokens=a.max_tokens)
