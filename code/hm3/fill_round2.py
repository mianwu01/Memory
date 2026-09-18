"""Append the round-2 section (prompt v2 API, fresh-seed deterministic test, Shopping v3.2)
to docs/hidden-mechanism-v3-results.md."""
import json
from pathlib import Path

from .llm import summarize
from .report import det_table, gate_table, llm_table

ROOT = Path(__file__).resolve().parents[2]
doc = ROOT / "docs" / "hidden-mechanism-v3-results.md"
s = doc.read_text()
if "## 7. Round 2" in s:
    raise SystemExit("round 2 section already present")
parts = ["\n## 7. Round 2（2026-09-03，预注册 §9；prompt v2、fresh test seeds、Shopping v3.2）\n"]
# API round 2
r2 = summarize(ROOT / "results/real/hm3/round2")
r1 = json.load(open(ROOT / "results/real/hm3/llm_summary.json"))
parts.append("### 7.1 API round 2：prompt v2（policy ledger → propagate → check），同一 episode 与 cells\n")
for d in ("travel", "search"):
    parts.append(f"#### {d}\n\n" + llm_table(r2, d) + "\n")
    fv, gc, gv, fc = (r2["cells"].get(f"{d}/full/verbose"), r2["cells"].get(f"{d}/graph/compact"),
                      r2["cells"].get(f"{d}/graph/verbose"), r2["cells"].get(f"{d}/full/compact"))
    if fv and gc:
        d_ees = gc["ees"] - fv["ees"]; red = 1 - gc["input_tokens"] / fv["input_tokens"]
        verdict = "PASS" if (d_ees >= -0.10 and red >= 0.30) else "FAIL"
        parts.append(f"主判断 (graph, compact) 相对 (full, verbose)：EES 差 {d_ees:+.3f}，input tokens 减少 {red*100:.1f}% → **{verdict}**。\n")
    if fv and gv:
        parts.append(f"selection 隔离：EES {gv['ees'] - fv['ees']:+.3f}，input 减少 {(1 - gv['input_tokens'] / fv['input_tokens'])*100:.1f}%。 ")
    if fv and fc:
        parts.append(f"serialization 隔离：EES {fc['ees'] - fv['ees']:+.3f}，input 减少 {(1 - fc['input_tokens'] / fv['input_tokens'])*100:.1f}%。\n")
    # round 1 vs round 2 per cell
    rows = ["| cell | round 1 EES | round 2 EES |", "|---|---:|---:|"]
    for key in sorted(k for k in r2["cells"] if k.startswith(d + "/")):
        rows.append(f"| {key.split('/', 1)[1]} | {r1['cells'].get(key, {}).get('ees', float('nan')):.3f} | {r2['cells'][key]['ees']:.3f} |")
    parts.append("\n".join(rows) + "\n")
tot = r2["total"]
parts.append(f"Round 2 合计 {tot['cells']} cells，input {tot['input_tokens']:,} / output {tot['output_tokens']:,} tokens，估计费用 ${tot['cost']:.3f}。\n")
# deterministic round 2
files = sorted((ROOT / "results/real/hm3/round2").glob("det_test2_*.json"))
merged = {"config": None, "runs": {}}
for f in files:
    r = json.load(open(f)); merged["config"] = merged["config"] or r["config"]
    for k, v in r["runs"].items():
        merged["runs"].setdefault(k, {"generation_seconds": v["generation_seconds"], "learners": {}})["learners"].update(v["learners"])
json.dump(merged, open(ROOT / "results/real/hm3/round2/det_test2.json", "w"), indent=1)
parts.append("### 7.2 Deterministic replication，fresh test seeds 20/21/22（train 120/121/122），全部方法\n")
parts.append("`graph_pooled`（所有 template 共享一个正则化 gradient-boosted gate，template 身份作 one-hot，传播不变）与 `program_reg` 在这一轮是预先加入的方法，其余与 round 1 相同。\n")
parts.append(det_table(merged) + "\n")
# shopping32
g32 = ROOT / "results/development/hm3/gate_shopping32.json"
if g32.exists():
    gate = json.load(open(g32))
    c = gate["domains"]["shopping32"]["checks"]
    parts.append("### 7.3 Shopping v3.2：初始状态与 hidden policy 解耦\n")
    parts.append(gate_table(gate) + "\n")
    parts.append(f"C4：{ {k: round(v, 3) for k, v in c['C4_killers_fail']['ees'].items()} }；C7：graph {c['C7_graph_beats_blackbox']['graph_mean']:.3f}，black boxes { {k: round(v, 3) for k, v in c['C7_graph_beats_blackbox']['blackbox_mean'].items()} }；C8：program {c['C8_program_ran']['program']:.3f}。\n")
    t32 = ROOT / "results/real/hm3/round2/det_test2_shopping32.json"
    if t32.exists():
        parts.append("Shopping v3.2 test（seeds 20/21/22）：\n\n" + det_table(json.load(open(t32))) + "\n")
doc.write_text(s + "\n".join(parts))
print("round 2 section appended")
