from __future__ import annotations

import unittest

from causal_benchmarks.common import audit_predictions, runtime_view, validate_episode
from causal_benchmarks.dynamic_travel import (
    LearnedImpactSelector,
    audit_dataset,
    evaluate_t1,
    exact_key_baseline,
    generate_dataset,
    oracle_propagation_baseline,
)


class DynamicTravelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = generate_dataset(100, seed=7)

    def test_schema_and_counterfactual_delta(self):
        for episode in self.dataset:
            validate_episode(episode)

    def test_exact_key_leaves_propagation_headroom(self):
        report = audit_predictions(
            self.dataset, [exact_key_baseline(ep) for ep in self.dataset]
        )
        self.assertGreaterEqual(report["propagation_required_episodes"], 75)
        self.assertLess(report["affected_recall"], 0.75)
        self.assertLess(report["affected_state_accuracy"], 0.75)

    def test_oracle_reconstructs_post_state(self):
        report = audit_predictions(
            self.dataset, [oracle_propagation_baseline(ep) for ep in self.dataset]
        )
        self.assertEqual(report["affected_precision"], 1.0)
        self.assertEqual(report["affected_recall"], 1.0)
        self.assertEqual(report["affected_state_accuracy"], 1.0)
        self.assertEqual(report["full_state_accuracy"], 1.0)

    def test_t0_admission_passes(self):
        audit = audit_dataset(self.dataset)
        self.assertTrue(audit["admission"]["pass"])
        self.assertEqual(audit["downstream_query_leakage"]["leaked"], 0)

    def test_train_outcomes_and_test_runtime_are_isolated(self):
        train = [episode for episode in self.dataset if episode["split"] == "train"]
        test = [episode for episode in self.dataset if episode["split"] == "test"]
        self.assertTrue(all("observed_transition" in episode for episode in train))
        self.assertTrue(all("observed_transition" not in episode for episode in test))
        train_views = [runtime_view(episode, training=True) for episode in train]
        learner = LearnedImpactSelector.fit(train_views)
        for episode in test:
            view = runtime_view(episode)
            self.assertNotIn("gold", view)
            self.assertNotIn("observed_transition", view)
            self.assertTrue(learner.predict(view))

    def test_t1_six_arms_and_novel_split(self):
        report = evaluate_t1(self.dataset)
        self.assertEqual(
            set(report["arms"]),
            {
                "exact_kv",
                "domain_solver",
                "matched_lexical",
                "learned_graph",
                "oracle_graph",
                "full_state",
            },
        )
        self.assertEqual(report["generalization"]["train_test_entity_overlap"], 0)
        self.assertTrue(report["generalization"]["held_out_regime_signatures"])
        self.assertEqual(report["arms"]["domain_solver"]["task_success_rate"], 1.0)
        for arm in report["arms"].values():
            self.assertIn("compact", arm["serialization"])
            self.assertIn("verbose", arm["serialization"])


if __name__ == "__main__":
    unittest.main()
