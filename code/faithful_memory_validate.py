"""Exercise author mechanisms; development evidence, not benchmark scores."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from faithful_memory import AuthorMemory, Runtime, environment


RECORDS = [
    "Nora leads the Orion satellite review project. The review was originally scheduled "
    "for Monday in Oslo. Its access phrase is cobalt-lantern. Elias is the safety reviewer.",
    "Update for Nora's Orion satellite review: the meeting has moved from Monday to "
    "Tuesday, still in Oslo. Elias must approve the safety checklist before the review. "
    "The access phrase remains cobalt-lantern.",
    "Elias completed the Orion safety checklist and approved it. Nora can now hold "
    "the Orion review on Tuesday in Oslo using access phrase cobalt-lantern.",
]
QUERY = "What is the access phrase for Nora's Orion review, where is it held, and on which day?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["mem0", "amem", "lightmem"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    environment()
    if args.offline:
        os.environ.setdefault("OPENAI_API_KEY", "unused-offline-test")
        os.environ.setdefault("OPENAI_BASE_URL", "https://unused.invalid/v1")
    r = Runtime(args.out, args.arm, "mechanism-development")
    if not args.offline:
        r.install_clients()
    try:
        memory = AuthorMemory(args.arm, r)
        if args.offline and args.arm == "mem0":
            # True native sparse+semantic+entity retrieval, with extraction
            # separately tested in the online mode. No fabricated LLM result.
            memory.backend.add(RECORDS[0], user_id=r.instance, infer=False)
            memory.backend.add("The river picnic is in Bergen.", user_id=r.instance, infer=False)
            result = memory.retrieve(QUERY)
            assert "cobalt-lantern" in result
            sparse = memory.backend.vector_store.keyword_search(
                query="cobalt lantern", top_k=5, filters={"user_id": r.instance})
            assert sparse, "Enabled BM25 must return a matching stored record"
        elif args.offline and args.arm == "amem":
            # The real retrieval implementation must expand links beyond top-1.
            # Synthetic stored notes make this a deterministic unit check of
            # the author path, not claimed experimental performance.
            from memory_layer_robust import RobustMemoryNote
            a = RobustMemoryNote("NEIGHBOR_SENTINEL", keywords=["sentinel"], context="neighbor", tags=["test"])
            b = RobustMemoryNote("QUERY_TARGET", keywords=["query"], context="target", tags=["test"], links=[0])
            memory.backend.memories = {a.id: a, b.id: b}
            memory.backend.retriever.search = lambda query, k: [1]
            result = memory.backend.find_related_memories_raw("QUERY_TARGET", k=1)
            assert "QUERY_TARGET" in result and "NEIGHBOR_SENTINEL" in result
        elif args.offline and args.arm == "lightmem":
            messages = [{"role": "user", "content": " ".join(RECORDS) * 2}]
            original_length = len(messages[0]["content"])
            with r.native_call():
                compressed = memory.backend.compressor.compress(messages, memory.backend.segmenter.tokenizer)
                assert compressed and compressed[0]["content"]
                assert len(compressed[0]["content"]) < original_length, "Compressor did not reduce the development record"
                memory.backend.segmenter.propose_cut(["The Orion review is in Oslo.", "Nora leads the team."])
            result = compressed[0]["content"]
        else:
            for i, record in enumerate(RECORDS):
                memory.add(record, timestamp=f"2026-09-15 12:0{i}:00",
                           finalize=(args.arm != "lightmem" or i == len(RECORDS) - 1))
            memory.consolidate()
            result = memory.retrieve(QUERY)
            for fact in ("cobalt", "oslo", "tuesday"):
                assert fact in result.lower(), f"Missing development fact: {fact}"
            if args.arm == "amem":
                notes = list(memory.backend.memories.values())
                # UPDATE_NEIGHBOR is an author-supported evolution decision and
                # need not create a link. Requiring STRENGTHEN here selects on an
                # LLM's stochastic branch choice. Native link expansion is
                # verified independently by the deterministic offline test.
                assert memory.backend.evo_cnt > 0, "No native evolution observed"
        r.require_valid()
        snapshot = memory.snapshot()
        (r.directory / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
        report = {"passed": True, "arm": args.arm, "offline": args.offline,
                  "scope": "development mechanism validation, not benchmark results", "counts": r.counts,
                  "retrieved_text": result, "failures": r.failures}
    except Exception as exc:
        report = {"passed": False, "arm": args.arm, "offline": args.offline,
                  "error_type": type(exc).__name__, "failures": r.failures, "counts": r.counts}
        diagnostic = str(exc)
        for key, value in os.environ.items():
            if any(marker in key.upper() for marker in ("KEY", "TOKEN", "SECRET")) and len(value) > 8:
                diagnostic = diagnostic.replace(value, "[redacted]")
        report["diagnostic"] = re.sub(r"(?:sk_tr_|sk-|bo-|sess_)[A-Za-z0-9_-]{12,}", "[redacted]", diagnostic)[:1200]
        (r.directory / "validation.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
        raise SystemExit(1)
    (r.directory / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "retrieved_text"}), flush=True)


if __name__ == "__main__":
    main()
