"""Acceptance rules for bounded actor qualification (no network)."""
import copy
import unittest

from .actor_gate import qualify
from .actor_gate_report import assess_model_identity


class ActorGateTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(event="result", episode=str(i), correct=True,
                          finish_reason="stop", thinking_observed=True,
                          returned_model="deepseek-v4-flash-0731")
                     for i in range(10) for _ in range(3)]

    def test_stability_is_not_aggregate_accuracy(self):
        one_case = copy.deepcopy(self.rows)
        for i in (0, 1, 2):
            one_case[i]["correct"] = False
        self.assertTrue(qualify(one_case)["passed"])
        dispersed = copy.deepcopy(self.rows)
        for i in (0, 3, 6):
            dispersed[i]["correct"] = False
        self.assertEqual(qualify(dispersed)["correct"], 27)
        self.assertFalse(qualify(dispersed)["passed"])

    def test_incomplete_and_transport_failures_do_not_pass(self):
        self.assertFalse(qualify(self.rows[:-1])["passed"])
        self.rows[0] = dict(event="infrastructure_failure", episode="0")
        result = qualify(self.rows)
        self.assertEqual(result["infrastructure_unresolved"], 1)
        self.assertEqual(result["completed"], 29)
        self.assertFalse(result["passed"])

    def test_thinking_truncation_and_model_identity_are_required(self):
        for field, value in [("thinking_observed", False), ("finish_reason", "length"),
                             ("returned_model", "DeepSeek-V4-Pro-0813")]:
            with self.subTest(field=field):
                rows = copy.deepcopy(self.rows)
                rows[0][field] = value
                self.assertFalse(qualify(rows)["passed"])

    def test_passing_actor_does_not_authorize_discovery(self):
        result = qualify(self.rows)
        self.assertTrue(result["passed"])
        self.assertFalse(result["discovery_authorized_by_this_gate"])

    def test_case_only_metadata_amendment_preserves_raw_decision(self):
        self.rows[0]["returned_model"] = "DeepSeek-V4-Flash-0731"
        result = assess_model_identity(self.rows)
        self.assertFalse(result["strict_literal_model_id_gate_passed"])
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["returned_models"]), 2)
        self.assertEqual(result["normalized_returned_models"], ["deepseek-v4-flash-0731"])

    def test_model_identity_amendment_does_not_merge_versions(self):
        self.rows[0]["returned_model"] = "DeepSeek-V4-Flash-0813"
        self.assertFalse(assess_model_identity(self.rows)["passed"])
        self.rows[0]["returned_model"] = "DeepSeek-V4-Pro-0731"
        self.assertFalse(assess_model_identity(self.rows)["passed"])


if __name__ == "__main__":
    unittest.main()
