import copy
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
import httpx
from openai import APIError

from faithful_transport import ReasoningHistory, install_faithful_stream_transport
from test_relay_chat_transport import chunk, USAGE


class ExplicitStreamRecovery(unittest.TestCase):
    def test_identical_request_retried_without_splicing_partial_output(self):
        error = APIError("relay stream failure", request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
                         body={"code": "upstream_stream_read_error"})
        def interrupted():
            yield chunk({"content": "NEVER SPLICE THIS"})
            raise error
        original = Mock(side_effect=[nullcontext(interrupted()), nullcontext([
            chunk({"content": "COMPLETE"}, "stop"), chunk(usage=USAGE)])])
        client = SimpleNamespace(base_url="https://example.test/v1", chat=SimpleNamespace(completions=SimpleNamespace(create=original)))
        install_faithful_stream_transport(client)
        with patch("relay_chat_transport.wait_for_route_slot"), patch("faithful_transport.time.sleep"):
            result = client.chat.completions.create(model="test-model", messages=[{"role": "user", "content": "original"}], max_tokens=37)
        self.assertEqual(original.call_args_list[0], original.call_args_list[1])
        self.assertEqual(result.choices[0].message.content, "COMPLETE")
        self.assertTrue(result._transport_metrics["attempts"][0]["billing_unknown"])

    def test_missing_usage_is_not_eligible_for_repeated_generation(self):
        original = Mock(return_value=nullcontext([chunk({"content": "partial"})]))
        client = SimpleNamespace(base_url="https://example.test/v1", chat=SimpleNamespace(completions=SimpleNamespace(create=original)))
        install_faithful_stream_transport(client)
        with patch("relay_chat_transport.wait_for_route_slot"), self.assertRaises(RuntimeError):
            client.chat.completions.create(model="test-model", messages=[])
        self.assertEqual(original.call_count, 1)


class ReasoningProtocolTests(unittest.TestCase):
    def setUp(self):
        self.call = {"id": "call-a", "type": "function", "function": {
            "name": "RestaurantSearch", "arguments": '{"city":"Oslo","limit":3}'}}

    def test_restores_observed_field_without_changing_task_history(self):
        cache = ReasoningHistory()
        cache.remember({"tool_calls": [self.call], "reasoning_content": "observed provider field"})
        formatted = copy.deepcopy(self.call)
        formatted["function"]["arguments"] = '{"limit": 3, "city": "Oslo"}'
        messages = [{"role": "system", "content": "original prompt"},
                    {"role": "assistant", "content": None, "tool_calls": [formatted]},
                    {"role": "tool", "tool_call_id": "call-a", "content": "original result"}]
        before = copy.deepcopy(messages)
        prepared = cache.prepare(messages)
        self.assertEqual(messages, before)
        self.assertEqual(prepared[1].pop("reasoning_content"), "observed provider field")
        self.assertEqual(prepared, before)

    def test_refuses_invented_history(self):
        with self.assertRaisesRegex(ValueError, "not observed"):
            ReasoningHistory().prepare([{"role": "assistant", "tool_calls": [self.call]}])

    def test_missing_provider_field_is_observed_empty_non_thinking_response(self):
        cache = ReasoningHistory()
        cache.remember({"tool_calls": [self.call], "content": None})
        result = cache.prepare([{"role": "assistant", "tool_calls": [self.call]}])
        self.assertEqual(result[0]["reasoning_content"], "")

    def test_rejects_changed_or_ambiguous_history(self):
        cache = ReasoningHistory()
        cache.remember({"tool_calls": [self.call], "reasoning_content": "actual"})
        with self.assertRaises(ValueError):
            cache.prepare([{"role": "assistant", "tool_calls": [self.call], "reasoning_content": "invented"}])
        with self.assertRaises(ValueError):
            cache.remember({"tool_calls": [self.call], "reasoning_content": "different"})


if __name__ == "__main__":
    unittest.main()
