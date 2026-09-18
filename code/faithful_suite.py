"""Freeze and run a complete, provenance-checked comparison without a decoder."""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from faithful_memory import ARMS, COMPRESSOR, EMBEDDING, GRAPH, ROOT, environment

SOURCES = ["code/faithful_memory.py", "code/faithful_transport.py", "code/faithful_arena_run.py",
           "code/faithful_suite.py", "code/arena_causal_memory.py", "code/arena_e2e_inherit.py",
           "code/run_with_local_deepseek.py", "code/relay_chat_transport.py",
           "code/requirements-faithful-memory.txt", "code/faithful_acceptance.py",
           "code/faithful_locomo_validate.py", "code/faithful_memory_validate.py", "code/faithful_campaign.py",
           "code/faithful_development_recover.py", "code/faithful_recover_balance.py",
           "code/faithful_generation_probe.py", "code/faithful_concurrency_probe.py"]
REPOS = ("MemoryArena", "mem0", "AgenticMemory-paper", "LightMem", "mem0-memory-benchmarks")


def dispatch_cases(cases, run, workers):
    """Stop launching after a failed case; let already billed work finish.

    Do not enqueue the entire campaign: an exhausted account must not cause
    every remaining case to make an API request. Unstarted cases are explicit
    missing scope, never zero scores or silently omitted results.
    """
    if workers < 1:
        raise ValueError("workers must be positive")
    cases = list(cases)
    results = {}
    next_index = 0
    stopped = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}
        while pending or (not stopped and next_index < len(cases)):
            while not stopped and len(pending) < workers and next_index < len(cases):
                pending[pool.submit(run, cases[next_index])] = next_index
                next_index += 1
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                index = pending.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    arm, ident = cases[index]
                    result = {"arm": arm, "id": ident, "exit_code": 1,
                              "state": "launcher_error", "error_type": type(exc).__name__}
                results[index] = result
                stopped |= result["exit_code"] != 0
    for index in range(next_index, len(cases)):
        arm, ident = cases[index]
        results[index] = {"arm": arm, "id": ident, "exit_code": None,
                          "state": "not_started_after_failure", "seconds": 0}
    return [results[index] for index in range(len(cases))]


