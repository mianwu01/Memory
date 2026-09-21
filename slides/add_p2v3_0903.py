#!/usr/bin/env python3
"""Insert the P2 round-2 (Hidden Mechanism v3) slides into slides/8-30.pptx.

Keeps every existing slide untouched. Adds five slides directly after
'Same graph, forward: compact memory (PASS)' so the Request 1 block reads:
choosing → pieces → what we did → compact memory PASS → round 2 (five slides)
→ Request 2.  Backs the deck up once to 8-30.pre-v3-0903.bak.

Numbers from docs/hidden-mechanism-v3-results.md, results/development/hm3/gate*.json,
results/real/hm3/round2/{det_test2.json, llm_summary.json, paired_bootstrap.json}.
"""
import os
import shutil

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figs_0830")
SRC = os.path.join(HERE, "8-30.pptx")
BAK = os.path.join(HERE, "8-30.pre-v3-0903.bak")
if not os.path.exists(BAK):
    shutil.copy2(SRC, BAK)

BLACK = RGBColor(0, 0, 0)
GRAY = RGBColor(0x55, 0x55, 0x55)
BODY_FONT = "Georgia"
LEFT, CW = 0.38, 9.24

prs = Presentation(SRC)
titles = [next((sh.text_frame.text for sh in s.shapes if sh.has_text_frame and sh.text_frame.text.strip()), "")
          for s in prs.slides]
assert not any(t.startswith("Round 2") for t in titles), "round-2 slides already present"
ANCHOR = next(i for i, t in enumerate(titles) if t.startswith("Same graph, forward"))
BLANK = ([l for l in prs.slide_layouts if l.name.upper() == "BLANK"] or [prs.slide_layouts[6]])[0]


def add_slide(title, tag=None, title_size=20):
    s = prs.slides.add_slide(BLANK)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    tb = s.shapes.add_textbox(Inches(LEFT), Inches(0.18), Inches(CW), Inches(0.55))
    r = tb.text_frame.paragraphs[0].add_run()
    r.text = title; r.font.size = Pt(title_size); r.font.bold = True
    r.font.color.rgb = BLACK; r.font.name = BODY_FONT
    if tag:
        tb = s.shapes.add_textbox(Inches(6.4), Inches(0.02), Inches(3.35), Inches(0.3))
        p = tb.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.RIGHT
        r = p.add_run(); r.text = tag
        r.font.size = Pt(10); r.font.italic = True; r.font.color.rgb = GRAY; r.font.name = BODY_FONT
    return s


