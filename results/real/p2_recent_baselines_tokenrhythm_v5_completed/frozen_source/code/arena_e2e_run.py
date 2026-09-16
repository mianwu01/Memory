"""Run MemoryArena travel on an explicit, reproducible episode subset.

The upstream runner always traverses all 270 groups.  That makes a first
end-to-end comparison unnecessarily expensive and, when arms are interrupted at
different times, produces incomparable episode sets.  This wrapper monkeypatches
only the data-loader symbol imported by ``run_travel.py``; the external
MemoryArena checkout stays pristine.

Examples (run both arms with the same arguments)::

    python3 code/arena_e2e_run.py \
      --config results/real/e2e/travel_causal-learned.json --limit 1
    python3 code/arena_e2e_run.py \
      --config results/real/e2e/travel_long_context.json --limit 1

Existing generated plans are skipped by the upstream runner, so the command is
safe to resume.  Use ``--ids`` for a pre-registered subset that is independent
of dataset ordering.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse


REPO = Path(__file__).resolve().parents[1]
DEFAULT_ARENA = REPO / "benchmarks" / "MemoryArena"

INHERITANCE_V2_SYSTEM_PROMPT = """You are a tool-using travel planner. Solve only the day/slot cells explicitly requested by the current traveler. A deterministic decoder fills every other cell from a public base itinerary that is intentionally not shown to you.

Use the available search tools for target cells that need a new value. The memory context contains the trip's day-to-city scaffold and causal-ancestor cells from earlier travelers; for join/share constraints, copy the referenced ancestor value exactly.

Your final response must contain only this compact canonical format:
=== Traveler's Plan ===
Day 2:
Breakfast: Exact Restaurant Name, City(State)
Accommodation: Exact Accommodation Name, City(State)

Rules:
- Include only query-explicit days and slots; never invent or output inherited cells.
- Every `Day N:` heading must end in a colon. Do not use Markdown bullets.
- Use canonical labels: Current City, Transportation, Breakfast, Attraction, Lunch, Dinner, Accommodation.
- Restaurant, accommodation, and attraction names must exactly match tool results and must retain their city/state suffix. Separate multiple attractions with semicolons.
- Do not include prices, ratings, cuisines, explanations, or text outside the plan."""

INHERITANCE_V3_SYSTEM_PROMPT = INHERITANCE_V2_SYSTEM_PROMPT.replace(
    "a public base itinerary that is intentionally not shown to you",
    "a public base itinerary whose full form is not shown to you",
) + """

The `<query_target_base_cells>` rows contain public-base values only for the
cells the query changes. Use their city suffix as the day-local location cue,
especially on travel days. They are not target answers: replace them according
to the current constraint unless the query explicitly requests that value."""

INHERITANCE_V2_USER_PROMPT = """Solve the query-explicit travel-plan cells for {name}.

Query: {query}

