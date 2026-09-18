"""Measure whether the relay sustains concurrent complete streamed generations."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import time

from faithful_memory import ROOT, request_mode_parameters

PROMPT = "List the integers from 1 to 120, one per line, each followed by its square. No commentary, no markdown."
EXPECTED = [f"{i} {i * i}" for i in range(1, 121)]


def normalized_lines(text):
    return [" ".join(line.strip().replace(":", " ").replace("=", " ").split()) for line in text.splitlines() if line.strip()]


def one(index, model, endpoint, max_tokens):
    from openai import OpenAI

    client = OpenAI(max_retries=0)
    started = time.monotonic()
    first = None
    mode = request_mode_parameters(endpoint, "memory", "disabled")
    kwargs = {"extra_body": {"thinking": mode["thinking"]}}
    if "reasoning_effort" in mode:
        kwargs["reasoning_effort"] = mode["reasoning_effort"]
    try:
        stream = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": PROMPT}], temperature=0,
            max_tokens=max_tokens, stream=True, stream_options={"include_usage": True}, **kwargs)
        usage, finish, chunks, content, reasoning = None, None, 0, [], []
        provider = {}
        for chunk in stream:
            if first is None:
                first = time.monotonic() - started
            chunks += 1
            event = chunk.model_dump(exclude_none=True)
            for key in ("cost_cny", "billing_pending", "trace_id"):
                if key in event:
                    provider[key] = event[key]
            if chunk.choices and chunk.choices[0].finish_reason:
                finish = chunk.choices[0].finish_reason
            for choice in chunk.choices:
                delta = choice.delta
                if getattr(delta, "content", None):
                    content.append(delta.content)
                observed = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                if observed:
                    reasoning.append(observed)
            if getattr(chunk, "usage", None):
                usage = chunk.usage.model_dump()
        text = "".join(content)
        reasoning_tokens = ((usage or {}).get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        valid_output = normalized_lines(text) == EXPECTED
        ok = finish == "stop" and usage is not None and reasoning_tokens == 0 and not reasoning and valid_output
        return {"index": index, "ok": ok, "status_code": 200,
                "first_token_seconds": first, "total_seconds": time.monotonic() - started,
                "chunks": chunks, "finish_reason": finish, "usage": usage,
                "reasoning_content_observed": bool(reasoning), "valid_output": valid_output, **provider}
    except Exception as exc:
        return {"index": index, "ok": False, "error_type": type(exc).__name__,
                "error_code": str(getattr(exc, "code", ""))[:100],
                "status_code": getattr(exc, "status_code", None),
                "total_seconds": time.monotonic() - started}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, nargs="+", default=[8, 16])
    ap.add_argument("--max-tokens", type=int, default=800)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError("Probe output exists; keep every probe record")
    if any(level < 1 for level in args.concurrency):
        raise ValueError("concurrency levels must be positive")
    model, endpoint = os.environ["OPENAI_MODEL"], os.environ["OPENAI_BASE_URL"].rstrip("/")
    report = {"schema": "faithful-memory-concurrency-probe/v1", "created_at": time.time(),
              "model": model, "endpoint": endpoint, "max_tokens": args.max_tokens,
              "prompt": PROMPT, "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "levels": []}
    for level in args.concurrency:
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=level) as pool:
            rows = list(pool.map(lambda i: one(i, model, endpoint, args.max_tokens), range(level)))
        ok = [row for row in rows if row["ok"]]
        level_report = {"concurrency": level, "wall_seconds": time.monotonic() - started,
                        "succeeded": len(ok), "failed": len(rows) - len(ok),
                        "status_codes": sorted({str(row.get("status_code")) for row in rows if not row["ok"]}),
                        "max_first_token_seconds": max((row["first_token_seconds"] or 0) for row in ok) if ok else None,
                        "max_total_seconds": max(row["total_seconds"] for row in ok) if ok else None,
                        "output_tokens": sum((row["usage"] or {}).get("completion_tokens", 0) for row in ok),
                        "provider_reported_cny": sum(float(row.get("cost_cny") or 0) for row in rows
                                                     if row.get("billing_pending") is False),
                        "rows": rows}
        report["levels"].append(level_report)
        print(json.dumps({key: value for key, value in level_report.items() if key != "rows"}), flush=True)
        if level_report["failed"]:
            report["verdict"] = f"stop: incomplete or failed streams at concurrency {level}"
            break
    else:
        report["verdict"] = "all requested concurrency levels produced complete validated outputs"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as handle:
        json.dump(report, handle, indent=2)
    shown = str(args.out.resolve().relative_to(ROOT)) if args.out.resolve().is_relative_to(ROOT) else str(args.out)
    print(json.dumps({"verdict": report["verdict"], "out": shown}))
    if any(level["failed"] for level in report["levels"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
