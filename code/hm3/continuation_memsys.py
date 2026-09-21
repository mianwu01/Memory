"""Native memory outputs on the frozen stronger-actor HM3 panel.

Run each system/episode in its own process. Author code is read-only; local
stores are isolated. No recovered-rid substitution for generated memory text.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from .core import Episode, segments
from .continuation_actor import Actor, CONFIG, ENDPOINT, MODEL, write_once
from .structure_alignment import ordered_reads


COMMITS = {"mem0": ("mem0", "c7ee362aff94a369af70f13f2b4f853f6793ff4c"),
           "amem": ("AgenticMemory-paper", "0c8039f28fdcc08189a23c07a3437d9d2482f9c2"),
           "lightmem": ("LightMem", "8449d574df6bae1bdf3314a1564da65e2f37e046")}


class NativeMeter:
    def __init__(self, directory):
        self.directory = directory
        self.lock = threading.Lock()
        self.calls = 0
        self.failed = False

    def install(self):
        import openai
        parent = openai.OpenAI
        meter = self

        class Metered(parent):
            def __init__(self, *a, **kw):
                kw.update(timeout=CONFIG["timeout_seconds"], max_retries=0)
                super().__init__(*a, **kw)
                original = self.chat.completions.create

                def measured(*a, **kw):
                    with meter.lock:
                        if meter.calls >= 96 or meter.failed:
                            raise RuntimeError("native request limit or preceding invalid response")
                        meter.calls += 1
                        i = meter.calls
                    upstream_limit = kw.get("max_tokens")
                    kw["max_tokens"] = 16384
                    kw["extra_body"] = {**(kw.get("extra_body") or {}), **CONFIG["extra_body"]}
                    started = time.monotonic()
                    row = dict(call=i, model=kw.get("model"), messages=kw.get("messages"),
                               response_format=kw.get("response_format"), temperature=kw.get("temperature"),
                               upstream_max_tokens=upstream_limit, max_tokens=16384)
                    try:
                        r = original(*a, **kw)
                        row.update(event="result", returned_model=r.model,
                                   choices=[c.model_dump() for c in r.choices],
                                   usage=r.usage.model_dump() if r.usage else None,
                                   provider_cost_cny=getattr(r, "cost_cny", None))
                        if not r.usage or any(c.finish_reason == "length" for c in r.choices):
                            meter.failed = True
                        return r
                    except Exception as exc:
                        meter.failed = True
                        row.update(event="infrastructure_failure", error_type=type(exc).__name__,
                                   status=getattr(exc, "status_code", None))
                        raise RuntimeError("native API failure; sanitized details in ledger") from None
                    finally:
                        row["seconds"] = time.monotonic()-started
                        with meter.lock:
                            with (meter.directory / "memory_calls.jsonl").open("a") as f:
                                f.write(json.dumps(row) + "\n")
                self.chat.completions.create = measured
        openai.OpenAI = Metered
        return parent


def light_config(store, models):
    return {
        "pre_compress": True,
        "pre_compressor": {"model_name": "llmlingua-2", "configs": {
            "llmlingua_config": {"model_name": str(models / "llmlingua-2-bert-base-multilingual-cased-meetingbank"),
                                 "device_map": "cpu", "use_llmlingua2": True},
            "compress_config": {"instruction": "", "rate": .6, "target_token": -1}}},
        "topic_segment": True, "precomp_topic_shared": True,
        "topic_segmenter": {"model_name": "llmlingua-2"},
        "messages_use": "user_only", "metadata_generate": True, "text_summary": True,
        "memory_manager": {"model_name": "openai", "configs": {
            "model": MODEL, "api_key": os.environ["OPENAI_API_KEY"], "max_tokens": 16384,
            "openai_base_url": ENDPOINT}},
        "extract_threshold": .1, "index_strategy": "embedding",
        "text_embedder": {"model_name": "huggingface", "configs": {
            "model": str(models / "all-MiniLM-L6-v2"), "embedding_dims": 384,
            "model_kwargs": {"device": "cpu"}}},
        "retrieve_strategy": "embedding",
        "embedding_retriever": {"model_name": "qdrant", "configs": {
            "collection_name": "memories", "embedding_model_dims": 384,
            "path": str(store / "qdrant"), "on_disk": True}},
        "update": "offline", "extraction_mode": "flat",
        "history_db_path": str(store / "history.db"),
        "logging": {"level": "INFO", "console_level": "WARNING", "file_enabled": True,
                    "log_dir": str(store / "logs")}}


def build_memory(system, ep, store, source, directory):
    models = source / ".tmp/models"
    texts = [json.dumps(s, indent=1) for s in segments(ep.H)]
    write_once(directory / "write_inputs.json", texts)
    query = ep.query + "\n" + json.dumps(ep.I)
    events = []
    if system == "mem0":
        from mem0 import Memory
        backend = Memory.from_config({
            "llm": {"provider": "openai", "config": {"model": MODEL,
                    "api_key": os.environ["OPENAI_API_KEY"], "openai_base_url": ENDPOINT,
                    "temperature": 0, "max_tokens": 16384}},
            "embedder": {"provider": "huggingface", "config": {
                "model": str(models / "all-MiniLM-L6-v2"), "embedding_dims": 384,
                "model_kwargs": {"device": "cpu"}}},
            "vector_store": {"provider": "qdrant", "config": {"collection_name": "memories",
                             "path": str(store / "qdrant"), "embedding_model_dims": 384}},
            "history_db_path": str(store / "history.db")})
        for i, text in enumerate(texts):
            events.append(dict(stage="add", segment=i, result=backend.add(text, user_id=ep.id, infer=True)))
        result = backend.search(query, filters={"user_id": ep.id}, top_k=8)
        text = "\n".join(r["memory"] for r in result["results"])
        snapshot = backend.get_all(filters={"user_id": ep.id})
    elif system == "amem":
        from memory_layer import AgenticMemorySystem
        backend = AgenticMemorySystem(model_name=str(models / "all-MiniLM-L6-v2"),
                                      llm_backend="openai", llm_model=MODEL)
        for i, item in enumerate(texts):
            ident = backend.add_note(item, time=f"20260901{i:02d}00")
            events.append(dict(stage="add_note", segment=i, note=vars(backend.memories[ident]),
                               evolution_count=backend.evo_cnt))
        result = backend.find_related_memories_raw(query, k=8)
        text = result if isinstance(result, str) else result[0]
        if not isinstance(text, str):
            raise TypeError("unexpected A-Mem retrieval contract")
        snapshot = {key: vars(value) for key, value in backend.memories.items()}
    else:
        from lightmem.memory.lightmem import LightMemory
        backend = LightMemory.from_config(light_config(store, models))
        for i, item in enumerate(texts):
            stamp = f"2026-09-01 {i:02d}:00:00"
            result = backend.add_memory(messages=[{"role": "user", "content": item, "time_stamp": stamp},
                                                  {"role": "assistant", "content": "", "time_stamp": stamp}],
                                        force_segment=True, force_extract=True)
            events.append(dict(stage="add_memory", segment=i, result=result))
        backend.construct_update_queue_all_entries(max_workers=1)
        backend.offline_update_all_entries(score_threshold=.9, max_workers=1)
        events.append(dict(stage="offline_update", statistics=backend.get_token_statistics()))
        result = backend.retrieve(query, limit=8)
        text = "\n".join(result)
        snapshot = backend.embedding_retriever.get_all()
    write_once(directory / "native_events.json", events)
    write_once(directory / "native_snapshot.json", snapshot)
    return dict(text=text, result=result, query=query)


def run(args):
    import openai
    source = Path(args.source).resolve()
    out = Path(args.out)
    episodes = json.loads(Path(args.episodes).read_text())
    ep = Episode.from_dict(episodes[args.index])
    directory = out / args.system / ep.id
    directory.mkdir(parents=True, exist_ok=True)
    repo_name, expected = COMMITS[args.system]
    repo = source / "benchmarks" / repo_name
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip()
    if commit != expected or dirty:
        raise RuntimeError("Author checkout differs from frozen clean version")
    source_files = [Path(__file__), Path(__file__).with_name("continuation_actor.py")]
    write_once(directory / "protocol.json", dict(system=args.system, episode=ep.id, commit=commit,
               model=MODEL, actor_config=CONFIG, retrieval_k=8, ingestion="one public history segment per write",
               adaptation="native returned memory text, no raw-record recovery", source=str(repo),
               hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}))
    if (directory / "status.json").exists():
        print((directory / "status.json").read_text())
        return
    os.environ.update(CUDA_VISIBLE_DEVICES="", TOKENIZERS_PARALLELISM="false", MEM0_TELEMETRY="false",
                      ANONYMIZED_TELEMETRY="false", OPENAI_BASE_URL=ENDPOINT,
                      NLTK_DATA=str(source / ".tmp/nltk_data"), FASTEMBED_CACHE_PATH=str(source / ".tmp/fastembed"))
    keys = [x.strip() for x in Path(args.key_file).read_text().splitlines() if x.strip() and not x.startswith("#")]
    os.environ["OPENAI_API_KEY"] = keys[0]
    store = Path(".tmp/continuation_stores") / out.name / args.system / ep.id
    store = store.resolve()
    os.environ["MEM0_DIR"] = str(store / "mem0_home")
    for rel in ["benchmarks/mem0", "benchmarks/AgenticMemory-paper", "benchmarks/LightMem/src"]:
        sys.path.insert(0, str(source / rel))
    meter = NativeMeter(directory)
    start = time.monotonic()
    status = dict(system=args.system, episode=ep.id)
    try:
        if (directory / "memory_output.json").exists():
            result = json.loads((directory / "memory_output.json").read_text())
        else:
            store.mkdir(parents=True, exist_ok=False)
            parent = meter.install()
            capture = io.StringIO()
            errors = []

            class Capture(logging.Handler):
                def emit(self, record):
                    if record.levelno >= logging.ERROR:
                        errors.append(record.name)

            handler = Capture()
            logging.getLogger().addHandler(handler)
            try:
                with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                    result = build_memory(args.system, ep, store, source, directory)
            finally:
                openai.OpenAI = parent
                logging.getLogger().removeHandler(handler)
            markers = [x for x in ["error analyzing", "error processing api", "compress error",
                                   "error in parallel", "storing without evolution"] if x in capture.getvalue().lower()]
            if meter.failed or markers or errors:
                write_once(directory / "fallback.json", dict(api_invalid=meter.failed, markers=markers, loggers=errors))
                raise RuntimeError("author error or fallback; native output not a valid run")
            write_once(directory / "memory_output.json", result)
        actor = Actor(directory / "actor", args.key_file, max_requests=3)
        for repeat in range(3):
            actor.ask(ep, ordered_reads(ep, ep.S0.objects, []), f"native_{args.system}", repeat,
                      memory_text=result["text"])
        status.update(status="completed", output_characters=len(result["text"]))
    except Exception as exc:
        import traceback
        status.update(status="invalid_execution", error_type=type(exc).__name__,
                      traceback=[dict(file=Path(x.filename).name, line=x.lineno, function=x.name)
                                 for x in traceback.extract_tb(exc.__traceback__)])
    status.update(memory_calls=meter.calls, seconds=time.monotonic()-start)
    write_once(directory / "status.json", status)
    print(json.dumps(status), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default="../Memory")
    p.add_argument("--episodes", required=True)
    p.add_argument("--system", choices=COMMITS, required=True)
    p.add_argument("--index", type=int, default=0)
    p.add_argument("--out", required=True)
    p.add_argument("--key-file", default="api/api.txt")
    run(p.parse_args())
