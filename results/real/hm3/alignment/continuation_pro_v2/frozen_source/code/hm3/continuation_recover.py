"""One bounded recovery of new transport failures after the frozen campaign.

Never retry semantic/format errors or completed replies. Keep old ledgers intact.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from .continuation_actor import Actor, fit_dependence, validation_arms, write_once
from .core import Episode
from .llm import build_messages
from .domains import get_domain
from .generate import generate_split
from .structure_alignment import digest


def ordered_episode(saved):
    """Restore generator key order; sorted-key JSON has identical data, different prompts."""
    domain = get_domain(saved["domain"])
    index = int(saved["id"].rsplit("-", 1)[1])
    ep = next(ep for ep in generate_split(domain, saved["seed"], saved["split"], index+1)
              if ep.id == saved["id"])
    assert ep.to_dict() == saved, "Regenerated episode differs semantically from frozen case"
    return ep


def run(args):
    root = Path(args.root)
    ledger = [json.loads(x) for x in (root / "ledger.jsonl").read_text().splitlines()]
    old = {r["job_id"]: r for r in ledger}
    intents = [json.loads(x) for x in (root / "requests.jsonl").read_text().splitlines()]
    if any(r["job_id"] not in old for r in intents):
        raise RuntimeError("campaign has unresolved in-flight requests; wait for runner completion")
    recovery = json.loads((root / "recovery.json").read_text())
    previously_recovered = set(recovery["failed_requests"]+recovery["in_flight_unknown"])
    candidates = [r for r in ledger if r["event"] == "infrastructure_failure"
                  and r["job_id"] not in previously_recovered]
    out = root / "transport_recovery"
    write_once(out / "protocol.json", dict(policy="one retry of new infrastructure failures only; no semantic retries",
               candidate_ids=[r["job_id"] for r in candidates], max_attempts_per_failed_job=1,
               scientific_protocol_changed=False))
    actor = Actor(out, args.key_file, max_requests=300)
    eps = {r["id"]: ordered_episode(r) for r in json.loads((root / "episodes.json").read_text())}
    manifests = {r["episode"]: r for r in json.loads((root / "manifests.json").read_text())}

    def recover(row):
        ep = eps[row["episode"]]
        visible = None
        if row["stage"] == "source_changed":
            fit = json.loads((root / f"{ep.id}_fit.json").read_text())
            _, visible = validation_arms(ep, manifests[ep.id]["groups"], fit)
        assert digest(build_messages(get_domain(ep.domain), visible or ep, row["reads"], "verbose")) == row["prompt_sha256"]
        return actor.ask(ep, row["reads"], row["stage"], row["repeat"], visible_ep=visible,
                         metadata={**row.get("metadata", {}), "recovery_of": row["job_id"]})
    with ThreadPoolExecutor(max_workers=4) as pool:
        recovered = list(pool.map(recover, candidates))
    merged = {**old, **{r["job_id"]: r for r in recovered}}
    # A failed training call can have prevented the entire validation stage.
    # Only then fit and execute that already-frozen validation panel for the first time.
    for ep in eps.values():
        fp = root / f"{ep.id}_fit.json"
        if fp.exists():
            continue
        train = sorted([r for r in merged.values() if r["episode"] == ep.id and r["stage"] == "train"],
                       key=lambda r: r["repeat"])
        if len(train) != 128 or any(r["event"] != "result" for r in train):
            continue
        fit = fit_dependence(manifests[ep.id]["masks"], [r["correct"] for r in train])
        write_once(out / f"{ep.id}_fit.json", fit)
        arms, changed = validation_arms(ep, manifests[ep.id]["groups"], fit)
        write_once(out / f"{ep.id}_arms.json", arms)
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = [pool.submit(actor.ask, ep, reads, name, repeat,
                                visible_ep=changed if name == "source_changed" else None, metadata=meta)
                    for name, (reads, meta) in arms.items() for repeat in range(3)]
            for job in jobs:
                job.result()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="results/real/hm3/alignment/continuation_pro_v2")
    p.add_argument("--key-file", default="api/api.txt")
    run(p.parse_args())
