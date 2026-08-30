"""Launch MemoryArena's memory server with our CausalMemorySystem registered.

MemoryArena ships with NO LICENSE file, so we do not fork, patch, or vendor their
source. Instead we import their FastAPI app, inject one extra factory into
MEMORY_FACTORIES at runtime, and serve it. Their tree stays byte-for-byte pristine
(verify with `git -C benchmarks/MemoryArena status`).

Usage:
    python3 code/arena_serve_causal.py --port 8000
Then point run_travel.py at --memory_system causal (or causal-topk / long_context / bm25).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ARENA = Path(__file__).resolve().parents[1] / "benchmarks" / "MemoryArena"
# server.py does `from memory_systems import ...`, i.e. it expects memory/ itself
# on sys.path, not just the repo root.
sys.path.insert(0, str(ARENA))
sys.path.insert(0, str(ARENA / "memory"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _stub_missing_sdks():
    """Insert do-nothing modules for optional memory-system SDKs that are absent.

    Only fills in names that genuinely fail to import, so a real installed SDK is
    never shadowed. Any attribute access returns a class whose constructor raises,
    so a stubbed backend fails loudly at use time rather than silently pretending.
    """
    import importlib
    import types

    class _Unavailable:
        _name = "?"

        def __init__(self, *a, **k):
            raise RuntimeError(
                f"memory backend '{type(self)._name}' is not installed in this "
                f"environment; it was stubbed so the server could start")

    def _make(name):
        mod = types.ModuleType(name)

        def __getattr__(attr):
            # never fabricate dunders -- importlib inspects __file__/__spec__ etc.
            # and a fake class there corrupts the import machinery.
            if attr.startswith("__") and attr.endswith("__"):
                raise AttributeError(attr)
            return type(attr, (_Unavailable,), {"_name": f"{name}.{attr}"})
        mod.__getattr__ = __getattr__
        mod.__path__ = []
        mod.__file__ = f"<stub {name}>"
        return mod

    # Iteratively stub whatever the import chain actually reports missing --
    # nested vendored packages (e.g. MemoRAG -> semantic_text_splitter) surface
    # only once the outer import gets far enough.
    stubbed = []
    for _ in range(40):
        try:
            importlib.import_module("memory.server")
            break
        except ModuleNotFoundError as e:
            missing = (e.name or "").split(".")[0]
            if not missing or missing in stubbed:
                raise
            sys.modules.setdefault(missing, _make(missing))
            stubbed.append(missing)
            for m in [k for k in sys.modules if k.startswith("memory")]:
                sys.modules.pop(m, None)
    if stubbed:
        print(f"stubbed unavailable SDKs: {', '.join(stubbed)}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0")
    a = ap.parse_args()

    os.chdir(ARENA)
    # MemoryArena's memory_systems package transitively imports torch, and
    # `import torch` probes the driver via NVML even when it will never run a
    # kernel -- enough for a node watchdog to flag the process as using a GPU
    # (this got the 2026-08-27 session killed). Pin it off before that import.
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    import uvicorn

    # server.py eagerly imports ALL 12 memory systems, several of which need
    # third-party SDKs we deliberately do not install (mirix/letta/zep/mem0 are
    # heavy and some need external services). Stub the missing ones so the import
    # succeeds; the baselines we actually compare against (long_context, rag) and
    # our plugin have no such deps. Requesting a stubbed system raises at
    # initialize time, which is the honest behaviour -- it is simply unavailable.
    _stub_missing_sdks()

    from memory import server as arena_server
    from arena_causal_memory import CausalMemorySystem

    class InheritanceMemoryAdapter:
        """Give an upstream baseline the same public-base decoder contract.

        The base itinerary is the first public chunk supplied by MemoryArena.  It is
        cached without consulting gold answers or the evaluator, then appended to the
        backend's ordinary retrieval context so the shared e2e decoder can recover it.
        """

        def __init__(self, backend, decoder_base_tag=False):
            self.backend = backend
            self.base_plan = ""
            self.decoder_base_tag = decoder_base_tag

        def add_chunk(self, chunk):
            if not self.base_plan:
                try:
                    payload = json.loads(chunk)
                except (TypeError, json.JSONDecodeError):
                    payload = {}
                if payload.get("is_base_person"):
                    self.base_plan = str(payload.get("final_plan") or "")
            return self.backend.add_chunk(chunk)

        def wrap_user_prompt(self, prompt):
            wrapped = self.backend.wrap_user_prompt(prompt)
            sentinel = "</memory_context>"
            if sentinel not in wrapped:
                raise RuntimeError("baseline memory context is missing </memory_context>")
            head, tail = wrapped.split(sentinel, 1)
            opening = "<memory_context>"
            if opening not in head:
                raise RuntimeError("baseline memory context is missing <memory_context>")
            backend_body = head.split(opening, 1)[1].strip()
            base_tag = ("decoder_base_itinerary" if self.decoder_base_tag
                        else "public_base_itinerary")
            policy_text = (
                "Solve only query-explicit target cells. A deterministic decoder "
                "copies every other cell from the public base itinerary."
                if self.decoder_base_tag else
                "Copy every day/slot from the public base itinerary unless the current "
                "traveler's query explicitly changes that day/slot. Always output the "
                "complete plan."
            )
            policy = [
                f"<{base_tag}>",
                self.base_plan or "None",
                f"</{base_tag}>",
                "<inheritance_policy>",
                policy_text,
                "</inheritance_policy>",
            ]
            # Put the canonical public plan first. The baseline's JSON chunk may
            # contain an escaped ``=== Name's Plan ===`` string; appending our plan
            # would let the shared decoder match that escaped header first.
            return "\n".join([opening, *policy, backend_body, sentinel]) + tail

    # Runtime registration -- the "plugin" contract (memory/server.py:49).
    arena_server.MEMORY_FACTORIES["causal"] = lambda: CausalMemorySystem(graph_mode="rule")
    # Ablation: same slot parsing + hold rule, but NO graph (keep every slot).
    # Isolates "structured slots" from "causal ancestor selection".
    arena_server.MEMORY_FACTORIES["causal-noG"] = lambda: CausalMemorySystem(
        graph_mode="rule", ablate_graph=True)
    # constraint edges + a HAND-PICKED trip scaffold (see CausalMemorySystem docstring)
    arena_server.MEMORY_FACTORIES["causal-scaffold"] = lambda: CausalMemorySystem(
        graph_mode="rule", include_scaffold=True)
    # milestone M4: the same masking driven by a graph DISCOVERED from data
    # (code/travel_grace_discovery.py -> results/real/travel_learned_graph.json),
    # with no hand-authored slot list anywhere.
    # ARENA is <repo>/benchmarks/MemoryArena, so the repo root is parents[1].
    learned = os.getenv("CAUSAL_LEARNED_GRAPH") or str(
        ARENA.parents[1] / "results" / "real" / "travel_learned_graph.json")
    arena_server.MEMORY_FACTORIES["causal-learned"] = lambda: CausalMemorySystem(
        graph_mode="learned", learned_graph_path=learned, use_names=True)
    # PURE discovery: same learned graph, but the query is NOT parsed for person
    # names. `causal-learned` still leans on that name oracle to pick WHICH person,
    # so only this arm answers "can a learned graph drive the mask on its own?".
    # Expect a bigger context (it cannot narrow to the named traveller) -- the
    # question is how much answerability survives without the oracle.
    arena_server.MEMORY_FACTORIES["causal-learned-pure"] = lambda: CausalMemorySystem(
        graph_mode="learned", learned_graph_path=learned, use_names=False)
    # Exploratory PS repair: retain graph-selected dependencies, but decode the
    # full itinerary by inheriting every query-unspecified cell from the public
    # base plan. The runner enforces the same query-only policy on final text.
    arena_server.MEMORY_FACTORIES["causal-learned-inherit"] = lambda: CausalMemorySystem(
        graph_mode="learned", learned_graph_path=learned, use_names=True,
        inherit_unspecified_from_base=True, keep_provenance=False)
    arena_server.MEMORY_FACTORIES["causal-learned-pure-inherit"] = lambda: CausalMemorySystem(
        graph_mode="learned", learned_graph_path=learned, use_names=False,
        inherit_unspecified_from_base=True, keep_provenance=False)
    arena_server.MEMORY_FACTORIES["causal-noG-inherit"] = lambda: CausalMemorySystem(
        graph_mode="rule", ablate_graph=True, inherit_unspecified_from_base=True,
        keep_provenance=False)
    arena_server.MEMORY_FACTORIES["bm25-inherit"] = lambda: InheritanceMemoryAdapter(
        arena_server.RAGMemorySystem(retrieval_method="bm25"))
    arena_server.MEMORY_FACTORIES["long_context-inherit"] = lambda: InheritanceMemoryAdapter(
        arena_server.LongContextMemorySystem())
    # New experiment family (v2): query-target delta serialization plus a
    # decoder-only public base tag.  These names are intentionally new so the
    # frozen v1 outputs above cannot be overwritten or silently reinterpreted.
    def query_ancestry_compact_v2():
        return CausalMemorySystem(
            graph_mode="learned", learned_graph_path=learned, use_names=False,
            inherit_unspecified_from_base=True, keep_provenance=False,
            compact_serialization=True, decoder_base_tag=True)

    # Keep the development-era name reproducible, but give the formal arm an
    # accurate name: compact-v2 resolves traveler references in the constraint
    # body and is therefore not the old fully name-free "pure" selector.
    arena_server.MEMORY_FACTORIES["causal-learned-pure-inherit-compact-v2"] = (
        query_ancestry_compact_v2)
    arena_server.MEMORY_FACTORIES["causal-query-ancestry-inherit-compact-v2"] = (
        query_ancestry_compact_v2)
    arena_server.MEMORY_FACTORIES["causal-noG-inherit-v2"] = (
        lambda: CausalMemorySystem(
            graph_mode="rule", ablate_graph=True,
            inherit_unspecified_from_base=True, keep_provenance=False,
            decoder_base_tag=True))
    arena_server.MEMORY_FACTORIES["bm25-inherit-v2"] = lambda: InheritanceMemoryAdapter(
        arena_server.RAGMemorySystem(retrieval_method="bm25"), decoder_base_tag=True)
    arena_server.MEMORY_FACTORIES["long-context-inherit-v2"] = (
        lambda: InheritanceMemoryAdapter(
            arena_server.LongContextMemorySystem(), decoder_base_tag=True))

    print(f"registered: causal, causal-noG, causal-scaffold, causal-learned, "
          f"causal-learned-pure, causal-learned-inherit, causal-learned-pure-inherit "
          f"causal-noG-inherit, bm25-inherit, long_context-inherit, "
          f"causal-learned-pure-inherit-compact-v2, causal-noG-inherit-v2, "
          f"causal-query-ancestry-inherit-compact-v2, "
          f"bm25-inherit-v2, long-context-inherit-v2 "
          f"({len(arena_server.MEMORY_FACTORIES)} factories total; graph={learned})", flush=True)
    uvicorn.run(arena_server.app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
