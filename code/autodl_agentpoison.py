"""Rerun the frozen AgentPoison matrix with AutoDL and recorded API usage.

The carrier, task matrix, driver, ReAct trajectory, and judgement are reused.
Only provider transport and concurrent scheduling of independent groups change.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import agentpoison_strategyqa_gate as gate

ROOT = gate.ROOT


class AutoDLAnswerer:
    def __init__(self, args, path):
        from openai import OpenAI
        self.args, self.path = args, path
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=args.base_url,
                             timeout=120.0, max_retries=0)
        self.lock = threading.Lock()

    def append(self, row):
        with self.lock, self.path.open("a") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()

    def call(self, prompt, stop, task_key, call_index, decoder_seed):
        duration, failures = 0.0, 0
        for attempt in range(1, self.args.api_retries + 1):
            started = time.monotonic()
            event = dict(schema="agentpoison-api-call-usage/v2", task_key=task_key,
                         call_index=call_index, decoder_seed=int(decoder_seed) + int(call_index) - 1,
                         attempt=attempt, requested_model=self.args.model, endpoint=self.args.base_url,
                         thinking={"type": "disabled"}, reasoning_effort="none", pricing_known=False,
                         cost_value_semantics="unpriced accumulator; numeric zero is not a zero-cost quote",
                         estimated_cost=0.0)
            try:
                response = self.client.chat.completions.create(
                    model=self.args.model,
                    messages=[{"role": "system", "content": gate.SYSTEM_PROMPT},
                              {"role": "user", "content": prompt}],
                    temperature=self.args.temperature, max_tokens=self.args.max_tokens, top_p=1,
                    seed=int(decoder_seed) + int(call_index) - 1, stop=[stop],
                    reasoning_effort="none", extra_body={"thinking": {"type": "disabled"}})
                if not response.usage or not response.choices:
                    raise RuntimeError("Missing usage or choices")
                elapsed = time.monotonic() - started
                duration += elapsed
                raw = response.usage.model_dump()
                inp, out = int(raw["prompt_tokens"]), int(raw["completion_tokens"])
                cached = int((raw.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
                reasoning = int((raw.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
                event.update(input_tokens=inp, output_tokens=out, cached_tokens=cached,
                             duration_seconds=elapsed, returned_model=response.model,
                             finish_reason=response.choices[0].finish_reason, raw_usage=raw,
                             provider_cost_cny=getattr(response, "cost_cny", None),
                             billing_pending=getattr(response, "billing_pending", None))
                self.append(event)
                if reasoning or getattr(response.choices[0].message, "reasoning_content", None):
                    raise RuntimeError("Provider did not honor registered nonthinking mode")
                return dict(text=response.choices[0].message.content or "", error="",
                            finish_reason=event["finish_reason"], usage={**event, "api_attempts": attempt,
                            "failed_attempts": failures, "duration_seconds": duration})
            except Exception as exc:
                elapsed = time.monotonic() - started
                duration += elapsed
                failures += 1
                event.update(input_tokens=0, output_tokens=0, cached_tokens=0,
                             duration_seconds=elapsed, error=type(exc).__name__,
                             status_code=getattr(exc, "status_code", None), usage_unknown=True)
                self.append(event)
                # Technical service errors alone permit identical-request retries.
                status = getattr(exc, "status_code", None)
                retryable = status in (408, 429, 500, 502, 503, 504) or type(exc).__name__ in (
                    "APITimeoutError", "APIConnectionError")
                if not retryable or attempt == self.args.api_retries:
                    raise RuntimeError(f"AgentPoison API failure: {type(exc).__name__}; status={status}") from None
                time.sleep(min(2 ** (attempt - 1), 20))


def load_arguments(base, workers):
    old_path = ROOT / "results/real/p3_agentpoison_round2/frozen_protocol.json"
    old = json.loads(old_path.read_text())
    args = SimpleNamespace(**{key: old[key] for key in (
        "calibration_ids", "calibration_replicates", "seed_blocks", "test_replicates",
        "utility_replicates", "driver_threshold", "driver_min_retrievals", "temporal_ancestry_hops",
        "cluster_k", "cluster_cosine_threshold", "max_steps", "temperature", "max_tokens")})
    args.model, args.base_url = os.environ["OPENAI_MODEL"], os.environ["OPENAI_BASE_URL"]
    args.api_retries = 3
    return args, old, old_path


def run(base, workers, resume=False):
    base = base.resolve()
    base.mkdir(parents=True, exist_ok=True)
    args, old, old_path = load_arguments(base, workers)
    dev = ROOT / ".tmp/agentpoison/strategyqa_dev.json"
    test, train, record_ids, contents, react_prompt = gate.load_carrier(dev)
    gate.validate_design(args, test)
    tasks, call_order = gate.make_tasks(args, test)
    if [gate.projected_task(task) for task in tasks] != old["task_schedule"] or call_order != old["call_order"]:
        raise ValueError("New matrix differs from the preserved round-2 design")
    snapshot = gate.DPRSnapshot(record_ids, contents,
        [str(sample["question"]) + " " + gate.CANONICAL_TRIGGER for sample in train[:2]],
        ROOT / ".tmp/agentpoison/strategyqa_dpr_snapshot.npz", "cpu", 8)
    if snapshot.snapshot_sha256 != old["snapshot_sha256"]:
        raise ValueError("DPR retrieval snapshot differs from fixed design")
    # Load the read-only encoder before starting concurrent retrievals.
    snapshot._load_model()
    protocol = copy.deepcopy(old)
    protocol.update(model=args.model, base_url=args.base_url,
        cost_estimate_usd_per_million_tokens=None,
        provider_pricing="unknown; no prior-provider rates applied",
        execution_amendment=dict(source_protocol=str(old_path.relative_to(ROOT)),
            source_protocol_sha256=gate.sha256_file(old_path),
            workers=workers, thinking={"type": "disabled"}, reasoning_effort="none",
            scheduling="independent query/replicate/track groups concurrent; original within-group arm order",
            technical_retry="up to 3 identical attempts for connection, timeout, or HTTP 408/429/5xx only",
            decoder_seed_note="requested per frozen schedule; provider determinism is not assumed",
            source_hashes={str(path.relative_to(ROOT)):gate.sha256_file(path) for path in
                           [Path(__file__), ROOT/'code/agentpoison_strategyqa_gate.py',
                            ROOT/'code/agentpoison_strategyqa_summary.py']}))
    frozen = base / "frozen_protocol.json"
    checkpoint = base / "checkpoint.json"
    if resume:
        if json.loads(frozen.read_text()) != protocol:
            raise ValueError("Resume protocol changed")
        state = json.loads(checkpoint.read_text())
    else:
        if frozen.exists() or checkpoint.exists():
            raise ValueError("Existing run requires --resume; preserve all attempts")
        gate.atomic_json(frozen, protocol)
        state = dict(protocol_sha256=gate.sha256_file(frozen), completed={}, driver=None, state="running")
        gate.atomic_json(checkpoint, state)
    output = base / "agentpoison_strategyqa_gate.json"
    answerer = AutoDLAnswerer(args, output.with_suffix(".api_usage.jsonl"))
    lock = threading.Lock()

    def groups(phase):
        grouped = defaultdict(list)
        for task in tasks:
            if task["phase"] == phase:
                grouped[(task["query_id"], task["replicate"], task["trigger"])].append(task)
        return list(grouped.values())

    def run_group(group):
        for task in group:
            with lock:
                if task["task_key"] in state["completed"]:
                    continue
            removed = set((state["driver"] or {}).get("expanded_record_ids", [])) if task["arm"] in (
                "gated", "clean_gated") else set()
            result = gate.run_trajectory(task, snapshot, answerer, react_prompt, removed, args.max_steps)
            result["usage"].update(pricing_known=False,
                cost_value_semantics="unpriced accumulator; numeric zero is not a zero-cost quote")
            with lock:
                state["completed"][task["task_key"]] = result
                gate.atomic_json(checkpoint, state)
                print(json.dumps(dict(completed=len(state["completed"]), expected=len(tasks),
                                      phase=task["phase"], task_key=task["task_key"])), flush=True)

    def execute_phase(phase):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_group, group) for group in groups(phase)]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    for pending in futures:
                        pending.cancel()
                    with lock:
                        state.update(state="failed", error_type=type(exc).__name__)
                        gate.atomic_json(checkpoint, state)
                    raise

    execute_phase("calibration")
    calibration = [state["completed"][task["task_key"]] for task in tasks if task["phase"] == "calibration"]
    state["driver"] = gate.learn_driver(calibration, snapshot, args.driver_threshold,
        args.driver_min_retrievals, args.temporal_ancestry_hops, args.cluster_k, args.cluster_cosine_threshold)
    gate.atomic_json(checkpoint, state)
    gate.atomic_json(base / "frozen_driver.json", state["driver"])
    execute_phase("test")
    ordered = [state["completed"][task["task_key"]] for task in tasks]
    gate.attach_posthoc_correctness(ordered, test)
    poison = set(record_ids[-2:])
    driver = state["driver"]
    report = dict(schema="agentpoison-strategyqa-paired-gate/v1", protocol=protocol, driver=driver,
        posthoc_evaluation_only=dict(
            label_access_boundary="correctness and poison membership attached only after frozen driver and all trajectories",
            poison_record_ids=sorted(poison),
            implicated_poison_ids=sorted(set(driver["implicated_record_ids"]) & poison),
            expanded_poison_ids=sorted(set(driver["expanded_record_ids"]) & poison)),
        calibration=[row for row in ordered if row["phase"] == "calibration"],
        heldout=[row for row in ordered if row["phase"] == "test"],
        pricing_known=False, cost_value_semantics="unpriced accumulator; numeric zero is not a zero-cost quote")
    gate.atomic_json(output, report)
    import agentpoison_strategyqa_summary as summary
    sys.argv = [str(ROOT / 'code/agentpoison_strategyqa_summary.py'), '--input', str(output),
                '--out', str(base / 'summary.json'), '--frozen-protocol', str(frozen)]
    summary.main()
    scored = json.loads((base / 'summary.json').read_text())
    scored.update(pricing_known=False,
                  cost_value_semantics="unknown price; zero compatibility accumulators are not a zero-cost quote")
    gate.atomic_json(base / 'summary.json', scored)
    state.update(state="complete", report=str(output), summary=str(base / 'summary.json'))
    gate.atomic_json(checkpoint, state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError('This protocol permits 1 to 4 workers')
    run(args.out_dir, args.workers, args.resume)


if __name__ == '__main__':
    main()
