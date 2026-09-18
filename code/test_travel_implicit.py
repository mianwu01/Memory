"""Protocol tests: transformations cannot create gold or future-write shortcuts."""
import copy
import json
import types
import unittest

from t0_travel import parse_episode
from travel_implicit import (
    HistoryNotes, audit_rows, extract_notices, install_variant,
    strip_future_notices, training_rows, transform_row,
)


def example():
    return {
        "id": 901,
        "base_person": {"name": "Alice", "query": "Plan my trip.",
                        "daily_plans": [{"days": 1, "lunch": "Base restaurant"}]},
        "questions": [
            "I am Bob.\nI'm traveling with Alice.\nOn the first day, I want lunch cheaper than Alice's first-day lunch.\nI like museums.",
            "I am Carol.\nI'm joining Alice and Bob.\nOn the first day, I want dinner at the same restaurant as Bob's first-day lunch.\nPlease retain the original transportation.",
        ],
        "answers": [[{"days": 1, "lunch": "Secret Bob gold"}], [{"days": 1, "dinner": "Secret Carol gold"}]],
    }


class TravelImplicitTests(unittest.TestCase):
    def test_gold_and_non_dependencies_unchanged(self):
        original = example()
        snapshot = copy.deepcopy(original)
        transformed = transform_row(original)
        self.assertEqual(original, snapshot)
        self.assertEqual(transformed["answers"], original["answers"])
        self.assertEqual(transformed["base_person"]["daily_plans"], original["base_person"]["daily_plans"])
        self.assertIn("I like museums.", transformed["questions"][0])
        self.assertIn("Please retain the original transportation.", transformed["questions"][1])
        for query in transformed["questions"]:
            self.assertNotIn("Secret", query)
        self.assertTrue(audit_rows([original], [transformed])["passed"])

    def test_history_notice_requires_host_write(self):
        transformed = transform_row(example())
        notes = HistoryNotes()
        self.assertEqual(notes.resolve(transformed["questions"][0]).notices, ())
        notes.add_chunk(json.dumps({"name": "Alice", "query": transformed["base_person"]["query"]}))
        bob = notes.resolve(transformed["questions"][0])
        self.assertEqual(len(bob.notices), 1)
        self.assertIn("Alice's first-day lunch", bob.memory_text)
        self.assertEqual(notes.resolve(transformed["questions"][1]).notices, ())
        clean = json.loads(notes.add_chunk(json.dumps({"name": "Bob", "query": transformed["questions"][0]})))
        self.assertEqual(extract_notices(clean["query"]), [])
        carol = notes.resolve(transformed["questions"][1])
        self.assertIn("Bob's first-day lunch", carol.memory_text)
        self.assertEqual(carol.notices[0]["write_round"], 1)

    def test_explicit_pair_receives_identical_announcements(self):
        row = example()
        implicit, explicit = transform_row(row), transform_row(row, "explicit")
        self.assertEqual(implicit["base_person"], explicit["base_person"])
        for left, right, original in zip(implicit["questions"], explicit["questions"], row["questions"]):
            self.assertEqual(extract_notices(left), extract_notices(right))
            self.assertEqual(strip_future_notices(right), original)

    def test_training_view_reconstructs_original_constraint_targets(self):
        row = example()
        original = parse_episode(row)
        resolved = parse_episode(training_rows([row])[0])
        def deps(ep):
            return [[(s["text"], s["src_cell"], s["tgt_cell"]) for s in r["sentences"] if s["is_dep"]]
                    for r in ep["rounds"]]
        self.assertEqual(deps(original), deps(resolved))

    def test_install_wraps_real_actor_observations(self):
        row = example()
        converted = {**row, "questions": [{"round_idx": i, "name": name, "query": q}
                      for i, (name, q) in enumerate(zip(["Bob", "Carol"], row["questions"]), 1)]}
        # Match TravelPlannerEnvironment.reset exactly: group_id, not id.
        observation = {"group_id": converted["id"], "step": 0,
                       **{k: v for k, v in converted.items() if k != "id"}}
        class Client:
            def reset(self, seed=None):
                return copy.deepcopy(observation)
        runner = types.SimpleNamespace(EnvironmentClient=Client, load_travel_data=lambda: [converted])
        install_variant(runner, "implicit")
        loaded = runner.load_travel_data()[0]
        observed = runner.EnvironmentClient().reset(seed=901)
        self.assertEqual(loaded["questions"], observed["questions"])
        self.assertEqual(loaded["base_person"], observed["base_person"])
        self.assertEqual(loaded["answers"], observed["answers"])
        self.assertEqual(set(observed), set(observation))
        self.assertEqual(observed["group_id"], 901)
        self.assertEqual(observed["questions"][0]["round_idx"], 1)
        self.assertNotEqual(observed["questions"][0]["query"], row["questions"][0])

    def test_double_transformation_fails(self):
        with self.assertRaises(ValueError):
            transform_row(transform_row(example()))


if __name__ == "__main__":
    unittest.main()
