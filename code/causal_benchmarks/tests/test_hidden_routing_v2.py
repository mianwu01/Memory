from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from causal_benchmarks.common import runtime_view, validate_episode
from causal_benchmarks.hidden_routing_v2 import (
    BASELINE_NAMES,
    V2_TASKS,
    ConsistentCodebookProgram,
    HiddenRouteLearner,
    ShortcutImpactTables,
    _DOMAIN,
    audit_dataset,
    exact_kv_mask,
    generate_dataset,
    gold_free_program_mask,
    matched_retrieval_mask,
)


class HiddenRoutingV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = generate_dataset(episodes_per_domain=24, seed=31)

    def test_generation_is_deterministic_and_schema_valid(self) -> None:
        self.assertEqual(
            self.dataset,
            generate_dataset(episodes_per_domain=24, seed=31),
        )
        self.assertNotEqual(
            self.dataset,
            generate_dataset(episodes_per_domain=24, seed=32),
        )
        self.assertEqual({episode["task"] for episode in self.dataset}, set(V2_TASKS))
        for episode in self.dataset:
            validate_episode(episode)
            self.assertEqual(
                set(episode["query"]["intervention"]),
                {"node", "old_value", "new_value", "kind"},
            )

    def test_opaque_ids_query_boundary_and_heldout_compositions(self) -> None:
        for task in V2_TASKS:
            train = [ep for ep in self.dataset if ep["task"] == task and ep["split"] == "train"]
            test = [ep for ep in self.dataset if ep["task"] == task and ep["split"] == "test"]
            train_ids = {node for ep in train for node in ep["memory_state"]}
            test_ids = {node for ep in test for node in ep["memory_state"]}
            self.assertFalse(train_ids & test_ids)
            self.assertTrue(all(node.startswith("v_") for node in train_ids | test_ids))
            train_compositions = {
                ep["gold"]["audit_annotations"]["route_composition"] for ep in train
            }
            test_compositions = {
                ep["gold"]["audit_annotations"]["route_composition"] for ep in test
            }
            self.assertTrue(test_compositions - train_compositions)
            for episode in test:
                query = episode["query"]["text"]
                target = episode["query"]["intervention"]["node"]
                self.assertIn(target, query)
                downstream = set(episode["gold"]["affected_nodes"]) - {target}
                self.assertTrue(downstream)
                self.assertTrue(
                    all(node not in query for node in downstream),
                    msg=episode["episode_id"],
                )
                self.assertGreaterEqual(
                    episode["gold"]["audit_annotations"]["max_active_hops"], 2
                )

    def test_train_outcomes_and_eval_runtime_are_isolated(self) -> None:
        for task in V2_TASKS:
            task_rows = [ep for ep in self.dataset if ep["task"] == task]
            train_views = [
                runtime_view(ep, training=True) for ep in task_rows if ep["split"] == "train"
            ]
            eval_views = [
                runtime_view(ep, training=False) for ep in task_rows if ep["split"] == "test"
            ]
            self.assertTrue(all("gold" not in view for view in train_views + eval_views))
            self.assertTrue(all("observed_transition" in view for view in train_views))
            self.assertTrue(all("observed_transition" not in view for view in eval_views))
            learner = HiddenRouteLearner(task).fit(train_views)
            program = ConsistentCodebookProgram(task).fit(train_views)
            tables = ShortcutImpactTables(task).fit(train_views)
            for view in eval_views:
                self.assertTrue(learner.predict_mask(view))
                self.assertTrue(program.predict_mask(view))
                self.assertTrue(tables.predict_masks(view)["source_union"]["predicted_write_nodes"])
                contaminated = copy.deepcopy(view)
                contaminated["gold"] = {"affected_nodes": []}
                with self.assertRaises(ValueError):
                    learner.predict_mask(contaminated)
                with self.assertRaises(ValueError):
                    program.predict_mask(contaminated)
                with self.assertRaises(ValueError):
                    tables.predict_masks(contaminated)

    def test_learners_reject_forbidden_training_inputs(self) -> None:
        task = V2_TASKS[0]
        episode = next(ep for ep in self.dataset if ep["task"] == task and ep["split"] == "train")
        clean = runtime_view(episode, training=True)
        contaminated = copy.deepcopy(clean)
        contaminated["gold"] = copy.deepcopy(episode["gold"])
        with self.assertRaises(ValueError):
            HiddenRouteLearner(task).fit([contaminated])
        with self.assertRaises(ValueError):
            ConsistentCodebookProgram(task).fit([contaminated])
        with self.assertRaises(ValueError):
            ShortcutImpactTables(task).fit([contaminated])
        missing = copy.deepcopy(clean)
        del missing["observed_transition"]
        with self.assertRaises(ValueError):
            HiddenRouteLearner(task).fit([missing])
        with self.assertRaises(ValueError):
            ConsistentCodebookProgram(task).fit([missing])

    def test_nonoracle_predictions_do_not_use_designer_codebooks(self) -> None:
        task = V2_TASKS[1]
        task_rows = [ep for ep in self.dataset if ep["task"] == task]
        train_views = [
            runtime_view(ep, training=True) for ep in task_rows if ep["split"] == "train"
        ]
        eval_view = runtime_view(
            next(ep for ep in task_rows if ep["split"] == "test"), training=False
        )
        with patch.dict(_DOMAIN, {}, clear=True):
            learner = HiddenRouteLearner(task).fit(train_views)
            program = ConsistentCodebookProgram(task).fit(train_views)
            tables = ShortcutImpactTables(task).fit(train_views)
            learned = learner.predict_mask(eval_view)
            programmed = program.predict_mask(eval_view)
            lookup = tables.predict_masks(eval_view)
            self.assertTrue(learned)
            self.assertEqual(programmed, learned)
            self.assertTrue(lookup["source_regime_table"]["predicted_write_nodes"])
            self.assertTrue(exact_kv_mask(eval_view))
            self.assertTrue(matched_retrieval_mask(eval_view, len(learned)))
            self.assertTrue(gold_free_program_mask(eval_view))

    def test_model_summaries_store_no_graphs_or_post_states(self) -> None:
        for task in V2_TASKS:
            train_views = [
                runtime_view(ep, training=True)
                for ep in self.dataset
                if ep["task"] == task and ep["split"] == "train"
            ]
            learner = HiddenRouteLearner(task).fit(train_views)
            program = ConsistentCodebookProgram(task).fit(train_views)
            tables = ShortcutImpactTables(task).fit(train_views)
            summaries = {
                "learner": learner.summary(),
                "program": program.summary(),
                "tables": tables.summary(),
            }
            serialized = json.dumps(summaries, sort_keys=True)
            for forbidden in (
                "post_state",
                "affected_nodes",
                "required_reads",
                "active_edges",
                "propagation_paths",
            ):
                self.assertNotIn(f'"{forbidden}":', serialized)
            for summary in summaries.values():
                self.assertEqual(summary["stored_graphs"], 0)
                self.assertEqual(summary["stored_post_states"], 0)

    def test_gold_mutation_cannot_change_nonoracle_masks(self) -> None:
        task = V2_TASKS[2]
        task_rows = [ep for ep in self.dataset if ep["task"] == task]
        train_views = [
            runtime_view(ep, training=True) for ep in task_rows if ep["split"] == "train"
        ]
        test_episode = next(ep for ep in task_rows if ep["split"] == "test")
        view = runtime_view(test_episode, training=False)
        learner = HiddenRouteLearner(task).fit(train_views)
        program = ConsistentCodebookProgram(task).fit(train_views)
        tables = ShortcutImpactTables(task).fit(train_views)

        def masks(runtime_record):
            learned = learner.predict_mask(runtime_record)
            return {
                "learned": learned,
                "consistent_program": program.predict_mask(runtime_record),
                "lookup": tables.predict_masks(runtime_record),
                "exact": exact_kv_mask(runtime_record),
                "matched": matched_retrieval_mask(runtime_record, len(learned)),
                "program": gold_free_program_mask(runtime_record),
            }

        baseline = masks(view)
        modified = copy.deepcopy(test_episode)
        modified["gold"]["graph"] = []
        modified["gold"]["active_edges"] = []
        modified["gold"]["required_reads"] = []
        changed_view = runtime_view(modified, training=False)
        self.assertEqual(view, changed_view)
        self.assertEqual(baseline, masks(changed_view))

    def test_fair_consistent_program_removes_learned_only_headroom(self) -> None:
        for task in V2_TASKS:
            task_rows = [ep for ep in self.dataset if ep["task"] == task]
            train_views = [
                runtime_view(ep, training=True)
                for ep in task_rows
                if ep["split"] == "train"
            ]
            test_views = [
                runtime_view(ep, training=False)
                for ep in task_rows
                if ep["split"] == "test"
            ]
            learner = HiddenRouteLearner(task).fit(train_views)
            program = ConsistentCodebookProgram(task).fit(train_views)
            self.assertEqual(program.candidate_configurations, 16)
            self.assertEqual(len(program.consistent_configurations), 1)
            self.assertEqual(
                [learner.predict_mask(view) for view in test_views],
                [program.predict_mask(view) for view in test_views],
            )

    def test_history_endpoint_records_enumerate_potential_graph(self) -> None:
        for episode in self.dataset:
            history_pairs = sorted(
                sorted((record["endpoint_a"], record["endpoint_b"]))
                for record in episode["history"]
                if record.get("kind") == "route_observation"
            )
            gold_pairs = sorted(
                sorted((edge["source"], edge["target"]))
                for edge in episode["gold"]["graph"]
            )
            self.assertEqual(history_pairs, gold_pairs)

    def test_fail_closed_partial_verdict_and_baseline_matrix(self) -> None:
        report = audit_dataset(self.dataset)
        self.assertEqual(set(report["domains"]), set(V2_TASKS))
        self.assertEqual(tuple(report["baselines"]), BASELINE_NAMES)
        self.assertFalse(report["admission"]["all_domains_pass"])
        self.assertEqual(report["admission"]["verdict"], "PARTIAL")
        self.assertTrue(report["admission"]["per_domain_microbenchmark_pass"])
        self.assertFalse(report["admission"]["correctness_necessity_supported"])
        self.assertFalse(report["admission"]["structurally_independent_domains"])
        self.assertEqual(
            set(report["access_boundary"]["baseline_training_access"]),
            set(BASELINE_NAMES) - {"oracle_graph"},
        )
        for domain in report["domains"].values():
            self.assertFalse(domain["admission"]["pass"])
            self.assertTrue(domain["microbenchmark"]["pass"])
            self.assertEqual(domain["verdict"], "PARTIAL")
            self.assertEqual(set(domain["baselines"]), set(BASELINE_NAMES))
            self.assertEqual(domain["baselines"]["learned_graph"]["exact_mask_rate"], 1.0)
            self.assertEqual(
                domain["baselines"]["consistent_codebook_program"]["exact_mask_rate"],
                1.0,
            )
            self.assertEqual(
                domain["baselines"]["consistent_codebook_program"],
                domain["baselines"]["learned_graph"],
            )
            self.assertEqual(domain["baselines"]["oracle_graph"]["exact_mask_rate"], 1.0)
            self.assertEqual(
                domain["baselines"]["gold_free_program"]["affected_recall"], 1.0
            )
            self.assertLess(
                domain["baselines"]["source_union"]["affected_f1"],
                domain["baselines"]["learned_graph"]["affected_f1"],
            )
            self.assertEqual(
                domain["diagnostics"]["history_potential_edge_exposure_rate"], 1.0
            )
            self.assertFalse(
                domain["admission"]["history_does_not_enumerate_potential_graph"]
            )
            self.assertFalse(
                domain["admission"]["consistent_codebook_program_leaves_headroom"]
            )
            self.assertTrue(
                domain["diagnostics"]["mask_only_task_solved_by_sufficient_superset"]
            )
            self.assertFalse(domain["admission"]["correctness_necessity_supported"])

    def test_structural_pseudoreplication_is_reported_as_failure(self) -> None:
        report = audit_dataset(self.dataset)
        structural = report["structural_replication_audit"]
        self.assertTrue(structural["all_domains_structurally_identical"])
        self.assertEqual(structural["unique_structural_fingerprints"], 1)
        self.assertEqual(
            structural["duplicate_domain_groups"], [sorted(V2_TASKS)]
        )
        self.assertFalse(structural["structurally_independent_domains"])
        self.assertFalse(structural["pass"])


if __name__ == "__main__":
    unittest.main()