def add_text(slide, y, lines, h=4.4, leading=1.4):
    tb = slide.shapes.add_textbox(Inches(LEFT), Inches(y), Inches(CW), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    for i, line in enumerate(lines):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.line_spacing = leading
        txt, sz, bold = line[:3]
        col = line[3] if len(line) == 4 else BLACK
        r = para.add_run(); r.text = txt
        r.font.size = Pt(sz); r.font.bold = bold; r.font.color.rgb = col; r.font.name = BODY_FONT
    return tb


def add_pic(slide, name, left, top, width):
    pic = slide.shapes.add_picture(os.path.join(FIG, name), Inches(left), Inches(top), width=Inches(width))
    return pic


def below(pic, gap=0.10):
    return (pic.top + pic.height) / 914400 + gap


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


new = []

# 1 — why the travel result was not enough, and the round-2 task
s = add_slide("Round 2 — what the travel PASS did and did not show", tag="effectiveness · the audit")
add_text(s, 0.78, [
    ("Travel queries name person, day and slot, so the strongest simple method is memory[(person, day, slot)] = "
     "new value. Four lookup baselines reach a propagation sufficient-mask rate of 1.0. The PASS therefore "
     "shows that structured memory and compression work; it does not show that learned causal structure "
     "is needed.", 11.5, False),
    ("", 5, False),
    ("·  the inheritance decoder tests constrained editing; a real causal memory must let one change "
     "invalidate downstream state", 11, False),
    ("·  selection and serialization were bundled, so the 39.55% input reduction is not attributable to the graph",
     11, False),
    ("·  the real-API round used a conservative reachability solver and a retry policy that re-asked "
     "semantic failures", 11, False),
    ("", 5, False),
    ("Round 2 restates the task:  learned hidden mechanism → causal memory maintenance → executable "
     "downstream repair. The query exposes only the source; the answer is a set of non-idempotent "
     "transactions; the score is executable exact success.", 11.5, True)])
notes(s, "Say plainly what the travel PASS established and what it could not. Then the restated task in "
         "one line: hidden mechanism, maintenance, executable repair.")
new.append(s)

# 2 — the task and the four mechanisms
s = add_slide("Round 2 — the task and the four hidden mechanisms", tag="components")
pic = add_pic(s, "v3_task.png", 0.45, 0.70, 9.10)
add_text(s, below(pic), [
    ("Four generators with different mechanisms, each hidden parameter recoverable from one outcome witness "
     "in the history (identifiability enforced by construction; distractor witnesses added):", 10.8, False),
    ("Travel — provider auto-rebook and buffer, hotel late cutoff, restaurant shift-or-cancel, bundle linkage.  "
     "Shopping — compatibility factor graph, promotion hypergraph, budget re-optimisation.  "
     "Search — trust weights, dedup, unresolved-child policy under a window.  "
     "Formal — versioned scope binding, shadowing, sensitivity along a proof DAG.", 10.8, False)], h=1.7, leading=1.25)
notes(s, "The figure is the whole task in one strip: intervention, stale detection through the hidden mechanism, "
         "witness reads, minimal transactions. Every write costs, so a superset fails and a lookup that writes "
         "to an auto-updated object is illegal.")
new.append(s)

# 3 — gate
s = add_slide("Round 2 — the zero-API gate", tag="eight checks, thresholds frozen before any output")
add_text(s, 0.80, [
    ("C1 query names only the source · C2 train/dev/test disjoint · C3 same query and visible summary, "
     "different history → different gold (pairs differ in 77–100%) · C4 lookup, kNN, superset ≤ 0.50 · "
     "C5 oracle and history-only oracle = 1.0 · C6 one extra idempotent write breaks the endpoint in "
     "180/180 episodes · C7 learned graph above every black box on ≥ 2/3 seeds · C8 the strongest "
     "relational learner has run.", 11.2, False),
    ("", 5, False),
    ("Travel, Search, Formal pass all eight.", 11.5, True),
    ("Shopping v3 fails C4 alone: the visible-regime table copies 0.567 and kNN 0.511, because most episodes "
     "carry one hidden decision and the initial state is consistent with the hidden policies.", 11.5, False),
    ("Shopping v3.2 decouples the initial state from the policies (random promotion status, random "
     "accessories; the store re-evaluates only on a relevant change) → table 0.461, kNN 0.239, all eight pass.",
     11.5, False),
    ("", 5, False),
    ("Disclosed: four rounds of feature revision on the relational learners on dev seed 0 before the gate; "
     "test seeds and API outputs came after.", 10.8, False, GRAY)])
notes(s, "The gate is the benchmark's validity certificate. Read the C3 and C6 lines: history is load-bearing "
         "and non-idempotence bites. Shopping needed the v3.2 fix; say why.")
new.append(s)

# 4 — who completes the repair
s = add_slide("Round 2 — who completes the repair", tag="fresh test seeds 20–22 · train 120–122")
pic = add_pic(s, "v3_methods.png", 0.50, 0.68, 8.60)
add_text(s, below(pic), [
    ("Lookups and the conservative superset collapse on the executable endpoint; both oracles reach 1.0. "
     "The learned graph beats every black box in every task. The per-object relational learner, given the "
     "same history-parsed regimes and local rules, ties the graph on Shopping and Search and is ahead on "
     "Formal (0.89 vs 0.72); the graph keeps its lead on Travel (0.88 vs 0.67), where values compose along a "
     "multi-hop numeric chain.", 11.2, False),
    ("Claim we can make: composable relational structure plus history-parsed regimes is what completes "
     "repair. Claim we cannot make: the causal-graph form is necessary in all four tasks.", 11.2, True)],
    h=1.6, leading=1.25)
notes(s, "This is the honest centre of the round. Killers fail, oracles pass, structure learners succeed; "
         "the graph's exclusive advantage is the compositional Travel chain.")
new.append(s)

# 5 — LLM runtime
s = add_slide("Round 2 — the LLM runtime: selection × serialization", tag="deepseek-v4-flash · 2 rounds × 400 cells · $12.9")
pic = add_pic(s, "v3_api.png", 0.45, 0.68, 9.10)
add_text(s, below(pic), [
    ("Cells: exact / source / graph / program / full selection × verbose / compact serialization, 20 test "
     "episodes each, Travel and Search. Round 1 asked for the JSON directly; round 2 (pre-registered) adds a "
     "policy-ledger step before the answer.", 11.0, False),
    ("The pre-registered point rule flipped between rounds (round 1: Search pass, Travel fail; round 2: the "
     "reverse). Paired per-episode bootstraps over both rounds cross zero for every selection and "
     "serialization contrast, so non-inferiority on exact success is not established at 20 episodes per cell. "
     "What holds: graph/compact needs 68–80% less input, and the best LLM cell (0.65 / 0.70) sits far below "
     "the deterministic graph on the same episodes (0.86 / 0.99).", 11.0, False)], h=1.7, leading=1.25)
notes(s, "Selection is measured on the runtime that will use it; the runtime is the bottleneck. The thinking "
         "mode probe exhausted its reasoning budget with no answer, so a stronger runtime or 80 episodes per "
         "cell is the next step.")
new.append(s)

# 6 — decisions
s = add_slide("Round 2 — what we can write, and your decisions", tag="P2 · effectiveness")
add_text(s, 0.82, [
    ("Can write", 12.5, True),
    ("·  the v3 benchmark makes lookup, kNN and superset fail on an executable endpoint that two oracles "
     "complete; history is load-bearing (C3) and every extra write is fatal (C6)", 11, False),
    ("·  learned relational structure with history-parsed regimes reaches 0.72–1.00 exact success on fresh "
     "seeds; black boxes stay at 0.26–0.75", 11, False),
    ("·  graph selection cuts LLM input by 68–80% at statistically indistinguishable exact success", 11, False),
    ("Cannot write", 12.5, True),
    ("·  that learned causal structure is necessary on all four tasks — Formal favours the per-object learner", 11, False),
    ("·  that the LLM runtime already exploits the learned structure — its best cell is 0.70", 11, False),
    ("Decisions", 12.5, True),
    ("1 ·  keep Shopping v3.2 as the version of record and drop v3?", 11, False),
    ("2 ·  API power: 80 episodes per cell (≈ $25 per domain) or a stronger runtime?", 11, False),
    ("3 ·  is the Formal gap (0.72 vs 0.89) a method problem to solve before submission, or a finding to report?",
     11, False)])
notes(s, "Close on decisions only. Three questions, each with a cost attached.")
new.append(s)

# move the new slides to sit directly after the anchor
sld = prs.slides._sldIdLst
items = list(sld)
new_items = items[-len(new):]
for it in new_items:
    sld.remove(it)
for k, it in enumerate(new_items):
    sld.insert(ANCHOR + 1 + k, it)
prs.save(SRC)
print("saved", SRC, "slides:", len(prs.slides))
