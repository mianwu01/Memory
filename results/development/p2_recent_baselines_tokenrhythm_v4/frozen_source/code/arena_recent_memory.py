"""Native memory adapters for the September 4 comparison (no upstream edits).

Run one experiment arm per process. A-Mem's native constructor resets its Chroma
collection, so episodes must be sequential within that process. All stores are
fresh per episode. Only public base plans and the actor's own writebacks enter.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = os.environ.get("OPENAI_MODEL", "deepseek-v4-flash")
ARMS = ("ours", "noG", "noGcompact", "bm25", "full", "dense", "summary", "mem0", "amem", "lightmem")


def prepare_environment():
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["MEM0_TELEMETRY"] = "false"
    os.environ["ANONYMIZED_TELEMETRY"] = "false"
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    for rel in ("benchmarks/mem0", "benchmarks/A-mem", "benchmarks/LightMem/src"):
        path = str(ROOT / rel)
        if path not in sys.path:
            sys.path.insert(0, path)


def embedding_model():
    return str(ROOT / ".tmp/models/all-MiniLM-L6-v2")


def upstream_class(filename, name):
    path = ROOT / "benchmarks/MemoryArena/memory/memory_systems" / filename
    spec = importlib.util.spec_from_file_location("arena_native_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)


class Ledger:
    def __init__(self, output, arm, episode, instance):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.arm, self.episode, self.instance = arm, episode, instance
        self.phase, self.round = "init", 0
        self.lock = threading.Lock()
        self.failed_calls = 0

    def write(self, event, **payload):
        row = dict(schema="memoryarena-memory-events/v1", event=event,
                   arm=self.arm, episode_id=self.episode, instance=self.instance,
                   phase=self.phase, round_idx=self.round, **payload)
        with self.lock, (self.output / "memory_events.jsonl").open("a") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def instrument(self, client):
        """Instrument this client only; actor settings are untouched.

        Memory metadata uses non-thinking JSON with a common 8192-token cap.
        A-Mem's OpenAI JSON schema is transported as JSON object and validated
        locally. Native prompts, update decisions and retrieval remain intact.
        """
        client.timeout = 180
        client.max_retries = 2
        if os.environ.get("MEMORY_API_TRANSPORT") == "stream_accumulate":
            from relay_chat_transport import install_stream_transport
            install_stream_transport(client)
        create = client.chat.completions.create

        def measured(*args, **kwargs):
            if self.failed_calls:
                raise RuntimeError("memory API disabled after an unresolved failure")
            kwargs["max_tokens"] = 8192
            extra = dict(kwargs.get("extra_body") or {})
            extra["thinking"] = {"type": "disabled"}
            kwargs["extra_body"] = extra
            schema = None
            fmt = kwargs.get("response_format") or {}
            if fmt.get("type") == "json_schema":
                schema = fmt["json_schema"]["schema"]
                kwargs["response_format"] = {"type": "json_object"}
                kwargs["messages"] = list(kwargs["messages"]) + [{"role": "user", "content":
                    "Return JSON conforming exactly to this schema (including string-valued IDs):\n" + json.dumps(schema)}]
            started = time.monotonic()
            try:
                response = create(*args, **kwargs)
            except Exception as exc:
                # Exception strings can contain request headers: record type only.
                self.write("llm_error", error_type=type(exc).__name__,
                           status_code=getattr(exc, "status_code", None),
                           transport_attempts=getattr(exc, "transport_attempts", None),
                           duration_seconds=time.monotonic() - started)
                self.failed_calls += 1
                raise
            usage = response.usage.model_dump() if response.usage else {}
            self.write("llm", usage=usage, returned_model=response.model,
                       provider_cost_cny=getattr(response, "cost_cny", None),
                       transport_metrics=getattr(response, "_transport_metrics", None),
                       finish_reason=response.choices[0].finish_reason,
                       duration_seconds=time.monotonic() - started)
            if response.choices[0].finish_reason == "length":
                self.write("metadata_repair", reason="length", next_max_tokens=16384)
                kwargs["max_tokens"] = 16384
                started = time.monotonic()
                try:
                    response = create(*args, **kwargs)
                except Exception as exc:
                    self.failed_calls += 1
                    self.write("llm_error", error_type=type(exc).__name__, repair=True,
                               status_code=getattr(exc, "status_code", None),
                               transport_attempts=getattr(exc, "transport_attempts", None),
                               duration_seconds=time.monotonic() - started)
                    raise
                usage = response.usage.model_dump() if response.usage else {}
                self.write("llm", usage=usage, returned_model=response.model,
                           transport_metrics=getattr(response, "_transport_metrics", None),
                           provider_cost_cny=getattr(response, "cost_cny", None),
                           finish_reason=response.choices[0].finish_reason,
                           duration_seconds=time.monotonic() - started, repair=True)
                if response.choices[0].finish_reason == "length":
                    self.failed_calls += 1
                    raise RuntimeError("memory metadata truncated after one repair")
            if schema:
                import jsonschema
                try:
                    jsonschema.validate(json.loads(response.choices[0].message.content), schema)
                except (ValueError, jsonschema.ValidationError):
                    self.failed_calls += 1
                    self.write("metadata_error", reason="schema_validation")
                    raise
            return response

        client.chat.completions.create = measured


class RecentMemory:
    """Local MemoryClient-compatible interface with the shared v3 base contract."""
    def __init__(self, arm, user_id, output, graph=None):
        if arm not in ARMS:
            raise ValueError(arm)
        prepare_environment()
        self.arm, self.base, self.count = arm, "", 0
        self.instance = uuid.uuid4().hex
        match = re.search(r"data_(\d+)", user_id)
        self.ledger = Ledger(output, arm, int(match[1]) if match else user_id, self.instance)
        self.store = ROOT / ".tmp/recent-memory-stores" / self.instance
        self.store.mkdir(parents=True)
        self.user_id = user_id
        started = time.monotonic()
        self.backend = self._make(graph)
        self.ledger.write("init", duration_seconds=time.monotonic() - started)

    def _make(self, graph):
        if self.arm in {"ours", "noG", "noGcompact"}:
            from arena_causal_memory import CausalMemorySystem
            return CausalMemorySystem(
                graph_mode="rule" if self.arm == "noG" else "learned",
                learned_graph_path=graph, use_names=self.arm == "noG",
                ablate_graph=self.arm != "ours", inherit_unspecified_from_base=True,
                keep_provenance=False, compact_serialization=self.arm != "noG",
                decoder_base_tag=True)
        if self.arm == "bm25":
            return upstream_class("rag.py", "RAGMemorySystem")(retrieval_method="bm25")
        if self.arm == "full":
            return upstream_class("long_context.py", "LongContextMemorySystem")()
        if self.arm == "dense":
            from sentence_transformers import SentenceTransformer
            self.embedder = SentenceTransformer(embedding_model(), device="cpu")
            self.chunks, self.vectors = [], []
            return None
        if self.arm == "summary":
            from openai import OpenAI
            self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"],
                                 base_url=os.environ["OPENAI_BASE_URL"])
            self.ledger.instrument(self.client)
            self.summary = ""
            return None
        if self.arm == "mem0":
            from mem0 import Memory
            backend = Memory.from_config({
                "llm": {"provider": "deepseek", "config": {
                    "model": MODEL, "api_key": os.environ["OPENAI_API_KEY"],
                    "deepseek_base_url": os.environ["OPENAI_BASE_URL"], "max_tokens": 8192}},
                "embedder": {"provider": "huggingface", "config": {
                    "model": embedding_model(), "model_kwargs": {"device": "cpu"},
                    "embedding_dims": 384}},
                "vector_store": {"provider": "qdrant", "config": {
                    "collection_name": "memories", "path": str(self.store / "qdrant"),
                    "embedding_model_dims": 384}},
                "history_db_path": str(self.store / "history.db"),
            })
            self.ledger.instrument(backend.llm.client)
            return backend
        if self.arm == "amem":
            from agentic_memory.memory_system import AgenticMemorySystem
            backend = AgenticMemorySystem(model_name=embedding_model(), llm_backend="openai",
                                          llm_model=MODEL, api_key=os.environ["OPENAI_API_KEY"])
            self.ledger.instrument(backend.llm_controller.llm.client)
            return backend
        if self.arm == "lightmem":
            from lightmem.memory.lightmem import LightMemory
            backend = LightMemory.from_config({
                "pre_compress": False, "topic_segment": False,
                "metadata_generate": True, "text_summary": True,
                "messages_use": "user_only", "index_strategy": "embedding",
                "retrieve_strategy": "embedding", "update": "offline",
                "memory_manager": {"model_name": "deepseek", "configs": {
                    "model": MODEL, "api_key": os.environ["OPENAI_API_KEY"],
                    "deepseek_base_url": os.environ["OPENAI_BASE_URL"],
                    "max_tokens": 8192, "thinking": "disabled"}},
                "text_embedder": {"model_name": "huggingface", "configs": {
                    "model": embedding_model(), "model_kwargs": {"device": "cpu"},
                    "embedding_dims": 384}},
                "embedding_retriever": {"model_name": "qdrant", "configs": {
                    "collection_name": "memories", "path": str(self.store / "qdrant"),
                    "embedding_model_dims": 384, "on_disk": True}},
                "history_db_path": str(self.store / "history.db"),
                "logging": {"level": "WARNING", "console_level": "WARNING"},
            })
            self.ledger.instrument(backend.manager.client)
            # Upstream's DeepSeek manager omits the update helper that its
            # LightMemory.offline_update_all_entries calls. Reuse the author's
            # OpenAI helper with the native DeepSeek generate_response method.
            from lightmem.factory.memory_manager.openai import OpenaiManager
            import types
            backend.manager._call_update_llm = types.MethodType(
                OpenaiManager._call_update_llm, backend.manager)
            return backend
        raise AssertionError(self.arm)

    def add(self, chunk):
        self.ledger.phase, self.ledger.round = "write", self.count
        failures_before = self.ledger.failed_calls
        started = time.monotonic()
        payload = json.loads(chunk)
        if payload.get("is_base_person"):
            self.base = payload.get("final_plan", "")
        result = None
        if self.arm in {"ours", "noG", "noGcompact", "bm25", "full"}:
            result = self.backend.add_chunk(chunk)
        elif self.arm == "dense":
            # Same 2048-token chunk unit as native MemoryArena BM25.
            import tiktoken
            enc = tiktoken.encoding_for_model("gpt-4o-mini")
            tokens = enc.encode(chunk, disallowed_special=())
            for start in range(0, len(tokens), 2048):
                piece = enc.decode(tokens[start:start + 2048])
                self.chunks.append(piece)
                self.vectors.append(self.embedder.encode(piece, normalize_embeddings=True))
        elif self.arm == "summary":
            response = self.client.chat.completions.create(model=MODEL, temperature=0.1,
                messages=[{"role": "system", "content":
                    "Maintain a rolling travel memory for later travelers. Update the previous "
                    "summary using this new record. Preserve traveler names, exact day/slot/venue "
                    "and city strings, constraints and dependencies. Do not conflate travelers. "
                    "Keep within 2000 words; prioritize precise facts over commentary. "
                    "Return only the updated memory."},
                    {"role": "user", "content": "Previous memory:\n" + self.summary +
                     "\nNew record:\n" + chunk}])
            self.summary = response.choices[0].message.content
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            tokens = enc.encode(self.summary, disallowed_special=())
            if len(tokens) > 4096:
                response = self.client.chat.completions.create(model=MODEL, temperature=0.1,
                    messages=[{"role": "system", "content":
                        "Compress this travel memory to at most 3000 tokens. Keep names, days, "
                        "exact venue/city values and cross-traveler dependencies. Use compact "
                        "tables and shared base plus explicit traveler deltas. Return only memory."},
                        {"role": "user", "content": self.summary}])
                self.summary = response.choices[0].message.content
                tokens = enc.encode(self.summary, disallowed_special=())
                if len(tokens) > 4096:
                    self.summary = enc.decode(tokens[:4096])
                    self.ledger.write("summary_budget_clip", tokens_before=len(tokens), budget=4096)
            result = {"summary": self.summary}
        elif self.arm == "mem0":
            result = self.backend.add(chunk, user_id=self.user_id)
        elif self.arm == "amem":
            # Author SDK exposes analysis separately; explicitly run its native
            # metadata method before add_note/evolution (not empty metadata).
            metadata = self.backend.analyze_content(chunk)
            ident = self.backend.add_note(chunk, **metadata)
            result = vars(self.backend.memories[ident])
        elif self.arm == "lightmem":
            from datetime import datetime, timedelta
            stamp = (datetime(2026, 9, 4) + timedelta(minutes=self.count)).strftime("%Y/%m/%d (%a) %H:%M")
            result = self.backend.add_memory(
                [{"role": "user", "content": chunk, "time_stamp": stamp}],
                force_segment=True, force_extract=True)
            # Treat each completed travel round as a consolidation boundary.
            self.backend.construct_update_queue_all_entries(max_workers=1)
            self.backend.offline_update_all_entries(score_threshold=0.8, max_workers=1)
        if self.ledger.failed_calls > failures_before:
            raise RuntimeError("native backend swallowed an API/metadata failure; refusing to score this attempt")
        self.ledger.write("write", chunk=chunk, result=result,
                          duration_seconds=time.monotonic() - started)
        self.count += 1
        return result

    def wrap_user_prompt(self, prompt):
        self.ledger.phase, self.ledger.round = "retrieve", self.count
        started = time.monotonic()
        if self.arm in {"ours", "noG", "noGcompact", "bm25", "full"}:
            wrapped = self.backend.wrap_user_prompt(prompt)
            body = wrapped.split("<memory_context>", 1)[1].split("</memory_context>", 1)[0]
        elif self.arm == "dense":
            import numpy as np
            query = self.embedder.encode(prompt, normalize_embeddings=True)
            scores = np.array(self.vectors) @ query if self.vectors else []
            order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:5]
            body = "\n".join(self.chunks[i] for i in order)
        elif self.arm == "summary":
            body = self.summary
        elif self.arm == "mem0":
            result = self.backend.search(prompt, filters={"user_id": self.user_id}, limit=5)
            body = "\n".join(row["memory"] for row in result.get("results", []))
        elif self.arm == "amem":
            result = self.backend.search(prompt.lower(), k=5)
            body = "\n".join(str(row.get("content", "")) + " (context: " +
                             str(row.get("context", "")) + ")" for row in result)
        elif self.arm == "lightmem":
            body = "\n".join(self.backend.retrieve(prompt, limit=5))
        if self.arm not in {"ours", "noG", "noGcompact"}:
            body = ("\n<decoder_base_itinerary>\n" + self.base +
                    "\n</decoder_base_itinerary>\n<inheritance_policy>\n"
                    "Solve only query-explicit target cells. A deterministic decoder "
                    "copies every other cell from the public base itinerary.\n"
                    "</inheritance_policy>\n" + (body or "None"))
        wrapped = "<memory_context>" + body + "\n</memory_context>\nUser: " + prompt
        self.ledger.write("retrieve", prompt=prompt, context=wrapped,
                          duration_seconds=time.monotonic() - started)
        return wrapped
