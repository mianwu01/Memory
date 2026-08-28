"""T0: pre-registered falsification test for the MemoryArena/travel instantiation.

See docs/memoryarena-instantiation.md par.8. Pure text parsing over the 270
group_travel_planner episodes -- no LLM, no GPU, no environment.

Usage: python3 code/t0_travel.py <path/to/travel_rows.json> [--dump-flagged]
"""

import json
import math
import re
import sys
from collections import Counter, defaultdict

SLOTS = ["breakfast", "lunch", "dinner", "accommodation", "attraction", "transportation"]
SLOT_ALIASES = {
    "breakfast": ["breakfast"],
    "lunch": ["lunch"],
    "dinner": ["dinner"],
    "accommodation": ["accommodation", "stay", "stays", "place", "room"],
    "attraction": ["attraction", "attractions"],
    "transportation": ["transportation", "flight", "flights"],
}
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7}

PREAMBLE_RE = re.compile(r"^I'm (traveling with|joining|going on this trip with)")
DEP_KEYWORDS = re.compile(
    r"\b(join|joins|joining|same|share|shares|sharing|than|within|compared|hers|his|theirs|"
    r"of it\b|everyone|the group|previous|earlier)\b"
)
JOIN_RE = re.compile(
    r"\b(join|eat with|stay with|share with|share accommodation with|stay at the same (?:place|accommodation) as|"
    r"stay in the same|dine with|(?:have|having|get|grab) (?:lunch|dinner|breakfast)[^.]{0,45}with\b)\b"
)


def norm(text):
    return text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')


def day_mentions(s):
    days = []
    for m in re.finditer(r"\b(first|second|third|fourth|fifth|sixth|seventh)[- ]day\b", s, re.I):
        days.append((ORDINALS[m.group(1).lower()], m.start()))
    for m in re.finditer(r"\bday[- ](\d)\b", s, re.I):
        days.append((int(m.group(1)), m.start()))
    for m in re.finditer(r"\bthe (first|second|third|fourth|fifth|sixth|seventh) day\b", s, re.I):
        days.append((ORDINALS[m.group(1).lower()], m.start()))
    return sorted(set(days), key=lambda x: x[1])


def slot_mentions(s):
    out = []
    low = s.lower()
    for slot, aliases in SLOT_ALIASES.items():
        for a in aliases:
            for m in re.finditer(r"\b" + a + r"\b", low):
                out.append((slot, m.start()))
    return sorted(out, key=lambda x: x[1])


