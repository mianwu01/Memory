"""Separate a missing returned response from request preparation/parser errors."""
import unittest
import hashlib
import json
from pathlib import Path
import tempfile

from autodl_usage_coverage import collect, failed_transport_receipts, unlogged_returned_response


TRACE = '''Traceback (most recent call last):
  File "/workspace/code/faithful_memory.py", line 146, in measured
    reasoning_history.remember(choice.message)
  File "/workspace/code/faithful_transport.py", line 73, in remember
    key = self.signature(calls)
  File "/workspace/code/faithful_transport.py", line 63, in signature
    arguments = json.loads(arguments)
  File "/usr/lib/python3.10/json/decoder.py", line 353, in raw_decode
    obj, end = self.scan_once(s, idx)
json.decoder.JSONDecodeError: Expecting ',' delimiter: line 1 column 48 (char 47)
'''


class UsageCoverageTests(unittest.TestCase):
    def test_post_response_gap_is_recognized(self):
        self.assertTrue(unlogged_returned_response(TRACE))

    def test_request_preparation_failure_does_not_imply_a_returned_response(self):
        trace = TRACE.replace('reasoning_history.remember(choice.message)',
                              'reasoning_history.prepare(kwargs["messages"])').replace('in remember', 'in prepare')
        self.assertFalse(unlogged_returned_response(trace))

    def test_downstream_native_parser_failure_does_not_imply_missing_usage(self):
        trace = TRACE.replace('faithful_memory.py', 'openai_client.py').replace('in measured', 'in chat_with_tools')
        self.assertFalse(unlogged_returned_response(trace))

    def test_transport_and_unrelated_json_errors_are_not_counted(self):
        self.assertFalse(unlogged_returned_response('RuntimeError: incomplete stream: missing finish reason or usage'))
        self.assertFalse(unlogged_returned_response('json.decoder.JSONDecodeError: malformed JSON'))

    def test_retried_errors_are_counted_without_counting_success(self):
        rows = [dict(status_code=429, error_type="RateLimitError"), dict(status_code=200)]
        self.assertEqual(failed_transport_receipts(dict(event="llm", transport=dict(attempts=rows))), rows[:1])
        self.assertEqual(failed_transport_receipts(dict(event="api_error", attempts=rows[:1])), rows[:1])

    def test_all_attempts_preserved_without_guessing_unlogged_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "frozen_source/code"
            source.mkdir(parents=True)
            (source / "faithful_memory.py").write_text('result = create(*args, **kwargs)\nreasoning_history.remember(choice.message)\nruntime.event("llm", model=result.model\n')
            (source / "faithful_transport.py").write_text("frozen transport fixture\n")
            hashes = {"code/" + p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
            key = "implicit/mem0/120/r0"
            (base / "protocol.json").write_text(json.dumps(dict(source_hashes=hashes, cases=[dict(key=key)])))
            for n, rows in enumerate([
                [dict(event="api_error", attempts=[dict(status_code=429, error_type="RateLimitError")])],
                [dict(event="llm", usage=dict(prompt_tokens=10, completion_tokens=2),
                      transport=dict(attempts=[dict(status_code=429, error_type="RateLimitError"), dict(status_code=200)]))],
            ]):
                attempt = base / "cases" / key / f"attempt_{n}"
                attempt.mkdir(parents=True)
                (attempt / "events.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
            (attempt / "error_traceback.txt").write_text(TRACE)
            report = collect(base)
            self.assertEqual(report["failed_transport_attempt_receipts"], 2)
            self.assertEqual(report["api_error_events_with_unknown_usage"], 1)
            self.assertEqual(report["minimum_unlogged_returned_responses"], 1)
            self.assertEqual(report["recorded_llm_responses"], 1)
            self.assertEqual(report["recorded_input_tokens"], 10)
            self.assertEqual(report["recorded_output_tokens"], 2)
            self.assertIsNone(report["affected_attempts"][0]["usage"])
            self.assertIsNone(report["monetary_cost"])
            (source / "faithful_memory.py").write_text("modified generation source")
            with self.assertRaisesRegex(ValueError, "differs from protocol"):
                collect(base)


if __name__ == "__main__":
    unittest.main()
