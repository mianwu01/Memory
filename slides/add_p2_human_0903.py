#!/usr/bin/env python3
"""Insert the P2 (memory maintenance, Hidden Mechanism v3) block into
slides/8-30_huaman_edit.pptx, in that deck's register: a claim-sentence title,
one figure and one plain paragraph; a 'Test ... on ...' prose slide; 'Results'
slides with a figure and short labelled lines; a 'Setting' table.

Placed after the E0 slide and before the memory-poisoning block, so the deck
reads: formulation → E0 → P2 (5 slides) → P3.  Backs the deck up once to
8-30_huaman_edit.pre-p2.bak.  Figures from fig_p2v3_0903.py.
"""
import os
import shutil

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figs_0830")
SRC = os.path.join(HERE, "8-30_huaman_edit.pptx")
BAK = os.path.join(HERE, "8-30_huaman_edit.pre-p2.bak")
if not os.path.exists(BAK):
    shutil.copy2(SRC, BAK)

BLACK = RGBColor(0, 0, 0)
BODY_FONT = "Georgia"
LEFT, CW = 0.38, 9.24

prs = Presentation(SRC)
titles = [next((sh.text_frame.text for sh in s.shapes if sh.has_text_frame and sh.text_frame.text.strip()), "")
          for s in prs.slides]
assert not any("maintenance" in t for t in titles), "P2 slides already present"
ANCHOR = next(i for i, t in enumerate(titles) if t.startswith("Conditioning on write"))
BLANK = ([l for l in prs.slide_layouts if l.name.upper() == "BLANK"] or [prs.slide_layouts[6]])[0]


def add_slide(title, size=20):
    s = prs.slides.add_slide(BLANK)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    tb = s.shapes.add_textbox(Inches(LEFT), Inches(0.18), Inches(CW), Inches(0.44))
    r = tb.text_frame.paragraphs[0].add_run()
    r.text = title; r.font.size = Pt(size); r.font.bold = True; r.font.color.rgb = BLACK; r.font.name = BODY_FONT
    return s