def fingerprints():
    environment()
    from env.env_systems.travel_planner_env.data_loader import load_travel_data
    values = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}
    values["dataset:MemoryArena"] = hashlib.sha256(json.dumps(
        load_travel_data(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    from huggingface_hub import try_to_load_from_cache
    for name in ("model.safetensors", "config.json", "tokenizer.json", "tokenizer_config.json", "modules.json", "sentence_bert_config.json"):
        cached = try_to_load_from_cache("sentence-transformers/all-MiniLM-L6-v2", name)
        if not isinstance(cached, str):
            raise RuntimeError("A-Mem canonical embedding model is not cached: " + name)
        values["canonical_embedding:" + name] = hashlib.sha256(Path(cached).read_bytes()).hexdigest()
    values[str(GRAPH.relative_to(ROOT))] = hashlib.sha256(GRAPH.read_bytes()).hexdigest()
    dataset = ROOT / "benchmarks/AgenticMemory-paper/data/locomo10.json"
    values[str(dataset.relative_to(ROOT))] = hashlib.sha256(dataset.read_bytes()).hexdigest()
    for name in REPOS:
        repo = ROOT / "benchmarks" / name
        values["upstream:" + name] = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip()
        if dirty:
            raise RuntimeError(f"Upstream checkout changed: {name}")
    for folder in (EMBEDDING, COMPRESSOR):
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.suffix in {".json", ".txt", ".bin", ".safetensors"}:
                values["model:" + str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    for name in sorted({d.metadata["Name"] for d in importlib.metadata.distributions() if d.metadata["Name"]}):
        values["dependency:" + name] = importlib.metadata.version(name)
    return values


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["development", "evaluation"], required=True)
    ap.add_argument("--family", required=True)
    ap.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--env-port", type=int, default=8941)
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--actor-thinking", choices=["default", "disabled"], default="default")
    ap.add_argument("--development-family", default="faithful_memory_v2")
    args = ap.parse_args()
    if Path(args.family).name != args.family or args.family in {".", ".."}:
        raise ValueError("Expected one family name")
    base = ROOT / "results" / ("development" if args.phase == "development" else "real") / args.family
    base.mkdir(parents=True, exist_ok=True)
    ids = [101] if args.phase == "development" else list(range(111, 121))
    order = [(arm, ident) for j, ident in enumerate(ids)
             for arm in ARMS[j % len(ARMS):] + ARMS[:j % len(ARMS)]]
    current = fingerprints()
    protocol_path = base / "protocol.json"
    if args.freeze:
        if args.phase != "evaluation":
            raise ValueError("Only evaluation is frozen")
        from faithful_acceptance import acceptance
        acceptance_path = ROOT / "results/development" / args.development_family / "acceptance.json"
        saved = json.loads(acceptance_path.read_text())
        accepted = acceptance(args.development_family, defer_native=saved.get("native_gates") == "deferred")
        if saved["source_hashes"] != current or saved["evidence_sha256"] != accepted["evidence_sha256"]:
            raise RuntimeError("Acceptance source/evidence changed")
        protocol = {"schema": "faithful-memory-comparison/v1", "frozen_at": time.time(),
                    "arms": list(ARMS), "episode_ids": ids, "source_hashes": current,
                    "case_order": order,
                    "order_policy": "interleave methods within each episode, rotating starting method across episodes; all cache hits and concurrency remain reported",
                    "model": os.environ["OPENAI_MODEL"], "endpoint": os.environ["OPENAI_BASE_URL"],
                    "actor_thinking": args.actor_thinking, "memory_thinking": "disabled",
                    "actor": "unmodified MemoryArena TravelPlannerAgent", "max_steps": 30,
                    "actor_max_tokens": 32768, "custom_decoder": False,
                    "custom_actor_prompts": False, "tool_filter": False,
                    "reasoning_history": "exact observed provider field passed back with tool calls",
                    "lightmem": "full sensory/metadata pipeline; native offline update at completed session boundary",
                    "retrieval_k": {"mem0": 200, "lightmem": 60, "amem": 10, "dense": 10, "bm25": 3},
                    "amem": "paper robust agent; original prompts/parser/evolution/retrieval and original 1000 output-token budget",
                    "memory_thinking_observation": "thinking=disabled plus verified relay reasoning_effort=none; any observed memory reasoning tokens invalidates execution",
                    "selection": "entire existing graph holdout 111-120; reused historical holdout, disclosed",
                    "realizations": 1, "attempt_policy": "one attempt; technical recovery requires a separate preregistered amendment",
                    "actor_length_policy": "retain native bounded response; original actor output is scored without repair",
                    "request_retry_policy": "up to 4 attempts before headers; explicit upstream_stream_read_error after headers permits at most 2 identical-request retries, with all attempts accounted. No semantic/length/score retries.",
                    "dispatch_failure_policy": "stop launching cases after any case failure; allow already running cases to finish; record all unstarted cases as missing scope",
                    "cpu_threads_per_worker": 2,
                    "development_hardware_note": "Earlier interface tests inherited OMP_NUM_THREADS=72; development timings are not compared to formal timings.",
                    "acceptance_sha256": hashlib.sha256(acceptance_path.read_bytes()).hexdigest(),
                    "interpretation": "fixed common backbone and original actor; not universal method rankings or proven causal necessity",
                    "development_family": args.development_family,
                    "native_gates": saved.get("native_gates", "required"),
                    "fidelity_claim_ready": saved.get("fidelity_claim_ready", True),
                    "workers": args.workers,
                    "concurrency_note": "worker count changes wall time and relay load only; every case keeps one attempt and the registered request retry policy"}
        with protocol_path.open("x") as handle:
            json.dump(protocol, handle, indent=2)
        print(json.dumps({"frozen": str(protocol_path), "cases": len(ids) * len(ARMS)}), flush=True)
        return
    if args.phase == "evaluation":
        frozen = json.loads(protocol_path.read_text())
        if frozen["source_hashes"] != current:
            raise RuntimeError("Source/dependency/model changed after freeze")
        for key, value in {"model": os.environ["OPENAI_MODEL"], "endpoint": os.environ["OPENAI_BASE_URL"],
                           "actor_thinking": args.actor_thinking, "episode_ids": ids,
                           "workers": args.workers}.items():
            if frozen[key] != value:
                raise RuntimeError(f"Frozen setting changed: {key}")
    else:
        p = base / ("development_launch_" + time.strftime("%Y%m%d_%H%M%S") + ".json")
        p.write_text(json.dumps({"source_hashes": current, "arms": args.arms, "ids": ids,
                                 "actor_thinking": args.actor_thinking}, indent=2))
    cases = [(arm, i) for arm, i in order if arm in args.arms]
    for arm, i in cases:
        if (base / "travel" / f"{arm}_{i}").exists():
            raise RuntimeError(f"Output already exists; explicit accounting required: {arm}/{i}")
    logs = base / "logs"
    logs.mkdir(exist_ok=True)

    def run(case):
        arm, i = case
        out = base / "travel" / f"{arm}_{i}"
        started = time.monotonic()
        command = [sys.executable, "-u", str(ROOT / "code/faithful_arena_run.py"),
                   "--arm", arm, "--id", str(i), "--out", str(out), "--env-port", str(args.env_port),
                   "--actor-thinking", args.actor_thinking]
        child_env = os.environ.copy()
        # The user's shell exports 72 OpenMP threads. Avoid oversubscribing the
        # CPU when running several independent method/episode workers.
        for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            child_env[key] = "2"
        child_env["HF_HUB_OFFLINE"] = "1"
        child_env["HF_DATASETS_OFFLINE"] = "1"
        with (logs / f"{arm}_{i}.log").open("x") as handle:
            proc = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, env=child_env)
        row = {"arm": arm, "id": i, "exit_code": proc.returncode, "seconds": time.monotonic() - started}
        print(json.dumps(row), flush=True)
        return row

    results = dispatch_cases(cases, run, args.workers)
    (base / ("launch_status_" + time.strftime("%Y%m%d_%H%M%S") + ".json")).write_text(json.dumps(results, indent=2))
    if any(row["exit_code"] != 0 for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
