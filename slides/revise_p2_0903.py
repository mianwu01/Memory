#!/usr/bin/env python3
"""Rebuild the P2 block of slides/8-30_huaman_edit.pptx in the style of the P3 slides
(2026-09-03, second review): problem -> setting -> result -> analysis -> setting -> result,
one dominant figure per slide, one or two sentences below it, details in the speaker notes.

  6  Can learned temporal structure make agent memory more useful?   (problem)
  7  GRACE as a memory module in MemoryArena                          (setting 1)
  8  The learned graph works as a memory-selection structure          (result 1)
  9  But Travel did not require discovering the dependency            (analysis)
 10  Hide the dependency and require exact repair                     (setting 2)
 11  When dependencies are hidden, learned relational structure matters (result 2)
 12  Setting                                                          (unchanged backup table)
 ... P3 block unchanged ...
 17  Appendix — the LLM runtime                                        (old slide, retitled, moved)

Always rebuilds from the pristine human deck, kept once as 8-30_huaman_edit.pre-p2rev.bak,
so it can be re-run after editing the figures.  Figures from fig_p2rev_0903.py.
"""
import os
import shutil

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figs_0830")
SRC = os.path.join(HERE, "8-30_huaman_edit.pptx")
BAK = os.path.join(HERE, "8-30_huaman_edit.pre-p2rev.bak")
if not os.path.exists(BAK):
    shutil.copy2(SRC, BAK)

BLACK = RGBColor(0, 0, 0)
BODY_FONT = "Georgia"
LEFT, CW = 0.38, 9.24
CAP_SIZE = 14.0  # the deck's default text size, used by the P3 caption paragraphs

prs = Presentation(BAK)


def title_of(slide):
    return next((sh.text_frame.text for sh in slide.shapes if sh.has_text_frame and sh.text_frame.text.strip()), "")


titles = [title_of(s) for s in prs.slides]
I_E0 = next(i for i, t in enumerate(titles) if t.startswith("Conditioning on write"))
I_OLD = [next(i for i, t in enumerate(titles) if t.startswith("Memory maintenance gives us")),
         next(i for i, t in enumerate(titles) if t.startswith("Test maintenance on four synthetic")),
         next(i for i, t in enumerate(titles) if t == "Results" and i > I_E0)]
I_LLM = next(i for i, t in enumerate(titles) if t.startswith("Results: the LLM runtime"))
assert I_OLD == [I_E0 + 1, I_E0 + 2, I_E0 + 3] and I_LLM == I_E0 + 4, (I_E0, I_OLD, I_LLM)
BLANK = ([l for l in prs.slide_layouts if l.name.upper() == "BLANK"] or [prs.slide_layouts[6]])[0]


def add_slide(title, size=20):
    s = prs.slides.add_slide(BLANK)
    # python-pptx names a new slide part by position, which collides with surviving parts after a
    # deletion; take the first unused name instead so the saved zip has no duplicate entries
    s.part.partname = prs.part.package.next_partname("/ppt/slides/slide%d.xml")
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    tb = s.shapes.add_textbox(Inches(LEFT), Inches(0.18), Inches(CW), Inches(0.44))
    r = tb.text_frame.paragraphs[0].add_run()
    r.text = title; r.font.size = Pt(size); r.font.bold = True; r.font.color.rgb = BLACK; r.font.name = BODY_FONT
    return s


