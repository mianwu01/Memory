"""Stream fragmentation must not change plans, tools or billed usage."""
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
import httpx
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from openai.types.chat import ChatCompletionChunk
from relay_chat_transport import accumulate_chunks, install_stream_transport


def chunk(delta=None, finish=None, usage=None):
    return ChatCompletionChunk.model_validate({
        "id": "test", "created": 1, "model": "test-model", "object": "chat.completion.chunk",
        "choices": [] if delta is None and finish is None else [
            {"index": 0, "delta": delta or {}, "finish_reason": finish}], "usage": usage})


USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
         "prompt_tokens_details": {"cached_tokens": 60}}


class StreamTests(unittest.TestCase):
    def test_pre_header_timeout_recovers_with_unknown_billing_record(self):
        error = APITimeoutError(request=httpx.Request("POST", "https://example.test/v1/chat/completions"))
        original = Mock(side_effect=[error, nullcontext([
            chunk({"content": "OK"}, "stop"), chunk(usage=USAGE)])])
        client = SimpleNamespace(base_url="https://example.test/v1", chat=SimpleNamespace(
            completions=SimpleNamespace(create=original)))
        install_stream_transport(client)
        with patch("relay_chat_transport.wait_for_route_slot"), patch("relay_chat_transport.time.sleep") as sleep:
            response = client.chat.completions.create(model="test-model", messages=[], max_tokens=37)
        self.assertEqual(original.call_count, 2)
        self.assertEqual(original.call_args.kwargs["max_tokens"], 37)
        self.assertEqual(client.timeout.read, 180)
        sleep.assert_called_once_with(15)
        failed = response._transport_metrics["attempts"][0]
        self.assertFalse(failed["stream_opened"])
        self.assertTrue(failed["billing_unknown"])
        self.assertEqual(failed["error_type"], "APITimeoutError")

    def test_pre_header_connection_errors_exhaust_a_finite_budget(self):
        error = APIConnectionError(request=httpx.Request("POST", "https://example.test/v1/chat/completions"))
        original = Mock(side_effect=error)
        client = SimpleNamespace(base_url="https://example.test/v1", chat=SimpleNamespace(
            completions=SimpleNamespace(create=original)))
        install_stream_transport(client)
        with patch("relay_chat_transport.wait_for_route_slot"), patch("relay_chat_transport.time.sleep") as sleep:
            with self.assertRaises(APIConnectionError) as raised:
                client.chat.completions.create(model="test-model", messages=[])
        self.assertEqual(original.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [15, 30, 60])
        self.assertEqual(len(raised.exception.transport_attempts), 4)

    def test_timeout_in_an_opened_stream_is_not_retried(self):
        error = APITimeoutError(request=httpx.Request("POST", "https://example.test/v1/chat/completions"))
        def interrupted():
            yield chunk({"content": "partial"})
            raise error
        original = Mock(return_value=nullcontext(interrupted()))
        client = SimpleNamespace(base_url="https://example.test/v1", chat=SimpleNamespace(
            completions=SimpleNamespace(create=original)))
        install_stream_transport(client)
        with patch("relay_chat_transport.wait_for_route_slot"), self.assertRaises(APITimeoutError):
            client.chat.completions.create(model="test-model", messages=[])
        self.assertEqual(original.call_count, 1)
        self.assertTrue(error.transport_attempts[0]["stream_opened"])

    def test_busy_service_retried_before_stream_opens(self):
        error = InternalServerError("busy", response=httpx.Response(503,
            request=httpx.Request("POST", "https://example.test/v1/chat/completions")),
            body={"code": "SERVICE_BUSY"})
        original = Mock(side_effect=[error, nullcontext([
            chunk({"content": "OK"}, "stop"), chunk(usage=USAGE)])])
        client = SimpleNamespace(base_url="https://example.test/v1", chat=SimpleNamespace(
            completions=SimpleNamespace(create=original)))
        install_stream_transport(client)
        with patch("relay_chat_transport.wait_for_route_slot"), patch("relay_chat_transport.time.sleep"):
            response = client.chat.completions.create(model="test-model", messages=[])
        self.assertEqual(original.call_count, 2)
        self.assertEqual(response._transport_metrics["attempts"][0]["status_code"], 503)

    def test_rate_rejection_retried_but_partial_stream_not_repeated(self):
        error = RateLimitError("rate limited", response=httpx.Response(429,
            request=httpx.Request("POST", "https://example.test/v1/chat/completions")),
            body={"code": "rate_limit_exceeded"})
        original = Mock(side_effect=[error, nullcontext([
            chunk({"content": "OK"}, "stop"), chunk(usage=USAGE)])])
        client = SimpleNamespace(base_url="https://example.test/v1", chat=SimpleNamespace(
            completions=SimpleNamespace(create=original)))
        install_stream_transport(client)
        with patch("relay_chat_transport.wait_for_route_slot"), patch("relay_chat_transport.time.sleep") as sleep:
            response = client.chat.completions.create(model="test-model", max_tokens=37,
                messages=[{"role": "user", "content": "test"}])
        self.assertEqual(original.call_count, 2)
        sleep.assert_called_once_with(15)
        self.assertEqual(original.call_args.kwargs["max_tokens"], 37)
        self.assertEqual(response._transport_metrics["attempts"][0]["status_code"], 429)
        original.reset_mock(side_effect=True)
        original.return_value = nullcontext([chunk({"content": "partial"})])
        with patch("relay_chat_transport.wait_for_route_slot"), self.assertRaises(RuntimeError):
            client.chat.completions.create(model="test-model", messages=[])
        self.assertEqual(original.call_count, 1)

    def test_interleaved_tools_reasoning_and_trailing_usage(self):
        response = accumulate_chunks([
            chunk({"reasoning_content": "look ", "content": ""}),
            chunk({"reasoning_content": "up", "tool_calls": [
                {"index": 0, "id": "call-a", "type": "function", "function": {"name": "lookup", "arguments": '{"city":'}},
                {"index": 1, "id": "call-b", "type": "function", "function": {"name": "lookup", "arguments": '{"city":'}}]}),
            chunk({"tool_calls": [
                {"index": 1, "function": {"arguments": '"Paris"}'}},
                {"index": 0, "function": {"arguments": '"Shanghai"}'}}]}, "tool_calls"),
            chunk(usage=USAGE)])
        message = response.choices[0].message
        self.assertEqual(message.reasoning_content, "look up")
        self.assertEqual([t.id for t in message.tool_calls], ["call-a", "call-b"])
        self.assertEqual(message.tool_calls[0].function.arguments, '{"city":"Shanghai"}')
        self.assertEqual(message.tool_calls[1].function.arguments, '{"city":"Paris"}')
        self.assertEqual(response.usage.prompt_tokens_details.cached_tokens, 60)

    def test_length_preserved_for_existing_repair_policy(self):
        response = accumulate_chunks([chunk({"content": "partial"}, "length"), chunk(usage=USAGE)])
        self.assertEqual(response.choices[0].finish_reason, "length")
        self.assertEqual(response.choices[0].message.content, "partial")

    def test_incomplete_stream_is_never_a_completed_plan(self):
        for events in ([chunk({"content": "looks complete"}), chunk(usage=USAGE)],
                       [chunk({"content": "done"}, "stop")], []):
            with self.assertRaises(RuntimeError):
                accumulate_chunks(events)


if __name__ == "__main__":
    unittest.main()
