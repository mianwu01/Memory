"""Travel-R v0: reconstruct MemoryArena/travel so dependencies live in HISTORY,
not in the current query — then audit whether the reconstruction actually
achieves criterion C1 (no query-time oracle) or leaks lexical shortcuts.

Transform R1 (prospective relocation): every dependency sentence of round t
referencing source person P is (a) removed from round t's query and replaced by a
generic pointer, (b) appended to source round P's query as a third-person
"Planning note" (so it enters memory when P's round is written).

Audit:
  A1. residual named-dependency rate in transformed CURRENT queries (C1 check);
  A2. BM25 retrieval of gold source rounds from the transformed query
      (self-name shortcut: announcements contain the target's name);
  A3. same but with the target's name masked from history chunks (upper bound on
      how much of A2 is pure name matching).

Usage: python3 code/travel_r.py <travel_rows.json> [--emit out.json]
"""

import json
import re
import sys

sys.path.insert(0, "code")
from t0_travel import BM25, build_chunks, norm, parse_episode  # noqa: E402

DAY_WORD = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh"}


def third_person(sentence, target, src):
    """Crude first->third person rewrite of the target's constraint sentence,
    re-anchored in the source's voice (src's possessives become 'my')."""
    s = sentence
    # 1) the target's first person -> third person (before touching the source)
    s = re.sub(r"\bI am\b", target + " is", s)
    s = re.sub(r"\bI'm\b", target + " is", s)
    s = re.sub(r"\bI'd like\b", target + " would like", s)
    s = re.sub(r"\bI'd prefer\b", target + " would prefer", s)
    s = re.sub(r"\bI want\b", target + " wants", s)
    s = re.sub(r"\bI prefer\b", target + " prefers", s)
    s = re.sub(r"\bI\b", target, s)
    s = re.sub(r"\bmy\b", f"{target}'s", s)
    s = re.sub(r"\bme\b", target, s)
    # 2) the source (whose round now hosts the note) -> first person
    s = re.sub(r"\b" + src + r"'s\b", "my", s)
    s = re.sub(r"\b" + src + r"\b", "me", s)
    return s


def pointer(entry):
    tc = entry.get("tgt_cell") or {}
    if tc.get("day") and tc.get("slot"):
        return (f"For {tc['slot']} on the {DAY_WORD[tc['day']]} day, follow the "
                f"arrangement that was announced for me earlier in the trip.")
    return "Please follow any arrangements that were announced for me earlier in the trip."


def transform(rows):
    out, stats = [], {"moved": 0, "kept": 0, "pointer_generic": 0}
    parsed = [parse_episode(r) for r in rows]
    for row, ep in zip(rows, parsed):
        names = ep["names"]
        new_q = []
        notes = [[] for _ in range(len(names))]        # notes[k] -> appended to round k (0=base)
        for r in ep["rounds"]:
            lines = [f"I am {r['name']}."]
            pre = [ln for ln in norm(r["query"]).split("\n")
                   if ln.strip() and re.match(r"^I'm (traveling|joining|going)", ln.strip())]
            lines += pre
            for s in r["sentences"]:
                if s["is_dep"] and s["srcs"]:
                    src = s["srcs"][-1]                 # latest source: all refs already past
                    k = names.index(src)
                    notes[k].append("Planning note: " + third_person(s["text"], r["name"], src))
                    ptr = pointer(s)
                    lines.append(ptr)
                    stats["moved"] += 1
                    if ptr.startswith("Please"):
                        stats["pointer_generic"] += 1
                else:
                    lines.append(s["text"])
                    stats["kept"] += 1
            new_q.append("\n".join(lines))
        # base-person notes go into the base query; round-k notes append to round k's query
        base_q = norm(row["base_person"]["query"])
        if notes[0]:
            base_q += "\n" + "\n".join(notes[0])
        for k in range(1, len(names)):
            if notes[k]:
                new_q[k - 1] += "\n" + "\n".join(notes[k])
        out.append({"id": row["id"],
                    "base_person": {**row["base_person"], "query": base_q},
                    "questions": new_q, "answers": row["answers"]})
    return out, stats


def audit(orig_rows, r_rows):
    orig = [parse_episode(r) for r in orig_rows]
    tran = [parse_episode(r) for r in r_rows]
    # A1: residual named deps in transformed current queries
    dep_o = sum(s["is_dep"] for ep in orig for r in ep["rounds"] for s in r["sentences"])
    dep_t = sum(s["is_dep"] for ep in tran for r in ep["rounds"] for s in r["sentences"])
    res = {"A1_dep_sentences_orig": dep_o, "A1_dep_sentences_travelR": dep_t,
           "A1_residual_rate": round(dep_t / dep_o, 4)}
    # A2/A3: BM25 gold-parent retrieval on transformed episodes
    rec = {k: [] for k in ("A2@2", "A2@3", "A2@5", "A3@2", "A3@3", "A3@5",
                           "rand@2", "rand@3", "rand@5")}
    for ep_o, ep_t, row_t in zip(orig, tran, r_rows):
        gold_of = {}
        name2round = {n: k for k, n in enumerate(ep_o["names"])}
        for r in ep_o["rounds"]:
            g = {name2round[n] for s in r["sentences"] if s["is_dep"] for n in s["srcs"]}
            if g:
                gold_of[r["t"]] = g
        chunks = build_chunks({**ep_t, "row": row_t})
        for t, gold in gold_of.items():
            q = ep_t["rounds"][t - 1]["query"]
            avail = chunks[:t]
            sc = BM25(avail).score(q)
            rank = sorted(range(len(avail)), key=lambda i: -sc[i])
            for k in (2, 3, 5):
                rec[f"A2@{k}"].append(len(gold & set(rank[:k])) / len(gold))
                rec[f"rand@{k}"].append(min(k, len(avail)) / len(avail))
            # A3: mask the target's own name out of history chunks
            masked = [re.sub(r"\b" + ep_t["rounds"][t - 1]["name"] + r"\b", "SOMEONE", c)
                      for c in avail]
            sc2 = BM25(masked).score(q)
            rank2 = sorted(range(len(avail)), key=lambda i: -sc2[i])
            for k in (2, 3, 5):
                rec[f"A3@{k}"].append(len(gold & set(rank2[:k])) / len(gold))
    for k, v in rec.items():
        res[k + "_recall"] = round(sum(v) / len(v), 4)
    return res


def main():
    rows = json.load(open(sys.argv[1]))
    r_rows, stats = transform(rows)
    print(json.dumps({"transform": stats}, indent=2))
    print(json.dumps(audit(rows, r_rows), indent=2))
    if "--emit" in sys.argv:
        out = sys.argv[sys.argv.index("--emit") + 1]
        json.dump(r_rows, open(out, "w"))
        print("wrote", out)
    # show one before/after example
    ep = parse_episode(rows[0])
    print("\n--- example: row id=1, round 3 (Bart) BEFORE ---")
    print(norm(rows[0]["questions"][2])[:600])
    print("\n--- AFTER (Bart's query) ---")
    print(r_rows[0]["questions"][2][:600])
    print("\n--- AFTER (Emma's query, now carrying the note) ---")
    print(r_rows[0]["questions"][1][:900])


if __name__ == "__main__":
    main()