def add_text(slide, y, h, lines, size=12.0, spacing=1.35):
    tb = slide.shapes.add_textbox(Inches(LEFT), Inches(y), Inches(CW), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    for i, line in enumerate(lines):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.line_spacing = spacing
        txt, bold = (line, False) if isinstance(line, str) else line
        r = para.add_run(); r.text = txt
        r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = BLACK; r.font.name = BODY_FONT
    return tb


def add_pic(slide, name, left, top, width):
    return slide.shapes.add_picture(os.path.join(FIG, name), Inches(left), Inches(top), width=Inches(width))


def below(pic, gap=0.12):
    return (pic.top + pic.height) / 914400 + gap


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


new = []

# ---- 1. the object: a hidden mechanism behind memory maintenance
s = add_slide("Memory maintenance gives us a hidden mechanism to learn")
pic = add_pic(s, "v3_task.png", 0.45, 0.70, 9.10)
add_text(s, below(pic), 1.5, [
    "One object changes; other memories become stale through policies that never appear in the query or the "
    "state and only show up in what happened after earlier changes. The agent has to find them in the history "
    "and repair with transactions that each cost something, so a missed repair and an unnecessary write both fail.",
], size=12.5)
notes(s, "Effectiveness part. The travel result from last time showed structured memory and compression work; it "
         "could not show that learned structure is needed, because the query named every affected cell. Here the "
         "query names only the source, the mechanism is hidden in earlier outcomes, and the answer must be executed.")
new.append(s)

# ---- 2. test maintenance on four synthetic memories
s = add_slide("Test maintenance on four synthetic memories")
add_text(s, 0.85, 4.5, [
    "LLM:  DeepSeek-v4-flash for the runtime arm (Travel and Search); every method is also replicated "
    "deterministically on all four.",
    "The four generators vary the mechanism that makes a memory stale",
    ("Travel", True),
    "A flight moves. Whether the transfer follows on its own, by how many minutes, whether the hotel keeps a "
    "late-arrival flag, whether the restaurant shifts or cancels, and whether a bundle must be re-booked all "
    "depend on the provider, hotel, restaurant and vendor.",
    ("Shopping", True),
    "A base item is replaced. Accessory compatibility, promotion eligibility and the budget rule decide which "
    "lines are swapped, dropped or re-priced.",
    ("Search", True),
    "A document is published or retracted. Trust weights, de-duplication and the treatment of unresolved "
    "children decide which claim verdicts flip.",
    ("Formal", True),
    "A definition is bumped or activated. Scope shadowing and per-lemma sensitivity decide which proofs need "
    "re-checking along the dependency graph.",
    "Every hidden policy is recoverable from one earlier outcome in the history. Methods share the same "
    "training data: lookups, kNN, a conservative superset, black-box predictors, a relational program "
    "learner, the learned graph, and two oracles. An eight-check gate ran before any test or API output.",
], size=11.5, spacing=1.22)
notes(s, "Same shape as the auditing setup slide: one LLM line, one framing line, one paragraph per setup. The "
         "identifiability sentence matters: the generator keeps adding earlier interventions until the history "
         "parser can recover every policy the oracle used, then adds distractor witnesses for other entities.")
new.append(s)

# ---- 3. results: who completes the repair
s = add_slide("Results", size=18)
pic = add_pic(s, "v3_methods.png", 0.55, 0.62, 8.90)
add_text(s, below(pic, 0.14), 1.7, [
    ("Fresh test seeds, executable exact success:", True),
    "Lookups, kNN and the conservative superset fail; the two oracles reach 1.0. Every extra write is fatal, "
    "and the gold answer changes when only the history changes.",
    "The learned graph beats every black box in all four tasks. Given the same history-parsed policies, the "
    "per-object program learner ties it on Shopping and Search and leads on Formal; the graph leads on Travel, "
    "where values compose along a chain.",
], size=12.0, spacing=1.3)
notes(s, "What we can write: composable relational structure plus policies read from history is what completes "
         "repair. What we cannot write: that the causal-graph form is necessary in all four tasks. Shopping is the "
         "v3.2 generator: the first version leaked its policies through the initial state and failed the gate.")
new.append(s)

# ---- 4. results: the LLM runtime
s = add_slide("Results: the LLM runtime", size=18)
pic = add_pic(s, "v3_api.png", 0.45, 0.62, 9.10)
add_text(s, below(pic, 0.14), 1.7, [
    ("Selection × serialization, 20 episodes per cell, two prompt rounds:", True),
    "Graph selection with compact serialization needs 68–80% less input than the full context.",
    "Its exact success is statistically indistinguishable from the full context: the paired intervals cross zero "
    "in both rounds. The best LLM cell (0.70) stays far below the deterministic graph on the same episodes (0.99).",
], size=12.0, spacing=1.3)
notes(s, "The point rule we pre-registered flipped between the two rounds, so we report the paired bootstrap. "
         "Twenty episodes per cell resolve differences of about 0.25 and no more; a confirmatory selection "
         "claim needs about 80 per cell or a stronger runtime.")
new.append(s)

# ---- 5. setting table
s = add_slide("Setting", size=18)
rows = [
    ("", "Deterministic replication", "LLM runtime"),
    ("LLM", "—", "DeepSeek-v4-flash, T=0"),
    ("Tasks", "Travel · Shopping v3.2 · Search · Formal", "Travel · Search"),
    ("Data", "train 200 / test 60 per seed, seeds 20–22", "20 test episodes, seed 10"),
    ("Methods", "5 killers · 4 black boxes · program learner · learned graph · 2 oracles", "5 selections × 2 serializations"),
    ("Metric", "executable exact success", "executable exact success, input tokens"),
    ("Gate", "8 checks on dev seeds 0–2 before any output", "same gate; API only where it passed"),
    ("Cost", "CPU only", "2 rounds × 400 cells, $12.9"),
]
tbl = s.shapes.add_table(len(rows), 3, Inches(0.8), Inches(0.95), Inches(8.4), Inches(3.4)).table
for w, col in zip((1.4, 3.7, 3.3), tbl.columns):
    col.width = Inches(w)
for i, row in enumerate(rows):
    for j, val in enumerate(row):
        cell = tbl.cell(i, j); cell.text = val
        for para in cell.text_frame.paragraphs:
            for r in para.runs:
                r.font.size = Pt(11); r.font.name = BODY_FONT; r.font.bold = (i == 0 or j == 0)
notes(s, "Backup: the exact settings behind the two results slides.")
new.append(s)

sld = prs.slides._sldIdLst
items = list(sld)
new_items = items[-len(new):]
for it in new_items:
    sld.remove(it)
for k, it in enumerate(new_items):
    sld.insert(ANCHOR + 1 + k, it)
prs.save(SRC)
print("saved", SRC, "slides:", len(prs.slides))
