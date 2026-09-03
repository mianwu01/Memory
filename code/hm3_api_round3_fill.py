"""Append the API round-3 section (80 episodes per main cell) to docs/hidden-mechanism-v3-results.md."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
doc = ROOT / "docs/hidden-mechanism-v3-results.md"
s = doc.read_text()
if "### 7.5 API round 3" in s:
    raise SystemExit("already present")
a = json.load(open(ROOT / "results/real/hm3/round3/paired_analysis.json"))
summ = json.load(open(ROOT / "results/real/hm3/round3/llm_summary.json"))
lines = ["", "### 7.5 API round 3：主判断的功效补样（预注册 §11；每 cell 80 episodes，prompt v2）", "",
         "| 域 | cell | n | EES | input tokens |", "|---|---|---:|---:|---:|"]
for d in ("travel", "search"):
    for cell, v in a[d]["cells"].items():
        lines.append(f"| {d} | {cell} | {v['n']} | {v['ees']:.3f} | {v['input_tokens']:,} |" if v["ees"] is not None else f"| {d} | {cell} | 0 | — | — |")
lines += ["", "| 域 | 比较 | mean | 95% CI | W/T/L | n |", "|---|---|---:|---:|---|---:|"]
for d in ("travel", "search"):
    for name, key in (("graph/compact − full/verbose", "main_judgement"), ("graph/verbose − full/verbose", "selection_isolation"), ("full/compact − full/verbose", "serialization_isolation")):
        m = a[d][key]["paired"] if key == "main_judgement" else a[d][key]
        if m["n"]:
            lines.append(f"| {d} | {name} | {m['mean']:+.3f} | [{m['ci_lo']:+.3f}, {m['ci_hi']:+.3f}] | {m['wtl'][0]}/{m['wtl'][1]}/{m['wtl'][2]} | {m['n']} |")
for d in ("travel", "search"):
    mj = a[d]["main_judgement"]
    if mj["ees_delta"] is not None:
        lines.append(f"\n{d.capitalize()} 主判断（点估计规则）：EES 差 {mj['ees_delta']:+.3f}，input 减少 {mj['input_reduction']*100:.1f}% → **{'PASS' if mj['point_rule_pass'] else 'FAIL'}**；"
                     f"配对 95% 区间 [{mj['paired']['ci_lo']:+.3f}, {mj['paired']['ci_hi']:+.3f}]（n = {mj['paired']['n']}）。")
t = summ["total"]
lines.append(f"\nRound 3 合计 {t['cells']} cells，input {t['input_tokens']:,} / output {t['output_tokens']:,} tokens，估计费用 ${t['cost']:.3f}。"
             f" 不完整的 cell（基础设施失败）见各 shard ledger 的 `infrastructure_failure` 记录。")
doc.write_text(s + "\n".join(lines) + "\n")
print("appended 7.5")
