"""Read-only progress/status export for full-history native conformance jobs."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time


def snapshot(base: Path, arms: tuple[str, ...] = ("mem0", "amem", "lightmem")) -> dict:
    report = {"scope": "native interface conformance, not paper score reproduction",
              "updated": time.time(), "arms": {}}
    for arm in arms:
        root = base / arm
        item = {"state": "initializing"}
        protocol = root / "protocol.json"
        if protocol.exists():
            p = json.loads(protocol.read_text())
            item.update(history_target=p["history_turns"], sample_id=p["sample_id"],
                        question_indices=p["question_indices"], model=p["model"])
        events = root / "events.jsonl"
        counts = Counter()
        tokens = Counter()
        last = None
        if events.exists():
            with events.open() as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        # Writers append one event at a time; a partial last
                        # line is pending and never counted as complete.
                        continue
                    counts[row["event"]] += 1
                    if row["event"] == "llm":
                        usage = row.get("usage") or {}
                        tokens.update({k: int(usage.get(k) or 0) for k in ("prompt_tokens", "completion_tokens")})
                    last = row
            item.update(state="running", counts=dict(counts), tokens=dict(tokens))
            if last:
                item.update(round=last["round"], last_event=last["event"], last_event_time=last.get("time"))
        validation = root / "validation.json"
        if validation.exists():
            item["validation"] = json.loads(validation.read_text())
            item["state"] = "passed" if item["validation"]["passed"] else "failed"
        report["arms"][arm] = item
    report["complete"] = all(v["state"] in {"passed", "failed"} for v in report["arms"].values())
    report["all_passed"] = all(v["state"] == "passed" for v in report["arms"].values())
    base.mkdir(parents=True, exist_ok=True)
    temporary = base / "progress.json.tmp"
    temporary.write_text(json.dumps(report, indent=2))
    temporary.replace(base / "progress.json")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--arms", default="mem0,amem,lightmem")
    args = parser.parse_args()
    while True:
        report = snapshot(args.base, tuple(args.arms.split(",")))
        print(json.dumps({"complete": report["complete"], "all_passed": report["all_passed"],
                          "arms": {k: {"state": v["state"], "round": v.get("round"),
                                       "llm": v.get("counts", {}).get("llm", 0)}
                                   for k, v in report["arms"].items()}}), flush=True)
        if not args.watch or report["complete"]:
            break
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
