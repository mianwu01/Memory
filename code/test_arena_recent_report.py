import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena_recent_report import audit_family, metered_usage
from arena_recent_budget import billable_family_paths


class ReportTests(unittest.TestCase):
    def test_copied_completed_view_is_not_billed_twice(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = ['p2_recent_baselines_tokenrhythm_v5',
                     'p2_recent_baselines_tokenrhythm_v5_summary_recovery_1',
                     'p2_recent_baselines_tokenrhythm_v5_completed']
            for name in names:
                base = root / 'results/real' / name
                base.mkdir(parents=True)
                (base / 'protocol.json').write_text('{}')
            (root / 'results/real' / names[-1] / 'result_view_manifest.json').write_text('{}')
            self.assertEqual({p.name for p in billable_family_paths(root)}, set(names[:2]))

    def test_unknown_billing_attempts_survive_recovery_and_final_failure(self):
        retry = {"status_code": None, "error_type": "APITimeoutError", "stream_opened": False}
        total = metered_usage([
            {"usage": {"prompt_tokens": 100, "completion_tokens": 20},
             "transport_metrics": {"attempts": [retry, {"status_code": 200}]}},
            {"event": "llm_error", "transport_attempts": [retry]},
        ])
        self.assertEqual(total["responses_with_usage"], 1)
        self.assertEqual(total["transport_failures_without_usage"], 2)
        self.assertEqual(total["pre_stream_connection_failures"], 2)
        self.assertAlmostEqual(total["estimated_cny"], 0.00036)

    def test_cached_input_is_not_charged_twice(self):
        total = metered_usage([{"usage": {"prompt_tokens": 1000000,
            "completion_tokens": 100000, "prompt_tokens_details": {"cached_tokens": 750000}},
            "duration_seconds": 1}])
        self.assertAlmostEqual(total["estimated_cny"], 0.5 + 0.03 + 0.8)
        self.assertEqual(total["input_tokens"], 1000000)

    def test_missing_arms_prevent_paired_completion(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "protocol.json").write_text(json.dumps({"phase": "development",
                "episode_ids": [101], "endpoint": "https://tokenrhythm.studio/v1", "model": "deepseek-flash"}))
            report = audit_family(path)
            self.assertFalse(report["paired_scope_complete"])
            self.assertEqual(len(report["arms"]), 10)
            self.assertTrue(all(not arm["complete"] for arm in report["arms"].values()))


if __name__ == "__main__":
    unittest.main()
