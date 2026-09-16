import threading
import unittest

from faithful_suite import dispatch_cases


class CampaignFailure(unittest.TestCase):
    def test_failure_stops_new_calls_without_discarding_inflight_work(self):
        started = []
        peers_started = threading.Barrier(2)

        def run(case):
            arm, ident = case
            started.append(arm)
            peers_started.wait(timeout=5)
            return {"arm": arm, "id": ident, "exit_code": 1}

        rows = dispatch_cases([("failed", 101), ("inflight", 101), ("unstarted", 101)], run, 2)
        self.assertCountEqual(started, ["failed", "inflight"])
        self.assertEqual([r["exit_code"] for r in rows], [1, 1, None])
        self.assertEqual(rows[-1]["state"], "not_started_after_failure")

    def test_complete_run_preserves_registered_order_and_scope(self):
        cases = [(arm, i) for i in (111, 112) for arm in ("ours", "mem0")]
        rows = dispatch_cases(cases, lambda c: {"arm": c[0], "id": c[1], "exit_code": 0}, 2)
        self.assertEqual([(r["arm"], r["id"]) for r in rows], cases)
        self.assertTrue(all(r["exit_code"] == 0 for r in rows))


if __name__ == "__main__":
    unittest.main()
