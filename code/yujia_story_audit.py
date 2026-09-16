"""Build an evidence-backed audit of the complete Yujia experiment storyline.

The audit deliberately treats negative results as first-class outcomes.  It
reads frozen result artifacts, derives the acceptance decisions again, and
keeps structure recovery, downstream utility, efficiency, auditing, and online
mitigation as separate claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


REPO = Path(__file__).resolve().parents[1]
SOURCES = {
    "simulation_v2": Path("results/development/yujia_simulation_v2.json"),
    "four_task_t1": Path("results/development/causal_benchmarks/suite_t1.json"),
    "memoryarena_e2e": Path("results/real/p2_compact_v3/e2e_scores.json"),
    "memoryarena_protocol": Path("results/real/p2_compact_v3/frozen_protocol.json"),
    "safety_synthesis": Path("results/real/p3_hidden_driver_recovery_summary.json"),
    "api_decoder_dev_v9": Path(
        "results/development/causal_benchmarks/api_decoder_dev_v9_summary.json"
    ),
    "api_six_arm_protocol_v1": Path(
        "results/causal_benchmarks/api_six_arm_test_v1_protocol.json"
    ),
    "api_six_arm_summary_v1": Path(
        "results/causal_benchmarks/api_six_arm_test_v1_summary.json"
    ),
    "four_task_killer_dev_audit": Path(
        "results/development/causal_benchmarks/killer_lookup_dev_audit.json"
    ),
    "hidden_routing_v2_admission": Path(
        "results/development/causal_benchmarks/hidden_routing_v2_admission.json"
    ),
}

MANIFEST_ONLY_SOURCES = {
    "api_decoder_dev_v9_protocol": Path(
        "results/development/causal_benchmarks/api_decoder_dev_v9_protocol.json"
    ),
    "api_decoder_dev_v9_results": Path(
        "results/development/causal_benchmarks/api_decoder_dev_v9_results.jsonl"
    ),
    "api_decoder_dev_v9_ledger": Path(
        "results/development/causal_benchmarks/api_decoder_dev_v9_usage.jsonl"
    ),
    "api_six_arm_results_v1": Path(
        "results/causal_benchmarks/api_six_arm_test_v1_results.jsonl"
    ),
    "api_six_arm_ledger_v1": Path(
        "results/causal_benchmarks/api_six_arm_test_v1_usage.jsonl"
    ),
}

FOUR_TASK_STATIC_VALIDITY = {
    "dynamic_travel": {
        "status": "PARTIAL",
        "shortcut": "fixed small schema permits source-to-train-impact-union lookup",
    },
    "dynamic_shopping": {
        "status": "PARTIAL",
        "shortcut": "observable regime signature permits an impact-template lookup",
    },
    "dynamic_search": {
        "status": "PASS_TASK_VALIDITY_ONLY",
        "shortcut": (
            "query cannot name episode-specific opaque descendants; learned arm remains "
            "a learned-gate plus deterministic-provenance hybrid"
        ),
    },
    "causal_formal": {
        "status": "NO_GO",
        "shortcut": "intervention.kind exposes gate status under a fixed topology",
    },
}


def _read_json(root: Path, relative: Path) -> Any:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"required audit source is missing: {path}")
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fraction_reduction(smaller: float, larger: float) -> float:
    if larger <= 0:
        raise ValueError("comparison denominator must be positive")
    return 1.0 - smaller / larger


def _p2_arm(report: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    try:
        return report[name]
    except KeyError as error:  # pragma: no cover - malformed frozen artifact
        raise KeyError(f"missing MemoryArena arm: {name}") from error


def _formulations() -> dict[str, dict[str, Any]]:
    common_t1 = {
        "training_sample": (
            "one completed train episode: (pre_state, intervention, post_state); "
            "gold graph/affected labels are never learner-visible"
        ),
        "evaluation_sample": (
            "one outcome-isolated test episode: (history, pre_state, query, "
            "structured intervention source); post_state and gold remain evaluator-only"
        ),
        "variable_granularity": (
            "one named scalar or categorical state cell; a complete state is the vector "
            "of those cells, not one opaque embedding"
        ),
        "primary_intrinsic_metrics": [
            "affected-set precision/recall",
            "required-read recall where defined",
            "negative-control preservation",
        ],
        "primary_task_metric": "whole-episode post-intervention state success",
        "efficiency_metrics": ["serialized characters", "fraction of full-state context"],
    }
    return {
        "simulation": {
            "repository_binding": "code/yujia_simulation_v2.py",
            "benchmark_binding": "project-owned linear/MLP write-hold-read SCM",
            "sample": "one lagged transition (X[t-1], regime[t], X[t])",
            "trajectory": "one independent write-hold-read episode",
            "variables": "scalar coordinates c,m,y,d1,d2,p1,p2; hidden h is generator-only",
            "grouped_fallback": "h_group averages measured proxies p1 and p2",
            "primary_metric": "typed parent/edge precision, recall, and F1 over five seeds",
            "claim_boundary": "no latent-variable identification claim",
        },
        "dynamic_travel": {
            **common_t1,
            "repository_binding": "code/causal_benchmarks/dynamic_travel.py",
            "benchmark_binding": "project-owned Dynamic Travel; not upstream MemoryArena registration",
            "variables": (
                "itinerary cells such as flight.arrival_hour, transfer.end_hour, "
                "attraction/dinner status, and hotel.checkin_status"
            ),
            "intervention": "one terse flight/venue/hotel/profile state change",
            "claim_boundary": "shared deterministic value decoder isolates impact selection",
        },
        "dynamic_shopping": {
            **common_t1,
            "repository_binding": "code/causal_benchmarks/dynamic_shopping.py",
            "benchmark_binding": "project-owned Dynamic Shopping; inspired by bundled_shopping",
            "variables": (
                "availability, cart component, price, policy, subtotal, total, and "
                "remaining-budget cells"
            ),
            "intervention": "one cancellation, price correction, or adapter-policy change",
            "claim_boundary": "known product schema/catalog and shared deterministic value decoder",
        },
        "dynamic_search": {
            **common_t1,
            "repository_binding": "code/causal_benchmarks/dynamic_search.py",
            "benchmark_binding": "project-owned versioned evidence/provenance search graph",
            "variables": "document/version/trust/evidence/claim state cells and provenance edges",
            "intervention": "one source revision, retraction, trust transition, or version change",
            "claim_boundary": "dependency/provenance claim unless learned selection beats provenance parser",
        },
        "causal_formal": {
            **common_t1,
            "repository_binding": "code/causal_benchmarks/causal_formal.py",
            "benchmark_binding": "project-owned math/physics sequential notebooks",
            "variables": "primitive definition/parameter/axiom cells and derived lemma/theorem cells",
            "intervention": "one correction, axiom activation, or axiom retraction",
            "claim_boundary": "program/dataflow task, not empirical causality or an agent-safety result",
        },
        "memoryarena_p2": {
            "repository_binding": "code/arena_causal_memory.py + external benchmarks/MemoryArena",
            "benchmark_binding": "MemoryArena group_travel_planner, held-out episode IDs 111-120",
            "sample": "one agent round nested within a multi-person travel episode",
            "variables": "typed person/day/slot memory cells; graph is a type-level selector",
            "primary_task_metrics": ["PS", "SPS", "SR"],
            "efficiency_metrics": ["API input/output tokens", "cost", "API/wall duration"],
            "claim_boundary": (
                "original Travel is no-go for causal-discovery necessity; compact-v3 also "
                "bundles selection and serialization"
            ),
        },
        "p3_minja_agentpoison": {
            "repository_binding": (
                "code/minja_causal_audit.py and frozen MINJA/AgentPoison result artifacts"
            ),
            "benchmark_binding": "MINJA-QA and AgentPoison ReAct-StrategyQA",
            "sample": "one instrumented retrieval/action transition; evaluation aggregates by seed block",
            "variables": "event channels plus record identity/embedding cluster/temporal ancestry",
            "audit_metrics": ["ordered-edge recovery", "driver precision/recall", "write ancestry"],
            "mitigation_metrics": ["held-out ASR", "accuracy", "majority seed direction"],
            "claim_boundary": "auditing evidence and online mitigation are separate hypotheses",
        },
    }


def build_audit(root: Path = REPO) -> dict[str, Any]:
    """Load frozen evidence and derive the project-level scientific verdict."""

    loaded = {name: _read_json(root, path) for name, path in SOURCES.items()}
    simulation = loaded["simulation_v2"]
    t1 = loaded["four_task_t1"]
    p2 = loaded["memoryarena_e2e"]
    p2_protocol = loaded["memoryarena_protocol"]
    p3 = loaded["safety_synthesis"]
    api_dev = loaded["api_decoder_dev_v9"]
    api_protocol = loaded["api_six_arm_protocol_v1"]
    api_summary = loaded["api_six_arm_summary_v1"]
    killer_dev = loaded["four_task_killer_dev_audit"]
    hidden_v2 = loaded["hidden_routing_v2_admission"]["audit"]

    sim_summary = simulation["summary"]
    observed_families = ("linear_observed", "mlp_observed")
    simulation_observed_pass = all(
        sim_summary[family]["regime_conditioned"]["overall_f1_mean"] >= 0.95
        and sim_summary[family]["regime_conditioned"]["seeds"] >= 5
        for family in observed_families
    )
    latent_observed_f1 = sim_summary["mlp_latent"]["regime_conditioned"][
        "overall_f1_mean"
    ]
    grouped_f1 = sim_summary["mlp_latent"]["grouped_proxy_fallback"][
        "overall_f1_mean"
    ]

    task_headlines = {
        task: row["headline"] for task, row in t1["tasks"].items()
    }
    all_t1_isolated = bool(t1["all_novel_splits_pass"])
    all_t1_beat_generic = bool(t1["all_learned_beat_generic_retrieval"])
    domain_wins = list(t1["tasks_beating_domain_solver"])
    supported_causal_tasks = list(t1["tasks_supporting_causal_learning_claim"])

    pure_name = "query-ancestry-v3-heldout-111-120"
    nog_name = "noG-v3-heldout-111-120"
    bm25_name = "bm25-v3-heldout-111-120"
    long_name = "long-context-v3-heldout-111-120"
    pure = _p2_arm(p2, pure_name)
    nog = _p2_arm(p2, nog_name)
    bm25 = _p2_arm(p2, bm25_name)
    long_context = _p2_arm(p2, long_name)
    paired_key = f"{pure_name}_minus_{nog_name}"
    ps_delta = p2["_paired_comparisons"][paired_key]["metrics"]["ps"][
        "mean_delta_points"
    ]
    input_reduction_vs_nog = _fraction_reduction(
        pure["usage"]["total_input_tokens"], nog["usage"]["total_input_tokens"]
    )
    required = p2_protocol["primary_acceptance"]
    p2_frozen_pass = (
        ps_delta
        >= required["pure_minus_noG_episode_mean_ps_delta_minimum_points"]
        and input_reduction_vs_nog
        >= required["pure_relative_noG_api_input_reduction_minimum_fraction"]
    )

    audit_status = p3["evidence_classification"]["status"]
    minja_mitigation = p3["p3_b_online_mitigation"]["minja"][
        "protocol_judgement"
    ]["pass"]
    agentpoison_mitigation = p3["p3_b_online_mitigation"]["agentpoison"][
        "protocol_judgement"
    ]["pass"]
    all_mitigation_pass = p3["p3_b_online_mitigation"][
        "all_frozen_online_protocols_passed"
    ]

    api_expected = sum(
        arm["calls_expected"]
        for task in api_summary["matrix"].values()
        for arm in task.values()
    )
    api_semantic_scored = sum(
        round(arm["calls_expected"] * arm["semantic_coverage"])
        for task in api_summary["matrix"].values()
        for arm in task.values()
    )
    api_learned_endpoints = {
        task: rows["learned_graph"]["endpoint_success_valid_only"]
        for task, rows in api_summary["matrix"].items()
    }
    api_dev_gate_pass = bool(
        api_dev.get("all_task_decoder_gates_pass")
        and api_dev.get("manifest_audit", {}).get("complete")
        and api_dev.get("full_gate_scope_audit", {}).get("complete")
        and api_dev.get("integrity_audit", {}).get("complete")
    )
    api_integrity_complete = bool(api_summary["integrity_audit"]["complete"])
    api_scope_complete = bool(api_summary["full_scope_complete"])
    api_experiment_complete = bool(api_summary["experiment_complete"])

    source_manifest = {
        name: {
            "path": str(relative),
            "sha256": _sha256(root / relative),
        }
        for name, relative in SOURCES.items()
    }
    source_manifest.update(
        {
            name: {
                "path": str(relative),
                "sha256": _sha256(root / relative),
            }
            for name, relative in MANIFEST_ONLY_SOURCES.items()
        }
    )
    metrics_review = root / "docs" / "memory-evaluation-literature-review.md"

    return {
        "schema": "yujia-story-audit/v1",
        "audit_date": "2026-08-31",
        "source_manifest": source_manifest,
        "storyline": {
            "simulation_must_do": {
                "status": "PASS_OBSERVED_WITH_LATENT_BOUNDARY"
                if simulation_observed_pass
                else "FAIL",
                "observed_linear_and_mlp_pass": simulation_observed_pass,
                "latent_observed_only_f1": latent_observed_f1,
                "grouped_proxy_fallback_f1": grouped_f1,
                "latent_identification_supported": False,
            },
            "effectiveness_efficiency": {
                "status": "PARTIAL_PASS_SUPPORTING_NOT_CAUSAL_NECESSITY",
                "four_task_novel_split_pass": all_t1_isolated,
                "four_task_learned_beats_generic_retrieval": all_t1_beat_generic,
                "tasks_beating_strong_domain_solver": domain_wins,
                "tasks_supporting_causal_learning_claim": supported_causal_tasks,
                "memoryarena_compact_v3_frozen_protocol_pass": p2_frozen_pass,
                "memoryarena_pure_minus_nog_ps_points": ps_delta,
                "memoryarena_input_reduction_vs_nog": input_reduction_vs_nog,
                "memoryarena_input_reduction_vs_bm25": _fraction_reduction(
                    pure["usage"]["total_input_tokens"],
                    bm25["usage"]["total_input_tokens"],
                ),
                "memoryarena_input_reduction_vs_long_context": _fraction_reduction(
                    pure["usage"]["total_input_tokens"],
                    long_context["usage"]["total_input_tokens"],
                ),
                "memoryarena_duration_reduction_vs_long_context": _fraction_reduction(
                    pure["usage"]["duration_seconds"],
                    long_context["usage"]["duration_seconds"],
                ),
                "boundary": (
                    "The four zero-LLM tasks use a shared oracle value decoder; all learned "
                    "selectors tie the strongest domain solver. Original Travel and compact-v3 "
                    "cannot identify causal-discovery necessity."
                ),
            },
            "four_task_real_api": {
                "status": (
                    "EXECUTED_COMPLETE"
                    if api_experiment_complete
                    else "EXECUTED_WITH_UNSCORED_MISSING_NOT_CONFIRMATORY"
                ),
                "dev_decoder_gate_pass": api_dev_gate_pass,
                "protocol_cases": api_protocol["full_scope_audit"]["cases"],
                "result_rows": api_summary["integrity_audit"]["results"],
                "semantic_scored_rows": api_semantic_scored,
                "unscored_rows": api_expected - api_semantic_scored,
                "integrity_complete": api_integrity_complete,
                "full_scope_complete": api_scope_complete,
                "experiment_complete": api_experiment_complete,
                "ledger_events": api_summary["integrity_audit"]["ledger_events"],
                "ledger_cost_usd": api_summary["integrity_audit"][
                    "ledger_total_estimated_cost_usd"
                ],
                "learned_endpoint_success_valid_only": api_learned_endpoints,
                "static_task_validity": FOUR_TASK_STATIC_VALIDITY,
                "causal_necessity_supported": False,
                "boundary": (
                    "The learned arm shows real-API value execution conditional on a valid "
                    "SelectionPlan response. The frozen domain arm is conservative potential "
                    "reachability rather than the strongest executable solver; structured "
                    "shortcuts remain in three tasks. Node-set contract errors were also "
                    "retried in v1, so valid-only endpoint success is not one-call reliability."
                ),
            },
            "anti_shortcut_redesign": {
                "status": "STOPPED_BEFORE_NEW_API",
                "v1_killer_dev_stop_rule_triggered": bool(
                    killer_dev["overall_stop_rule_triggered"]
                ),
                "v1_tasks_triggering_stop_rule": list(
                    killer_dev["tasks_triggering_stop_rule"]
                ),
                "hidden_routing_v2_verdict": hidden_v2["admission"]["verdict"],
                "hidden_routing_v2_confirmatory_pass": bool(
                    hidden_v2["admission"]["all_domains_pass"]
                ),
                "hidden_routing_v2_structurally_independent_domains": bool(
                    hidden_v2["structural_replication_audit"]["pass"]
                ),
                "hidden_routing_v2_correctness_necessity_supported": bool(
                    hidden_v2["admission"]["correctness_necessity_supported"]
                ),
                "next_preregistration": "docs/hidden-mechanism-v3-preregistration.md",
                "next_api_authorized": False,
                "boundary": (
                    "All four v1 lookup shortcuts can produce sufficient write supersets. "
                    "Hidden-routing v2 is a useful latent-codebook/sparse-mask microbenchmark, "
                    "but a fair train-enabled program ties the learner, history enumerates "
                    "potential edges, sufficient supersets solve the mask-only endpoint, and "
                    "the four domain shells are structurally identical. V3 therefore remains "
                    "a preregistration pending external Yujia review, not an API result."
                ),
            },
            "trustworthiness_auditing": {
                "status": audit_status,
                "confirmatory_pass": p3["evidence_classification"][
                    "confirmatory_pass"
                ],
                "boundary": p3["claim_boundary"],
            },
            "actionable_safety": {
                "status": "PASS" if all_mitigation_pass else "FAIL",
                "minja_frozen_protocol_pass": bool(minja_mitigation),
                "agentpoison_frozen_protocol_pass": bool(agentpoison_mitigation),
                "guarantee_supported": bool(all_mitigation_pass),
            },
            "full_two_selling_point_story_supported": False,
            "overall_status": "PARTIAL_EVIDENCE_NOT_FULL_STORY",
        },
        "four_task_t1": task_headlines,
        "requirements_from_8_15": {
            "precise_sample_variable_trajectory_formulation": "COMPLETED_IN_THIS_AUDIT",
            "repository_and_benchmark_binding": "COMPLETED_IN_THIS_AUDIT",
            "metrics_literature_review": (
                "COMPLETED" if metrics_review.is_file() else "MISSING"
            ),
            "scalability_grouping_fallback": (
                "PARTIAL_SIMULATION_PROXY_GROUP_ONLY"
                if grouped_f1 >= 0.95
                else "IMPLEMENTED_BUT_FAILED"
            ),
            "double_check_with_yujia": "PENDING_EXTERNAL_CONFIRMATION",
        },
        "formulations": _formulations(),
        "claim_policy": {
            "supported": [
                "Regime conditioning recovers the observed linear and nonlinear simulation structure.",
                "On all four synthetic tasks, train-only impact selection generalizes beyond generic matched retrieval and reduces serialized context.",
                "MemoryArena compact-v3 passes its frozen PS/non-inferiority plus input-reduction protocol.",
                "Frozen real-agent evidence supports hidden-driver auditing with identification boundaries.",
                "The frozen six-arm v1 demonstrates that compact SelectionPlans can drive real-API value updates, conditional on valid responses.",
            ],
            "not_supported": [
                "A learned causal graph is necessary on any of the four redesigned tasks.",
                "The four T1 task results demonstrate learned structural equations or end-to-end language-agent performance.",
                "Original MemoryArena Travel establishes causal-discovery necessity.",
                "The method identifies unobserved latent causal variables.",
                "The current audit-derived intervention guarantees agent safety.",
                "The method is uniformly faster on every latency comparison.",
                "The frozen real-API v1 establishes causal necessity or beats the strongest executable domain solver.",
                "The v1 valid-only endpoint score is an unbiased one-call reliability estimate.",
                "Hidden-routing v2 establishes correctness necessity or four independent domain replications.",
                "The unimplemented v3 preregistration is experimental evidence.",
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("results/development/yujia_story_audit.json"),
    )
    args = parser.parse_args()
    report = build_audit(args.root)
    output = args.out if args.out.is_absolute() else args.root / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report["storyline"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
