from __future__ import annotations

import unittest

from yujia_story_audit import build_audit


class YujiaStoryAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_audit()

    def test_negative_results_block_full_story_overclaim(self):
        story = self.report["storyline"]
        self.assertEqual(
            story["simulation_must_do"]["status"],
            "PASS_OBSERVED_WITH_LATENT_BOUNDARY",
        )
        self.assertEqual(
            story["effectiveness_efficiency"]["tasks_beating_strong_domain_solver"],
            [],
        )
        self.assertEqual(story["actionable_safety"]["status"], "FAIL")
        self.assertFalse(story["full_two_selling_point_story_supported"])

    def test_formulation_and_external_signoff_boundary(self):
        self.assertEqual(len(self.report["four_task_t1"]), 4)
        self.assertIn("dynamic_travel", self.report["formulations"])
        self.assertEqual(
            self.report["requirements_from_8_15"]["double_check_with_yujia"],
            "PENDING_EXTERNAL_CONFIRMATION",
        )


if __name__ == "__main__":
    unittest.main()
