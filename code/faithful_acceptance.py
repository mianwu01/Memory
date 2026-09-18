"""Create a hash-linked acceptance record before the main evaluation freezes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from faithful_memory import ARMS, ROOT
from faithful_report import events


def evidence(path, field):
    report = json.loads(path.read_text())
    review = path.parent / "review.json"
    reviewed = json.loads(review.read_text()) if review.exists() else {}
    if report.get(field) is not True:
        if not (reviewed.get("schema") == "amem-optional-link-criterion-review/v1"
                and reviewed.get("accepted") is True
                and report.get("diagnostic") == "No actual links established on connected development records"):
            raise ValueError("Unaccepted evidence: " + str(path.relative_to(ROOT)))
        rows = events(path.parent / "events.jsonl")
        if hashlib.sha256((path.parent / "events.jsonl").read_bytes()).hexdigest() != reviewed["events_sha256"]:
            raise ValueError("Reviewed evidence changed")
        writes = [r for r in rows if r["event"] == "write"]
        reads = [r for r in rows if r["event"] == "retrieve"]
        if (len(writes) != 3 or len(reads) != 1 or writes[-1]["result"]["evolution_count"] < 1
                or not all(f in reads[0]["text"].lower() for f in ("cobalt", "oslo", "tuesday"))
                or any(r["event"] in {"api_error", "invalid"} for r in rows)):
            raise ValueError("Saved evidence does not satisfy corrected mechanism criterion")
    if report.get("failures"):
        raise ValueError("Unaccepted evidence: " + str(path.relative_to(ROOT)))
    if review.exists() and not json.loads(review.read_text()).get("accepted", False):
        raise ValueError("Superseded validation: " + str(path))
    files = [path, path.parent / "events.jsonl"] + ([review] if review.exists() else [])
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def acceptance(family, defer_native=False):
    from faithful_suite import fingerprints
    base = ROOT / "results/development" / family
    source = fingerprints()
    amendment_path = base / "amem_budget_amendment.json"
    amendment = json.loads(amendment_path.read_text()) if amendment_path.exists() else None
    transport_path = base / "stream_recovery_amendment.json"
    transport = json.loads(transport_path.read_text()) if transport_path.exists() else None
    recovery_path = base / "development_recovery_sources.json"
    recovery = json.loads(recovery_path.read_text()) if recovery_path.exists() else {}
    if recovery:
        if recovery.get("schema") != "faithful-memory-recovery-sources/v2":
            raise ValueError("Unsupported recovery mapping schema")
        expected_native_mode = "deferred" if defer_native else "included"
        if recovery.get("native_gates") != expected_native_mode:
            raise ValueError("Acceptance native-gate mode differs from registered recovery")
        if recovery.get("endpoint", "").rstrip("/") != os.environ["OPENAI_BASE_URL"].rstrip("/") or recovery.get("model") != os.environ["OPENAI_MODEL"]:
            raise ValueError("Recovery route differs from acceptance route")
    retrieval_path = base / "retrieval_config_amendment.json"
    retrieval = json.loads(retrieval_path.read_text()) if retrieval_path.exists() else None
    hashes, mechanisms, deferred_native = {}, {}, {}
    expected = {
        "mem0": {"mem0_keyword_search", "mem0_search", "mem0_entity_boosts"},
        "amem": {"amem_process_memory", "amem_find_related_memories_raw", "amem_generate_query"},
        "lightmem": {"lightmem_precompress", "lightmem_topic_segment", "lightmem_metadata", "lightmem_update"}}
    for arm in ARMS:
        folder = base / recovery.get(arm, f"travel/{arm}_101")
        hashes.update(evidence(folder / "status.json", "complete"))
        prov = json.loads((folder / "provenance.json").read_text())
        for name, digest in prov["source_hashes"].items():
            if source[name] != digest:
                target = source[name]
                if transport and name in transport["new_sources"] and target == transport["new_sources"][name]:
                    target = transport["old_sources"][name]
                transport_only = target == digest
                unchanged_branch = (amendment and name == "code/faithful_memory.py"
                    and arm in amendment["compatible_unchanged_arms"]
                    and digest == amendment["old_source_sha256"]
                    and target == amendment["new_source_sha256"])
                retrieval_unchanged = (retrieval and name == "code/faithful_memory.py"
                    and arm in retrieval["unchanged_generation_arms"]
                    and digest == retrieval["old_source_sha256"]
                    and source[name] == retrieval["new_source_sha256"])
                if not (unchanged_branch or transport_only or retrieval_unchanged):
                    raise ValueError("Development generation code changed: " + arm + "/" + name)
        for name, value in (("model", os.environ["OPENAI_MODEL"]), ("endpoint", os.environ["OPENAI_BASE_URL"]),
                            ("actor_thinking", "default")):
            if prov[name] != value:
                raise ValueError("Development model/actor setting changed: " + arm)
    offline = ROOT / "results/development/faithful_memory_v1/validation"
    for arm, name in (("mem0", "mem0_offline_2"), ("amem", "amem_offline"), ("lightmem", "lightmem_offline_2")):
        hashes.update(evidence(offline / name / "validation.json", "passed"))
        folder = base / (amendment["new_online_output"] if amendment and arm == "amem"
                         else "validation/" + arm + "_online")
        hashes.update(evidence(folder / "validation.json", "passed"))
        rows = events(folder / "events.jsonl")
        observed = {r["mechanism"] for r in rows if r["event"] == "mechanism"}
        if not expected[arm] <= observed:
            raise ValueError("Missing required native mechanisms: " + arm + ": " + str(expected[arm] - observed))
        for row in rows:
            if row["event"] == "llm" and (row["endpoint"] != os.environ["OPENAI_BASE_URL"] or row["requested_model"] != os.environ["OPENAI_MODEL"]):
                raise ValueError("Mechanism validation used another provider")
        mechanisms[arm] = sorted(observed)
        native = amendment["new_native_output"] if amendment and arm == "amem" else "native/" + arm
        native = recovery.get("native/" + arm, native)
        deferred_native[arm] = native
        if defer_native:
            continue
        folder = base / native
        hashes.update(evidence(folder / "validation.json", "passed"))
        proto = json.loads((folder / "protocol.json").read_text())
        status = json.loads((folder / "validation.json").read_text())
        if not proto["full_history"] or status["history_turns"] != proto["history_turns"]:
            raise ValueError("Incomplete native-task history")
        if status["counts"]["native_question"] != len(proto["question_indices"]):
            raise ValueError("Incomplete native QA scope")
        for key in ("model", "endpoint"):
            if proto[key] != os.environ["OPENAI_MODEL" if key == "model" else "OPENAI_BASE_URL"]:
                raise ValueError("Native-task validation used another provider")
        if proto["source_sha256"] != source["code/faithful_locomo_validate.py"]:
            raise ValueError("Native-task generation source changed")
    if amendment:
        hashes[str(amendment_path.relative_to(ROOT))] = hashlib.sha256(amendment_path.read_bytes()).hexdigest()
    balance_path = base / "balance_recovery_amendment.json"
    for path in (transport_path, recovery_path, retrieval_path, balance_path):
        if path.exists():
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    record = {"schema": "faithful-memory-acceptance/v1", "accepted": True, "created_at": time.time(),
              "development_family": family, "source_hashes": source, "evidence_sha256": hashes,
              "observed_mechanisms": mechanisms,
              "development_generation_amendment": amendment,
              "native_gates": "deferred" if defer_native else "required",
              "fidelity_claim_ready": not defer_native,
              "interpretation": "Configured author mechanisms, native complete-history task and original actor interfaces verified; no claim of published-score replication or scientific success."}
    if defer_native:
        record["deferred_native_outputs"] = deferred_native
        record["interpretation"] = ("Configured author mechanisms and original actor interfaces verified; the native "
                                    "complete-history LoCoMo checks are deferred and must be reported separately "
                                    "before any fidelity claim; no claim of published-score replication or scientific success.")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    ap.add_argument("--defer-native", action="store_true")
    args = ap.parse_args()
    result = acceptance(args.family, defer_native=args.defer_native)
    path = ROOT / "results/development" / args.family / "acceptance.json"
    with path.open("x") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({"accepted": True, "path": str(path)}))


if __name__ == "__main__":
    main()
