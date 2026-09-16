"""Author implementations with observable, fail-closed task interfaces.

No actor prompt, answer decoder, retrieval algorithm, or author memory prompt is
replaced here. Memory calls use non-thinking DeepSeek; the actor setting is
registered separately. Transport records requests/responses without credentials.
"""
from __future__ import annotations

import contextlib
import copy
import functools
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
EMBEDDING = ROOT / ".tmp/models/all-MiniLM-L6-v2"
# LLMLingua dispatches tokenization by this literal model-family substring.
# Keep the canonical name when using a local cached model; no algorithm patch.
COMPRESSOR = ROOT / ".tmp/models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
GRAPH = ROOT / "results/real/p2_compact_v3/travel_learned_graph_holdout_111_120.json"
ARMS = ("ours", "noGcompact", "query_only", "bm25", "full", "dense", "summary", "mem0", "amem", "lightmem")


def environment():
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["MEM0_TELEMETRY"] = "false"
    os.environ["ANONYMIZED_TELEMETRY"] = "false"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("NLTK_DATA", str(ROOT / ".tmp/nltk_data"))
    os.environ.setdefault("FASTEMBED_CACHE_PATH", str(ROOT / ".tmp/fastembed"))
    for rel in ("benchmarks/MemoryArena", "benchmarks/mem0",
                "benchmarks/AgenticMemory-paper", "benchmarks/LightMem/src"):
        p = str(ROOT / rel)
        if p not in sys.path:
            sys.path.insert(0, p)


class InvalidExecution(RuntimeError):
    """A technical fallback must not be reported as a valid method result."""


def request_mode_parameters(endpoint, phase, actor_thinking):
    if phase == "actor" and actor_thinking == "default":
        return {}
    params = {"thinking": {"type": "disabled"}}
    # The relay's normalized OpenAI route ignores DeepSeek's thinking field on
    # hard prompts. A paired exact-request probe verified this standard field.
    if endpoint.rstrip("/") == "https://aiaaa.cc/v1":
        params["reasoning_effort"] = "none"
    return params


