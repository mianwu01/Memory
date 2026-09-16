from __future__ import annotations

import json
import unittest

from causal_benchmarks.api_selection_plans import ARM_NAMES
from causal_benchmarks.api_six_arm_experiment import (
    build_test_cases,
    protocol_manifest,
    summarize_test,
    validate_test_scope,
)


class APISixArmExperimentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases, cls.episodes, cls.learners = build_test_cases(
            episodes=150, seed=17, limit_per_task=1
        )
        cls.dev_gate = {
            "protocol_case_manifest_sha256": "dev-manifest",
            "all_task_decoder_gates_pass": True,
            "integrity_audit": {"complete": True},
            "full_gate_scope_audit": {"complete": True},
        }

    def test_four_tasks_six_arms_and_paired_seeds(self) -> None:
        self.assertEqual(len(self.cases), 24)
        self.assertEqual(
            {case["arm"] for case in self.cases}, set(ARM_NAMES)
        )
        self.assertEqual(len({case["task_family"] for case in self.cases}), 4)
        for episode_id in {case["episode_id"] for case in self.cases}:
            episode_cases = [
                case for case in self.cases if case["episode_id"] == episode_id
            ]
            self.assertEqual(len({case["decoder_seed"] for case in episode_cases}), 1)

    def test_prompts_have_no_outcome_fields(self) -> None:
        forbidden = (
            '"gold"',
            "post_state",
            "observed_transition",
            "required_reads",
            "affected_nodes",
            "propagation_paths",
        )
        for case in self.cases:
            serialized = json.dumps(case["payload"], sort_keys=True)
            for field in forbidden:
                self.assertNotIn(field, serialized)
            self.assertEqual(
                set(case["payload"]["current_context_state"]),
                set(case["context_nodes"]),
            )

    def test_full_arm_writes_runtime_state_and_plans_are_value_free(self) -> None:
        for case in self.cases:
            plan_text = json.dumps(case["plan"], sort_keys=True)
            self.assertNotIn("post_state", plan_text)
            if case["arm"] == "full_state_history":
                episode = self.episodes[case["episode_id"]]
                self.assertEqual(
                    set(case["write_nodes"]), set(episode["memory_state"])
                )

    def test_protocol_is_deterministic(self) -> None:
        with self.assertRaises(ValueError):
            validate_test_scope(self.cases, limit_per_task=1)
        cases, _, learners = build_test_cases(
            episodes=150, seed=17, limit_per_task=12
        )
        scope = validate_test_scope(cases, limit_per_task=12)
        self.assertTrue(scope["complete"])
        self.assertEqual(scope["cases"], 288)
        first = protocol_manifest(
            cases,
            learners,
            self.dev_gate,
            episodes=150,
            seed=17,
            limit=12,
            model="deepseek-v4-flash",
            temperature=0.0,
            max_tokens=32768,
            api_retries=3,
            base_url="https://api.deepseek.com/v1",
            timeout_seconds=120.0,
            workers=4,
            uncached_input_usd_per_million=2.5,
            cached_input_usd_per_million=0.25,
            output_usd_per_million=10.0,
        )
        rebuilt_cases, _, rebuilt_learners = build_test_cases(
            episodes=150, seed=17, limit_per_task=12
        )
        second = protocol_manifest(
            rebuilt_cases,
            rebuilt_learners,
            self.dev_gate,
            episodes=150,
            seed=17,
            limit=12,
            model="deepseek-v4-flash",
            temperature=0.0,
            max_tokens=32768,
            api_retries=3,
            base_url="https://api.deepseek.com/v1",
            timeout_seconds=120.0,
            workers=4,
            uncached_input_usd_per_million=2.5,
            cached_input_usd_per_million=0.25,
            output_usd_per_million=10.0,
        )
        self.assertEqual(first, second)

    def test_summary_does_not_zero_fill_missing_engineering_rows(self) -> None:
        semantic_case, engineering_case = self.cases[:2]
        semantic_row = {
            "request_id": semantic_case["request_id"],
            "task_family": semantic_case["task_family"],
            "episode_id": semantic_case["episode_id"],
            "arm": semantic_case["arm"],
            "semantic_scored": True,
            "semantic_contract_failure": True,
            "semantic_contract_valid": False,
            "failure_class": "semantic_contract",
            "updates": {},
            "write_value_accuracy": 0.0,
            "usage": {},
            "api_duration_seconds": 0.0,
        }
        engineering_row = {
            "request_id": engineering_case["request_id"],
            "task_family": engineering_case["task_family"],
            "episode_id": engineering_case["episode_id"],
            "arm": engineering_case["arm"],
            "semantic_scored": False,
            "failure_class": "truncated",
            "updates": None,
            "write_value_accuracy": None,
            "usage": {},
            "api_duration_seconds": 0.0,
        }
        protocol = {
            "case_manifest_sha256": "test-manifest",
            "test_episodes_per_task": 1,
            "full_scope_audit": {"complete": False},
        }
        report = summarize_test(
            [semantic_row, engineering_row],
            self.cases,
            self.episodes,
            protocol,
            {"complete": False},
        )
        accounting = report["failure_classification"]
        self.assertEqual(
            accounting["semantic_contract_failure_request_ids"],
            [semantic_case["request_id"]],
        )
        self.assertEqual(
            accounting["unresolved_engineering_request_ids"],
            [engineering_case["request_id"]],
        )
        self.assertEqual(len(accounting["missing_request_ids"]), 22)
        missing_group = report["matrix"]["dynamic_shopping"]["exact_kv"]
        self.assertEqual(missing_group["calls_received"], 0)
        self.assertIsNone(missing_group["write_value_accuracy_valid_only"])
        self.assertIsNone(missing_group["endpoint_success_valid_only"])


if __name__ == "__main__":
    unittest.main()
