from __future__ import annotations

import copy
import json
import unittest

from causal_benchmarks import (
    causal_formal,
    dynamic_search,
    dynamic_shopping,
    dynamic_travel,
)
from causal_benchmarks.api_selection_plans import (
    ARM_NAMES,
    SCHEMA_VERSION,
    TASK_FAMILIES,
    audit_killer_lookups_on_dev,
    build_nonoracle_plans,
    build_oracle_plan,
    build_six_arm_plans,
    fit_killer_lookup,
    fit_learned_selector,
    predict_killer_masks,
    validate_plan,
)
from causal_benchmarks.common import runtime_view


class APISelectionPlansTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        specs = {
            "dynamic_travel": (dynamic_travel, 60),
            "dynamic_shopping": (dynamic_shopping, 60),
            "dynamic_search": (dynamic_search, 60),
            "causal_formal": (causal_formal, 120),
        }
        cls.fixtures = {}
        for family, (module, episodes) in specs.items():
            dataset = module.generate_dataset(episodes=episodes, seed=17)
            train_views = [
                runtime_view(episode, training=True)
                for episode in dataset
                if episode["split"] == "train"
            ]
            test_episode = next(
                episode for episode in dataset if episode["split"] == "test"
            )
            dev_episode = next(
                episode for episode in dataset if episode["split"] == "dev"
            )
            test_view = runtime_view(test_episode, training=False)
            cls.fixtures[family] = {
                "dataset": dataset,
                "train_views": train_views,
                "dev_episode": dev_episode,
                "episode": test_episode,
                "view": test_view,
                "learner": fit_learned_selector(family, train_views),
            }

    def test_all_four_tasks_build_normalized_six_arm_plans(self) -> None:
        self.assertEqual(set(self.fixtures), set(TASK_FAMILIES))
        for family, fixture in self.fixtures.items():
            plans = build_six_arm_plans(
                family,
                fixture["view"],
                fixture["learner"],
                oracle_episode=fixture["episode"],
            )
            self.assertEqual(tuple(plans), ARM_NAMES)
            target = fixture["view"]["query"]["intervention"]["node"]
            for arm, plan in plans.items():
                self.assertEqual(plan.schema_version, SCHEMA_VERSION)
                self.assertEqual(plan.arm, arm)
                self.assertIn(target, plan.predicted_write_nodes)
                self.assertTrue(
                    set(plan.predicted_write_nodes)
                    <= set(plan.selected_context_nodes)
                )
                validate_plan(
                    plan,
                    fixture["view"],
                    oracle_allowed=arm == "oracle_graph",
                )

    def test_plans_never_contain_post_values_or_evaluator_labels(self) -> None:
        forbidden = (
            "post_state",
            "required_reads",
            "affected_nodes",
            "affected_state",
            "propagation_paths",
        )
        for family, fixture in self.fixtures.items():
            plans = build_six_arm_plans(
                family,
                fixture["view"],
                fixture["learner"],
                oracle_episode=fixture["episode"],
            )
            for plan in plans.values():
                serialized = json.dumps(plan.to_dict(), sort_keys=True)
                for field in forbidden:
                    self.assertNotIn(field, serialized)

    def test_exact_full_and_matched_budget_contracts(self) -> None:
        for family, fixture in self.fixtures.items():
            plans = build_nonoracle_plans(
                family, fixture["view"], fixture["learner"]
            )
            target = fixture["view"]["query"]["intervention"]["node"]
            self.assertEqual(plans["exact_kv"].predicted_write_nodes, (target,))
            all_nodes = tuple(sorted(fixture["view"]["memory_state"]))
            self.assertEqual(
                plans["full_state_history"].predicted_write_nodes, all_nodes
            )
            self.assertEqual(
                plans["full_state_history"].selected_context_nodes, all_nodes
            )
            learned = plans["learned_graph"]
            matched = plans["matched_retrieval"]
            self.assertEqual(matched.write_budget, learned.write_budget)
            self.assertEqual(matched.context_budget, learned.context_budget)
            self.assertEqual(matched.edge_budget, learned.edge_budget)
            self.assertEqual(
                len(matched.selected_history_ids), len(learned.selected_history_ids)
            )

    def test_domain_arm_matches_strongest_gold_free_executable_solver(self) -> None:
        for family, fixture in self.fixtures.items():
            view = runtime_view(fixture["dev_episode"], training=False)
            plans = build_nonoracle_plans(family, view, fixture["learner"])
            if family == "dynamic_travel":
                expected = dynamic_travel._domain_impacted(view)
            elif family == "dynamic_shopping":
                expected = dynamic_shopping.domain_solver_selection(view)[
                    "predicted_affected_nodes"
                ]
            elif family == "dynamic_search":
                expected = dynamic_search.provenance_domain_prediction(view)[
                    "affected_nodes"
                ]
            else:
                expected = causal_formal.oracle_graph_baseline(view)["affected_nodes"]
            self.assertEqual(
                plans["domain_solver"].predicted_write_nodes,
                tuple(sorted(expected)),
            )
            serialized = json.dumps(
                plans["domain_solver"].to_dict(), sort_keys=True
            )
            self.assertNotIn("post_state", serialized)
            self.assertNotIn("required_reads", serialized)

    def test_killer_lookups_are_train_only_and_outcome_free_at_prediction(self) -> None:
        for family, fixture in self.fixtures.items():
            lookup = fit_killer_lookup(family, fixture["train_views"])
            dev_view = runtime_view(fixture["dev_episode"], training=False)
            masks = predict_killer_masks(family, dev_view, lookup)
            target = dev_view["query"]["intervention"]["node"]
            self.assertEqual(set(masks), {"source_union", "query_signature"})
            for mask in masks.values():
                self.assertIn(target, mask)
                self.assertLessEqual(set(mask), set(dev_view["memory_state"]))

            contaminated = copy.deepcopy(dev_view)
            contaminated["gold"] = fixture["dev_episode"]["gold"]
            with self.assertRaises(ValueError):
                predict_killer_masks(family, contaminated, lookup)

            with self.assertRaises(ValueError):
                fit_killer_lookup(
                    family,
                    [runtime_view(fixture["dev_episode"], training=False)],
                )
            polluted_train = [copy.deepcopy(fixture["train_views"][0])]
            polluted_train[0]["gold"] = {"affected_nodes": []}
            with self.assertRaises(ValueError):
                fit_killer_lookup(family, polluted_train)

            supervised_train = [copy.deepcopy(fixture["train_views"][0])]
            supervised_train[0]["observed_transition"]["affected_nodes"] = []
            with self.assertRaisesRegex(ValueError, "non-runtime supervision"):
                fit_killer_lookup(family, supervised_train)

            serialized_lookup = json.dumps(lookup.summary(), sort_keys=True)
            for forbidden in (
                "post_state",
                "affected_nodes",
                "required_reads",
                "propagation_paths",
            ):
                self.assertNotIn(forbidden, serialized_lookup)

            paraphrased = copy.deepcopy(dev_view)
            paraphrased["query"]["text"] = "A completely different surface form."
            self.assertEqual(
                masks,
                predict_killer_masks(family, paraphrased, lookup),
            )

    def test_killer_admission_audit_is_dev_only(self) -> None:
        for family, fixture in self.fixtures.items():
            dev = [
                episode
                for episode in fixture["dataset"]
                if episode["split"] == "dev"
            ]
            report = audit_killer_lookups_on_dev(
                family, fixture["train_views"], dev
            )
            self.assertEqual(report["split"], "dev")
            self.assertEqual(
                set(report["arms"]), {"source_union", "query_signature"}
            )
            if family == "causal_formal":
                source = report["arms"]["source_union"]
                self.assertLess(source["affected_exact_match"], 0.95)
                self.assertGreaterEqual(
                    source["propagation_sufficient_mask_rate"], 0.95
                )
                self.assertTrue(source["query_only_stop_rule_triggered"])
            with self.assertRaisesRegex(ValueError, "dev-only"):
                audit_killer_lookups_on_dev(
                    family,
                    fixture["train_views"],
                    [fixture["episode"]],
                )

    def test_nonoracle_path_rejects_gold_and_test_outcomes(self) -> None:
        fixture = self.fixtures["dynamic_search"]
        with self.assertRaises(ValueError):
            build_nonoracle_plans(
                "dynamic_search", fixture["episode"], fixture["learner"]
            )
        contaminated = copy.deepcopy(fixture["view"])
        contaminated["observed_transition"] = {
            "post_state": fixture["episode"]["gold"]["post_state"]
        }
        with self.assertRaises(ValueError):
            build_nonoracle_plans(
                "dynamic_search", contaminated, fixture["learner"]
            )

    def test_fit_requires_gold_free_train_runtime_transitions(self) -> None:
        fixture = self.fixtures["dynamic_travel"]
        contaminated = [copy.deepcopy(fixture["train_views"][0])]
        contaminated[0]["gold"] = {"post_state": {}}
        with self.assertRaises(ValueError):
            fit_learned_selector("dynamic_travel", contaminated)
        missing_transition = [copy.deepcopy(fixture["train_views"][0])]
        del missing_transition[0]["observed_transition"]
        with self.assertRaises(ValueError):
            fit_learned_selector("dynamic_travel", missing_transition)

    def test_oracle_uses_graph_structure_not_gold_outcomes(self) -> None:
        removable = {
            "post_state",
            "affected_nodes",
            "affected_state",
            "required_reads",
            "required_tool_queries",
            "propagation_paths",
            "final_answers",
        }
        for family, fixture in self.fixtures.items():
            baseline = build_oracle_plan(
                family, fixture["view"], fixture["episode"]
            )
            graph_only_episode = copy.deepcopy(fixture["episode"])
            for key in removable:
                graph_only_episode["gold"].pop(key, None)
            graph_only_episode["gold"]["active_edges"] = []
            rebuilt = build_oracle_plan(
                family, fixture["view"], graph_only_episode
            )
            self.assertEqual(baseline, rebuilt)

    def test_oracle_potential_graph_covers_deactivation_effects(self) -> None:
        for family, fixture in self.fixtures.items():
            for episode in fixture["dataset"]:
                if episode["split"] != "test":
                    continue
                view = runtime_view(episode, training=False)
                plan = build_oracle_plan(family, view, episode)
                self.assertLessEqual(
                    set(episode["gold"]["affected_nodes"]),
                    set(plan.predicted_write_nodes),
                    msg=episode["episode_id"],
                )


if __name__ == "__main__":
    unittest.main()