def parse_episode(row):
    """Parse one episode into rounds with constraint sentences and dependency edges."""
    base_name = row["base_person"]["name"]
    names = [base_name] + [re.match(r"I am (\w+)", norm(q)).group(1) for q in row["questions"]]
    rounds = []
    for t, q in enumerate(row["questions"], start=1):
        q = norm(q)
        self_name = names[t]
        lines = [ln.strip() for ln in q.split("\n") if ln.strip()]
        sentences, preamble_ok = [], False
        for ln in lines:
            if ln == f"I am {self_name}.":
                continue
            if PREAMBLE_RE.match(ln):
                preamble_ok = True
                continue
            sentences.append(ln)
        prior_names = names[:t]          # base(idx0) + rounds 1..t-1
        future_names = names[t + 1:]
        parsed = []
        for s in sentences:
            srcs = [n for n in prior_names if re.search(r"\b" + n + r"\b", s)]
            future_refs = [n for n in future_names if re.search(r"\b" + n + r"\b", s)]
            days, slots = day_mentions(s), slot_mentions(s)
            entry = {
                "text": s, "srcs": srcs, "future_refs": future_refs,
                "is_dep": bool(srcs), "kw_no_name": bool(DEP_KEYWORDS.search(s)) and not srcs,
                "style": None, "src_cell": None, "tgt_cell": None,
            }
            if srcs:
                # source cell via a window after the name: "X's [day] [slot]", bare "X's",
                # or "X had for <slot> on <day>"
                poss = None
                for n in srcs:
                    m = re.search(r"\b" + n + r"(?:'s|\s+had)\b", s)
                    if m:
                        win = s[m.start(): m.start() + 70]
                        pd = day_mentions(win)
                        ps = slot_mentions(win)
                        poss = (n, pd[0][0] if pd else None, ps[0][0] if ps else None, m.span())
                        break
                if poss:
                    # target cell = first day/slot outside the name window
                    rem = s[:poss[3][0]]
                    rd, rs = day_mentions(rem), slot_mentions(rem)
                    tgt = {"day": rd[0][0] if rd else None, "slot": rs[0][0] if rs else None}
                    if poss[2]:
                        entry["style"] = "possessive"
                        entry["src_cell"] = {"person": poss[0], "day": poss[1], "slot": poss[2]}
                    else:
                        entry["style"] = "elided_possessive"  # "within $150 of Eric's"
                        entry["src_cell"] = {"person": poss[0],
                                             "day": poss[1] if poss[1] else tgt["day"],
                                             "slot": tgt["slot"]}
                    entry["tgt_cell"] = tgt
                elif JOIN_RE.search(s):
                    entry["style"] = "join"
                    rd, rs = day_mentions(s), slot_mentions(s)
                    entry["tgt_cell"] = {"day": rd[0][0] if rd else None,
                                         "slot": rs[0][0] if rs else None}
                    entry["src_cell"] = {"person": srcs[0], "day": entry["tgt_cell"]["day"],
                                         "slot": entry["tgt_cell"]["slot"]}
                else:
                    entry["style"] = "unparsed_dep"
                    rd, rs = day_mentions(s), slot_mentions(s)
                    entry["tgt_cell"] = {"day": rd[0][0] if rd else None,
                                         "slot": rs[0][0] if rs else None}
            parsed.append(entry)
        rounds.append({
            "t": t, "name": self_name, "query": q, "preamble_ok": preamble_ok,
            "sentences": parsed,
        })
    return {"id": row["id"], "base_name": base_name, "names": names,
            "D": len(row["base_person"]["daily_plans"]), "rounds": rounds, "row": row}


# ---------- chunk construction (mirrors run_travel.py:226-232, 343; no scratchpad) ----------

def format_plan(daily_plans, name):
    lines = [f"=== {name}'s Plan ==="]
    for d in daily_plans:
        lines.append(f"Day {d['days']}:")
        for k in ["current_city", "transportation", "breakfast", "attraction", "lunch", "dinner", "accommodation"]:
            lines.append(f"{k.replace('_', ' ').title()}: {d.get(k) or '-'}")
        lines.append("")
    return "\n".join(lines)


def build_chunks(ep):
    # ensure_ascii=False matches run_travel.py:226-232 / :281-292. It is load-bearing:
    # with the default escaping, non-ASCII venue names ("和缘浪漫民宿, Billings(Montana)")
    # are stored as \uXXXX, so any system that keeps chunks verbatim appears to "lose"
    # them under a literal-substring check while a system that re-renders parsed JSON
    # appears to keep them. That is an encoding artifact, not a memory-quality effect.
    row = ep["row"]
    chunks = [json.dumps({"name": ep["base_name"], "query": norm(row["base_person"]["query"]),
                          "is_base_person": True,
                          "final_plan": format_plan(row["base_person"]["daily_plans"], ep["base_name"])},
                         ensure_ascii=False)]
    for t, ans in enumerate(row["answers"], start=1):
        name = ep["names"][t]
        chunks.append(json.dumps({"name": name, "query": ep["rounds"][t - 1]["query"],
                                  "final_plan": format_plan(ans, name)}, ensure_ascii=False))
    return chunks  # chunks[k] is written after round k (k=0 base)


# ---------- 30-line BM25 ----------

STOP = set("i a an the for on of to with and or in at is are am be my that this it".split())


def toks(s):
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP]


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [toks(d) for d in docs]
        self.N = len(self.docs)
        self.avg = sum(len(d) for d in self.docs) / max(1, self.N)
        self.tf = [Counter(d) for d in self.docs]
        df = Counter()
        for d in self.docs:
            for w in set(d):
                df[w] += 1
        self.idf = {w: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for w, n in df.items()}
        self.k1, self.b = k1, b

    def score(self, query):
        qt = toks(query)
        out = []
        for i in range(self.N):
            s, L = 0.0, len(self.docs[i])
            for w in qt:
                if w in self.tf[i]:
                    f = self.tf[i][w]
                    s += self.idf.get(w, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * L / self.avg))
            out.append(s)
        return out


