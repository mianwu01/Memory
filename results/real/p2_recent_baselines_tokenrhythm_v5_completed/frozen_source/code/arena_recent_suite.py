"""Bounded paired MemoryArena run; invoke through run_with_local_deepseek.py."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from arena_recent_memory import ARMS, MODEL, ROOT, prepare_environment

GRAPH = "results/real/p2_compact_v3/travel_learned_graph_holdout_111_120.json"
SOURCE_FILES = ["code/arena_recent_memory.py", "code/arena_e2e_run.py",
                "code/arena_e2e_inherit.py", "code/arena_causal_memory.py",
                "code/arena_recent_suite.py", "code/run_with_local_deepseek.py",
                "code/relay_chat_transport.py", GRAPH]


def source_hashes():
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCE_FILES}
    for repo in ["mem0", "A-mem", "LightMem", "MemoryArena"]:
        hashes["upstream_commit:" + repo] = subprocess.check_output(
            ["git", "-C", str(ROOT / "benchmarks" / repo), "rev-parse", "HEAD"], text=True).strip()
    for filename in ["model.safetensors", "config.json", "tokenizer.json"]:
        path = ROOT / ".tmp/models/all-MiniLM-L6-v2" / filename
        hashes["embedding:" + filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["development", "evaluation"], required=True)
    ap.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    ap.add_argument("--workers", type=int, default=9)
    ap.add_argument("--env-port", type=int, default=8931)
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--family", default="p2_recent_baselines_tokenrhythm_v5")
    args = ap.parse_args()
    if not 1 <= args.env_port <= 65535:
        ap.error("env-port must be between 1 and 65535")
    prepare_environment()
    os.environ["MEMORY_API_TRANSPORT"] = "stream_accumulate"
    endpoint = os.environ.get("OPENAI_BASE_URL", "").rstrip("/")
    if not endpoint.startswith("https://") or not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("Use the local DeepSeek wrapper and the authorized relay")
    if Path(args.family).name != args.family or args.family in {".", ".."}:
        raise ValueError("family must be a single directory name")
    ids = [101] if args.phase == "development" else [111, 112, 113]
    base = ROOT / ("results/development" if args.phase == "development" else "results/real") / args.family
    base.mkdir(parents=True, exist_ok=True)
    protocol = dict(schema="memoryarena-recent-baselines/v1", phase=args.phase,
                    episode_ids=ids, arms=list(ARMS), model=MODEL,
                    endpoint=endpoint, source_hashes=source_hashes(),
                    interpretation="paired descriptive replication; reused historical holdout IDs, not pristine confirmatory",
                    decoder="query-target/base-inheritance-v3", actor_thinking="default",
                    transport="stream_accumulate", sdk_retries=0,
                    request_start_spacing_seconds=2.1, explicit_http_retries=3,
                    retriable_pre_stream_statuses=[429, 500, 502, 503, 504],
                    retriable_pre_stream_transport_errors=["APIConnectionError", "APITimeoutError"],
                    timeout_seconds=dict(connect=30, read=180, write=60, pool=60),
                    opened_stream_retry=False, failed_attempt_billing="unknown_without_usage",
                    rate_retry_delays_seconds=[15, 30, 60],
                    memory_thinking="disabled", memory_max_tokens=8192,
                    memory_length_repair_max_tokens=16384, summary_budget_cl100k=4096,
                    graph=GRAPH, seeds="one API realization per arm/episode",
                    selection="first three IDs of existing 111-120 graph holdout; fixed before new evaluation",
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    protocol_path = base / "protocol.json"
    if args.phase == "evaluation":
        if args.freeze:
            # Exclusive creation prevents quietly changing the experiment.
            with protocol_path.open("x") as handle:
                json.dump(protocol, handle, indent=2)
            print("FROZEN", protocol_path, flush=True)
            return
        frozen = json.loads(protocol_path.read_text())
        if frozen["source_hashes"] != source_hashes():
            raise RuntimeError("Source changed after freeze; record a new protocol version")
        if any(frozen[key] != protocol[key] for key in ("episode_ids", "model", "endpoint", "arms")):
            raise RuntimeError("Frozen episode selection, route, model or arms changed")
    else:
        if protocol_path.exists():
            previous = json.loads(protocol_path.read_text())
            if any(previous[key] != protocol[key] for key in ("model", "endpoint", "source_hashes")):
                raise RuntimeError("Development route/model/source changed; use a new family")
        protocol_path.write_text(json.dumps(protocol, indent=2))

    config_dir = base / "configs"
    config_dir.mkdir(exist_ok=True)
    template = json.loads((ROOT / "results/real/p2_compact_v3/configs/travel_query-ancestry-v3-heldout-111-120.json").read_text())
    for arm in args.arms:
        if (base / "e2e" / arm).exists():
            raise RuntimeError("Arm output already exists; use a new family for a fresh run")
        cfg = json.loads(json.dumps(template))
        cfg["agent"].update(base_url=endpoint, model_name=MODEL)
        cfg["task_specific"]["llm_transport"] = "stream_accumulate"
        cfg["memory"].update(local_arm=arm, memory_system_name="recent-" + arm)
        cfg["env"]["env_server_url"] = f"http://127.0.0.1:{args.env_port}"
        cfg["output"] = dict(output_dir=str(base / "e2e" / arm),
                              log_dir=str(base / "logs" / arm),
                              global_csv=str(base / ("results_" + arm + ".csv")))
        (config_dir / (arm + ".json")).write_text(json.dumps(cfg, indent=2))

    logs = base / "logs"
    logs.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "code") + os.pathsep + str(ROOT / "benchmarks/MemoryArena")
    env["HF_HOME"] = str(ROOT / ".tmp/hf")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CUDA_VISIBLE_DEVICES"] = ""
    with (logs / "environment.log").open("a") as env_log:
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "env.env_server:app",
                                   "--host", "127.0.0.1", "--port", str(args.env_port), "--log-level", "warning"],
                                  cwd=ROOT / "benchmarks/MemoryArena", env=env,
                                  stdout=env_log, stderr=subprocess.STDOUT)
        try:
            import requests
            session = requests.Session()
            session.trust_env = False
            deadline = time.monotonic() + 120
            while True:
                if server.poll() is not None:
                    raise RuntimeError("environment server failed; inspect environment.log")
                try:
                    if session.get(f"http://127.0.0.1:{args.env_port}/env/list", timeout=2).ok:
                        break
                except requests.RequestException:
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError("environment startup")
                time.sleep(0.5)

            def run(arm):
                start = time.monotonic()
                with (logs / (arm + ".log")).open("a") as handle:
                    completed = subprocess.run([sys.executable, "-u", str(ROOT / "code/arena_e2e_run.py"),
                        "--config", str(config_dir / (arm + ".json")), "--ids", *map(str, ids)],
                        cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
                result = dict(arm=arm, exit_code=completed.returncode,
                              wall_seconds=time.monotonic() - start)
                print(json.dumps(result), flush=True)
                return result

            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                results = list(pool.map(run, args.arms))
            (base / ("run_status_" + time.strftime("%Y%m%d_%H%M%S") + ".json")).write_text(json.dumps(results, indent=2))
            if any(row["exit_code"] for row in results):
                raise SystemExit(1)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
