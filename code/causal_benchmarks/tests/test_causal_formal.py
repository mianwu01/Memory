"""Tests for the deterministic causal formal-reasoning prototype."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from causal_benchmarks.causal_formal import (
    LearnedImpactSelector,
    audit_dataset,
    formal_runtime_view,
    generate_dataset,
    generate_episodes,
    learned_graph_baseline,
    main,
    predict_exact_key,
    predict_oracle_propagation,
    run_t1,
)
from causal_benchmarks.common import SCHEMA_VERSION, validate_episode


class CausalFormalTest(unittest.TestCase):
    def test_generation_is_deterministic_and_schema_valid(self) -> None:
        first = generate_episodes(count=24, seed=11)
        second = generate_episodes(count=24, seed=11)
        different = generate_episodes(count=24, seed=12)
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertEqual({episode["schema_version"] for episode in first}, {SCHEMA_VERSION})
        for episode in first:
            validate_episode(episode)

    def test_runner_adapters(self) -> None:
        dataset = generate_dataset(episodes=12, seed=3)
        report = audit_dataset(dataset)
        self.assertEqual(len(dataset), 12)
        self.assertEqual(report["episodes"], 12)

    def test_large_dataset_covers_each_scenario_in_each_split(self) -> None:
        dataset = generate_dataset(episodes=120, seed=4)
        for task in ("causal_formal_math", "causal_formal_phys"):
            task_rows = [episode for episode in dataset if episode["task"] == task]
            scenarios = {episode["metadata"]["scenario"] for episode in task_rows}
            self.assertEqual(len(scenarios), 6)
            for split in ("train", "dev", "test"):
                self.assertEqual(
                    {
                        episode["metadata"]["scenario"]
                        for episode in task_rows
                        if episode["split"] == split
                    },
                    scenarios,
                )

    def test_query_never_enumerates_derived_descendants(self) -> None:
        for episode in generate_episodes(count=24, seed=5):
            query = episode["query"]["text"]
            self.assertFalse(episode["metadata"]["query_lists_descendants"])
            for result in episode["gold"]["affected_results"]:
                self.assertNotIn(result, query)

    def test_outcomes_are_visible_only_on_train(self) -> None:
        dataset = generate_dataset(episodes=120, seed=5)
        for episode in dataset:
            if episode["split"] == "train":
                self.assertIn("observed_transition", episode)
                view = formal_runtime_view(episode, training=True)
                self.assertIn("observed_transition", view)
            else:
                self.assertNotIn("observed_transition", episode)
                view = formal_runtime_view(episode, training=False)
                self.assertNotIn("observed_transition", view)
            self.assertNotIn("gold", view)

    def test_train_only_learner_fits_and_predicts_after_gold_deletion(self) -> None:
        dataset = generate_dataset(episodes=120, seed=8)
        train = [episode for episode in dataset if episode["split"] == "train"]
        test = [episode for episode in dataset if episode["split"] == "test"]
        train_views = [formal_runtime_view(episode, training=True) for episode in train]
        selector = LearnedImpactSelector().fit(train_views)
        self.assertEqual(selector.transitions_seen, len(train))
        self.assertTrue(set(selector.fit_episode_ids).isdisjoint(
            {episode["episode_id"] for episode in test}
        ))
        for episode in test:
            view = formal_runtime_view(episode, training=False)
            prediction = learned_graph_baseline(view, selector)
            self.assertEqual(prediction["post_state"], episode["gold"]["post_state"])
            self.assertEqual(
                prediction["affected_nodes"], episode["gold"]["affected_nodes"]
            )
        with self.assertRaisesRegex(ValueError, "evaluator gold"):
            LearnedImpactSelector().fit([train[0]])
        polluted = formal_runtime_view(test[0], training=False)
        polluted["gold"] = test[0]["gold"]
        with self.assertRaisesRegex(ValueError, "outcome-free"):
            selector.select(polluted)

    def test_t1_split_has_novel_values_templates_and_regime_pairs(self) -> None:
        report = run_t1(generate_dataset(episodes=120, seed=17))
        split = report["split_diagnostics"]
        self.assertEqual(split["train_observed_transitions"], split["train_episodes"])
        self.assertEqual(split["dev_test_outcome_leaks"], 0)
        self.assertEqual(split["template_overlap"], [])
        self.assertEqual(split["numeric_primitive_value_overlaps"], [])
        self.assertGreater(split["heldout_target_regime_combinations"], 0)
        self.assertGreater(split["heldout_long_impact_episodes"], 0)

    def test_t1_six_arms_and_orthogonal_serialization(self) -> None:
        report = run_t1(generate_dataset(episodes=120, seed=17))
        self.assertEqual(
            set(report["arms"]),
            {
                "exact_kv",
                "program_dataflow",
                "matched_budget_retrieval",
                "learned_graph",
                "oracle_graph",
                "full_history",
            },
        )
        learned = report["arms"]["learned_graph"]
        program = report["arms"]["program_dataflow"]
        matched = report["arms"]["matched_budget_retrieval"]
        self.assertEqual(learned["effectiveness"]["episode_success"], 1.0)
        self.assertEqual(program["effectiveness"]["episode_success"], 1.0)
        self.assertLess(matched["effectiveness"]["episode_success"], 1.0)
        self.assertEqual(
            matched["serialization"]["compact"]["selected_update_nodes_mean"],
            learned["serialization"]["compact"]["selected_update_nodes_mean"],
        )
        for arm in report["selection_x_serialization"].values():
            self.assertEqual(
                arm["verbose"]["episode_success"], arm["compact"]["episode_success"]
            )
        self.assertLess(
            learned["serialization"]["compact"]["serialized_chars_mean"],
            learned["serialization"]["verbose"]["serialized_chars_mean"],
        )
        self.assertEqual(
            learned["effectiveness"]["negative_control_preservation"], 1.0
        )
        self.assertFalse(report["verdict"]["learned_graph_necessity_pass"])
        self.assertTrue(report["verdict"]["train_only_pipeline_pass"])

    def test_active_and_inactive_regime_edges(self) -> None:
        episodes = generate_episodes(count=12, seed=7, family="math")
        active = next(
            ep for ep in episodes if ep["metadata"]["scenario"] == "active_gate_update"
        )
        inactive = next(
            ep for ep in episodes if ep["metadata"]["scenario"] == "inactive_gate_update"
        )
        self.assertIn("lemma.active_branch", active["gold"]["affected_results"])
        self.assertIn("theorem.final", active["gold"]["affected_results"])
        self.assertEqual(inactive["gold"]["affected_results"], [])
        self.assertEqual(
            inactive["gold"]["affected_nodes"], ["definition.twist"]
        )
        inactive_edges = {
            (edge["source"], edge["target"])
            for edge in inactive["gold"]["active_edges"]
        }
        self.assertNotIn(
            ("definition.twist", "lemma.active_branch"), inactive_edges
        )

    def test_axiom_retraction_propagates_but_preserves_controls(self) -> None:
        episode = next(
            ep
            for ep in generate_episodes(count=12, seed=9, family="phys")
            if ep["metadata"]["scenario"] == "axiom_retraction"
        )
        self.assertIn("lemma.active_force", episode["gold"]["affected_results"])
        self.assertIn(
            "theorem.displacement_score", episode["gold"]["affected_results"]
        )
        self.assertEqual(
            episode["gold"]["unaffected_controls"],
            ["control.calibration_checksum", "control.detector_bias"],
        )
        for control in episode["gold"]["unaffected_controls"]:
            self.assertEqual(
                episode["memory_state"][control], episode["gold"]["post_state"][control]
            )

    def test_oracle_does_not_require_evaluator_gold(self) -> None:
        episode = generate_episodes(count=1, seed=13, family="math")[0]
        observable = {key: value for key, value in episode.items() if key != "gold"}
        exact = predict_exact_key(observable)
        oracle = predict_oracle_propagation(observable)
        self.assertNotEqual(exact["post_state"], episode["gold"]["post_state"])
        self.assertEqual(oracle["post_state"], episode["gold"]["post_state"])

    def test_t0_has_large_exact_key_headroom(self) -> None:
        report = audit_dataset(generate_dataset(episodes=120, seed=17))
        self.assertAlmostEqual(report["propagation_required_rate"], 5 / 6)
        self.assertAlmostEqual(report["exact_key"]["episode_success"], 1 / 6)
        self.assertEqual(report["exact_key"]["affected_result_recall"], 0.0)
        self.assertEqual(report["oracle_propagation"]["episode_success"], 1.0)
        self.assertEqual(report["headroom"]["affected_result_recall"], 1.0)
        self.assertTrue(report["admission"]["pass"])
        self.assertEqual(report["downstream_query_leakage"]["leaked"], 0)

    def test_cli_jsonl_and_t0(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "formal.jsonl"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    main(
                        [
                            "generate",
                            "--count",
                            "3",
                            "--seed",
                            "2",
                            "--family",
                            "math",
                            "--output",
                            str(output),
                        ]
                    ),
                    0,
                )
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 3)
            self.assertEqual(json.loads(stdout.getvalue())["episodes"], 3)

    def test_cli_t1(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main(["t1", "--count", "120", "--seed", "17"]), 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["schema"], "causal-formal-t1/v1")
        self.assertTrue(report["verdict"]["train_only_pipeline_pass"])


if __name__ == "__main__":
    unittest.main()
