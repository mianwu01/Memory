"""Synthesize the original P3 auditing claim without rewriting gate outcomes.

P3-A asks whether a causal audit can recover the hidden driver of a published
agent-safety failure.  P3-B is the later, stricter online-mitigation extension.
The former did not have a pre-registered binary acceptance rule, so this script
reports a descriptive evidence status and deliberately emits no retrospective
``pass=true``.  The two frozen P3-B judgements are copied verbatim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FORBIDDEN = {
    "poison_label", "poison_source", "test_answer", "test_outcome",
    "test_groundtruth",
}


def load(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--minja-replication",
        default="results/real/minja_replication_summary.json")
    parser.add_argument(
        "--minja-audits", nargs=3,
        default=[
            "results/real/minja_audit_report_v2.json",
            "results/real/minja_audit_report_seed1.json",
            "results/real/minja_audit_report_seed2.json",
        ])
    parser.add_argument(
        "--minja-online",
        default="results/real/minja_online_gate_summary.json")
    parser.add_argument(
        "--agentpoison-raw",
        default=("results/real/p3_agentpoison_round2/"
                 "agentpoison_strategyqa_gate.json"))
    parser.add_argument(
        "--agentpoison-summary",
        default="results/real/p3_agentpoison_round2/summary.json")
    parser.add_argument(
        "--out",
        default="results/real/p3_hidden_driver_recovery_summary.json")
    args = parser.parse_args()

    paths = {
        "minja_replication": ROOT / args.minja_replication,
        "minja_online": ROOT / args.minja_online,
        "agentpoison_raw": ROOT / args.agentpoison_raw,
        "agentpoison_summary": ROOT / args.agentpoison_summary,
    }
    audit_paths = [ROOT / item for item in args.minja_audits]
    minja = load(paths["minja_replication"])
    minja_online = load(paths["minja_online"])
    agentpoison_raw = load(paths["agentpoison_raw"])
    agentpoison = load(paths["agentpoison_summary"])
    audits = [load(path) for path in audit_paths]

    aggregate = minja["aggregate"]
    grace = aggregate["regime_grace"]
    decisive = aggregate["decisive_note_free_poison_retrieved"]
    control = aggregate["note_free_no_poison_control"]
    provenance = [audit.get("provenance", {}).get("driver_rounds", [])
                  for audit in audits]
    if len(audits) != 3 or any(not rows for rows in provenance):
        raise ValueError("MINJA provenance must be present for all three seeds")

    raw_driver = agentpoison_raw["driver"]
    decision_inputs = set(raw_driver["decision_inputs"])
    forbidden_inputs = set(raw_driver["forbidden_inputs"])
    if not agentpoison_raw["protocol"].get(
            "driver_decision_before_test_label_access"):
        raise ValueError("AgentPoison driver was not frozen before test labels")
    if not REQUIRED_FORBIDDEN.issubset(forbidden_inputs):
        missing = sorted(REQUIRED_FORBIDDEN - forbidden_inputs)
        raise ValueError(f"AgentPoison forbidden-input boundary missing {missing}")
    if decision_inputs & forbidden_inputs:
        raise ValueError("AgentPoison driver inputs intersect forbidden inputs")

    driver_eval = agentpoison["driver_posthoc_evaluation_only"]
    posthoc = agentpoison_raw["posthoc_evaluation_only"]
    if set(raw_driver["implicated_record_ids"]) != set(
            posthoc["implicated_poison_ids"]):
        raise ValueError("direct AgentPoison driver precision is not 1.0")
    if set(raw_driver["expanded_record_ids"]) != set(
            posthoc["expanded_poison_ids"]):
        raise ValueError("expanded AgentPoison driver precision is not 1.0")

    minja_gate = minja_online["protocol_judgement"]
    agentpoison_gate = agentpoison["protocol_judgement"]
    if not isinstance(minja_gate.get("pass"), bool):
        raise ValueError("MINJA online judgement has no boolean pass")
    if not isinstance(agentpoison_gate.get("pass"), bool):
        raise ValueError("AgentPoison online judgement has no boolean pass")

    source_files = {
        key: {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}
        for key, path in paths.items()
    }
    source_files["minja_audits"] = [
        {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}
        for path in audit_paths
    ]

    output = {
        "schema": "p3-hidden-driver-evidence-synthesis/v1",
        "original_research_question": (
            "Reuse a recent agent-safety failure scenario with minor runtime "
            "instrumentation and test whether the causal method recovers the "
            "hidden driver of the observed failure."),
        "evidence_classification": {
            "status": "SUPPORTED_WITH_IDENTIFICATION_BOUNDARIES",
            "classification_type": (
                "descriptive synthesis of frozen evidence; not a newly "
                "pre-registered binary acceptance test"),
            "confirmatory_pass": None,
            "online_mitigation_is_a_separate_extension": True,
        },
        "p3_a_hidden_driver_auditing": {
            "minja_structural_recovery": {
                "carrier": "MINJA-QA (NeurIPS 2025)",
                "decisive_note_free_poison_retrieved": decisive,
                "note_free_no_poison_control": control,
                "ordered_edge_found_seeds": grace["found_seeds"],
                "ordered_edge_gated_seeds": grace["gated_seeds"],
                "provenance_seeds_with_write_ancestor": sum(
                    bool(rows) for rows in provenance),
                "top_write_ancestors": [rows[0] for rows in provenance],
                "identification_boundaries": [
                    ("poison_retr is constructed from is_poison and therefore "
                     "tests recovery of an oracle-tagged event channel, not "
                     "fully blind record discovery"),
                    ("lag-0 orientation is constrained by the instrumented "
                     "runtime order retrieval-before-action"),
                ],
            },
            "agentpoison_label_free_record_recovery": {
                "carrier": "AgentPoison ReAct-StrategyQA (NeurIPS 2024)",
                "decision_inputs": sorted(decision_inputs),
                "forbidden_inputs": sorted(forbidden_inputs),
                "driver_frozen_before_test_label_access": True,
                "posthoc_record_metrics": driver_eval,
                "interpretation": (
                    "The direct temporal-ancestry driver recovers one of two "
                    "poison records; the frozen embedding-cluster expansion "
                    "recovers both. Poison membership is attached post hoc."),
                "boundary": (
                    "Recovery had no separate pre-registered binary PASS rule; "
                    "development query 20 is also inside calibration IDs 0-31, "
                    "so this is supporting evidence rather than an independent "
                    "confirmatory recovery verdict."),
            },
        },
        "p3_b_online_mitigation": {
            "minja": {
                "protocol_judgement": minja_gate,
                "micro": minja_online["micro"],
            },
            "agentpoison": {
                "protocol_judgement": agentpoison_gate,
                "micro": agentpoison["micro"],
            },
            "all_frozen_online_protocols_passed": bool(
                minja_gate["pass"] and agentpoison_gate["pass"]),
            "interpretation": (
                "Both frozen online protocols remain FAIL because only one of "
                "three seed blocks improves; these failures do not overwrite "
                "the separate hidden-driver recovery evidence."),
        },
        "claim_boundary": (
            "The project does not claim to beat MemAudit on poison-detection "
            "scores; its positive claim is temporal dependency, gated read "
            "structure, and write ancestry."),
        "source_files": source_files,
    }
    atomic_json(ROOT / args.out, output)
    print("P3-A:", output["evidence_classification"]["status"])
    print("P3-B online pass values:",
          f"MINJA={minja_gate['pass']}",
          f"AgentPoison={agentpoison_gate['pass']}")


if __name__ == "__main__":
    main()
