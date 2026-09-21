"""Scientific interface tests; no API calls or benchmark reruns."""
import unittest
import json

import numpy as np

from .continuation_actor import fit_dependence, state_diagnostic, validation_arms
from .core import segments
from .domains import get_domain
from .generate import generate_split
from .llm import build_messages
from .continuation_recover import ordered_episode
from .structure_alignment import ordered_reads, digest


class ContinuationTests(unittest.TestCase):
    def test_saved_episode_recovers_exact_prompt_order(self):
        domain = get_domain("travel")
        ep = generate_split(domain, 2, "dev", 1)[0]
        saved = json.loads(json.dumps(ep.to_dict(), sort_keys=True))
        restored = ordered_episode(saved)
        reads = ordered_reads(ep, ep.S0.objects, [r["rid"] for r in ep.H])
        self.assertEqual(digest(build_messages(domain, ep, reads, "verbose")),
                         digest(build_messages(domain, restored, reads, "verbose")))

    def test_trial_lag_and_randomization_constraints(self):
        masks = np.random.default_rng(1729).integers(0, 2, (512, 4))
        fit = fit_dependence(masks, masks[:, 2])
        self.assertEqual(fit["threshold_parents"], [2])
        self.assertEqual(fit["ranking"][0], 2)
        graph = np.array(fit["graph"])
        self.assertFalse(np.any(graph[:, :4] != ""))

    def test_constant_outcome_has_no_identified_parents(self):
        masks = np.random.default_rng(42).integers(0, 2, (128, 3))
        fit = fit_dependence(masks, np.zeros(128))
        self.assertTrue(fit["outcome_constant"])
        self.assertEqual(fit["threshold_parents"], [])
        self.assertEqual(fit["ranking"], [0, 1, 2])

    def test_visible_context_budget_and_source_intervention(self):
        ep = generate_split(get_domain("travel"), 2, "dev", 1)[0]
        groups = [[r["rid"] for r in s] for s in segments(ep.H)]
        arms, changed = validation_arms(ep, groups, {"ranking": list(range(len(groups)))})
        k = len(arms["learned_top2"][0]["records"])
        for name, (reads, _) in arms.items():
            self.assertEqual(set(reads["objects"]), set(ep.S0.objects))
            if name.startswith(("wrong_", "random_")) or name.endswith("_matched"):
                self.assertEqual(len(reads["records"]), k)
        self.assertFalse(set(groups[0]) & set(arms["source_blocked"][0]["records"]))
        self.assertEqual(ep.A, changed.A)
        self.assertEqual(ep.S0.canonical(), changed.S0.canonical())
        self.assertTrue(all(a == b for a, b in zip(ep.H, changed.H) if a["rid"] not in groups[0]))
        empty = arms["query_only"][0]
        messages = build_messages(get_domain("travel"), ep, empty, "verbose")
        history = messages[1]["content"].split("### HISTORY", 1)[1].split("### CURRENT STATE", 1)[0]
        self.assertIn("[]", history)
        self.assertNotIn('"rid"', history)
        diagnostic = state_diagnostic(ep)
        self.assertEqual(diagnostic["n_boundaries"], len(groups)+1)


if __name__ == "__main__":
    unittest.main()
