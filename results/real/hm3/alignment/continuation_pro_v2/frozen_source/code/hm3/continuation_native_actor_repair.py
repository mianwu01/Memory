"""Restore exact shared actor framing, reusing all valid native memory outputs.

Native memory construction is not rerun. Prior actor ledgers remain archived.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from .continuation_actor import Actor, write_once
from .continuation_recover import ordered_episode
from .domains import get_domain
from .llm import build_messages
from .structure_alignment import digest, ordered_reads


def framing(messages):
    user = messages[1]["content"]
    start, rest = user.split("### HISTORY", 1)
    _, end = rest.split("### CURRENT STATE", 1)
    return [messages[0], start, end]


def main():
    root = Path("results/real/hm3/alignment/continuation_pro_v2")
    native = Path("results/real/hm3/alignment/continuation_memsys")
    eps = {r["id"]: ordered_episode(r) for r in json.loads((root / "episodes.json").read_text())}
    originals = [json.loads(x) for x in (root / "ledger.jsonl").read_text().splitlines()]
    references = {ep: next(r for r in originals if r["episode"] == ep) for ep in eps}
    write_once(native / "actor_interface_repair.json", {
        "reason": "sorted-key episode JSON changed shared state field ordering",
        "fix": "reconstruct exactly the same episode in generator insertion order; assert semantic equality",
        "cached_memory_unchanged": True, "old_actor_variant": "actor/ledger.jsonl (state-key-order variant)",
        "primary_actor_variant": "actor_v2/ledger.jsonl (exact common framing)",
        "retry_policy": "new changed actor input once per frozen repeat; no semantic retries"})
    jobs = []
    for system in ["mem0", "amem", "lightmem"]:
        for ep in eps.values():
            directory = native / system / ep.id
            source = directory / "memory_output.json"
            if not source.exists():
                continue
            memory = json.loads(source.read_text())
            actor = Actor(directory / "actor_v2", "api/api.txt", max_requests=3)
            reads = ordered_reads(ep, ep.S0.objects, [])
            ref = references[ep.id]
            reference_messages = json.loads((root / "inputs" / (ref["prompt_sha256"]+".json")).read_text())
            candidate = build_messages(get_domain(ep.domain), ep, reads, "verbose")
            assert framing(candidate) == framing(reference_messages)
            write_once(directory / "actor_v2/interface_check.json", {
                "reference_prompt_sha256": ref["prompt_sha256"], "shared_framing_sha256": digest(framing(candidate)),
                "exact_shared_system_state_query": True,
                "memory_output_sha256": digest(memory), "prior_actor_excluded_from_primary_table": True})
            for repeat in range(3):
                jobs.append((actor, ep, reads, system, repeat, memory["text"]))

    def ask(job):
        actor, ep, reads, system, repeat, memory = job
        return actor.ask(ep, reads, f"native_{system}", repeat, memory_text=memory,
                         metadata={"interface": "exact_shared_framing", "native_memory_reused": True})
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(ask, jobs))


if __name__ == "__main__":
    main()
