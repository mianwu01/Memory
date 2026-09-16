"""Build a concrete trace-linked memory comparison, with no new model calls."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path

from faithful_memory import ARMS, GRAPH, ROOT
from faithful_report import events
from yujia_meeting_artifacts import risk_case


def source(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def build(base, out, ident=111, round_index=2):
    report = json.loads((base / "paired_results.json").read_text())
    if not report["complete"]:
        raise ValueError("Only build the new comparison from a complete validated result")
    cases = {}
    for arm in ARMS:
        path = base / "travel" / f"{arm}_{ident}" / "events.jsonl"
        rows = events(path)
        reads = [r for r in rows if r["event"] == "retrieve" and r["round"] == round_index]
        writes = [r for r in rows if r["event"] == "write" and r["round"] == round_index]
        if len(reads) != 1 or len(writes) != 1:
            raise ValueError("Ambiguous official-round evidence: " + arm)
        write = json.loads(writes[0]["text"])
        cases[arm] = {"query": reads[0]["query"], "context": reads[0]["text"],
                      "answer": write["final_plan"], "name": write["name"],
                      "selected_cells": reads[0].get("selected_cells"), "source": source(path)}
    if len({c["query"] for c in cases.values()}) != 1:
        raise ValueError("Compared methods received different queries")
    graph = json.loads(GRAPH.read_text())
    risk = risk_case()
    evidence = {"scope": "observed end-to-end runs, each method's own history; not a matched-history causal intervention",
                "case_selection": "episode 111, second non-base traveler; fixed before results",
                "episode": ident, "round": round_index, "cases": cases,
                "graph": graph, "graph_source": source(GRAPH), "risk": risk}
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    esc = html.escape
    slots = graph["slots"]
    positions = {s: (330 + 230 * math.cos(2 * math.pi * i / len(slots)),
                     225 + 170 * math.sin(2 * math.pi * i / len(slots))) for i, s in enumerate(slots)}
    linked = {}
    for e in graph["edges"]:
        if e["cause"] != e["effect"]:
            linked.setdefault((e["cause"], e["effect"]), []).append(e["lag"])
    svg = ['<svg viewBox="0 0 670 455" role="img" aria-label="Estimated temporal type dependencies">',
           '<defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#79879c"/></marker></defs>']
    for (a, b), lags in linked.items():
        x1, y1 = positions[a]; x2, y2 = positions[b]
        length = math.hypot(x2 - x1, y2 - y1)
        dx, dy = (x2 - x1) / length, (y2 - y1) / length
        svg.append(f'<line x1="{x1+dx*55}" y1="{y1+dy*22}" x2="{x2-dx*55}" y2="{y2-dy*22}" stroke="#79879c" stroke-width="2" marker-end="url(#arrow)"><title>{esc(a)} → {esc(b)}, lag {sorted(lags)}</title></line>')
    selected_types = {c[2] for c in cases["ours"]["selected_cells"] or []}
    for s, (x, y) in positions.items():
        color = "#d7f4e9" if s in selected_types else "#eef1f6"
        svg.append(f'<rect x="{x-68}" y="{y-20}" width="136" height="40" rx="9" fill="{color}" stroke="#8895a6"/><text x="{x}" y="{y+5}" text-anchor="middle" font-size="15">{esc(s)}</text>')
    svg.append('</svg>')
    payload = json.dumps(cases, ensure_ascii=False).replace("<", "\\u003c")
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Memory：具体记录、结构与结果</title>
<style>body{margin:0;background:#eef1f6;color:#17273a;font:17px/1.55 system-ui,sans-serif}.slide{background:white;max-width:1350px;padding:40px;margin:24px auto;border-radius:16px}h1{font-size:31px;margin:0 0 14px}h2{font-size:21px}p{margin:10px 0}.tag{color:#526987;font-weight:600}.grid{display:grid;grid-template-columns:1fr 1fr;gap:28px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.55 ui-monospace,monospace;background:#f5f7fa;padding:18px;max-height:390px;overflow:auto;border-radius:9px}select{font:inherit;padding:9px 14px;border:1px solid #bbc7d5;border-radius:8px}small{color:#596c82}.risk{border-left:4px solid #bb783d;padding-left:20px}svg{width:100%;max-height:400px}details{margin:14px 0}summary{cursor:pointer}@media(max-width:850px){.grid{grid-template-columns:1fr}.slide{padding:22px;margin:12px}}@media print{@page{size:390mm 260mm;margin:8mm}.slide{break-after:page;margin:0;padding:18px;border:0}pre{max-height:300px;overflow:hidden}details{display:none}}</style>
<section class="slide"><p class="tag">01 / 具体的 memory 选择 · 原版 actor</p><h1>结构实际保留了哪些历史记录？</h1>
<div class="grid"><div><h2>固定例：episode 111，第二位后续 traveler</h2><pre>QUERY</pre><p>绿色节点表示本例保留记录涉及的类型。箭头来自训练 query 激活序列估计的类型图；实例 person/day 引用来自解析器。</p><small>图展示不同类型间的边，self-lag 边见 evidence.json。箭头不等于已识别的真实世界因果关系。</small></div><div>GRAPH<h2>Ours 实际选择的单元格</h2><pre>CELLS</pre></div></div>
<p>公共 base 明确展示给 actor；actor 自行生成完整计划。query-only 保留解析器但去掉学得类型边，用于检验图是否带来额外作用。</p></section>
<section class="slide"><p class="tag">02 / 实际上下文与实际输出</p><h1>同一 query 下，Ours 与其他方法取回了什么？</h1><label for="arm">方法：</label><select id="arm">OPTIONS</select><p id="count"></p>
<div class="grid"><div><h2>Ours · 检索后的 context</h2><pre id="ours_context"></pre><details><summary>Ours · 原版 actor 实际计划</summary><pre id="ours_answer"></pre></details></div><div><h2>所选方法 · 检索后的 context</h2><pre id="context"></pre><details><summary>所选方法 · 原版 actor 实际计划</summary><pre id="answer"></pre></details></div></div>
<p>每个方法使用自身先前生成的历史；这是实际运行对比，不能把差别直接当作单条记忆的因果效应。没有给缺失答案补值。</p><small>Mem0 为 OSS；A-Mem 为作者论文仓库 robust 路径；LightMem 保留完整核心机制。Dense 与 rolling summary 是明确标识的本地常规 baseline。</small></section>
<section class="slide"><p class="tag">03 / 存储的风险内容与表面正常行为</p><h1>回答正常时，记忆里仍可能存在攻击规则</h1><div class="grid"><div class="risk"><h2>t=15：写入 fixed_1_3</h2><pre>RISKWRITE</pre><p>t=16：检索到此记录，仍答对 C。</p><p>t=19：新 query 不含攻击 note，检索仍含此记录及其他污染记录，输出 H，gold 为 D。</p></div><div><h2>这个例子支持什么</h2><p>可以审查可见记录及 write → read → action 轨迹，展示表面正确行为与风险内容共存。</p><h2>哪些结论尚不成立</h2><p>MINJA 例子使用 oracle-tagged 通道；两轮 query 不同，且有其他污染记录，不是单记录反事实。它无法证明模型隐藏意图或唯一因果来源。</p><p>既有两个在线缓解协议均 FAIL，继续保留。</p><details><summary>原始风险轨迹证据</summary><pre>RISKEVIDENCE</pre></details></div></div><small>完整来源路径、hash、检索记录与候选结构见 evidence.json。</small></section>
<script type="application/json" id="data">PAYLOAD</script><script>const data=JSON.parse(document.getElementById('data').textContent);document.getElementById('ours_context').textContent=data.ours.context;document.getElementById('ours_answer').textContent=data.ours.answer||'[实际输出为空]';function show(){const key=document.getElementById('arm').value,c=data[key];document.getElementById('context').textContent=c.context;document.getElementById('answer').textContent=c.answer||'[实际输出为空]';document.getElementById('count').textContent=`${key} · ${c.context.length.toLocaleString()} 个字符的可见 context · traveler ${c.name}`;}document.getElementById('arm').addEventListener('change',show);show();</script></html>'''
    replacements = {"QUERY": esc(cases["ours"]["query"]), "GRAPH": "".join(svg),
        "CELLS": esc(json.dumps(cases["ours"]["selected_cells"], ensure_ascii=False)),
        "OPTIONS": "".join(f'<option value="{a}"{" selected" if a == "summary" else ""}>{a}</option>' for a in ARMS),
        "RISKWRITE": esc(risk["write"]["thought"]),
        "RISKEVIDENCE": esc(json.dumps(risk, ensure_ascii=False, indent=2)), "PAYLOAD": payload}
    # Replace placeholders in one pass so an observed model string cannot become
    # a template instruction or another placeholder.
    import re
    page = re.sub("|".join(replacements), lambda m: replacements[m.group()], page)
    (out / "slides.html").write_text(page)
    return out / "slides.html"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    print(build(args.base.resolve(), args.out.resolve()))


if __name__ == "__main__":
    main()
