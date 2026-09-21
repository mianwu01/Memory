"""Offline task/reference screening. Does not call models or create trajectories."""
import argparse
import base64
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re


def normalize_answer(text):
    # Diagnostic only: never promote this to a semantically complete checker.
    return re.sub(r"[^\w]+", " ", text).strip().lower()


def extract_reference_answer(text):
    matches = re.findall(r"Exact Answer\*{0,2}\s*:\*{0,2}\s*([^\n]+)", text, re.I)
    return normalize_answer(matches[-1]) if matches else None


def decrypt(text, password):
    data = base64.b64decode(text)
    key = hashlib.sha256(password.encode()).digest()
    return bytes(value ^ key[i % len(key)] for i, value in enumerate(data)).decode()


def main(directory):
    path = Path(directory)
    rows = [json.loads(s) for s in (path/"progressive_search.jsonl").read_text().splitlines()]
    original = {}
    data = (path/"browse_comp_test_set.csv").read_bytes()
    for i, row in enumerate(csv.DictReader(io.StringIO(data.decode()))):
        query = " ".join(decrypt(row["problem"], row["canary"]).split())
        answer = decrypt(row["answer"], row["canary"])
        assert query not in original
        original[query] = dict(original_row=i, answer=answer)
    mapping = []
    for row in rows:
        gold = original.get(" ".join(row["questions"][-1].split()))
        answers = [extract_reference_answer(a) for a in row["answers"]]
        mapping.append(dict(memoryarena_id=row["id"], sessions=len(row["questions"]),
                            mapped=bool(gold), original_row=gold["original_row"] if gold else None,
                            prior_same_as_final=sum(a is not None and a == answers[-1] for a in answers[:-1]),
                            final_reference_string_matches_original=bool(gold and answers[-1] == normalize_answer(gold["answer"]))))
    report = dict(tasks=len(rows), questions=sum(len(r["questions"]) for r in rows),
                  session_count_distribution=dict(sorted(Counter(len(r["questions"]) for r in rows).items())),
                  exact_question_mappings=sum(r["mapped"] for r in mapping),
                  prior_reference_repeats_final=sum(r["prior_same_as_final"] > 0 for r in mapping),
                  final_reference_string_matches_original=sum(r["final_reference_string_matches_original"] for r in mapping),
                  source_sha256={name:hashlib.sha256((path/name).read_bytes()).hexdigest()
                                 for name in ("progressive_search.jsonl", "browse_comp_test_set.csv")},
                  interpretation="String diagnostics only. A mismatch can reflect aliases, wording, or incorrect reference; no LLM was used to adjudicate. Not actor results.",
                  actual_agent_trajectories=0, memory_state_transitions_observed=0,
                  gate_2_passed=False, mappings=mapping)
    (path/"search_screen_report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k != "mappings"}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", nargs="?", default="results/development/hm3/native_task_screen")
    main(p.parse_args().directory)
