"""One diagnostic A-Mem neighbor request with only max_tokens raised to 16k."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import time

from faithful_memory import environment
from faithful_transport import install_faithful_stream_transport


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    environment()
    from llm_text_parsers import parse_update_neighbors
    from openai import OpenAI
    rows = [json.loads(line) for line in args.events.read_text().splitlines()]
    event = [r for r in rows if r["event"] == "llm" and any(c["finish_reason"] == "length" for c in r["choices"])][-1]
    args.out.mkdir(parents=True, exist_ok=False)
    request = {"model": event["requested_model"], "messages": event["messages"],
               "temperature": 0.7, "max_tokens": 16000,
               "extra_body": {"thinking": {"type": "disabled"}}}
    prompt = "\n".join(m.get("content") or "" for m in request["messages"])
    n = int(re.search(r"continue for all (\d+) neighbors", prompt).group(1))
    (args.out / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2))
    client = OpenAI()
    install_faithful_stream_transport(client)
    started = time.monotonic()
    response = client.chat.completions.create(**request)
    (args.out / "response.json").write_text(response.model_dump_json(indent=2))
    content = response.choices[0].message.content or ""
    parsed = parse_update_neighbors(content, n)
    original = parse_update_neighbors(event["choices"][0]["message"]["content"], n)
    report = {"scope": "Diagnostic only; original native 1000-token FAIL is unchanged",
              "only_changed_parameter": {"max_tokens": [event["max_tokens"], 16000]},
              "temperature": 0.7, "expected_neighbors": n,
              "original": {"usage": event["usage"], "finish_reason": "length",
                           "neighbors_with_context": sum(bool(x["context"]) for x in original),
                           "neighbors_with_tags": sum(bool(x["tags"]) for x in original)},
              "diagnostic": {"duration_seconds": time.monotonic() - started,
                             "finish_reason": response.choices[0].finish_reason,
                             "usage": response.usage.model_dump(),
                             "neighbors_with_context": sum(bool(x["context"]) for x in parsed),
                             "neighbors_with_tags": sum(bool(x["tags"]) for x in parsed)},
              "parsed_neighbors": parsed}
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "parsed_neighbors"}, indent=2))


if __name__ == "__main__":
    main()
