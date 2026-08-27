"""T0 audit of the released AMA-Bench test set (CPU-only, no LLM).

Questions answered:
  L1  step-citation leakage: does the question already cite the steps the gold
      answer cites (zero-retrieval questions)?
  L2  answer-substring leakage: is the gold answer contained in the question?
  L3  evidence localization: for QA whose answers cite steps NOT given in the
      question, does BM25 over per-turn docs (question as query) recall them?

Usage: python3 code/ama_t0.py <open_end_qa_set.jsonl>
"""

import json
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, "code")
from t0_travel import BM25  # noqa: E402

STEP_RE = re.compile(r"\b(?:step|turn)s?\s+(\d+)\b", re.I)
RANGE_RE = re.compile(r"\b(?:between|from)\s+(?:step|turn)s?\s+(\d+)\s+(?:and|to)\s+(?:step|turn)s?\s+(\d+)", re.I)


def cited(text, expand_ranges=False):
    s = {int(m) for m in STEP_RE.findall(text)}
    if expand_ranges:
        for a, b in RANGE_RE.findall(text):
            a, b = int(a), int(b)
            if 0 <= b - a <= 3000:
                s |= set(range(a, b + 1))
    return s


def norm(s):
    return re.sub(r"\s+", " ", s.lower()).strip()


def main():
    rows = [json.loads(l) for l in open(sys.argv[1])]
    agg = defaultdict(Counter)
    loc = defaultdict(list)
    n_qa = 0
    for r in rows:
        dom, turns = r["domain"], r["trajectory"]
        docs = [f"Step {t.get('turn_idx', i)}: action: {t.get('action','')} "
                f"observation: {t.get('observation','')}" for i, t in enumerate(turns)]
        idx_of = {}
        for i, t in enumerate(turns):
            try:
                idx_of[int(t.get("turn_idx", i))] = i
            except (TypeError, ValueError):
                idx_of[i] = i
        bm = BM25(docs) if docs else None
        for qa in r["qa_pairs"]:
            n_qa += 1
            q, a, typ = qa["question"], qa["answer"], qa.get("type", "?")
            key = (dom, typ)
            q_steps_span = cited(q, expand_ranges=True)
            a_steps = cited(a)
            agg[key]["n"] += 1
            if norm(a) and norm(a) in norm(q):
                agg[key]["L2_answer_in_question"] += 1
            if not a_steps:
                agg[key]["L1_answer_cites_no_steps"] += 1
            elif a_steps <= q_steps_span:
                agg[key]["L1_zero_retrieval"] += 1        # all evidence steps handed over
            else:
                need = a_steps - q_steps_span
                agg[key]["L3_eligible"] += 1
                if bm:
                    sc = bm.score(q)
                    rank = sorted(range(len(docs)), key=lambda i: -sc[i])
                    got10 = set(rank[:10])
                    hit = [s for s in need if idx_of.get(s) in got10]
                    loc[key].append(len(hit) / len(need))
    # report
    out = {"rows": len(rows), "qa": n_qa, "per_domain_type": {}}
    for key in sorted(agg):
        d = dict(agg[key])
        if loc[key]:
            d["L3_bm25@10_evidence_recall"] = round(sum(loc[key]) / len(loc[key]), 3)
        out["per_domain_type"]["/".join(key)] = d
    # domain rollup
    roll = defaultdict(Counter)
    for (dom, typ), c in agg.items():
        for k, v in c.items():
            roll[dom][k] += v
    out["per_domain"] = {d: dict(c) for d, c in sorted(roll.items())}
    for d in out["per_domain"]:
        ls = [x for (dd, _), v in loc.items() if dd == d for x in v]
        if ls:
            out["per_domain"][d]["L3_bm25@10_evidence_recall"] = round(sum(ls) / len(ls), 3)
    tot = Counter()
    for c in agg.values():
        for k, v in c.items():
            tot[k] += v
    out["total"] = dict(tot)
    all_loc = [x for v in loc.values() for x in v]
    if all_loc:
        out["total"]["L3_bm25@10_evidence_recall"] = round(sum(all_loc) / len(all_loc), 3)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
