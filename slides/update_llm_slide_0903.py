#!/usr/bin/env python3
"""Refresh the 'Results: the LLM runtime' slide of 8-30_huaman_edit.pptx with the round-3
figure and text (80 episodes per main cell).  Rebuilds only that slide's picture and body."""
import json
import os

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIG = os.path.join(HERE, "figs_0830")
SRC = os.path.join(HERE, "8-30_huaman_edit.pptx")
BLACK = RGBColor(0, 0, 0); BODY_FONT = "Georgia"; LEFT, CW = 0.38, 9.24
a = json.load(open(os.path.join(ROOT, "results/real/hm3/round3/paired_analysis.json")))
prs = Presentation(SRC)
slide = next(s for s in prs.slides if any(sh.has_text_frame and ("the LLM runtime" in sh.text_frame.text) for sh in s.shapes))
for sh in list(slide.shapes):
    if sh.shape_type == 13 or (sh.has_text_frame and not ("the LLM runtime" in sh.text_frame.text)):
        sh._element.getparent().remove(sh._element)
pic = slide.shapes.add_picture(os.path.join(FIG, "v3_api.png"), Inches(0.45), Inches(0.62), width=Inches(9.10))
y = (pic.top + pic.height) / 914400 + 0.14
tb = slide.shapes.add_textbox(Inches(LEFT), Inches(y), Inches(CW), Inches(5.45 - y)); tf = tb.text_frame; tf.word_wrap = True


def line(txt, bold=False, first=False):
    para = tf.paragraphs[0] if first else tf.add_paragraph(); para.line_spacing = 1.3
    r = para.add_run(); r.text = txt; r.font.size = Pt(12); r.font.bold = bold; r.font.color.rgb = BLACK; r.font.name = BODY_FONT


def cell(d, k):
    return a[d]["cells"][k]["ees"]


tr, se = a["travel"]["main_judgement"], a["search"]["main_judgement"]
a4 = json.load(open(os.path.join(ROOT, "results/real/hm3/round4/paired_analysis.json")))
t4, s4 = a4["travel"]["graph_closed/compact - full/verbose(r3)"], a4["search"]["graph_closed/compact - full/verbose(r3)"]
line("Selection × serialization; 20 episodes per cell in rounds 1–2, 63–69 per main cell in rounds 3–4:", True, True)
line("Graph selection needs 70–80% less input than the full context in every round. At 20 episodes per cell the two rounds "
     "gave opposite verdicts; at 64 the picture is stable.")
line(f"Round 4 (graph selection closed over the objects its witnesses name): Travel {t4['ees_a']:.2f} against full context "
     f"{t4['ees_b']:.2f}, paired {t4['mean']:+.2f} [{t4['ci_lo']:+.2f}, {t4['ci_hi']:+.2f}]; Search {s4['ees_a']:.2f} against "
     f"{s4['ees_b']:.2f}, {s4['mean']:+.2f} [{s4['ci_lo']:+.2f}, {s4['ci_hi']:+.2f}]. The closure recovered half of Travel's gap; "
     "the rest is the runtime's use of a minimal evidence set. The best LLM cell stays far below the deterministic graph.")
prs.save(SRC)
print("LLM slide refreshed")