class Runtime:
    def __init__(self, directory, arm, episode, actor_thinking="disabled"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.arm, self.episode = arm, episode
        self.instance = uuid.uuid4().hex
        self.phase = "init"
        self.round = 0
        self.failures = []
        self.counts = {}
        self.lock = threading.Lock()
        self.original_openai = None
        self.actor_thinking = actor_thinking

    def event(self, kind, **payload):
        row = dict(schema="faithful-memory/v1", arm=self.arm, episode=self.episode,
                   instance=self.instance, phase=self.phase, round=self.round,
                   time=time.time(), event=kind, **payload)
        with self.lock:
            self.counts[kind] = self.counts.get(kind, 0) + 1
            with (self.directory / "events.jsonl").open("a") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def fail(self, reason):
        self.failures.append(reason)
        self.event("invalid", reason=reason)

    def require_valid(self):
        if self.failures:
            raise InvalidExecution("; ".join(self.failures))

    def install_clients(self):
        """Install before importing authors' modules; preserve their call APIs."""
        import openai
        from faithful_transport import ReasoningHistory, install_faithful_stream_transport
        runtime = self
        original = openai.OpenAI
        self.original_openai = original

        class MeteredOpenAI(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if str(self.base_url).rstrip("/") != os.environ["OPENAI_BASE_URL"].rstrip("/"):
                    raise InvalidExecution("Unexpected API route")
                install_faithful_stream_transport(self)
                create = self.chat.completions.create
                reasoning_history = ReasoningHistory()

                def measured(*args, **kwargs):
                    runtime.require_valid()
                    native_limit = kwargs.get("max_tokens")
                    extra = dict(kwargs.get("extra_body") or {})
                    mode = request_mode_parameters(os.environ["OPENAI_BASE_URL"], runtime.phase, runtime.actor_thinking)
                    if mode:
                        extra["thinking"] = mode["thinking"]
                        if "reasoning_effort" in mode:
                            kwargs["reasoning_effort"] = mode["reasoning_effort"]
                    elif kwargs.get("messages"):
                        kwargs["messages"] = reasoning_history.prepare(kwargs["messages"])
                    kwargs["extra_body"] = extra
                    started = time.monotonic()
                    try:
                        result = create(*args, **kwargs)
                    except Exception as exc:
                        runtime.event("api_error", error_type=type(exc).__name__,
                                      status_code=getattr(exc, "status_code", None),
                                      attempts=getattr(exc, "transport_attempts", None),
                                      usage_unknown=True)
                        runtime.fail("API request did not produce a complete response")
                        raise
                    choices = result.choices
                    for choice in choices:
                        reasoning_history.remember(choice.message)
                    runtime.event("llm", model=result.model,
                                  endpoint=os.environ["OPENAI_BASE_URL"],
                                  provider_cost_cny=getattr(result, "cost_cny", None),
                                  billing_pending=getattr(result, "billing_pending", None),
                                  trace_id=getattr(result, "trace_id", None),
                                  requested_model=kwargs.get("model"),
                                  max_tokens=kwargs.get("max_tokens"),
                                  upstream_max_tokens=native_limit,
                                  thinking=extra.get("thinking", "provider_default"),
                                  reasoning_effort=kwargs.get("reasoning_effort", "provider_default"),
                                  messages=kwargs.get("messages"), tools=kwargs.get("tools"),
                                  usage=result.usage.model_dump() if result.usage else None,
                                  choices=[c.model_dump() for c in choices],
                                  transport=getattr(result, "_transport_metrics", None),
                                  duration_seconds=time.monotonic() - started)
                    runtime.validate_completion(result)
                    return result

                self.chat.completions.create = measured

        openai.OpenAI = MeteredOpenAI

    def validate_completion(self, result):
        if not result.usage or not result.choices:
            self.fail("Missing response usage or choices")
            raise InvalidExecution("Incomplete API response")
        details = getattr(result.usage, "completion_tokens_details", None)
        reasoning = getattr(details, "reasoning_tokens", 0) or 0
        if (self.phase != "actor" and os.environ.get("OPENAI_BASE_URL", "").rstrip("/") == "https://aiaaa.cc/v1"
                and reasoning > 0):
            self.fail("Relay ignored explicit reasoning_effort=none for memory")
            raise InvalidExecution("Memory model mode is inconsistent with registered request")
        if any(c.finish_reason == "length" for c in result.choices):
            if self.phase == "actor":
                # The original actor must see its original bounded response.
                # Do not discard hard cases or retry until an answer succeeds.
                self.event("actor_generation_failure", reason="native_token_limit",
                           policy="unaltered response passed to original actor; score its output")
            else:
                self.fail("Truncated memory completion")
                raise InvalidExecution("Incomplete memory generation; no repair")

    def watch(self, obj, method, label, validate=None):
        original = getattr(obj, method)

        @functools.wraps(original)
        def observed(*args, **kwargs):
            try:
                result = original(*args, **kwargs)
            except Exception as exc:
                self.fail(f"{label}: {type(exc).__name__}")
                raise
            self.event("mechanism", mechanism=label)
            if validate:
                validate(result)
            return result

        setattr(obj, method, observed)

    @contextlib.contextmanager
    def native_call(self):
        # Several upstream implementations print an error and return a fallback.
        # Observe it without changing their algorithm, then reject the run.
        stream = io.StringIO()
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                if record.levelno >= logging.ERROR:
                    records.append(record.getMessage())

        handler = Capture()
        logging.getLogger().addHandler(handler)
        try:
            with contextlib.redirect_stdout(stream):
                yield
        finally:
            logging.getLogger().removeHandler(handler)
            output = stream.getvalue()
            # Log exception types/markers, not arbitrary exception strings which
            # can include request headers or provider credentials.
            bad = any(s in output.lower() for s in (
                "compress error", "error processing api", "error in parallel",
                "secondary compress error", "error analyzing", "storing without evolution"))
            if bad or records:
                self.fail("Upstream reported a processing error or fallback")
            self.require_valid()


def native_arena_class(filename, name):
    path = ROOT / "benchmarks/MemoryArena/memory/memory_systems" / filename
    spec = importlib.util.spec_from_file_location("faithful_arena_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)


def lightmem_config(store, model):
    """Author LoCoMo LightMem configuration, CPU and authorized route only.

    The optional StructMem summarization extension is not LightMem and is not
    enabled. Native metadata text_summary is enabled, as in the author script.
    """
    return {
        "pre_compress": True,
        "pre_compressor": {"model_name": "llmlingua-2", "configs": {
            "llmlingua_config": {"model_name": str(COMPRESSOR), "device_map": "cpu",
                                 "use_llmlingua2": True},
            "compress_config": {"instruction": "", "rate": 0.6, "target_token": -1}}},
        "topic_segment": True, "precomp_topic_shared": True,
        "topic_segmenter": {"model_name": "llmlingua-2"},
        "messages_use": "user_only", "metadata_generate": True, "text_summary": True,
        "memory_manager": {"model_name": "openai", "configs": {
            "model": model, "api_key": os.environ["OPENAI_API_KEY"], "max_tokens": 16000,
            "openai_base_url": os.environ["OPENAI_BASE_URL"]}},
        "extract_threshold": 0.1, "index_strategy": "embedding",
        "text_embedder": {"model_name": "huggingface", "configs": {
            "model": str(EMBEDDING), "embedding_dims": 384, "model_kwargs": {"device": "cpu"}}},
        "retrieve_strategy": "embedding",
        "embedding_retriever": {"model_name": "qdrant", "configs": {
            "collection_name": "memories", "embedding_model_dims": 384,
            "path": str(store / "qdrant"), "on_disk": True}},
        "update": "offline", "extraction_mode": "flat",
        "history_db_path": str(store / "history.db"),
        "logging": {"level": "INFO", "console_level": "WARNING", "file_enabled": True,
                    "log_dir": str(store / "logs")},
    }


class AuthorMemory:
    """Minimal record/read boundary; memory operations remain author methods."""
    def __init__(self, arm, runtime, *, retrieval_k=None):
        environment()
        self.arm, self.runtime = arm, runtime
        if retrieval_k is None:
            # Author task-evaluation settings. Tiny library defaults (20/10)
            # should not handicap full-plan retrieval relative to a visible base.
            retrieval_k = {"mem0": 200, "lightmem": 60, "amem": 10}.get(arm)
        self.retrieval_k = retrieval_k
        self.store = runtime.directory / "store"
        self.store.mkdir()
        self.model = os.environ.get("OPENAI_MODEL", "deepseek-flash")
        self.backend = self._make()
        runtime.event("init", backend_module=type(self.backend).__module__,
                      backend_class=type(self.backend).__name__, retrieval_k=retrieval_k)

    def _make(self):
        r = self.runtime
        if self.arm == "mem0":
            from mem0 import Memory
            from mem0.utils.spacy_models import get_nlp_full, get_nlp_lemma
            if get_nlp_full() is None or get_nlp_lemma() is None:
                raise InvalidExecution("Mem0 spaCy full/lemma models unavailable")
            backend = Memory.from_config({
                "llm": {"provider": "openai", "config": {
                    "model": self.model, "api_key": os.environ["OPENAI_API_KEY"],
                    "openai_base_url": os.environ["OPENAI_BASE_URL"], "max_tokens": 16000}},
                "embedder": {"provider": "huggingface", "config": {
                    "model": str(EMBEDDING), "model_kwargs": {"device": "cpu"}, "embedding_dims": 384}},
                "vector_store": {"provider": "qdrant", "config": {
                    "collection_name": "memories", "path": str(self.store / "qdrant"),
                    "embedding_model_dims": 384}},
                "history_db_path": str(self.store / "history.db")})
            if backend.vector_store._get_bm25_encoder() is None or not backend.vector_store._has_bm25_slot:
                raise InvalidExecution("Mem0 BM25 encoder or sparse index disabled")
            for method in ("keyword_search", "search"):
                r.watch(backend.vector_store, method, "mem0_" + method)
            r.watch(backend, "_compute_entity_boosts", "mem0_entity_boosts")
            return backend
        if self.arm == "amem":
            from test_advanced_robust import RobustAdvancedMemAgent
            import llm_text_parsers as parsers
            self.agent = RobustAdvancedMemAgent(
                model=self.model, backend="openai", retrieve_k=self.retrieval_k or 10,
                temperature_c5=0.5)
            backend = self.agent.memory_system
            # The author's robust parser may use heuristics after a failed LLM
            # extraction. Retain that behavior but disqualify the attempt.
            for method in ("_heuristic_keywords", "_heuristic_context"):
                r.watch(parsers, method, "amem_" + method,
                        validate=lambda _result: r.fail("A-Mem metadata heuristic fallback"))
            for method in ("process_memory", "find_related_memories_raw", "consolidate_memories"):
                r.watch(backend, method, "amem_" + method)
            r.watch(self.agent, "generate_query_llm", "amem_generate_query")
            return backend
        if self.arm == "lightmem":
            from lightmem.memory.lightmem import LightMemory
            backend = LightMemory.from_config(lightmem_config(self.store, self.model))
            if not hasattr(backend, "compressor") or not hasattr(backend, "segmenter"):
                raise InvalidExecution("LightMem sensory pipeline not initialized")
            r.watch(backend.compressor, "compress", "lightmem_precompress")
            r.watch(backend.segmenter, "propose_cut", "lightmem_topic_segment")
            r.watch(backend.manager, "meta_text_extract", "lightmem_metadata")
            def validate_update(result):
                if not isinstance(result, dict) or not result.get("usage"):
                    r.fail("LightMem update missing parsed result/usage")
            r.watch(backend.manager, "_call_update_llm", "lightmem_update", validate_update)
            return backend
        if self.arm == "bm25":
            return native_arena_class("rag.py", "RAGMemorySystem")()
        if self.arm == "full":
            return native_arena_class("long_context.py", "LongContextMemorySystem")()
        raise ValueError(self.arm)

    def add(self, text, *, timestamp="2026-09-15 12:00:00", finalize=True):
        r = self.runtime
        r.phase = "memory_write"
        with r.native_call():
            if self.arm == "mem0":
                result = self.backend.add(text, user_id=r.instance)
            elif self.arm == "amem":
                ident = self.backend.add_note(text, time=timestamp)
                result = {"note": vars(self.backend.memories[ident]), "evolution_count": self.backend.evo_cnt,
                          "all_links": [list(note.links) for note in self.backend.memories.values()]}
                n = len(self.backend.memories)
                for note in self.backend.memories.values():
                    if any(not isinstance(i, int) or not 0 <= i < n for i in note.links):
                        r.fail("A-Mem produced an invalid link index")
            elif self.arm == "lightmem":
                result = self.backend.add_memory(
                    messages=[{"role": "user", "content": text, "time_stamp": timestamp},
                              {"role": "assistant", "content": "", "time_stamp": timestamp}],
                    force_segment=finalize, force_extract=finalize)
            else:
                result = self.backend.add_chunk(text)
        r.event("write", text=text, result=result)
        r.round += 1
        return result

    def consolidate(self):
        """Call at an explicit idle boundary, never using future task records."""
        if self.arm != "lightmem":
            return
        r = self.runtime
        r.phase = "memory_consolidate"
        with r.native_call():
            self.backend.construct_update_queue_all_entries(max_workers=1)
            self.backend.offline_update_all_entries(score_threshold=0.9, max_workers=1)
        r.event("consolidate", statistics=self.backend.get_token_statistics())

    def retrieve(self, query):
        r = self.runtime
        r.phase = "memory_read"
        with r.native_call():
            if self.arm == "mem0":
                kwargs = {} if self.retrieval_k is None else {"top_k": self.retrieval_k}
                result = self.backend.search(query, filters={"user_id": r.instance}, **kwargs)
                text = "\n".join(row["memory"] for row in result["results"])
            elif self.arm == "amem":
                keywords = self.agent.generate_query_llm(query)
                text = self.agent.retrieve_memory(keywords, k=self.agent.retrieve_k)
                result = text
            elif self.arm == "lightmem":
                result = self.backend.retrieve(query, limit=self.retrieval_k or 10)
                if not isinstance(result, list) or not all(isinstance(x, str) for x in result):
                    raise InvalidExecution("Unexpected LightMem retrieve contract")
                text = "\n".join(result)
            else:
                text = self.backend.wrap_user_prompt(query)
                result = text
        r.event("retrieve", query=query, text=text, result=result)
        return text

    def wrap_user_prompt(self, query):
        text = self.retrieve(query)
        if self.arm in {"bm25", "full"}:
            return text
        return "<memory_context>\n" + (text or "None") + "\n</memory_context>\nUser: " + query

    def snapshot(self):
        if self.arm == "amem":
            return {key: vars(value) for key, value in self.backend.memories.items()}
        if self.arm == "mem0":
            return self.backend.get_all(filters={"user_id": self.runtime.instance})
        if self.arm == "lightmem":
            return self.backend.embedding_retriever.get_all()
        return {}


class StructuredMemory:
    """Our memory policy for the original full-plan actor, with no decoder.

    A full public base is needed to emit unchanged plan cells. It is retained in
    our store and shown as memory, not copied into the answer. All three controls
    use the same base and representation. query_only removes learned slot edges
    while preserving the explicit-reference parser, isolating the learned graph.
    """
    def __init__(self, arm, runtime):
        from arena_causal_memory import CausalMemorySystem
        self.runtime, self.arm, self.base = runtime, arm, ""
        self.backend = CausalMemorySystem(
            graph_mode="learned", learned_graph_path=str(GRAPH), use_names=False,
            ablate_graph=arm == "noGcompact", inherit_unspecified_from_base=False,
            keep_provenance=False, compact_serialization=True, decoder_base_tag=False)
        if arm == "query_only":
            self.backend._learned = copy.deepcopy(self.backend._learned)
            self.backend._learned["slot_ancestors"] = {s: [] for s in self.backend._learned["slots"]}
            self.backend._learned["edges"] = []
        runtime.event("init", backend_class="CausalMemorySystem", graph_edges_enabled=arm == "ours",
                      decoder=False, policy="visible public base + selected historical cells")

    def add(self, text):
        self.runtime.phase = "memory_write"
        data = json.loads(text)
        if data.get("is_base_person"):
            self.base = data["final_plan"]
        result = self.backend.add_chunk(text)
        self.runtime.event("write", text=text)
        self.runtime.round += 1
        return result

    def wrap_user_prompt(self, query):
        self.runtime.phase = "memory_read"
        selected = self.backend._ancestors_of(query)
        if self.backend._people:
            selected = {cell for cell in selected if cell[0] != self.backend._people[0]}
        body = self.backend._render_compact(selected)
        text = ("<memory_context>\n<public_base_plan>\n" + self.base +
                "\n</public_base_plan>\n" + body + "\n</memory_context>\nUser: " + query)
        self.runtime.event("retrieve", query=query, text=text, selected_cells=sorted(selected))
        self.runtime.phase = "actor"
        return text


class ConventionalMemory:
    """Explicitly local conventional baselines, never labeled author methods."""
    def __init__(self, arm, runtime):
        self.arm, self.runtime = arm, runtime
        self.text, self.chunks, self.vectors = "", [], []
        if arm == "dense":
            from sentence_transformers import SentenceTransformer
            self.embedder = SentenceTransformer(str(EMBEDDING), device="cpu")
        else:
            from openai import OpenAI
            self.client = OpenAI()
        runtime.event("init", backend_class="ConventionalMemory", author_implementation=False)

    def add(self, text):
        self.runtime.phase = "memory_write"
        if self.arm == "dense":
            # Respect this encoder's actual window instead of silently embedding
            # only the first 256 tokens of a 2048-token chunk. Offsets preserve
            # the original venue strings in retrieved text.
            tok = self.embedder.tokenizer
            encoded = tok(text, add_special_tokens=False, return_offsets_mapping=True, truncation=False)
            offsets = encoded["offset_mapping"]
            width = self.embedder.max_seq_length - tok.num_special_tokens_to_add(pair=False)
            for start in range(0, len(offsets), max(1, width - 32)):
                end = min(start + width, len(offsets))
                piece = text[offsets[start][0]:offsets[end - 1][1]]
                self.chunks.append(piece)
                self.vectors.append(self.embedder.encode(piece, normalize_embeddings=True))
        else:
            result = self.client.chat.completions.create(
                model=os.environ["OPENAI_MODEL"], temperature=0, max_tokens=16000,
                messages=[{"role": "system", "content":
                    "Maintain a factual rolling memory of travel plans. Update the previous memory using "
                    "the new record. Preserve exact traveler names, complete base itinerary, explicit "
                    "changes, days, slot names, venue and city strings, and cross-traveler dependencies. "
                    "Use concise tables and references for repeated information. Return only the memory."},
                    {"role": "user", "content": "Previous memory:\n" + self.text + "\nNew record:\n" + text}])
            self.text = result.choices[0].message.content
        self.runtime.event("write", text=text, summary=self.text if self.arm == "summary" else None)
        self.runtime.round += 1

    def wrap_user_prompt(self, query):
        self.runtime.phase = "memory_read"
        if self.arm == "dense":
            import numpy as np
            v = self.embedder.encode(query, normalize_embeddings=True)
            scores = np.array(self.vectors) @ v if self.vectors else []
            order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:10]
            text = "\n".join(self.chunks[i] for i in order)
        else:
            text = self.text
        wrapped = "<memory_context>\n" + (text or "None") + "\n</memory_context>\nUser: " + query
        self.runtime.event("retrieve", query=query, text=wrapped)
        self.runtime.phase = "actor"
        return wrapped
