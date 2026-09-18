import unittest
from autodl_transport_recovery import reason_for_recovery


class RecoveryEligibility(unittest.TestCase):
    def test_wrapped_broken_stream_requires_api_receipt_and_exact_trace(self):
        rows = [dict(event="api_error", error_type="RuntimeError", status_code=None)]
        trace = "RuntimeError: incomplete stream: missing finish reason or usage"
        self.assertEqual(reason_for_recovery(rows, trace), "incomplete_stream_missing_finish_or_usage")
        self.assertIsNone(reason_for_recovery([], trace))
        self.assertIsNone(reason_for_recovery(rows, "ValueError: JSON parse failed"))
        stream_rows = [dict(event="api_error", error_type="RuntimeError", status_code=None,
                            attempts=[dict(stream_opened=True)])]
        self.assertEqual(reason_for_recovery(stream_rows, ""),
                         "stream_reconstruction_runtime_error_message_unavailable")
        self.assertIsNone(reason_for_recovery(rows + [dict(event="llm")], trace))
        self.assertIsNone(reason_for_recovery(
            rows + [dict(event="invalid", reason="Truncated memory completion")], trace))

    def test_auth_semantic_and_generic_runtime_errors_never_retry(self):
        for code in (400, 401, 402, 403):
            self.assertIsNone(reason_for_recovery(
                [dict(event="api_error", status_code=code, error_type="APIStatusError")], ""))
        for code in (429, 500, 503):
            self.assertEqual(reason_for_recovery(
                [dict(event="api_error", status_code=code)], ""), f"http_{code}")
        self.assertEqual(reason_for_recovery(
            [dict(event="api_error", status_code=None, error_type="RemoteProtocolError")], ""),
            "RemoteProtocolError")


if __name__ == "__main__":
    unittest.main()
