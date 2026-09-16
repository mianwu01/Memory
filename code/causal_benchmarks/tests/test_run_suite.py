from __future__ import annotations

import unittest

from causal_benchmarks.run_suite import TASK_MODULES, run_suite


class RedesignSuiteTest(unittest.TestCase):
    def test_all_tasks_share_schema_and_pass_admission(self):
        report = run_suite(episodes=60, seed=23)
        self.assertEqual(set(report["tasks"]), set(TASK_MODULES))
        self.assertTrue(report["all_schema_valid"])
        self.assertTrue(report["all_admission_pass"])
        for row in report["tasks"].values():
            self.assertEqual(row["episodes"], 60)
            self.assertEqual(row["headline"]["query_downstream_leakage"], 0.0)
            self.assertLess(row["headline"]["exact_key_affected_recall"], 0.95)
            self.assertEqual(row["headline"]["oracle_affected_recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
