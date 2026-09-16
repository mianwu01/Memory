import unittest

from faithful_report import probe_rows, usage


def row(endpoint, *, billed=None, pending=None):
    return {"event": "llm", "phase": "actor", "endpoint": endpoint,
            "usage": {"prompt_tokens": 1000, "completion_tokens": 100,
                      "prompt_tokens_details": {"cached_tokens": 400}},
            "choices": [{"finish_reason": "length"}],
            "provider_cost_cny": billed, "billing_pending": pending}


class CostAccounting(unittest.TestCase):
    def test_access_probe_counts_failed_generation_but_not_model_listing(self):
        probe = {"requests": [
            {"method": "GET", "path": "/models", "status": 403, "body": "{}"},
            {"method": "POST", "path": "/chat/completions", "status": 403,
             "body": '{"code":"INSUFFICIENT_BALANCE"}'}]}
        rows = list(probe_rows(probe))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][1]["status_code"], 403)
        self.assertNotIn("usage", rows[0][1]["response"])

    def test_known_tariff_counts_cached_input_and_failed_actor_output(self):
        u = usage([row("https://tokenrhythm.studio/v1")])
        self.assertAlmostEqual(u["estimated_cny"], 0.002016)
        self.assertEqual(u["length_responses"], 1)
        self.assertEqual(u["output_tokens"], 100)

    def test_provider_reported_charge_takes_precedence_without_cross_provider_tariff(self):
        u = usage([row("https://aiaaa.cc/v1", billed="0.013", pending=False)])
        self.assertEqual(u["estimated_cny"], 0.013)
        self.assertEqual(u["provider_reported_cny"], 0.013)
        self.assertEqual(u["unpriced_calls"], 0)
        unknown = usage([row("https://aiaaa.cc/v1", billed="0.013", pending=True)])
        self.assertEqual(unknown["unpriced_calls"], 1)
        self.assertEqual(unknown["estimated_cny"], 0)


if __name__ == "__main__":
    unittest.main()
