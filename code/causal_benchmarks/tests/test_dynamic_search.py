"""Tests for the isolated dynamic-evidence search prototype."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from causal_benchmarks.common import runtime_view, validate_episode
from causal_benchmarks.dynamic_search import (
    LearnedImpactSelector,
    SCENARIOS,
    active_edge_ids,
    audit_dataset,
    audit_t1,
    exact_key_prediction,
    generate_dataset,
    main,
    oracle_prediction,
    provenance_domain_prediction,
)


class DynamicSearchTest(unittest.TestCase):
    def test_generation_is_deterministic_and_schema_valid(self) -> None:
        first = generate_dataset(episodes=18, seed=4)
        second = generate_dataset(episodes=18, seed=4)
        different = generate_dataset(episodes=18, seed=5)
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        for episode in first:
            validate_episode(episode)

    def test_query_names_only_the_intervention_not_descendants(self) -> None:
        for episode in generate_dataset(episodes=24, seed=9):
            query = episode["query"]["text"]
            explicit = episode["query"]["intervention"]["node"]
            self.assertIn(explicit, query)
            for node in set(episode["gold"]["affected_nodes"]) - {explicit}:
                self.assertNotIn(node, query)

    def test_positive_events_require_propagation(self) -> None:
        episodes = generate_dataset(episodes=12, seed=0)
        for episode in episodes:
            if episode["gold"]["negative_control"]:
                continue
            exact = exact_key_prediction(episode)
            oracle = oracle_prediction(episode)
            answer_node = episode["gold"]["final_answers"]["answer_node"]
            self.assertGreater(len(episode["gold"]["affected_nodes"]), 1)
            self.assertNotEqual(
                exact["post_state"][answer_node], episode["gold"]["post_state"][answer_node]
            )
            self.assertEqual(oracle["post_state"], episode["gold"]["post_state"])

    def test_oracle_does_not_read_evaluator_gold(self) -> None:
        episode = next(
            ep
            for ep in generate_dataset(episodes=12, seed=4)
            if not ep["gold"]["negative_control"]
        )
        observable = {key: value for key, value in episode.items() if key != "gold"}
        oracle = oracle_prediction(observable)
        self.assertEqual(oracle["post_state"], episode["gold"]["post_state"])
        self.assertEqual(oracle["affected_nodes"], episode["gold"]["affected_nodes"])

    def test_low_trust_and_citation_copy_are_negative_controls(self) -> None:
        episodes = generate_dataset(episodes=12, seed=0)
        controls = [ep for ep in episodes if ep["gold"]["negative_control"]]
        self.assertEqual(
            {ep["gold"]["scenario"] for ep in controls},
            {
                "low_trust_update_negative",
                "citation_mirror_retraction_negative",
            },
        )
        for episode in controls:
            explicit = episode["query"]["intervention"]["node"]
            self.assertEqual(episode["gold"]["affected_nodes"], [explicit])
            self.assertEqual(
                active_edge_ids(episode["gold"]["post_state"], episode["gold"]["graph"]),
                sorted(edge["edge_id"] for edge in episode["gold"]["active_edges"]),
            )
            evidence_edge = next(
                edge
                for edge in episode["gold"]["graph"]
                if edge["source"] == explicit and edge["relation"] == "evidence"
            )
            self.assertNotIn(
                evidence_edge["edge_id"],
                {edge["edge_id"] for edge in episode["gold"]["active_edges"]},
            )

    def test_t0_audit_has_headroom_and_balanced_scenarios(self) -> None:
        report = audit_dataset(generate_dataset(episodes=60, seed=7))
        self.assertEqual(set(report["scenario_counts"]), set(SCENARIOS))
        self.assertTrue(all(report["admission"].values()))
        self.assertEqual(report["diagnostics"]["query_downstream_id_leakage"], 0.0)
        self.assertEqual(
            report["baselines"]["exact_key"]["propagation_episode_answer_accuracy"],
            0.0,
        )
        self.assertEqual(
            report["baselines"]["oracle_propagation"][
                "propagation_episode_answer_accuracy"
            ],
            1.0,
        )

    def test_train_outcomes_are_runtime_visible_but_test_outcomes_are_not(self) -> None:
        dataset = generate_dataset(episodes=120, seed=17)
        train = [episode for episode in dataset if episode["split"] == "train"]
        test = [episode for episode in dataset if episode["split"] == "test"]
        self.assertTrue(all("observed_transition" in episode for episode in train))
        self.assertTrue(all("observed_transition" not in episode for episode in test))
        train_views = [runtime_view(episode, training=True) for episode in train]
        test_views = [runtime_view(episode, training=False) for episode in test]
        self.assertTrue(all("gold" not in view for view in train_views + test_views))
        self.assertTrue(all("observed_transition" in view for view in train_views))
        self.assertTrue(all("observed_transition" not in view for view in test_views))
        self.assertTrue(all("post_state" not in json.dumps(view) for view in test_views))

    def test_learner_and_provenance_work_after_gold_is_deleted(self) -> None:
        dataset = generate_dataset(episodes=120, seed=11)
        train_views = [
            runtime_view(episode, training=True)
            for episode in dataset
            if episode["split"] == "train"
        ]
        test_views = [
            runtime_view(episode, training=False)
            for episode in dataset
            if episode["split"] == "test"
        ]
        learner = LearnedImpactSelector().fit(train_views)
        for view in test_views:
            learned = learner.predict(view)
            provenance = provenance_domain_prediction(view)
            self.assertIn("post_state", learned)
            self.assertIn("post_state", provenance)
        with self.assertRaises(ValueError):
            LearnedImpactSelector().fit(
                [episode for episode in dataset if episode["split"] == "train"]
            )

    def test_t1_novel_split_six_arms_and_honest_claim_boundary(self) -> None:
        report = audit_t1(generate_dataset(episodes=120, seed=17))
        self.assertEqual(report["status"], "complete")
        self.assertEqual(len(report["effects"]), 6)
        self.assertTrue(report["novel_test"]["pass"])
        self.assertEqual(report["novel_test"]["node_id_overlap"], 0)
        self.assertEqual(
            report["novel_test"]["heldout_trust_transitions"],
            ["high->medium", "medium->high"],
        )
        self.assertEqual(report["novel_test"]["heldout_entity_versions"], [3])
        self.assertEqual(report["effects"]["learned_graph"]["affected_recall"], 1.0)
        self.assertGreater(
            report["effects"]["learned_graph"]["affected_recall"],
            report["effects"]["matched_lexical_structured"]["affected_recall"],
        )
        self.assertEqual(
            report["effects"]["learned_graph"]["affected_recall"],
            report["effects"]["provenance_domain"]["affected_recall"],
        )
        self.assertFalse(report["admission"]["learned_beats_strong_provenance"])
        self.assertFalse(report["admission"]["supports_causal_learning_claim"])

    def test_selection_and_serialization_are_orthogonal(self) -> None:
        report = audit_t1(generate_dataset(episodes=120, seed=3))
        rows = report["selection_x_serialization"]
        self.assertEqual(len(rows), 12)
        for arm in report["effects"]:
            arm_rows = [row for row in rows if row["arm"] == arm]
            self.assertEqual(len(arm_rows), 2)
            verbose = next(row for row in arm_rows if row["serialization"] == "verbose")
            compact = next(row for row in arm_rows if row["serialization"] == "compact")
            self.assertEqual(verbose["affected_recall"], compact["affected_recall"])
            self.assertEqual(verbose["selected_cells_mean"], compact["selected_cells_mean"])
            self.assertLess(compact["serialization_chars_mean"], verbose["serialization_chars_mean"])

    def test_cli_writes_jsonl_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "episodes.jsonl"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    ["--episodes", "6", "--seed", "3", "--out", str(output), "--audit"]
                )
            summary = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 6)
            self.assertTrue(Path(summary["audit_out"]).exists())


if __name__ == "__main__":
    unittest.main()
