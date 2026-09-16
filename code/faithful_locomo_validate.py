"""Native-task conformance: a complete LoCoMo history, fixed category probes.

This is an interface/mechanism gate, not an accuracy benchmark or a reproduction
of published scores. Author ingestion, retrieval and answer prompts are used.
The shortest complete conversation is selected by turn count before any calls;
the first question of each author-supported category is used without selection
on answers. No turn or long-term update is removed to make a method fit Travel.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time

from faithful_memory import AuthorMemory, ROOT, Runtime, environment

DATA = ROOT / "benchmarks/AgenticMemory-paper/data/locomo10.json"


def selection():
    rows = json.loads(DATA.read_text())
    counts = [sum(len(v) for k, v in r["conversation"].items()
                  if k.startswith("session_") and isinstance(v, list)) for r in rows]
    index = min(range(len(rows)), key=lambda i: (counts[i], i))
    return index, rows[index], counts


def questions(sample, categories):
    return [next(i for i, q in enumerate(sample["qa"]) if int(q["category"]) == cat)
            for cat in categories if any(int(q["category"]) == cat for q in sample["qa"])]


def amem(memory, sample, index, chosen):
    from load_dataset import load_locomo_dataset
    from llm_text_parsers import parse_plain_text_answer
    parsed = load_locomo_dataset(DATA)[index]
    r = memory.runtime
    for session in parsed.conversation.sessions.values():
        for turn in session.turns:
            # Exact serialization in the author's evaluate_dataset().
            memory.add("Speaker " + turn.speaker + "says : " + turn.text,
                       timestamp=session.date_time)
    assert r.round == sum(len(s.turns) for s in parsed.conversation.sessions.values())
    for i in chosen:
        qa = parsed.qa[i]
        r.phase = "native_qa"
        with r.native_call():
            answer, prompt, context = memory.agent.answer_question(qa.question, qa.category, qa.final_answer)
        r.event("native_question", index=i, category=qa.category, question=qa.question,
                context=context, prompt=prompt, answer=parse_plain_text_answer(answer))


def lightmem(memory, sample, index, chosen):
    # Imports have local output-directory side effects; cwd is the run directory.
    sys.path.insert(0, str(ROOT / "benchmarks/LightMem/experiments/locomo"))
    from add_locomo import extract_locomo_sessions
    from prompts import METADATA_GENERATE_PROMPT_locomo
    from search_locomo import retrieve_combined, build_prompt_with_speaker_memories
    from retrievers import VectorRetriever
    from openai import OpenAI
    sessions, dates, _, _ = extract_locomo_sessions(sample["conversation"])
    r = memory.runtime
    for session, date in zip(sessions, dates):
        while session and session[0]["role"] != "user":
            session.pop(0)
        turns = len(session) // 2
        for i in range(turns):
            messages = session[i * 2:i * 2 + 2]
            if len(messages) < 2 or messages[0]["role"] != "user" or messages[1]["role"] != "assistant":
                raise RuntimeError("Unexpected native conversation pair")
            for msg in messages:
                msg["time_stamp"] = date
            last = session is sessions[-1] and i == turns - 1
            r.phase = "memory_write"
            with r.native_call():
                result = memory.backend.add_memory(messages=messages,
                    METADATA_GENERATE_PROMPT=METADATA_GENERATE_PROMPT_locomo,
                    force_segment=last, force_extract=last)
            r.event("write", messages=messages, result=result)
            r.round += 1
    memory.consolidate()
    # Access the current native Qdrant store directly; the published file loader
    # has a stale directory layout. Ranking and prompting are author functions.
    entries = memory.backend.embedding_retriever.get_all(with_vectors=True, with_payload=True)
    entries = [e.model_dump() if hasattr(e, "model_dump") else e for e in entries]
    if not entries:
        raise RuntimeError("Native history yielded no LightMem entries")
    retriever = VectorRetriever(memory.backend.text_embedder)
    client = OpenAI()
    for i in chosen:
        qa = sample["qa"][i]
        r.phase = "native_qa"
        with r.native_call():
            related = retrieve_combined(entries, retriever, qa["question"], total_limit=60)
            prompt = build_prompt_with_speaker_memories(qa["question"], related)
            response = client.chat.completions.create(model=memory.model,
                messages=[{"role": "system", "content": prompt}], temperature=0.0)
        r.event("native_question", index=i, category=qa["category"], question=qa["question"],
                context=related, prompt=prompt, answer=response.choices[0].message.content)


def mem0(memory, sample, index, chosen):
    sys.path.insert(0, str(ROOT / "benchmarks/mem0-memory-benchmarks"))
    from benchmarks.locomo.run import get_sorted_sessions, session_to_chunks, parse_locomo_date
    from benchmarks.locomo.prompts import get_answer_generation_prompt
    from openai import OpenAI
    r = memory.runtime
    conv = sample["conversation"]
    sessions = get_sorted_sessions(conv)
    for _, date, turns in sessions:
        for messages in session_to_chunks(turns, conv["speaker_a"], conv["speaker_b"]):
            # Native OSS server's add endpoint passes messages/user_id; its
            # current source does not pass the request timestamp to Memory.add.
            r.phase = "memory_write"
            with r.native_call():
                result = memory.backend.add(messages, user_id=r.instance)
            r.event("write", messages=messages, source_date=date, result=result)
            r.round += 1
    client = OpenAI()
    reference = max(filter(None, (parse_locomo_date(s[1]) for s in sessions))).strftime("%B %d, %Y")
    for i in chosen:
        qa = sample["qa"][i]
        r.phase = "native_qa"
        with r.native_call():
            # v2 OSS API renamed limit/user_id to top_k/filters. No retrieval
            # replacement; the author's current benchmark default is top 200.
            results = memory.backend.search(qa["question"], filters={"user_id": r.instance}, top_k=200)
            prompt = get_answer_generation_prompt(qa["question"], results["results"], reference_date=reference)
            response = client.chat.completions.create(model=memory.model,
                messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=4096)
        r.event("native_question", index=i, category=qa["category"], question=qa["question"],
                context=results, prompt=prompt, answer=response.choices[0].message.content)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["amem", "lightmem", "mem0"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    environment()
    index, sample, counts = selection()
    chosen = questions(sample, [1, 2, 3, 4, 5] if args.arm == "amem" else [1, 2, 3, 4])
    r = Runtime(args.out.resolve(), args.arm, sample["sample_id"])
    protocol = {"scope": "native task conformance, not scored performance", "registered_at": time.time(),
        "dataset_sha256": hashlib.sha256(DATA.read_bytes()).hexdigest(), "conversation_index": index,
        "sample_id": sample["sample_id"], "all_conversation_turn_counts": counts,
        "history_turns": counts[index], "selection": "shortest complete history; original order tiebreak",
        "question_indices": chosen, "qa_selection": "first question in each author-supported category",
        "full_history": True, "score_selection": False, "seed": 20260915,
        "model": os.environ["OPENAI_MODEL"], "endpoint": os.environ["OPENAI_BASE_URL"],
        "memory_thinking": "disabled", "qa_thinking": "disabled",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (r.directory / "protocol.json").write_text(json.dumps(protocol, indent=2))
    random.seed(20260915)
    r.install_clients()
    os.chdir(r.directory)
    try:
        memory = AuthorMemory(args.arm, r)
        globals()[args.arm](memory, sample, index, chosen)
        r.require_valid()
        assert r.round == counts[index], "Native ingestion missed history turns"
        assert r.counts.get("native_question") == len(chosen)
        (r.directory / "snapshot.json").write_text(json.dumps(memory.snapshot(), default=str, ensure_ascii=False))
        status = {"passed": True, "scope": protocol["scope"], "counts": r.counts,
                  "history_turns": r.round, "question_indices": chosen, "failures": r.failures}
    except Exception as exc:
        status = {"passed": False, "error_type": type(exc).__name__, "failures": r.failures,
                  "counts": r.counts, "history_turns": r.round}
    (r.directory / "validation.json").write_text(json.dumps(status, indent=2))
    print(json.dumps(status), flush=True)
    if not status["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
