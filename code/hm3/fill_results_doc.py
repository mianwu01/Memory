"""Fill the placeholders in docs/hidden-mechanism-v3-results.md from the result JSONs."""
import json
import sys
from pathlib import Path

from .report import det_table, gate_table, llm_table
from .run_det import summarize

ROOT = Path(__file__).resolve().parents[2]
doc = ROOT / "docs" / "hidden-mechanism-v3-results.md"
s = doc.read_text()
dev = json.load(open(ROOT / "results/development/hm3/det_dev.json"))
gate = json.load(open(ROOT / "results/development/hm3/gate.json"))
test = json.load(open(ROOT / "results/real/hm3/det_test.json"))
llm = json.load(open(ROOT / "results/real/hm3/llm_summary.json"))
s = s.replace("GATE_TABLE", gate_table(gate))
s = s.replace("DEV_TABLE", det_table(dev))
s = s.replace("TEST_TABLE", det_table(test))
cells = llm["cells"]


def cell(d, sel, ser, key):
    return cells.get(f"{d}/{sel}/{ser}", {}).get(key)


parts = []
for d in ("travel", "search"):
    parts.append(f"#### {d}\n\n" + llm_table(llm, d) + "\n")
    fv, gc, gv, fc = (cells.get(f"{d}/full/verbose"), cells.get(f"{d}/graph/compact"),
                      cells.get(f"{d}/graph/verbose"), cells.get(f"{d}/full/compact"))
    if fv and gc:
        d_ees = gc["ees"] - fv["ees"]
        red = 1 - gc["input_tokens"] / fv["input_tokens"] if fv["input_tokens"] else 0.0
        verdict = "PASS" if (d_ees >= -0.10 and red >= 0.30) else "FAIL"
        parts.append(f"主判断 (graph, compact) 相对 (full, verbose)：EES 差 {d_ees:+.3f}，input tokens 减少 "
                     f"{red * 100:.1f}% → **{verdict}**（阈值：EES 差 ≥ −0.10 且 input 减少 ≥ 30%）。\n")
    if fv and gv:
        parts.append(f"selection 隔离 (graph, verbose) − (full, verbose)：EES {gv['ees'] - fv['ees']:+.3f}，input tokens 减少 "
                     f"{(1 - gv['input_tokens'] / fv['input_tokens']) * 100:.1f}%。\n")
    if fv and fc:
        parts.append(f"serialization 隔离 (full, compact) − (full, verbose)：EES {fc['ees'] - fv['ees']:+.3f}，input tokens 减少 "
                     f"{(1 - fc['input_tokens'] / fv['input_tokens']) * 100:.1f}%。\n")
tot = llm["total"]
parts.append(f"合计 {tot['cells']} cells，input {tot['input_tokens']:,} / output {tot['output_tokens']:,} tokens，"
             f"估计费用 ${tot['cost']:.3f}（费率 2.5 / 0.25 / 10 USD per M，与仓库此前一致）。")
s = s.replace("LLM_SECTION", "\n".join(parts))
doc.write_text(s)
print("filled", doc)
