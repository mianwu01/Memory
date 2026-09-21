"""Scientific-protocol invariants for the alignment diagnostics."""
import copy
import unittest

import tiktoken

from .domains import get_domain
from .generate import generate_split
from .reader_repair import component_precedent_records
from .structure_alignment import matched_records, permutations, response_precedent_records
from .tcd_logs import TCDSelect, type_vocab


class AlignmentInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.domain = get_domain("travel")
        cls.ep = generate_split(cls.domain, 3, "dev", 1)[0]
        types = type_vocab([cls.ep])
        cls.selector = TCDSelect("parser", lag_aware=True)
        cls.selector.adj = {(a, b): 1 for a in types for b in types if a != b}
        cls.reference = cls.selector.select(cls.domain, cls.ep)

    def test_retrieval_does_not_access_gold(self):
        # Deleting every privileged evaluator field must not change retrieval.
        blind = copy.deepcopy(self.ep)
        for name in ("A", "S1", "R", "params", "required_reads", "relevant_params"):
            if hasattr(blind, name):
                setattr(blind, name, None)
        for select in (response_precedent_records, component_precedent_records):
            expected = select(self.domain, self.ep, self.reference["objects"])
            self.assertEqual(expected, select(self.domain, blind, self.reference["objects"]))

    def test_matched_control_preserves_context_and_count(self):
        reads, stats = matched_records(self.ep, self.reference, [], 17, tiktoken.get_encoding("cl100k_base"))
        self.assertEqual(reads["objects"], self.reference["objects"])
        self.assertEqual(len(reads["records"]), len(self.reference["records"]))
        self.assertEqual(len(set(reads["records"])), len(reads["records"]))
        self.assertEqual(stats["token_residual"], stats["history_proxy_tokens"] - stats["target_history_proxy_tokens"])

    def test_permutations_are_distinct_bijections(self):
        for types in (["a", "b", "c"], ["a", "b", "c", "d", "e", "f"]):
            maps = permutations(types)
            self.assertEqual(len({tuple(p[t] for t in types) for p in maps.values()}), 3)
            for p in maps.values():
                self.assertEqual(set(p.values()), set(types))
                self.assertNotEqual([p[t] for t in types], types)

    def test_actor_context_contains_record_referents(self):
        from .alignment_actor import close_referents
        closed = close_referents(self.ep, self.reference)
        selected = set(closed["records"])
        referents = {r["object_id"] for r in self.ep.H if r["rid"] in selected}
        self.assertTrue(referents.issubset(closed["objects"]))
        eligible = [r["rid"] for r in self.ep.H if r["object_id"] in closed["objects"]]
        reads, _ = matched_records(self.ep, closed, [], 17, tiktoken.get_encoding("cl100k_base"), eligible)
        self.assertTrue(set(reads["records"]).issubset(eligible))
        self.assertEqual(reads["objects"], closed["objects"])

    def test_existing_runner_adapter_matches_evaluated_rule(self):
        from .alignment_actor import close_referents
        from .llm import Selector
        from .reader_repair import ComponentKeySelect
        learner = ComponentKeySelect()
        learner.fit(self.domain, [self.ep])
        reads = learner.select(self.domain, self.ep)
        self.assertEqual(reads["records"], component_precedent_records(self.domain, self.ep, reads["objects"]))
        selected = Selector(self.domain, [self.ep]).select(self.domain, self.ep, "component_key2")
        self.assertEqual(selected, close_referents(self.ep, reads))

    def test_read_gate_panel_has_the_declared_temporal_direction(self):
        from .read_gate_tcd import panel
        X, masks, outcomes = panel(lambda chosen: "a" in chosen and "c" in chosen,
                                   ["a", "b", "c"], 32, 11)
        self.assertTrue((X[1:, -1] == masks[:-1, 0]*masks[:-1, 2]).all())
        self.assertTrue((X[:, :-1] == masks).all())
        self.assertTrue((outcomes == masks[:, 0]*masks[:, 2]).all())

    def test_official_runner_restores_working_directory_after_failure(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from .uncle_read_gate import working_directory
        original = Path.cwd()
        with TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                with working_directory(directory):
                    self.assertEqual(Path.cwd(), Path(directory))
                    raise RuntimeError("test cleanup")
        self.assertEqual(Path.cwd(), original)


if __name__ == "__main__":
    unittest.main()
