"""Failure classification must not silently convert infrastructure errors to scores."""
import unittest

from autodl_completion_report import classify_failure


class FailureClassificationTests(unittest.TestCase):
    def test_memory_length_is_distinct_from_allowed_actor_length(self):
        memory = dict(event="llm", phase="memory_write", choices=[dict(finish_reason="length")])
        actor = {**memory, "phase": "actor"}
        self.assertEqual(classify_failure({}, [memory])["category"], "model_length")
        self.assertEqual(classify_failure({}, [actor])["category"], "unknown")

    def test_network_failure_is_never_model_failure(self):
        row = dict(event="api_error", error_type="RateLimitError", status_code=429)
        self.assertEqual(classify_failure({"error_type": "InvalidExecution"}, [row])["category"], "transport_or_api")

    def test_two_causes_remain_mixed(self):
        rows = [dict(event="api_error", error_type="APITimeoutError"),
                dict(event="llm", phase="memory_write", choices=[dict(finish_reason="length")])]
        result = classify_failure({}, rows)
        self.assertEqual(result["category"], "mixed")
        self.assertEqual(result["evidenced_categories"], ["model_length", "transport_or_api"])

    def test_generic_fallback_is_not_assigned_to_model(self):
        self.assertEqual(classify_failure({"error_type": "InvalidExecution",
            "failures": ["Upstream reported a processing error or fallback"]}, [])["category"], "unknown")

    def test_explicit_parser_failure_is_separate_from_environment(self):
        self.assertEqual(classify_failure({"failures": ["A-Mem metadata heuristic fallback"]}, [])["category"], "model_format")
        self.assertEqual(classify_failure({"error_type": "KeyError"}, [])["category"], "environment_or_implementation")


if __name__ == "__main__":
    unittest.main()
