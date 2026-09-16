from __future__ import annotations

import json
import hashlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from causal_benchmarks.api_decoder_experiment import (
    APIConfig,
    LEDGER_SCHEMA,
    RetryableResponseError,
    SCHEMA,
    _execute_case,
    _ledger_failure_class,
    audit_and_rescore,
    build_dev_smoke_cases,
    parse_decoder_response,
    protocol_manifest,
    summarize,
    _run_cases,
)


class APIDecoderExperimentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.episodes = build_dev_smoke_cases(
            episodes=120, seed=17, limit_per_task=1
        )

    def test_four_tasks_two_arms_and_no_prompt_gold(self):
        self.assertEqual(len(self.cases), 8)
        self.assertEqual(
            {(case["task_family"], case["arm"]) for case in self.cases},
            {
                (task, arm)
                for task in (
                    "dynamic_travel",
                    "dynamic_shopping",
                    "dynamic_search",
                    "causal_formal",
                )
                for arm in ("oracle_context", "full_context")
            },
        )
        for case in self.cases:
            serialized = json.dumps(case["payload"])
            self.assertNotIn('"gold"', serialized)
            self.assertNotIn("observed_transition", serialized)
            self.assertNotIn("post_state", serialized)
        by_episode = {}
        for case in self.cases:
            by_episode.setdefault(case["episode_id"], set()).add(case["decoder_seed"])
        self.assertTrue(all(len(seeds) == 1 for seeds in by_episode.values()))

    def test_protocol_is_deterministic(self):
        first = protocol_manifest(self.cases, episodes=120, seed=17, limit=1)
        cases, _ = build_dev_smoke_cases(episodes=120, seed=17, limit_per_task=1)
        second = protocol_manifest(cases, episodes=120, seed=17, limit=1)
        self.assertEqual(first, second)
        self.assertEqual(first["phase"], "engineering_calibration")

    def test_shopping_resources_are_outcome_free_and_shared(self):
        shopping = [
            case for case in self.cases if case["task_family"] == "dynamic_shopping"
        ]
        self.assertEqual(len(shopping), 2)
        first = shopping[0]["payload"]["runtime_resources"]
        second = shopping[1]["payload"]["runtime_resources"]
        self.assertEqual(first, second)
        self.assertEqual(
            set(first["catalog"]),
            set(first["availability"]),
        )
        self.assertNotIn("cpu_nova_test", first["catalog"])
        intervention = shopping[0]["payload"]["intervention"]
        if intervention["node"].startswith("availability."):
            item_id = intervention["node"].split(".", 1)[1]
            self.assertEqual(
                first["availability"][item_id], bool(intervention["new_value"])
            )

    def test_shopping_payload_does_not_depend_on_gold_read_annotations(self):
        import copy

        from causal_benchmarks.api_decoder_experiment import _task_packet, _prompt_payload
        from causal_benchmarks.common import runtime_view

        original = next(
            episode
            for episode in self.episodes.values()
            if episode["task"] == "dynamic_shopping"
        )
        modified = copy.deepcopy(original)
        modified["gold"]["required_reads"] = ["deliberately.wrong"]
        view = runtime_view(modified, training=False)
        packet = _task_packet("dynamic_shopping", modified, view)
        payload = _prompt_payload(
            modified,
            view,
            packet,
            packet["oracle_context_nodes"],
            "oracle_context",
        )
        original_case = next(
            case
            for case in self.cases
            if case["task_family"] == "dynamic_shopping"
            and case["arm"] == "oracle_context"
        )
        self.assertEqual(payload, original_case["payload"])

    def test_formal_oracle_context_contains_unchanged_active_intermediates(self):
        cases, _ = build_dev_smoke_cases(
            episodes=150,
            seed=17,
            limit_per_task=6,
            task_families=["causal_formal"],
        )
        gate_cases = [
            case
            for case in cases
            if case["arm"] == "oracle_context"
            and case["payload"]["intervention"]["kind"] == "axiom_retraction"
        ]
        self.assertEqual(len(gate_cases), 2)
        expected = {
            "causal_formal_math": "theorem.core",
            "causal_formal_phys": "theorem.net_momentum",
        }
        for case in gate_cases:
            intermediate = expected[case["task"]]
            self.assertIn(intermediate, case["context_nodes"])
            self.assertIn(
                intermediate,
                {row["node"] for row in case["payload"]["selected_memory_records"]},
            )

    def test_strict_response_parser(self):
        case = self.cases[0]
        episode = self.episodes[case["episode_id"]]
        rows = [
            {"node": node, "value": episode["gold"]["post_state"][node]}
            for node in case["write_nodes"]
        ]
        response = json.dumps(
            {
                "schema_version": SCHEMA,
                "episode_id": case["episode_id"],
                "updates": rows,
            }
        )
        parsed = parse_decoder_response(
            response,
            episode_id=case["episode_id"],
            write_nodes=case["write_nodes"],
            pre_state=episode["memory_state"],
        )
        self.assertEqual(set(parsed["updates"]), set(case["write_nodes"]))
        recovered = parse_decoder_response(
            "```json\n" + response + "\n```",
            episode_id=case["episode_id"],
            write_nodes=case["write_nodes"],
            pre_state=episode["memory_state"],
        )
        self.assertEqual(recovered["parse_mode"], "lossless_fence_unwrap")
        wrong_identity = parse_decoder_response(
            response.replace(case["episode_id"], "wrong-id"),
            episode_id=case["episode_id"],
            write_nodes=case["write_nodes"],
            pre_state=episode["memory_state"],
        )
        self.assertFalse(wrong_identity["semantic_contract_valid"])
        self.assertIn("wrong episode_id", wrong_identity["semantic_contract_errors"])
        with self.assertRaises(RetryableResponseError) as caught:
            parse_decoder_response(
                json.dumps(
                    {
                        "schema_version": SCHEMA,
                        "episode_id": case["episode_id"],
                        "updates": {},
                    }
                ),
                episode_id=case["episode_id"],
                write_nodes=case["write_nodes"],
                pre_state=episode["memory_state"],
            )
        self.assertEqual(caught.exception.failure_kind, "type_schema")

    @staticmethod
    def _fake_openai(responses):
        queued = list(responses)
        calls = []

        class Completions:
            def create(self, **kwargs):
                calls.append(kwargs)
                content, finish_reason = queued.pop(0)
                return SimpleNamespace(
                    model=kwargs["model"],
                    usage=SimpleNamespace(
                        prompt_tokens=10,
                        completion_tokens=5,
                        prompt_tokens_details=SimpleNamespace(cached_tokens=0),
                    ),
                    choices=[
                        SimpleNamespace(
                            finish_reason=finish_reason,
                            message=SimpleNamespace(content=content),
                        )
                    ],
                )

        class OpenAI:
            def __init__(self, **_kwargs):
                self.chat = SimpleNamespace(completions=Completions())

        module = types.ModuleType("openai")
        module.OpenAI = OpenAI
        return module, calls

    def test_semantic_node_set_failure_is_scored_once_without_retry(self):
        case = self.cases[0]
        episode = self.episodes[case["episode_id"]]
        semantic_failure = json.dumps(
            {
                "schema_version": SCHEMA,
                "episode_id": case["episode_id"],
                "updates": [],
            }
        )
        would_be_success = json.dumps(
            {
                "schema_version": SCHEMA,
                "episode_id": case["episode_id"],
                "updates": [
                    {
                        "node": node,
                        "value": episode["gold"]["post_state"][node],
                    }
                    for node in case["write_nodes"]
                ],
            }
        )
        fake_openai, calls = self._fake_openai(
            [(semantic_failure, "stop"), (would_be_success, "stop")]
        )
        config = APIConfig(
            model="deepseek-v4-flash",
            base_url="https://example.invalid",
            retries=3,
        )
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            sys.modules, {"openai": fake_openai}
        ), patch.dict(
            os.environ, {"OPENAI_API_KEY": "unit-test-placeholder"}
        ):
            ledger = Path(temporary) / "usage.jsonl"
            row = _execute_case(
                case,
                self.episodes,
                config=config,
                ledger=ledger,
                decoder_seed=case["decoder_seed"],
            )
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
            rescored, audit = audit_and_rescore(
                [row], [case], self.episodes, events, config
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(row["api_attempts"], 1)
        self.assertTrue(row["semantic_scored"])
        self.assertTrue(row["semantic_contract_failure"])
        self.assertEqual(row["failure_class"], "semantic_contract")
        self.assertFalse(row["episode_success"])
        self.assertEqual(events[0]["failure_class"], "semantic_contract")
        self.assertEqual(events[0]["error"], "")
        legacy_event = dict(events[0])
        legacy_event.pop("failure_class")
        legacy_event["error"] = (
            "SchemaValidationError: update-node set does not exactly match "
            "allowed_write_nodes"
        )
        self.assertEqual(
            _ledger_failure_class(legacy_event), "semantic_contract"
        )
        self.assertTrue(audit["complete"], audit["errors"])
        self.assertTrue(rescored[0]["semantic_contract_failure"])

    def test_json_syntax_failure_uses_frozen_retry_budget(self):
        case = self.cases[0]
        episode = self.episodes[case["episode_id"]]
        success = json.dumps(
            {
                "schema_version": SCHEMA,
                "episode_id": case["episode_id"],
                "updates": [
                    {
                        "node": node,
                        "value": episode["gold"]["post_state"][node],
                    }
                    for node in case["write_nodes"]
                ],
            }
        )
        fake_openai, calls = self._fake_openai(
            [('{"schema_version":', "stop"), (success, "stop")]
        )
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            sys.modules, {"openai": fake_openai}
        ), patch.dict(
            os.environ, {"OPENAI_API_KEY": "unit-test-placeholder"}
        ), patch("causal_benchmarks.api_decoder_experiment.time.sleep"):
            ledger = Path(temporary) / "usage.jsonl"
            row = _execute_case(
                case,
                self.episodes,
                config=APIConfig(
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    retries=3,
                ),
                ledger=ledger,
                decoder_seed=case["decoder_seed"],
            )
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual(len(calls), 2)
        self.assertEqual(row["api_attempts"], 2)
        self.assertTrue(row["episode_success"])
        self.assertEqual(events[0]["failure_class"], "json_syntax")
        self.assertEqual(events[1]["failure_class"], "none")

    def test_empty_and_truncated_responses_have_distinct_retry_classes(self):
        case = self.cases[0]
        episode = self.episodes[case["episode_id"]]
        success = json.dumps(
            {
                "schema_version": SCHEMA,
                "episode_id": case["episode_id"],
                "updates": [
                    {
                        "node": node,
                        "value": episode["gold"]["post_state"][node],
                    }
                    for node in case["write_nodes"]
                ],
            }
        )
        fake_openai, calls = self._fake_openai(
            [("", "stop"), (success, "length"), (success, "stop")]
        )
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            sys.modules, {"openai": fake_openai}
        ), patch.dict(
            os.environ, {"OPENAI_API_KEY": "unit-test-placeholder"}
        ), patch("causal_benchmarks.api_decoder_experiment.time.sleep"):
            ledger = Path(temporary) / "usage.jsonl"
            row = _execute_case(
                case,
                self.episodes,
                config=APIConfig(
                    model="deepseek-v4-flash",
                    base_url="https://example.invalid",
                    retries=3,
                ),
                ledger=ledger,
                decoder_seed=case["decoder_seed"],
            )
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual(len(calls), 3)
        self.assertTrue(row["episode_success"])
        self.assertEqual(
            [event["failure_class"] for event in events],
            ["empty", "truncated", "none"],
        )

    def test_incomplete_manifest_cannot_pass_gate(self):
        protocol = protocol_manifest(self.cases, episodes=120, seed=17, limit=1)
        case = self.cases[0]
        row = {
            "schema": "causal-api-decoder-result/v1",
            "request_id": case["request_id"],
            "task_family": case["task_family"],
            "arm": case["arm"],
            "prompt_sha256": case["prompt_sha256"],
            "decoder_seed": case["decoder_seed"],
            "semantic_scored": True,
            "parse_mode": "direct_json",
            "write_value_accuracy": 1.0,
            "episode_success": True,
            "usage": {},
            "api_duration_seconds": 0.0,
            "json_valid": True,
            "api_error": "",
        }
        report = summarize(
            [row],
            protocol,
            APIConfig(model="deepseek-v4-flash", base_url="https://example.invalid"),
        )
        self.assertFalse(report["manifest_audit"]["complete"])
        self.assertFalse(report["all_task_decoder_gates_pass"])

    def test_summary_separates_missing_engineering_and_semantic_failures(self):
        protocol = protocol_manifest(self.cases, episodes=120, seed=17, limit=1)
        semantic_case, engineering_case = self.cases[:2]
        semantic_row = {
            "request_id": semantic_case["request_id"],
            "task_family": semantic_case["task_family"],
            "arm": semantic_case["arm"],
            "prompt_sha256": semantic_case["prompt_sha256"],
            "decoder_seed": semantic_case["decoder_seed"],
            "semantic_scored": True,
            "semantic_contract_failure": True,
            "semantic_contract_valid": False,
            "failure_class": "semantic_contract",
            "parse_mode": "direct_json",
            "json_valid": True,
            "write_value_accuracy": 0.0,
            "episode_success": False,
            "usage": {},
            "api_duration_seconds": 0.0,
            "api_error": "",
        }
        engineering_row = {
            "request_id": engineering_case["request_id"],
            "task_family": engineering_case["task_family"],
            "arm": engineering_case["arm"],
            "prompt_sha256": engineering_case["prompt_sha256"],
            "decoder_seed": engineering_case["decoder_seed"],
            "semantic_scored": False,
            "failure_class": "json_syntax",
            "parse_mode": None,
            "json_valid": False,
            "write_value_accuracy": None,
            "episode_success": None,
            "usage": {},
            "api_duration_seconds": 0.0,
            "api_error": "EngineeringResponseError[json_syntax]",
        }
        report = summarize(
            [semantic_row, engineering_row],
            protocol,
            APIConfig(
                model="deepseek-v4-flash", base_url="https://example.invalid"
            ),
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
        self.assertEqual(len(accounting["missing_request_ids"]), 6)
        self.assertEqual(report["coverage"]["semantic_rows"], 1)
        missing_group = report["matrix"]["dynamic_shopping"]["oracle_context"]
        self.assertEqual(missing_group["calls_received"], 0)
        self.assertIsNone(missing_group["write_value_accuracy_valid_only"])
        self.assertIsNone(missing_group["raw_json_validity_received_only"])

    def test_missing_ledger_cannot_pass_integrity_audit(self):
        case = self.cases[0]
        episode = self.episodes[case["episode_id"]]
        response = json.dumps(
            {
                "schema_version": SCHEMA,
                "episode_id": case["episode_id"],
                "updates": [
                    {
                        "node": node,
                        "value": episode["gold"]["post_state"][node],
                    }
                    for node in case["write_nodes"]
                ],
            }
        )
        fake_perfect_row = {
            "schema": "causal-api-decoder-result/v1",
            "request_id": case["request_id"],
            "task_family": case["task_family"],
            "task": case["task"],
            "episode_id": case["episode_id"],
            "arm": case["arm"],
            "prompt_sha256": case["prompt_sha256"],
            "decoder_seed": case["decoder_seed"],
            "write_nodes": case["write_nodes"],
            "context_nodes": case["context_nodes"],
            "api_error": "",
            "parse_error": "",
            "json_valid": True,
            "parse_mode": "direct_json",
            "semantic_scored": True,
            "write_value_accuracy": 1.0,
            "episode_success": True,
            "updates": {
                node: episode["gold"]["post_state"][node]
                for node in case["write_nodes"]
            },
            "raw_response": response,
            "usage": {},
            "api_attempts": 0,
            "api_duration_seconds": 0.0,
        }
        _, audit = audit_and_rescore(
            [fake_perfect_row],
            [case],
            self.episodes,
            [],
            APIConfig(
                model="deepseek-v4-flash", base_url="https://example.invalid"
            ),
        )
        self.assertFalse(audit["complete"])
        self.assertTrue(any("missing ledger" in error for error in audit["errors"]))

        complete_row = dict(fake_perfect_row)
        complete_row["usage"] = {
            "model_requested": "deepseek-v4-flash",
            "model_returned": "deepseek-v4-flash",
            "input_tokens": 5,
            "cached_input_tokens": 2,
            "output_tokens": 7,
            "estimated_cost_usd": 0.0001,
            "response_attempts": 1,
        }
        complete_row["api_attempts"] = 1
        complete_row["api_duration_seconds"] = 0.5
        ledger = [{
            "schema": LEDGER_SCHEMA,
            "request_id": case["request_id"],
            "attempt": 1,
            "prompt_sha256": case["prompt_sha256"],
            "model_requested": "deepseek-v4-flash",
            "model_returned": "deepseek-v4-flash",
            "decoder_seed": case["decoder_seed"],
            "input_tokens": 5,
            "cached_input_tokens": 2,
            "output_tokens": 7,
            "estimated_cost_usd": 0.0001,
            "duration_seconds": 0.5,
            "finish_reason": "stop",
            "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
            "error": "",
        }]
        _, complete_audit = audit_and_rescore(
            [complete_row],
            [case],
            self.episodes,
            ledger,
            APIConfig(
                model="deepseek-v4-flash", base_url="https://example.invalid"
            ),
        )
        self.assertTrue(complete_audit["complete"], complete_audit["errors"])
        tampered = dict(complete_row)
        tampered["raw_response"] = response + " "
        _, tampered_audit = audit_and_rescore(
            [tampered],
            [case],
            self.episodes,
            ledger,
            APIConfig(
                model="deepseek-v4-flash", base_url="https://example.invalid"
            ),
        )
        self.assertFalse(tampered_audit["complete"])
        self.assertTrue(
            any("response hash mismatch" in error for error in tampered_audit["errors"])
        )

    def test_orphan_response_ledger_fails_closed_before_reissue(self):
        case = self.cases[0]
        event = {
            "schema": LEDGER_SCHEMA,
            "request_id": case["request_id"],
            "attempt": 1,
            "prompt_sha256": case["prompt_sha256"],
            "model_requested": "deepseek-v4-flash",
            "model_returned": "deepseek-v4-flash",
            "decoder_seed": case["decoder_seed"],
            "input_tokens": 5,
            "cached_input_tokens": 0,
            "output_tokens": 5,
            "estimated_cost_usd": 0.0001,
            "duration_seconds": 0.5,
            "finish_reason": "stop",
            "response_sha256": "a" * 64,
            "error": "",
        }
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "usage.jsonl"
            ledger.write_text(json.dumps(event) + "\n")
            with self.assertRaisesRegex(ValueError, "orphan API response"):
                _run_cases(
                    [case],
                    self.episodes,
                    config=APIConfig(
                        model="deepseek-v4-flash",
                        base_url="https://example.invalid",
                    ),
                    ledger=ledger,
                    results_jsonl=Path(temporary) / "results.jsonl",
                    workers=1,
                )


if __name__ == "__main__":
    unittest.main()
