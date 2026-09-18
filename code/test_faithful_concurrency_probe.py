import unittest
from unittest import mock

import faithful_concurrency_probe as probe


class FakeUsage:
    def model_dump(self):
        return {"prompt_tokens": 10, "completion_tokens": 240, "completion_tokens_details": {}}


class FakeDelta:
    def __init__(self, content=None, reasoning_content=None):
        self.content = content
        self.reasoning_content = reasoning_content
        self.reasoning = None


class FakeChoice:
    def __init__(self, content=None, finish_reason=None, reasoning_content=None):
        self.delta = FakeDelta(content, reasoning_content)
        self.finish_reason = finish_reason


class FakeChunk:
    def __init__(self, content=None, finish_reason=None, usage=None, reasoning_content=None):
        self.choices = [FakeChoice(content, finish_reason, reasoning_content)] if content or finish_reason or reasoning_content else []
        self.usage = usage

    def model_dump(self, exclude_none=True):
        return {}


class FakeCompletions:
    def __init__(self, chunks):
        self.chunks = chunks

    def create(self, **kwargs):
        return iter(self.chunks)


class FakeClient:
    chunks = []

    def __init__(self, **kwargs):
        self.chat = type("Chat", (), {"completions": FakeCompletions(self.chunks)})()


class ConcurrencyProbeTest(unittest.TestCase):
    def run_with(self, chunks):
        FakeClient.chunks = chunks
        with mock.patch("openai.OpenAI", FakeClient):
            return probe.one(0, "model", "https://aiaaa.cc/v1", 800)

    def test_complete_expected_output_passes(self):
        text = "\n".join(f"{i}: {i * i}" for i in range(1, 121))
        row = self.run_with([FakeChunk(text), FakeChunk(finish_reason="stop", usage=FakeUsage())])
        self.assertTrue(row["ok"])
        self.assertTrue(row["valid_output"])

    def test_http_success_with_wrong_or_truncated_output_fails(self):
        row = self.run_with([FakeChunk("1 1"), FakeChunk(finish_reason="length", usage=FakeUsage())])
        self.assertFalse(row["ok"])
        self.assertFalse(row["valid_output"])

    def test_reasoning_content_fails_nonthinking_probe(self):
        text = "\n".join(f"{i} {i * i}" for i in range(1, 121))
        row = self.run_with([FakeChunk(text, reasoning_content="hidden"),
                             FakeChunk(finish_reason="stop", usage=FakeUsage())])
        self.assertFalse(row["ok"])
        self.assertTrue(row["reasoning_content_observed"])


if __name__ == "__main__":
    unittest.main()
