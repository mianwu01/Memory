from __future__ import annotations

import unittest

from causal_benchmarks.run_t1_suite import run_t1_suite


class T1SuiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_t1_suite(episodes=120, seed=17)

    def test_all_tasks_have_six_arm_reports_and_novel_splits(self):
        self.assertEqual(len(self.report["tasks"]), 4)
        self.assertTrue(self.report["all_novel_splits_pass"])
        for row in self.report["tasks"].values():
            self.assertLess(row["headline"]["efficiency_vs_full_fraction"], 1.0)

    def test_strong_domain_baselines_block_overclaim(self):
        self.assertEqual(self.report["tasks_beating_domain_solver"], [])
        self.assertEqual(self.report["tasks_supporting_causal_learning_claim"], [])


if __name__ == "__main__":
    unittest.main()