def add_caption(slide, y, text, size=CAP_SIZE, h=0.9, spacing=1.35):
    tb = slide.shapes.add_textbox(Inches(LEFT), Inches(y), Inches(CW), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    para = tf.paragraphs[0]; para.line_spacing = spacing
    r = para.add_run(); r.text = text
    r.font.size = Pt(size); r.font.bold = False; r.font.color.rgb = BLACK; r.font.name = BODY_FONT
    return tb


def add_pic(slide, name, left, top, width):
    return slide.shapes.add_picture(os.path.join(FIG, name), Inches(left), Inches(top), width=Inches(width))


def below(pic, gap=0.16):
    return (pic.top + pic.height) / 914400 + gap


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def delete_slide(index):
    lst = prs.slides._sldIdLst
    sid = lst[index]
    prs.part.drop_rel(sid.rId)
    lst.remove(sid)


def move_slide(old_index, new_index):
    lst = prs.slides._sldIdLst
    sid = lst[old_index]
    lst.remove(sid)
    lst.insert(new_index, sid)


# ------------------------------------------------------------------ 1. remove the three old P2 slides
for i in sorted(I_OLD, reverse=True):
    delete_slide(i)
assert title_of(prs.slides[I_E0 + 1]).startswith("Results: the LLM runtime")

new = []

# ------------------------------------------------------------------ 2. problem
s = add_slide("Can learned temporal structure make agent memory useful?", size=18)
pic = add_pic(s, "p2_problem.png", 0.45, 0.72, 9.10)
add_caption(s, below(pic), "Memory holds many cells written over past interactions, and the current decision needs only "
                           "some of them. Can a learned dependency structure tell the agent what to remember for the "
                           "current decision?")
notes(s, "Forward use of the same learned graph from the formulation slide. In MemoryArena travel the memory is "
         "persons × days × 7 itinerary slots written round by round, and the agent must emit a complete itinerary "
         "every round, so every slot is a target whose ancestors must survive selection. This is Requirement 1 from "
         "8/21: effectiveness on a real benchmark or agentic codebase, one or two representative setups.")
new.append(s)

# ------------------------------------------------------------------ 3. setting 1: GRACE x MemoryArena
s = add_slide("GRACE as a memory module in MemoryArena")
pic = add_pic(s, "p2_pipeline.png", 0.45, 0.68, 9.10)
add_caption(s, below(pic, 0.14), "GRACE learns temporal dependencies among the seven itinerary slots from past "
                                 "trajectories, and the learned ancestors decide which memory cells the current query "
                                 "needs. MemoryArena is an existing agentic benchmark in which stored memory is the only "
                                 "cross-round channel; our system registers as one more plug-in memory and is scored by "
                                 "the official scorer.", size=12.5)
notes(s, "GRACE (causalts) runs on per-regime multi-trial subsamples; the artifact of record is learned from the 260 "
         "episodes outside the held-out IDs (7 slot types × lag ≤ 3). Learned edges: breakfast, lunch, dinner and "
         "accommodation depend on their own earlier values at lags 1–3, and lunch on breakfast at lag 3; city, "
         "transportation and attraction are constant within a trip, so one retained copy reconstructs every round. "
         "Selection = ancestor slot types of the query's targets, the last max-lag writers, one copy of constants; "
         "then the compact target-delta serialization frozen on dev IDs 101–103. MemoryArena: persistent state "
         "drives later actions, memory is the only cross-round channel, a plug-in registry puts our system beside "
         "13 built-in memory systems on the official scorer; upstream has no license, so we register at runtime "
         "and never vendor. Agent: ReAct on deepseek-v4-flash, 12 max steps, shared decoder, env and tools across "
         "all arms. Discovery alternatives verified by implementation: CDNOTS+ as baseline; UnCLe, CUTS+, AVICI "
         "excluded.")
new.append(s)

# ------------------------------------------------------------------ 4. result 1: cards
s = add_slide("The learned graph works as a memory-selection structure", size=18)
pic = add_pic(s, "p2_cards.png", 0.45, 0.74, 9.10)
add_caption(s, below(pic), "On MemoryArena Travel, the learned graph works as a memory-selection structure and passes "
                           "the frozen effectiveness criterion.")
notes(s, "Held-out IDs 111–120; the graph was learned without them; four arms share model, decoder, steps and "
         "tools. Long context (not on the slide): 92.42% PS at 2.06M input tokens. Paired episode-mean PS: graph "
         "minus no-graph −1.43 [−4.29, 0.00], W/T/L 0/9/1; graph minus BM25 +19.80 [+10.04, +29.70]; graph minus "
         "long context +1.07 [−4.29, +7.50]. Frozen criterion: PS loss ≤ 5 points and input reduction ≥ 30% versus "
         "the no-graph arm → PASS. Boundary: graph selection and compact serialization are bundled in this arm. "
         "Earlier stages, all kept: IDs 1–5 gave PS 0% on both graph arms (strict full-plan denominator; 31/37 "
         "persons failed only on slots the query never asked to change) → the inheritance decoder; IDs 101–110 "
         "passed the main judgement against BM25 (+16.55) but cut input by only 14.7% against the frozen 30% → "
         "compact serialization → this round.")
new.append(s)

# ------------------------------------------------------------------ 5. analysis: the loophole
s = add_slide("But Travel did not require discovering the dependency")
pic = add_pic(s, "p2_audit.png", 0.45, 0.82, 9.10)
add_caption(s, below(pic, 0.20), "The PASS shows useful structured memory and compression, but the query itself "
                                 "already reveals which cells matter.")
notes(s, "The 9/3 audit. Travel queries name person, day and slot, so memory[(person, day, slot)] = new value "
         "already reads every affected cell: four lookup baselines reach a propagation sufficient-mask rate of "
         "1.0. So the PASS shows that structured storage and compression work; it cannot show that learned "
         "structure is needed. Two further points: the inheritance decoder tests constrained editing rather "
         "than propagation, and selection and serialization are bundled, so the token reduction is not "
         "attributable to the graph alone. The utility result stands; what is missing is attribution, so the "
         "next experiment hides the dependency.")
new.append(s)

# ------------------------------------------------------------------ 6. setting 2: hidden mechanism
s = add_slide("Hide the dependency and require exact repair")
pic = add_pic(s, "p2_hm3.png", 0.45, 0.68, 9.10)
add_caption(s, below(pic, 0.14), "The query names only what changed; the dependencies must be inferred from earlier "
                                 "outcomes.")
notes(s, "Hidden Mechanism v3. An episode is (history, pre-state, intervention, oracle actions, post-state, "
         "receipt); methods see only history, pre-state and intervention. The query names the source object and "
         "its new value and nothing else (gate C1). The answer is a set of non-idempotent transactions "
         "{op, object_id, expected_revision, payload}: each write bumps the revision, consumes a change token, "
         "charges a fee and drops the price lock even when it rewrites the same value, and a stale "
         "expected_revision is illegal. Score: executable exact success = all transactions legal, post-state equals "
         "the oracle's, receipt equals the oracle's; so a missed repair and an extra write both fail (one extra "
         "idempotent write fails 180/180). Every hidden parameter is recoverable from one earlier outcome witness, "
         "never from a policy statement; the generator keeps adding earlier interventions until every parameter "
         "the oracle consults is recoverable, then adds distractor witnesses for other entities. Travel: provider "
         "auto-rebook and buffer, hotel late cutoff, restaurant shift-or-cancel, bundle linkage. Shopping: "
         "compatibility, promotion strictness, budget (v3.2 starts promotions and accessories at random so the "
         "initial state does not leak the policies). Search: trust weight per source class, de-duplication, "
         "unresolved-child policy. Formal: section shadowing, per-lemma sensitivity along a proof DAG. An "
         "eight-check zero-API gate ran on dev seeds before any test or API output.")
new.append(s)

# ------------------------------------------------------------------ 7. result 2: the chart
s = add_slide("When dependencies are hidden, learned relational structure matters", size=17)
pic = add_pic(s, "p2_hm3_results.png", 0.55, 0.66, 8.90)
add_caption(s, below(pic, 0.14), "The learned graph beats the strongest black-box predictor in all four environments. "
                                 "Its clearest advantage is Travel, where effects compose over multiple hops.")
notes(s, "Fresh test seeds 20–22, train 200 / eval 60 per seed, mean of three, executable exact success. Lookups, "
         "kNN and the conservative superset stay at or below 0.46 in every environment; both oracles reach 1.0. "
         "The strongest black box is the GNN with history-parsed estimates in all four. Program learner "
         "(regularised) 0.67 / 0.78 / 0.99 / 0.89; learned graph 0.88 / 0.76 / 1.00 / 0.72 on Travel / Shopping "
         "v3.2 / Search / Formal. If asked about Formal: yes, this is an important boundary. The explicit graph "
         "form is not necessary everywhere; what the data support is learned relational structure with policies "
         "read from history, and the graph's exclusive lead is the multi-hop numeric chain. LLM runtime "
         "(appendix): at about 64 episodes per cell (API rounds 3–4), graph selection with witness closure "
         "cuts input by 70–74% at an exact-success cost of 0.10–0.19 on deepseek-v4-flash; non-inferiority at "
         "the −0.10 margin is not met, and the LLM stays far below the deterministic executor.")
new.append(s)

# ------------------------------------------------------------------ 8. place the new slides after E0
lst = prs.slides._sldIdLst
items = list(lst)
new_items = items[-len(new):]
for it in new_items:
    lst.remove(it)
for k, it in enumerate(new_items):
    lst.insert(I_E0 + 1 + k, it)

# ------------------------------------------------------------------ 9. the old LLM slide (rounds 1-2) goes;
# a fresh appendix slide with API rounds 3-4 (about 64 episodes per cell) is added at the end
I_LLM = I_E0 + 1 + len(new)
assert title_of(prs.slides[I_LLM]).startswith("Results: the LLM runtime")
delete_slide(I_LLM)

# the P2 setting table: LLM column now covers four API rounds
setting = prs.slides[I_LLM]
assert title_of(setting) == "Setting"
tbl = next(sh for sh in setting.shapes if getattr(sh, "has_table", False) and sh.has_table).table
for r_i, c_i, txt in ((3, 2, "20 test episodes per cell (rounds 1–2); ≈ 64 per cell (rounds 3–4)"),
                      (4, 2, "5 selections × 2 serializations; round 4 adds witness closure"),
                      (7, 2, "4 rounds, $32.1")):
    cell = tbl.cell(r_i, c_i)
    run = cell.text_frame.paragraphs[0].runs[0]
    run.text = txt

s = add_slide("Appendix — the LLM runtime: selection × serialization", size=18)
pic = add_pic(s, "p2_llm_r34.png", 0.55, 0.66, 8.90)
add_caption(s, below(pic, 0.14), "At about 64 episodes per cell, graph selection with witness closure cuts LLM input by "
                                 "70–74% at an exact-success cost of 0.10–0.19 on deepseek-v4-flash; non-inferiority at "
                                 "the −0.10 margin is not met. The LLM stays far below the deterministic graph on the "
                                 "same tasks.", size=13.0)
notes(s, "Backup for the P2 result slide. Rounds 1–2 (20 episodes per cell) were inconclusive: the paired "
         "intervals crossed zero and the pre-registered point rule flipped between rounds. Round 3 re-ran the "
         "four main cells with prompt v2 at 80 episodes per cell and hit its pre-declared $12 cap at 527 cells "
         "(63–69 per cell). Round 4 ($6.41, pre-registered) closed the graph selection: the graph's reads plus "
         "the objects its witness records name and their neighbours, because in 33 of 38 failing Travel episodes "
         "the witness records named objects absent from the selected state. The closure recovered half of "
         "Travel's gap (+0.234 [+0.094, +0.359] over the open selection). Verdict at this sample size: graph "
         "selection cuts input by 70–74% at an exact-success cost of 0.10–0.19; non-inferiority at −0.10 is not "
         "met. The deterministic graph reaches 0.86 (Travel) and 0.99 (Search) on the same tasks, so the "
         "runtime is the bottleneck. Total P2 API spend across four rounds: $32.1.")

prs.save(SRC)
print("saved", SRC, "slides:", len(prs.slides))
for i, sl in enumerate(prs.slides, 1):
    print(f"  {i:2d}  {title_of(sl)[:80]}")
