from __future__ import annotations

import json
import copy
import tempfile
import unittest
from pathlib import Path

from causal_benchmarks.common import runtime_view, validate_episode
from causal_benchmarks.dynamic_shopping import (
    audit_dataset,
    exact_key_baseline,
    fit_learned_selector,
    generate_dataset,
    main,
    oracle_propagation_baseline,
    run_t1_experiment,
    simulate,
)


class DynamicShoppingTest(unittest.TestCase):
    def test_generation_is_deterministic_and_schema_valid(self) -> None:
        first = generate_dataset(episodes=12, seed=17)
        second = generate_dataset(episodes=12, seed=17)
        self.assertEqual(first, second)
        self.assertNotEqual(first, generate_dataset(episodes=12, seed=18))
        for episode in first:
            validate_episode(episode)
            self.assertEqual(
                episode["query"]["explicit_state_keys"],
                [episode["query"]["intervention"]["node"]],
            )
            self.assertTrue(
                set(episode["gold"]["affected_nodes"])
                - set(episode["query"]["explicit_state_keys"])
            )
            self.assertEqual(
                set(path[-1] for path in episode["gold"]["propagation_paths"]),
                set(episode["gold"]["affected_nodes"])
                - set(episode["query"]["explicit_state_keys"]),
            )

    def test_exact_key_is_insufficient_and_oracle_is_complete(self) -> None:
        dataset = generate_dataset(episodes=12, seed=7)
        for episode in dataset:
            exact = exact_key_baseline(episode)
            oracle = oracle_propagation_baseline(episode)
            self.assertNotEqual(exact["post_state"], episode["gold"]["post_state"])
            self.assertEqual(oracle["post_state"], episode["gold"]["post_state"])
            self.assertEqual(oracle["affected_nodes"], episode["gold"]["affected_nodes"])
        report = audit_dataset(dataset)
        self.assertTrue(report["t0_pass"])
        self.assertEqual(report["exact_key"]["episode_success_rate"], 0.0)
        self.assertEqual(report["oracle_propagation"]["episode_success_rate"], 1.0)

    def test_regime_gates_display_propagation_and_controls_stay_fixed(self) -> None:
        dataset = generate_dataset(episodes=12, seed=3)
        by_scenario = {
            episode["gold"]["audit_annotations"]["scenario"]: episode
            for episode in dataset
        }
        strict = by_scenario["gpu_cancel_strict"]
        adapters = by_scenario["gpu_cancel_adapters"]
        self.assertIn("cart.monitor", strict["gold"]["affected_nodes"])
        self.assertNotIn("cart.monitor", adapters["gold"]["affected_nodes"])
        strict_edges = {
            (edge["source"], edge["target"])
            for edge in strict["gold"]["active_edges"]
        }
        adapter_edges = {
            (edge["source"], edge["target"])
            for edge in adapters["gold"]["active_edges"]
        }
        self.assertIn(("cart.gpu", "cart.monitor"), strict_edges)
        self.assertNotIn(("cart.gpu", "cart.monitor"), adapter_edges)
        for episode in dataset:
            for key in episode["gold"]["audit_annotations"][
                "negative_control_keys"
            ]:
                self.assertEqual(
                    episode["memory_state"][key], episode["gold"]["post_state"][key]
                )

    def test_required_reads_include_candidate_availability(self) -> None:
        dataset = generate_dataset(episodes=120, seed=17)
        episode = next(
            row
            for row in dataset
            if row["gold"]["audit_annotations"]["scenario"] == "gpu_cancel_strict"
        )
        _, reads, tool_queries = simulate(
            episode["memory_state"], episode["query"]["intervention"]
        )
        queried_slots = {query["slot"] for query in tool_queries}
        self.assertIn("monitor", queried_slots)
        monitor_keys = {
            node
            for node in episode["memory_state"]
            if node.startswith("availability.monitor_")
        }
        self.assertTrue(monitor_keys)
        self.assertLessEqual(monitor_keys, set(reads))

    def test_cli_writes_auditable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "dynamic-shopping.json"
            self.assertEqual(
                main(
                    [
                        "--episodes",
                        "12",
                        "--seed",
                        "9",
                        "--out",
                        str(output),
                        "--t1",
                    ]
                ),
                0,
            )
            payload = json.loads(output.read_text())
            self.assertEqual(payload["benchmark"], "dynamic_shopping")
            self.assertEqual(len(payload["episodes"]), 12)
            self.assertTrue(payload["audit"]["t0_pass"])
            self.assertIn("t1", payload)

    def test_observed_outcomes_exist_only_in_train_runtime(self) -> None:
        dataset = generate_dataset(episodes=60, seed=7)
        for episode in dataset:
            view = runtime_view(episode, training=True)
            self.assertNotIn("gold", view)
            self.assertEqual(view["metadata"], {"catalog_version": "synthetic-pc-cart/v1"})
            if episode["split"] == "train":
                self.assertIn("observed_transition", episode)
                transition = episode["observed_transition"]
                self.assertEqual(
                    set(transition), {"pre_state", "intervention", "post_state"}
                )
                self.assertNotIn("graph", transition)
                self.assertIn("observed_transition", view)
            else:
                self.assertNotIn("observed_transition", episode)
                self.assertNotIn("observed_transition", view)

    def test_learner_runs_after_gold_is_deleted(self) -> None:
        dataset = generate_dataset(episodes=60, seed=11)
        stripped = []
        for episode in dataset:
            record = copy.deepcopy(episode)
            del record["gold"]
            stripped.append(record)
        train = [record for record in stripped if record["split"] == "train"]
        test = [record for record in stripped if record["split"] == "test"]
        learner = fit_learned_selector(train)
        for record in test:
            predicted = learner.predict_affected(record)
            self.assertTrue(predicted)
            self.assertIn(record["query"]["intervention"]["node"], predicted)
        with self.assertRaises(ValueError):
            fit_learned_selector(
                [episode for episode in dataset if episode["split"] == "train"]
            )

    def test_test_split_has_novel_factors_and_heldout_regime(self) -> None:
        dataset = generate_dataset(episodes=60, seed=7)
        train = [episode for episode in dataset if episode["split"] == "train"]
        test = [episode for episode in dataset if episode["split"] == "test"]
        self.assertFalse(
            {
                episode["gold"]["audit_annotations"]["template_id"]
                for episode in train
            }
            & {
                episode["gold"]["audit_annotations"]["template_id"]
                for episode in test
            }
        )
        self.assertTrue(
            any(
                episode["gold"]["audit_annotations"]["novel_test_factors"][
                    "unseen_entity"
                ]
                for episode in test
            )
        )
        self.assertTrue(
            all(
                "cpu_nova_test"
                not in json.dumps(runtime_view(episode, training=True))
                for episode in train
            )
        )
        self.assertTrue(
            any(
                episode["gold"]["audit_annotations"]["novel_test_factors"][
                    "unseen_value"
                ]
                for episode in test
            )
        )
        self.assertNotIn(
            "cpu_cancel_hard_cap",
            {
                episode["gold"]["audit_annotations"]["scenario"]
                for episode in train
            },
        )
        self.assertIn(
            "cpu_cancel_hard_cap",
            {
                episode["gold"]["audit_annotations"]["scenario"]
                for episode in test
            },
        )

    def test_t1_six_arms_and_orthogonal_serialization(self) -> None:
        report = run_t1_experiment(generate_dataset(episodes=60, seed=7))
        self.assertEqual(
            set(report["arms"]),
            {
                "exact_kv",
                "domain_solver",
                "matched_retrieval",
                "learned_graph",
                "oracle_graph",
                "full_state_history",
            },
        )
        self.assertEqual(set(report["leakage_audit"].values()), {0})
        learned = report["arms"]["learned_graph"]
        domain = report["arms"]["domain_solver"]
        matched = report["arms"]["matched_retrieval"]
        self.assertEqual(learned["task_success"], 1.0)
        self.assertEqual(domain["task_success"], 1.0)
        self.assertEqual(learned["affected_precision"], 1.0)
        self.assertEqual(learned["affected_recall"], 1.0)
        self.assertEqual(
            learned["selected_cells"], matched["selected_cells"]
        )
        self.assertLess(matched["affected_recall"], learned["affected_recall"])
        self.assertLess(learned["required_read_recall"], 1.0)
        self.assertEqual(report["novel_test"]["heldout_regime_task_success"], 1.0)
        self.assertFalse(
            report["scientific_conclusion"][
                "learned_beats_domain_solver_on_task_success"
            ]
        )
        self.assertFalse(
            report["scientific_conclusion"]["causal_advantage_established"]
        )
        for arm in report["arms"].values():
            self.assertLess(
                arm["serialization"]["compact"]["characters"],
                arm["serialization"]["verbose"]["characters"],
            )


if __name__ == "__main__":
    unittest.main()
