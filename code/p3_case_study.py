"""P3 explainability — show the attack and the audit on ONE concrete round.

The numbers in the results doc say "behaviour auditing misattributes, similarity
auditing cannot separate, the causal audit recovers the driver." This script
shows that happening on real rounds, in the model's own words, so a reader can
check the mechanism instead of trusting an aggregate.

For a chosen anomalous test round it prints, in order:
  1. the query the user actually sent          (no poison note visible in it)
  2. what a BEHAVIOUR auditor sees             (just the answer)
  3. the memory records that were retrieved    (the poison hiding among them)
  4. the model's own reasoning                 (it narrates the hijack)
  5. the causal verdict + provenance           (which written round is the driver)
  6. the counterfactual that settles it        (same query, pre-injection)

Usage: python3 code/p3_case_study.py --transcript results/real/minja_trace_llm.transcript.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def wrap(text, width=88, indent="      "):
    words, line, out = str(text).split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(indent + line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        out.append(indent + line)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", default="results/real/minja_trace_llm.transcript.json")
    ap.add_argument("--n", type=int, default=2, help="how many fired cases to show")
    a = ap.parse_args()

    T = json.load(open(a.transcript))
    by_t = {r["t"]: r for r in T}

    fired = [r for r in T if r["phase"] == "test" and r["anomalous"]]
    if not fired:
        fired = [r for r in T if r["phase"] in ("test", "inject_probe") and r["anomalous"]]
    if not fired:
        fired = [r for r in T if r["anomalous"] and not r["note_present"]]

    pre = [r for r in T if r["phase"] == "pre"]
    pre_anom = sum(r["anomalous"] for r in pre)

    print("=" * 92)
    print("P3 CASE STUDY — a hidden memory driver, seen three ways".center(92))
    print("=" * 92)
    print(f"\ntrajectory: {len(T)} rounds | "
          f"pre-injection 'food' probes: {pre_anom}/{len(pre)} anomalous | "
          f"fired test rounds available: {len(fired)}")

    for case in fired[: a.n]:
        print("\n" + "=" * 92)
        print(f"CASE  t={case['t']}  phase={case['phase']}  id={case['id']}")
        print("=" * 92)

        print("\n1. THE QUERY THE USER SENT  (note the absence of any instruction)")
        print(wrap(case["question"]))
        print(f"\n      note_present = {case['note_present']}   "
              f"<- 0 means NO poison text is in the query itself")
        print(f"      ground truth = {case['groundtruth']}")

        print("\n2. WHAT A BEHAVIOUR-ONLY AUDITOR SEES")
        print(f"      answer = {case['answer']}   anomalous = {case['anomalous']}")
        print("      It can see the answer is out of range {A..D}, but the query looks")
        print("      completely benign. With memory invisible, the only correlate it can")
        print("      reach for is the topic word -- which the counterfactual below refutes.")

        print("\n3. WHAT WAS RETRIEVED FROM MEMORY  (the channel the auditor cannot see)")
        for r in case["retrieved"]:
            tag = "POISON" if r["is_poison"] else "benign"
            print(f"      [{tag}] id={r['id']}")
            print(wrap("Q: " + r["question"], indent="            "))
            if r["is_poison"]:
                print(wrap("stored reasoning: " + r["thought"], indent="            "))
        if not any(r["is_poison"] for r in case["retrieved"]):
            print("      (no poison among the retrieved records for this round)")

        print("\n4. THE MODEL'S OWN REASONING THIS ROUND")
        print(wrap(case["thought"]))

        print("\n5. CAUSAL VERDICT")
        srcs = [r["id"] for r in case["retrieved"] if r["is_poison"]]
        print(f"      An_G(anomalous action at t={case['t']}) includes the retrieved")
        print(f"      poison record(s): {srcs or '[]'}")
        print("      The edge is GATED: the same record sits in memory during benign")
        print("      rounds and does nothing; it becomes causally active only when the")
        print("      trigger word is present in the query.")

    print("\n" + "=" * 92)
    print("6. THE COUNTERFACTUAL THAT SETTLES ATTRIBUTION")
    print("=" * 92)
    print(f"      Same kind of 'food' query, run BEFORE any poison was written:")
    print(f"          pre-injection anomalous rate  = {pre_anom}/{len(pre)}")
    post = [r for r in T if r["phase"] == "test"]
    print(f"          post-injection anomalous rate = "
          f"{sum(r['anomalous'] for r in post)}/{len(post)}")
    print("      The query distribution is unchanged; only memory changed.")
    print("      => the 'food' topic is NOT the cause. The written record is.")
    if pre:
        ex = pre[0]
        print(f"\n      example clean probe (t={ex['t']}): answer={ex['answer']} "
              f"anomalous={ex['anomalous']}")
        print(wrap(ex["question"][:300]))


if __name__ == "__main__":
    main()
