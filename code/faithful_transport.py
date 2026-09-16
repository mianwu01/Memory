"""Lossless provider protocol support, separate from task/memory algorithms."""
from __future__ import annotations

import copy
import json
import time


def install_faithful_stream_transport(client):
    """Bounded recovery of an explicit relay outage, with identical requests.

    Original transport stays frozen for historical experiments. A failed stream
    never supplies any part of the returned completion. Semantic/model failures
    are outside this transport policy and cannot cause a resampling loop.
    """
    from relay_chat_transport import install_stream_transport
    install_stream_transport(client)
    original = client.chat.completions.create

    def create(*args, **kwargs):
        prior = []
        for attempt in range(3):
            try:
                result = original(*args, **kwargs)
            except Exception as exc:
                traces = list(getattr(exc, "transport_attempts", []))
                prior.extend(traces)
                object.__setattr__(exc, "transport_attempts", list(prior))
                eligible = (str(getattr(exc, "code", "")) == "upstream_stream_read_error"
                            and traces and traces[-1].get("stream_opened"))
                if not eligible or attempt == 2:
                    raise
                wait = 15 * (attempt + 1)
                prior[-1]["retry_wait_seconds"] = wait
                prior[-1]["retry_reason"] = "registered_explicit_upstream_stream_failure"
                time.sleep(wait)
            else:
                result._transport_metrics["attempts"] = prior + result._transport_metrics.get("attempts", [])
                return result

    client.chat.completions.create = create


class ReasoningHistory:
    """Restore only reasoning actually returned for the same tool-call group.

    MemoryArena's OpenAI formatter drops provider-specific reasoning_content.
    DeepSeek thinking mode requires it on the next request. Never synthesize
    missing reasoning or change an actor prompt, tool, tool result, or answer.
    """
    def __init__(self):
        self.observed = {}

    @staticmethod
    def signature(calls):
        rows = []
        for call in calls:
            if hasattr(call, "model_dump"):
                call = call.model_dump()
            function = call["function"]
            arguments = function["arguments"]
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            rows.append([call["id"], function["name"], arguments])
        return json.dumps(rows, sort_keys=True, ensure_ascii=False)

    def remember(self, message):
        if hasattr(message, "model_dump"):
            message = message.model_dump()
        calls = message.get("tool_calls")
        if not calls:
            return
        key = self.signature(calls)
        value = message.get("reasoning_content") or ""
        if key in self.observed and self.observed[key] != value:
            raise ValueError("Ambiguous reused tool identifiers; reasoning cannot be restored losslessly")
        self.observed[key] = value

    def prepare(self, messages):
        result = copy.deepcopy(messages)
        for message in result:
            if message.get("role") != "assistant" or not message.get("tool_calls"):
                continue
            key = self.signature(message["tool_calls"])
            if key not in self.observed:
                raise ValueError("Tool reasoning history was not observed; refusing to fabricate it")
            expected = self.observed[key]
            if "reasoning_content" in message and message["reasoning_content"] != expected:
                raise ValueError("Tool reasoning history differs from the observed model response")
            message["reasoning_content"] = expected
        return result