Use only the tools needed for those explicit cells. Memory ancestor rows are
authoritative references to earlier travelers. Output only a plan header plus
the requested `Day N:` and canonical slot lines. Preserve exact venue and city
strings from tool results; do not plan inherited cells or add explanations."""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--limit", type=int, default=1,
                       help="take the first N groups in benchmark order (default: 1)")
    group.add_argument("--ids", type=int, nargs="+",
                       help="run exactly these group IDs, in the given order")
    ap.add_argument("--arena_dir", default=str(DEFAULT_ARENA))
    ap.add_argument("--start_servers", action="store_true",
                    help="start and clean up the MemoryArena env/memory servers")
    args = ap.parse_args()

    arena = Path(args.arena_dir).resolve()
    config = Path(args.config).resolve()
    if not (arena / "run_travel.py").is_file():
        raise SystemExit(f"MemoryArena checkout not found at {arena}")
    if not config.is_file():
        raise SystemExit(f"config not found: {config}")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    experiment_cfg = json.load(open(config))
    inherit_unspecified = bool(
        experiment_cfg.get("task_specific", {}).get(
            "inherit_unspecified_from_base", False))
    decoder_version = str(
        experiment_cfg.get("task_specific", {}).get(
            "decoder", "query-target/base-inheritance-v1"))
    inheritance_v3 = decoder_version == "query-target/base-inheritance-v3"
    inheritance_v2 = decoder_version in {
        "query-target/base-inheritance-v2",
        "query-target/base-inheritance-v3",
    }
    inheritance_system_prompt = (
        INHERITANCE_V3_SYSTEM_PROMPT if inheritance_v3
        else INHERITANCE_V2_SYSTEM_PROMPT)
    inheritance_v2_max_tokens = int(
        experiment_cfg.get("task_specific", {}).get("llm_max_tokens", 8192))
    inheritance_v2_thinking = str(
        experiment_cfg.get("task_specific", {}).get(
            "llm_thinking", "default"))
    if inheritance_v2_thinking not in {"default", "disabled"}:
        raise ValueError(
            "task_specific.llm_thinking must be 'default' or 'disabled'")

    # Preserve the experiment's API-only/CPU-only contract.  This is set before
    # importing upstream modules because they transitively import torch.
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    os.environ.setdefault("HF_HOME", str(REPO / ".tmp" / "hf"))

    procs = []
    log_handles = []

    def start_stack():
        import requests

        cfg = json.load(open(config))
        memory_url = cfg["memory"]["server_url"].rstrip("/")
        env_url = cfg["env"]["env_server_url"].rstrip("/")
        memory_port = urlparse(memory_url).port
        if memory_port is None:
            raise RuntimeError(f"memory server URL has no port: {memory_url}")

        log_dir = REPO / ".tmp" / "e2e-server-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        mem_log = open(log_dir / "memory.log", "w")
        env_log = open(log_dir / "env.log", "w")
        log_handles.extend([mem_log, env_log])
        child_env = os.environ.copy()
        learned_graph = cfg.get("memory", {}).get("learned_graph_path")
        if learned_graph:
            graph_path = Path(learned_graph)
            if not graph_path.is_absolute():
                graph_path = REPO / graph_path
            child_env["CAUSAL_LEARNED_GRAPH"] = str(graph_path.resolve())
        procs.extend([
            subprocess.Popen(
                [sys.executable, "-u", str(REPO / "code" / "arena_serve_causal.py"),
                 "--port", str(memory_port), "--host", "127.0.0.1"],
                cwd=REPO, env=child_env, stdout=mem_log, stderr=subprocess.STDOUT),
            subprocess.Popen(
                [sys.executable, "-u", "env/env_server.py"],
                cwd=arena, env=child_env, stdout=env_log, stderr=subprocess.STDOUT),
        ])

        session = requests.Session()
        session.trust_env = False

        def wait_for(url, proc, log_path):
            deadline = time.time() + 120
            while time.time() < deadline:
                if proc.poll() is not None:
                    tail = Path(log_path).read_text(errors="replace")[-4000:]
                    raise RuntimeError(f"server exited while starting ({url}):\n{tail}")
                try:
                    if session.get(url, timeout=2).status_code < 500:
                        return
                except requests.RequestException:
                    pass
                time.sleep(0.5)
            tail = Path(log_path).read_text(errors="replace")[-4000:]
            raise RuntimeError(f"server did not become ready ({url}):\n{tail}")

        wait_for(memory_url + "/docs", procs[0], log_dir / "memory.log")
        wait_for(env_url + "/env/list", procs[1], log_dir / "env.log")
        print(f"E2E_SERVERS ready memory={memory_url} env={env_url}", flush=True)

    def stop_stack():
        for proc in reversed(procs):
            if proc.poll() is None:
                proc.terminate()
        for proc in reversed(procs):
            if proc.poll() is None:
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        for handle in log_handles:
            handle.close()

    try:
        if args.start_servers:
            start_stack()
        sys.path.insert(0, str(arena))
        os.chdir(arena)

        import run_travel

        # Optional in-process native baselines. One arm per process; fresh memory
        # per episode. This avoids optional SDK imports in the upstream server.
        local_arm = experiment_cfg.get("memory", {}).get("local_arm")
        if local_arm:
            from arena_recent_memory import RecentMemory
            memory_output = Path(experiment_cfg["output"]["output_dir"]).resolve()
            graph = experiment_cfg["memory"].get("learned_graph_path")
            if graph:
                graph = str((REPO / graph).resolve())

            def local_memory_factory(memory_system_name, user_id, server_url):
                return RecentMemory(local_arm, user_id, memory_output, graph=graph)

            run_travel.get_memory_system = local_memory_factory

        if inherit_unspecified:
            from arena_e2e_inherit import (
                add_query_target_base_cells,
                base_plan_from_memory_context,
                render_plan,
                strip_decoder_base_from_memory_context,
                target_cells_from_query,
            )

            upstream_agent = run_travel.TravelPlannerAgent

            if inheritance_v2:
                # Shared across every v2 arm.  The LLM emits only the cells the
                # query permits it to change; render_plan deterministically fills
                # the remaining public-base cells before env/memory writeback.
                import agent.travel_planner as travel_agent_module
                travel_agent_module.AGENT_USER_PROMPT_TEMPLATE = INHERITANCE_V2_USER_PROMPT

            runtime = {
                "episode_id": None,
                "attempt_id": None,
                "person": None,
                "round_idx": None,
                "call_idx": 0,
                "tool_names": None,
            }
            event_handle = None
            if inheritance_v2:
                configured_output = Path(experiment_cfg["output"]["output_dir"])
                if not configured_output.is_absolute():
                    configured_output = arena / configured_output
                configured_output.mkdir(parents=True, exist_ok=True)
                event_path = configured_output / "llm_call_usage.jsonl"
                event_handle = open(event_path, "a", encoding="utf-8")
                session_id = f"{int(time.time())}-{os.getpid()}-{uuid.uuid4().hex[:8]}"

                original_env_client = run_travel.EnvironmentClient

                class InstrumentedEnvironmentClient(original_env_client):
                    def reset(self, *positional, **keywords):
                        episode = keywords.get("seed")
                        if episode is None and positional:
                            episode = positional[0]
                        runtime.update({
                            "episode_id": int(episode) if episode is not None else None,
                            "attempt_id": f"{session_id}:{episode}",
                            "person": None,
                            "round_idx": None,
                            "call_idx": 0,
                            "tool_names": None,
                        })
                        return super().reset(*positional, **keywords)

                run_travel.EnvironmentClient = InstrumentedEnvironmentClient

            class InheritanceTravelPlannerAgent(upstream_agent):
                """Apply query-target/base inheritance before env and memory writes."""

                def __init__(self, *positional, **keywords):
                    if inheritance_v2:
                        keywords["system_prompt"] = inheritance_system_prompt
                    super().__init__(*positional, **keywords)
                    if inheritance_v2:
                        if experiment_cfg.get("task_specific", {}).get("llm_transport") == "stream_accumulate":
                            from relay_chat_transport import install_stream_transport
                            install_stream_transport(self.client.client)
                        if inheritance_v2_thinking == "disabled":
                            # DeepSeek exposes thinking as an OpenAI-compatible
                            # extra body field.  Patch only this runtime client
                            # instance, leaving the upstream checkout untouched.
                            # The ordinary upstream chat method still owns tool
                            # parsing and usage/cost accounting.
                            completions = self.client.client.chat.completions
                            api_create = completions.create

                            def create_without_thinking(*api_args, **api_kwargs):
                                extra_body = dict(api_kwargs.get("extra_body") or {})
                                extra_body["thinking"] = {"type": "disabled"}
                                api_kwargs["extra_body"] = extra_body
                                return api_create(*api_args, **api_kwargs)

                            completions.create = create_without_thinking
                        original_chat = self.client.chat_with_tools

                        def chat_with_usage(messages, tools, *args, **kwargs):
                            effective_tools = tools
                            if runtime.get("tool_names"):
                                effective_tools = [
                                    tool for tool in tools
                                    if tool.get("function", {}).get("name")
                                    in runtime["tool_names"]
                                ]

                            def invoke(call_messages, repair_reason=None):
                                before = self.client.get_usage_stats()
                                started = time.time()
                                call_keywords = dict(kwargs)
                                call_keywords["max_tokens"] = inheritance_v2_max_tokens
                                try:
                                    result = original_chat(
                                        call_messages, effective_tools, *args,
                                        **call_keywords)
                                except Exception as exc:
                                    event_handle.write(json.dumps({
                                        "schema": "memoryarena-llm-call-error/v1",
                                        "event": "api_error", "session_id": session_id,
                                        "attempt_id": runtime["attempt_id"],
                                        "episode_id": runtime["episode_id"],
                                        "round_idx": runtime["round_idx"],
                                        "error_type": type(exc).__name__,
                                        "status_code": getattr(exc, "status_code", None),
                                        "transport_attempts": getattr(exc, "transport_attempts", None),
                                        "duration_seconds": time.time() - started,
                                        "billing_usage_unknown": True,
                                    }) + "\n")
                                    event_handle.flush()
                                    raise
                                elapsed = time.time() - started
                                after = self.client.get_usage_stats()
                                runtime["call_idx"] = int(runtime["call_idx"]) + 1
                                raw = getattr(result, "raw_response", None)
                                choice = (raw.choices[0] if raw is not None
                                          and getattr(raw, "choices", None) else None)
                                event = {
                                    "schema": "memoryarena-llm-call-usage/v1",
                                    "session_id": session_id,
                                    "attempt_id": runtime["attempt_id"],
                                    "episode_id": runtime["episode_id"],
                                    "round_idx": runtime["round_idx"],
                                    "person": runtime["person"],
                                    "call_idx": runtime["call_idx"],
                                    "input_tokens": int(after["total_input_tokens"] - before["total_input_tokens"]),
                                    "output_tokens": int(after["total_output_tokens"] - before["total_output_tokens"]),
                                    "cost": float(after["total_cost"] - before["total_cost"]),
                                    "duration_seconds": elapsed,
                                    "message_chars": sum(
                                        len(str(message.get("content") or ""))
                                        for message in call_messages),
                                    "tool_schema_chars": len(json.dumps(
                                        effective_tools, ensure_ascii=False)),
                                    "n_messages": len(call_messages),
                                    "finish_reason": str(
                                        getattr(choice, "finish_reason", "") or ""),
                                    "returned_model": str(
                                        getattr(raw, "model", "") or ""),
                                    "transport_metrics": getattr(raw, "_transport_metrics", None),
                                    "provider_cost_cny": getattr(raw, "cost_cny", None),
                                    "usage": (raw.usage.model_dump() if raw is not None
                                              and getattr(raw, "usage", None) else None),
                                    "thinking_mode": inheritance_v2_thinking,
                                    "repair_reason": repair_reason,
                                }
                                event_handle.write(
                                    json.dumps(event, ensure_ascii=False) + "\n")
                                event_handle.flush()
                                os.fsync(event_handle.fileno())
                                return result, event

                            response, first_event = invoke(messages)
                            if (not response.tool_calls
                                    and (first_event["finish_reason"] == "length"
                                         or not str(response.content or "").strip())):
                                # DeepSeek occasionally consumes its entire
                                # completion budget in hidden reasoning and
                                # returns no visible final plan.  One frozen,
                                # format-only repair call preserves the same
                                # evidence/tools and avoids treating an API
                                # truncation as a semantic base-plan answer.
                                repair_messages = list(messages) + [{
                                    "role": "user",
                                    "content": (
                                        "Return the compact canonical final plan now. "
                                        "Output only the requested Day/slot lines; "
                                        "do not reason, call tools, or explain."),
                                }]
                                response, _repair_event = invoke(
                                    repair_messages,
                                    repair_reason=(
                                        "empty_final_after_" +
                                        (first_event["finish_reason"] or "unknown")),
                                )
                            return response

                        self.client.chat_with_tools = chat_with_usage

                def set_base_person(self, name: str, query: str, plan: str):
                    super().set_base_person(name, query, plan)
                    if inheritance_v2:
                        # Upstream resets ``base_messages`` here and otherwise
                        # re-inserts its full public base plan plus legacy system
                        # prompt on every call.  The deterministic decoder already
                        # owns that base; the v2 model must see neither duplicate.
                        self.base_messages = [{
                            "role": "system",
                            "content": inheritance_system_prompt,
                        }]

                def prepare_for_person(self, *positional, **keywords):
                    name = keywords.get("name")
                    round_idx = keywords.get("round_idx")
                    if name is None and positional:
                        name = positional[0]
                    if round_idx is None and len(positional) > 1:
                        round_idx = positional[1]
                    runtime.update({"person": name, "round_idx": round_idx,
                                    "call_idx": 0})
                    return super().prepare_for_person(*positional, **keywords)

                def act(self, prompt: str) -> str:
                    name = self._pending_name or "User"
                    memory_context = self._pending_memory_context or ""
                    base_plan = base_plan_from_memory_context(memory_context)
                    if not base_plan:
                        raise RuntimeError(
                            "inheritance decoding requested but the memory context "
                            "contains no base plan")
                    original_context = self._pending_memory_context
                    if inheritance_v2:
                        targets = target_cells_from_query(prompt)
                        target_slots = {slot for _day, slot in targets}
                        tool_names = set()
                        if target_slots & {"breakfast", "lunch", "dinner"}:
                            tool_names.add("RestaurantSearch")
                        if "accommodation" in target_slots:
                            tool_names.add("AccommodationSearch")
                        if "attraction" in target_slots:
                            tool_names.add("AttractionSearch")
                        if target_slots & {"transportation", "current_city"}:
                            tool_names.update({
                                "FlightSearch", "DistanceMatrix", "CitySearch"})
                        # Conservative fail-open for a future unparsed query.
                        runtime["tool_names"] = tool_names or None
                        visible_context = strip_decoder_base_from_memory_context(
                            memory_context)
                        if inheritance_v3:
                            visible_context = add_query_target_base_cells(
                                visible_context, base_plan, targets)
                        self._pending_memory_context = visible_context
                    try:
                        generated = super().act(prompt)
                    finally:
                        self._pending_memory_context = original_context
                    inherited = render_plan(
                        name, base_plan, generated,
                        (targets if inheritance_v2
                         else target_cells_from_query(prompt)))
                    if self._last_result is not None:
                        self._last_result.final_plan = inherited
                    return inherited

            run_travel.TravelPlannerAgent = InheritanceTravelPlannerAgent
            print(f"E2E_DECODER {decoder_version}", flush=True)

        load_all = run_travel.load_travel_data

        def load_subset():
            rows = load_all()
            if args.ids:
                by_id = {int(row["id"]): row for row in rows}
                missing = [i for i in args.ids if i not in by_id]
                if missing:
                    raise RuntimeError(f"episode IDs not found: {missing}")
                selected = [by_id[i] for i in args.ids]
            else:
                selected = rows[:args.limit]
            print("E2E_SUBSET ids=" + ",".join(str(row["id"]) for row in selected),
                  flush=True)
            return selected

        run_travel.load_travel_data = load_subset
        sys.argv = [str(arena / "run_travel.py"), "--config", str(config)]
        run_travel.main()
    finally:
        if "event_handle" in locals() and event_handle is not None:
            event_handle.close()
        stop_stack()


if __name__ == "__main__":
    main()
