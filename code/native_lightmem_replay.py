"""Two diagnostic replays of a failed native metadata request; no result repair.

Temperature/top_p defaults and JSON mode are reconstructed from the author's
OpenaiManager and BaseMemoryManagerConfig; recorded messages and token cap are
reused verbatim. A separately requested top_p=1 compatibility diagnostic is
recorded as an explicit parameter change. The original native validation remains
FAIL regardless of these diagnostic outcomes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import time

from faithful_memory import environment
from faithful_transport import install_faithful_stream_transport


def shape(text: str) -> dict:
    lines = Counter(text.splitlines())
    out = {"characters": len(text), "open_braces": text.count("{"), "close_braces": text.count("}"),
           "zero_width_space_count": text.count("\u200b"),
           "most_repeated_line": lines.most_common(1)[0] if lines else None}
    try:
        value = json.loads(text)
        out.update(json_valid=True, data_entries=len(value.get("data", [])) if isinstance(value, dict) else None)
    except json.JSONDecodeError as exc:
        out.update(json_valid=False, json_error=exc.msg, json_error_position=exc.pos)
    decoder = json.JSONDecoder()
    offset, complete = 0, 0
    while offset < len(text):
        rest = text[offset:].lstrip()
        if not rest:
            break
        offset = len(text) - len(rest)
        try:
            _, end = decoder.raw_decode(text, offset)
        except json.JSONDecodeError:
            break
        complete += 1
        offset = end
    out["complete_top_level_json_objects"] = complete
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--top-p", type=float, choices=(0.1, 1.0), default=0.1)
    args = parser.parse_args()
    environment()
    rows = [json.loads(line) for line in args.events.read_text().splitlines()]
    event = [r for r in rows if r["event"] == "llm" and any(c["finish_reason"] == "length" for c in r["choices"])][-1]
    args.out.mkdir(parents=True, exist_ok=False)
    request = {"model": event["requested_model"], "messages": event["messages"],
               "max_tokens": event["max_tokens"], "temperature": 0.1, "top_p": args.top_p,
               "response_format": {"type": "json_object"}, "extra_body": {"thinking": {"type": "disabled"}}}
    (args.out / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2))
    original = {"round": event["round"], "usage": event["usage"],
                "response_shape": shape(event["choices"][0]["message"]["content"]),
                "message_characters": [{"role": m["role"], "characters": len(m.get("content") or "")} for m in request["messages"]],
                "source_event_sha256": hashlib.sha256(args.events.read_bytes()).hexdigest()}
    (args.out / "original_analysis.json").write_text(json.dumps(original, ensure_ascii=False, indent=2))

    def replay(index):
        from openai import OpenAI
        client = OpenAI()
        install_faithful_stream_transport(client)
        started = time.monotonic()
        try:
            response = client.chat.completions.create(**request)
            result = {"index": index, "duration_seconds": time.monotonic() - started,
                      "finish_reason": response.choices[0].finish_reason,
                      "response_shape": shape(response.choices[0].message.content or ""),
                      "response": response.model_dump()}
        except Exception as exc:
            result = {"index": index, "error_type": type(exc).__name__, "status_code": getattr(exc, "status_code", None)}
        (args.out / f"replay_{index}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return {k: v for k, v in result.items() if k != "response"}

    with ThreadPoolExecutor(max_workers=2) as executor:
        replays = list(executor.map(replay, (1, 2)))
    report = {"scope": "Diagnostic only; original full-history conformance FAIL remains unchanged",
              "parameter_change": {"top_p": [0.1, args.top_p]} if args.top_p != 0.1 else {},
              "endpoint": os.environ["OPENAI_BASE_URL"], "original": original, "replays": replays,
              "upstream_parser": "clean_response strips optional code fence, runs json.loads, returns [] on JSONDecodeError; no concatenated-object repair.",
              "actual_failure_path": "Runtime rejected finish_reason=length before parser; upstream segment handler caught error and returned empty metadata; Runtime also rejected that fallback."}
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