# ---------- main ----------

def main():
    rows = json.load(open(sys.argv[1]))
    dump_flagged = "--dump-flagged" in sys.argv
    eps = [parse_episode(r) for r in rows]

    C = Counter()
    flagged, ordering, kw_no_name_samples = [], [], []
    per_round_dep = []
    depth_ep = Counter()
    cell_chain = Counter()
    slot_pair = Counter()
    cross = Counter()
    src_named_cell = Counter()
    retr = defaultdict(list)
    comp = defaultdict(list)

    for ep in eps:
        chunks = build_chunks(ep)
        parents_of = {}  # round t -> set of source round indices (0 = base)
        name2round = {n: k for k, n in enumerate(ep["names"])}
        tgt_cells = defaultdict(set)  # round -> {(day,slot)} constrained cells (targets)
        for r in ep["rounds"]:
            C["rounds"] += 1
            C["preamble_ok"] += r["preamble_ok"]
            deps = [s for s in r["sentences"] if s["is_dep"]]
            C["sentences"] += len(r["sentences"])
            C["dep_sentences"] += len(deps)
            C["kw_no_name"] += sum(1 for s in r["sentences"] if s["kw_no_name"])
            kw_no_name_samples += [s["text"] for s in r["sentences"] if s["kw_no_name"]][:1]
            per_round_dep.append(len(deps))
            ps = set()
            for s in deps:
                C["style_" + (s["style"] or "none")] += 1
                if s["future_refs"]:
                    ordering.append((ep["id"], r["t"], s["text"][:100]))
                for n in s["srcs"]:
                    ps.add(name2round[n])
                if s["style"] == "possessive":
                    sc = s["src_cell"]
                    src_named_cell["explicit_day" if sc["day"] else "no_day"] += 1
                    src_named_cell["explicit_slot" if sc["slot"] else "no_slot"] += 1
                    if sc["slot"] and s["tgt_cell"] and s["tgt_cell"]["slot"]:
                        slot_pair[(sc["slot"], s["tgt_cell"]["slot"])] += 1
                        cross["cross_slot" if sc["slot"] != s["tgt_cell"]["slot"] else "same_slot"] += 1
                        if sc["day"] and s["tgt_cell"]["day"]:
                            cross["cross_day" if sc["day"] != s["tgt_cell"]["day"] else "same_day"] += 1
                if s["style"] == "unparsed_dep":
                    flagged.append((ep["id"], r["t"], s["text"][:140]))
                if s["tgt_cell"] and s["tgt_cell"]["day"] and s["tgt_cell"]["slot"]:
                    tgt_cells[r["t"]].add((s["tgt_cell"]["day"], s["tgt_cell"]["slot"]))
            parents_of[r["t"]] = ps

        # M2: round-level depth
        depth = {0: 0}
        for t in range(1, len(ep["rounds"]) + 1):
            depth[t] = 1 + max([depth[p] for p in parents_of.get(t, set())], default=-1) \
                if parents_of.get(t) else 0
        maxd = max(depth.values())
        depth_ep[maxd] += 1

        # cell-level chains: referenced source cell was itself a constrained target
        for r in ep["rounds"]:
            for s in r["sentences"]:
                if s["is_dep"] and s["src_cell"] and s["src_cell"]["day"] and s["src_cell"]["slot"]:
                    sp = name2round.get(s["src_cell"]["person"], None)
                    if sp and (s["src_cell"]["day"], s["src_cell"]["slot"]) in tgt_cells.get(sp, set()):
                        cell_chain["chained"] += 1
                    else:
                        cell_chain["root"] += 1

        # M4: simulated retrieval per dependent round
        for r in ep["rounds"]:
            t = r["t"]
            gold = parents_of[t]
            if not gold:
                continue
            avail = chunks[:t]  # chunks 0..t-1
            bm = BM25(avail)
            scores = bm.score(r["query"])
            rank = sorted(range(len(avail)), key=lambda i: -scores[i])
            for k in (1, 2, 3, 5):
                got = set(rank[:k])
                retr[f"bm25@{k}_recall"].append(len(gold & got) / len(gold))
                retr[f"bm25@{k}_full"].append(gold <= got)
            # name-match over full query (preamble incl.) vs constraint sentences only
            full_names = {name2round[n] for n in ep["names"][:t]
                          if re.search(r"\b" + n + r"\b", r["query"])}
            cons_text = " ".join(s["text"] for s in r["sentences"])
            cons_names = {name2round[n] for n in ep["names"][:t]
                          if re.search(r"\b" + n + r"\b", cons_text)}
            for tag, got in (("namefull", full_names), ("namecons", cons_names)):
                retr[tag + "_recall"].append(len(gold & got) / len(gold))
                retr[tag + "_prec"].append(len(gold & got) / len(got) if got else 1.0)
                retr[tag + "_n"].append(len(got))

            # M5 compression (chars as token proxy /4)
            full_mem = sum(len(c) for c in avail)
            top3 = sum(len(avail[i]) for i in rank[:3])
            par = sum(len(avail[i]) for i in gold)
            # needed cells: for each dep sentence with resolved src cell, one plan line
            cell_chars = 0
            for s in r["sentences"]:
                if s["is_dep"] and s["src_cell"]:
                    sc = s["src_cell"]
                    sp = name2round.get(sc["person"])
                    if sp is not None and sc["day"] and sc["slot"]:
                        plan = json.loads(avail[sp])["final_plan"]
                        m = re.search(r"Day %d:\n(?:.*\n)*?%s: (.*)" % (sc["day"], sc["slot"].replace("_", " ").title()), plan)
                        val = m.group(1) if m else "?"
                        cell_chars += len(f"{sc['person']} Day {sc['day']} {sc['slot']}: {val}\n")
                    else:
                        cell_chars += 80  # unresolved cell placeholder
            comp["full_mem"].append(full_mem)
            comp["bm25_top3"].append(top3)
            comp["gold_parents"].append(par)
            comp["gold_cells"].append(cell_chars)

    # ---------- report ----------
    def avg(x):
        return sum(x) / len(x) if x else float("nan")

    dep_rounds = sum(1 for d in per_round_dep if d > 0)
    rep = {
        "episodes": len(eps),
        "rounds": C["rounds"],
        "preamble_parse_rate": C["preamble_ok"] / C["rounds"],
        "constraint_sentences": C["sentences"],
        "dep_sentences": C["dep_sentences"],
        "dep_sentence_share": C["dep_sentences"] / C["sentences"],
        "rounds_with_dep": dep_rounds,
        "rounds_with_dep_share": dep_rounds / C["rounds"],
        "M1_keyword_but_no_name": C["kw_no_name"],
        "M1_styles": {k[6:]: v for k, v in C.items() if k.startswith("style_")},
        "M1_src_cell_explicitness": dict(src_named_cell),
        "M2_episode_max_depth_dist": dict(sorted(depth_ep.items())),
        "M2_cell_level_chains": dict(cell_chain),
        "M3_future_or_unknown_refs": len(ordering),
        "cross_slot_vs_same": dict(cross),
        "top_slot_pairs (src->tgt)": Counter({f"{a}->{b}": n for (a, b), n in slot_pair.items()}).most_common(10),
        "M4_retrieval": {k: round(avg(v), 4) for k, v in sorted(retr.items())},
        "M5_compression_chars_avg": {k: round(avg(v)) for k, v in comp.items()},
        "M5_ratios": {
            "cells/full_mem": round(avg(comp["gold_cells"]) / avg(comp["full_mem"]), 4),
            "cells/bm25_top3": round(avg(comp["gold_cells"]) / avg(comp["bm25_top3"]), 4),
            "parents/full_mem": round(avg(comp["gold_parents"]) / avg(comp["full_mem"]), 4),
        },
        "flagged_unparsed_dep": len(flagged),
    }
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    if dump_flagged:
        print("\n--- flagged (unparsed dependency style) ---")
        for f in flagged[:25]:
            print(f)
        print("\n--- keyword-but-no-name samples ---")
        for s in kw_no_name_samples[:25]:
            print(repr(s[:140]))
        print("\n--- future/unknown name refs ---")
        for f in ordering[:25]:
            print(f)


if __name__ == "__main__":
    main()
