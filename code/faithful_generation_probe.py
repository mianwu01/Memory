"""Run one low-cost generation request before any registered recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from faithful_memory import ROOT, request_mode_parameters

PROMPT = "Reply with exactly PROBE_OK and no other text."


def run_probe(model, endpoint, max_tokens):
    from openai import OpenAI

    client = OpenAI(max_retries=0)
    mode = request_mode_parameters(endpoint, "memory", "disabled")
    kwargs = {"extra_body": {"thinking": mode["thinking"]}}
    if "reasoning_effort" in mode:
        kwargs["reasoning_effort"] = mode["reasoning_effort"]
    started = time.monotonic()
    content, reasoning, finish, usage = [], [], None, None
    provider = {}
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            temperature=0,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )
        chunks = 0
        for chunk in stream:
            chunks += 1
            row = chunk.model_dump(exclude_none=True)
            for key in ("cost_cny", "billing_pending", "trace_id"):
                if key in row:
                    provider[key] = row[key]
            if getattr(chunk, "usage", None):
                usage = chunk.usage.model_dump()
            for choice in chunk.choices:
                if choice.finish_reason:
                    finish = choice.finish_reason
                delta = choice.delta
                if getattr(delta, "content", None):
                    content.append(delta.content)
                observed = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                if observed:
                    reasoning.append(observed)
        text = "".join(content).strip()
        reasoning_tokens = ((usage or {}).get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        passed = text == "PROBE_OK" and finish == "stop" and usage is not None and reasoning_tokens == 0 and not reasoning
        return {"passed": passed, "status_code": 200, "response_text": text,
                "finish_reason": finish, "usage": usage, "reasoning_content_observed": bool(reasoning),
                "chunks": chunks, "seconds": time.monotonic() - started, **provider}
    except Exception as exc:
        return {"passed": False, "status_code": getattr(exc, "status_code", None),
                "error_type": type(exc).__name__, "error_code": str(getattr(exc, "code", ""))[:100],
                "seconds": time.monotonic() - started}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-tokens", type=int, default=32)
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError("Probe output exists; keep every probe record")
    if args.max_tokens < 8:
        raise ValueError("max-tokens is too small for a conclusive probe")
    model, endpoint = os.environ["OPENAI_MODEL"], os.environ["OPENAI_BASE_URL"].rstrip("/")
    result = run_probe(model, endpoint, args.max_tokens)
    report = {"schema": "faithful-memory-generation-probe/v1", "created_at": time.time(),
              "model": model, "endpoint": endpoint, "prompt": PROMPT,
              "max_tokens": args.max_tokens,
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), **result}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as handle:
        json.dump(report, handle, indent=2)
    shown = str(args.out.resolve().relative_to(ROOT)) if args.out.resolve().is_relative_to(ROOT) else str(args.out)
    print(json.dumps({"passed": report["passed"], "out": shown, "status_code": report.get("status_code")}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
