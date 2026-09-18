"""Receive streamed chat responses, return the usual SDK completion object.

This changes transport only. Messages, tools and generation settings pass
through unchanged. Incomplete streams fail instead of becoming partial plans.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path
import time


def wait_for_route_slot(endpoint, spacing=None):
    """One shared request-start schedule across arm processes and clients."""
    if spacing is None:
        # AutoDL's registered 2026-09-18 probe passed 16 concurrent requests.
        # Historical routes retain their original request-start spacing.
        spacing = 0.05 if str(endpoint).rstrip("/") == "https://www.autodl.art/api/v1" else 2.1
    directory = Path(__file__).resolve().parents[1] / ".tmp/relay-rate-limits"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (hashlib.sha256(str(endpoint).encode()).hexdigest()[:16] + ".json")
    with path.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        raw = handle.read()
        previous = float(json.loads(raw)["next_start"]) if raw else 0
        now = time.time()
        scheduled = max(now, previous)
        handle.seek(0)
        handle.truncate()
        json.dump({"next_start": scheduled + spacing}, handle)
        handle.flush()
        fcntl.flock(handle, fcntl.LOCK_UN)
    if scheduled > now:
        time.sleep(scheduled - now)


def accumulate_chunks(chunks):
    from openai.types.chat import ChatCompletion

    header, choices, usage = {}, {}, None
    started = time.monotonic()
    first_token = first_answer = None
    for chunk in chunks:
        if time.monotonic() - started > 600:
            raise TimeoutError("stream exceeded 600 seconds")
        event = chunk.model_dump(exclude_none=True)
        if event.get("error"):
            raise RuntimeError("upstream stream error")
        for name in ("id", "created", "model", "system_fingerprint", "service_tier",
                     "cost_cny", "billing_pending", "trace_id"):
            if name in event:
                header[name] = event[name]
        if event.get("usage"):
            usage = event["usage"]
        for item in event.get("choices", []):
            row = choices.setdefault(item["index"], {
                "index": item["index"], "message": {"role": "assistant", "content": None},
                "finish_reason": None, "logprobs": None, "tools": {}})
            delta = item.get("delta", {})
            if any(delta.get(k) for k in ("content", "reasoning_content", "tool_calls")):
                if first_token is None:
                    first_token = time.monotonic() - started
            if delta.get("content") and first_answer is None:
                first_answer = time.monotonic() - started
            for name in ("content", "reasoning_content", "refusal"):
                if delta.get(name) is not None:
                    row["message"][name] = (row["message"].get(name) or "") + delta[name]
            for tool in delta.get("tool_calls", []):
                target = row["tools"].setdefault(tool["index"], {
                    "id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                if tool.get("id"):
                    target["id"] += tool["id"]
                if tool.get("type"):
                    target["type"] = tool["type"]
                for name in ("name", "arguments"):
                    target["function"][name] += tool.get("function", {}).get(name) or ""
            if item.get("finish_reason"):
                row["finish_reason"] = item["finish_reason"]
    if not choices or usage is None or any(not row["finish_reason"] for row in choices.values()):
        raise RuntimeError("incomplete stream: missing finish reason or usage")
    for row in choices.values():
        tools = row.pop("tools")
        if tools:
            row["message"]["tool_calls"] = [tools[i] for i in sorted(tools)]
    completion = ChatCompletion.model_validate({**header, "object": "chat.completion",
        "choices": [choices[i] for i in sorted(choices)], "usage": usage})
    object.__setattr__(completion, "_transport_metrics", {
        "stream_read_seconds": time.monotonic() - started,
        "first_stream_token_seconds": first_token, "first_stream_answer_seconds": first_answer})
    return completion


def install_stream_transport(client):
    """Wrap one client, preserving native upstream call/parse interfaces."""
    import httpx
    from openai import APIConnectionError

    original = client.chat.completions.create
    # Hidden SDK retries obscure metering and did not fix the gateway timeout.
    client.max_retries = 0
    client.timeout = httpx.Timeout(connect=30, read=180, write=60, pool=60)

    def create(*args, **kwargs):
        if kwargs.get("stream"):
            raise ValueError("caller must request a completed response")
        kwargs["stream"] = True
        kwargs["stream_options"] = {**(kwargs.get("stream_options") or {}), "include_usage": True}
        attempts = []
        for attempt in range(4):
            wait_for_route_slot(client.base_url)
            started = time.monotonic()
            stream_opened = False
            try:
                with original(*args, **kwargs) as stream:
                    stream_opened = True
                    response = accumulate_chunks(stream)
                response._transport_metrics["attempts"] = attempts + [{
                    "status_code": 200, "seconds": time.monotonic() - started}]
                return response
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                attempts.append({"status_code": status, "error_type": type(exc).__name__,
                                 "seconds": time.monotonic() - started,
                                 "code": str(getattr(exc, "code", ""))[:100],
                                 "stream_opened": stream_opened,
                                 "billing_unknown": True})
                object.__setattr__(exc, "transport_attempts", list(attempts))
                # APIConnectionError includes APITimeoutError. A pre-header
                # timeout may already have incurred upstream generation cost;
                # log unknown billing, and never retry an opened stream.
                transient = status in (429, 500, 502, 503, 504) or isinstance(exc, APIConnectionError)
                if stream_opened or not transient or attempt == 3 or any(
                    marker in str(exc).lower() for marker in ("insufficient", "quota", "balance")):
                    raise
                delay = 15 * (2 ** attempt)
                http_response = getattr(exc, "response", None)
                raw_retry = http_response.headers.get("retry-after", "") if http_response is not None else ""
                try:
                    delay = max(delay, min(float(raw_retry), 60))
                except (TypeError, ValueError):
                    pass
                attempts[-1]["retry_wait_seconds"] = delay
                time.sleep(delay)

    client.chat.completions.create = create
