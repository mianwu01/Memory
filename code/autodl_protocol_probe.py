"""Record bounded JSON, tool and concurrency probes before the new campaign."""
from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

from run_with_autodl import ROOT, ENDPOINT, MODEL, environment


def request(payload):
    key = environment()["OPENAI_API_KEY"]
    started = time.monotonic()
    req = urllib.request.Request(ENDPOINT + "/chat/completions",
        data=json.dumps({"model": MODEL, **payload}).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read())
        return {"status": 200, "seconds": time.monotonic() - started, "response": data}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "seconds": time.monotonic() - started,
                "error": exc.read().decode("utf-8", "replace").replace(key, "[REDACTED]")[:1200]}
    except Exception as exc:
        return {"status": None, "seconds": time.monotonic() - started,
                "error": type(exc).__name__}


def main():
    out = ROOT / "results/development/autodl_20260918/protocol_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise ValueError("Probe output already exists")
    report = {"model": MODEL, "endpoint": ENDPOINT, "started_at": time.time(), "modes": {}}
    def save():
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, indent=2)); tmp.replace(out)
    base = {"messages": [{"role": "user", "content":
        'Extract the final city: Alice planned Paris, changed to Rome, and kept Rome. Reply only with JSON {"city":"Rome"}.'}],
        "temperature": 0, "max_tokens": 256, "response_format": {"type": "json_object"}}
    modes = {"thinking_disabled": {"thinking": {"type": "disabled"}},
             "effort_none": {"reasoning_effort": "none"},
             "both": {"thinking": {"type": "disabled"}, "reasoning_effort": "none"}}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(request, {**base, **mode}): name for name, mode in modes.items()}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]; result = future.result()
            choices = result.get("response", {}).get("choices", [])
            message = choices[0].get("message", {}) if choices else {}
            reasoning = (result.get("response", {}).get("usage", {}).get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
            try: valid = json.loads(message.get("content", "")) == {"city": "Rome"}
            except Exception: valid = False
            result["passed"] = valid and not reasoning and not message.get("reasoning_content") and choices[0].get("finish_reason") == "stop"
            report["modes"][name] = result; save()
            print(json.dumps({"phase": "mode", "name": name, "passed": result["passed"], "status": result["status"]}), flush=True)
    selected = next((n for n in ("thinking_disabled", "both", "effort_none") if report["modes"][n]["passed"]), None)
    report["selected_mode"] = modes.get(selected); save()
    if selected is None: raise SystemExit(1)
    tool = {"type": "function", "function": {"name": "add", "description": "Add two integers",
        "parameters": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]}}}
    messages = [{"role": "user", "content": "Use the add tool to calculate 2 plus 3, then report the result."}]
    first = request({"messages": messages, "tools": [tool], "max_tokens": 1024, "temperature": 0})
    report["tools_first"] = first; save()
    choices = first.get("response", {}).get("choices", [])
    message = choices[0].get("message", {}) if choices else {}
    calls = message.get("tool_calls", [])
    if calls:
        answer_messages = messages + [message]
        for call in calls:
            arguments = json.loads(call["function"]["arguments"])
            answer_messages.append({"role": "tool", "tool_call_id": call["id"], "content": str(arguments["a"] + arguments["b"])})
        report["tools_second"] = request({"messages": answer_messages, "tools": [tool], "max_tokens": 1024, "temperature": 0})
    report["tool_calls_present"] = bool(calls); save()
    report["concurrency"] = []
    for level in (4, 8, 16):
        started = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=level) as pool:
            rows = list(pool.map(lambda _: request({**base, **modes[selected]}), range(level)))
        item = {"level": level, "seconds": time.monotonic() - started, "rows": rows,
                "http_successes": sum(r["status"] == 200 for r in rows)}
        report["concurrency"].append(item); save()
        print(json.dumps({"phase": "concurrency", "level": level, "successes": item["http_successes"], "seconds": item["seconds"]}), flush=True)
        if item["http_successes"] != level: break
    report["completed_at"] = time.time(); save()


if __name__ == "__main__":
    main()
