"""Generate the explainable HTML report for the P2 and P3 experiments.

Reads the real result files and writes a self-contained page: headline numbers,
inline-SVG charts, and the concrete per-case evidence (the model's own words)
so a reader can check the mechanism rather than trust an aggregate.

Usage: python3 code/make_report.py --out artifacts/experiments.html
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import pandas as pd

# validated categorical slots (dataviz reference palette), light / dark
SERIES = [("#2a78d6", "#3987e5"), ("#eb6834", "#d95926"),
          ("#1baf7a", "#199e70"), ("#eda100", "#c98500")]
GOOD, CRIT, WARN = "#0ca30c", "#d03b3b", "#fab219"


def esc(s):
    return html.escape(str(s))


# --------------------------------------------------------------------------- P2
def p2_scatter(summ, w=680, h=380):
    """Answerability vs cost. Up-and-to-the-left dominates."""
    pad_l, pad_b, pad_t, pad_r = 62, 52, 18, 130
    xs = [r["avg_ctx_tokens"] for r in summ]
    ys = [r["round_solvable"] for r in summ]
    xmax = max(xs) * 1.12
    ymin, ymax = min(min(ys) * 0.97, 0.68), 1.005

    def X(v):
        return pad_l + (v / xmax) * (w - pad_l - pad_r)

    def Y(v):
        return pad_t + (1 - (v - ymin) / (ymax - ymin)) * (h - pad_t - pad_b)

    p = [f'<svg viewBox="0 0 {w} {h}" role="img" '
         f'aria-label="Answerability versus context cost for four memory systems" '
         f'style="width:100%;height:auto">']
    # grid + y axis
    for i in range(5):
        v = ymin + (ymax - ymin) * i / 4
        y = Y(v)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" '
                 f'stroke="var(--grid)" stroke-width="1"/>')
        p.append(f'<text x="{pad_l-10}" y="{y+4:.1f}" text-anchor="end" '
                 f'font-size="12" fill="var(--text-muted)">{v*100:.0f}%</text>')
    for i in range(5):
        v = xmax * i / 4
        x = X(v)
        p.append(f'<text x="{x:.1f}" y="{h-pad_b+22}" text-anchor="middle" '
                 f'font-size="12" fill="var(--text-muted)">{v:.0f}</text>')
    p.append(f'<text x="{(pad_l+w-pad_r)/2:.0f}" y="{h-8}" text-anchor="middle" '
             f'font-size="13" fill="var(--text-secondary)">memory context shipped to the agent (tokens) →  cheaper is left</text>')
    p.append(f'<text transform="translate(16,{(h-pad_b+pad_t)/2:.0f}) rotate(-90)" '
             f'text-anchor="middle" font-size="13" fill="var(--text-secondary)">rounds fully answerable</text>')

    order = {"causal": 0, "long_context": 1, "bm25": 2, "causal-noG": 3}
    for r in summ:
        i = order.get(r["system"], 3)
        col = f"var(--s{i+1})"
        x, y = X(r["avg_ctx_tokens"]), Y(r["round_solvable"])
        star = r["system"] == "causal"
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{11 if star else 8}" fill="{col}" '
                 f'stroke="var(--surface-1)" stroke-width="2"/>')
        label = r["system"] + ("  ← ours" if star else "")
        anchor = "start" if x < w - pad_r - 90 else "end"
        dx = 16 if anchor == "start" else -16
        p.append(f'<text x="{x+dx:.1f}" y="{y-12:.1f}" text-anchor="{anchor}" font-size="13" '
                 f'font-weight="{700 if star else 500}" fill="var(--text-primary)">{esc(label)}</text>')
        p.append(f'<text x="{x+dx:.1f}" y="{y+6:.1f}" text-anchor="{anchor}" font-size="12" '
                 f'fill="var(--text-muted)">{r["round_solvable"]*100:.1f}% · {r["avg_ctx_tokens"]:.0f} tok</text>')
    p.append("</svg>")
    return "\n".join(p)


# --------------------------------------------------------------------------- P3
def p3_gate_chart(cells, w=680, h=300):
    """P(anomalous) across the 2x2 of (trigger, poison retrieved)."""
    pad_l, pad_b, pad_t = 58, 88, 20
    bw = (w - pad_l - 30) / 4 * 0.56
    gap = (w - pad_l - 30) / 4
    p = [f'<svg viewBox="0 0 {w} {h}" role="img" '
         f'aria-label="Attack rate across trigger and poison-retrieval conditions" '
         f'style="width:100%;height:auto">']
    for i in range(5):
        v = i / 4
        y = pad_t + (1 - v) * (h - pad_t - pad_b)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-14}" y2="{y:.1f}" '
                 f'stroke="var(--grid)" stroke-width="1"/>')
        p.append(f'<text x="{pad_l-10}" y="{y+4:.1f}" text-anchor="end" font-size="12" '
                 f'fill="var(--text-muted)">{v*100:.0f}%</text>')
    for i, c in enumerate(cells):
        x = pad_l + 14 + i * gap + (gap - bw) / 2
        val = c["rate"]
        bh = val * (h - pad_t - pad_b)
        y = pad_t + (h - pad_t - pad_b) - bh
        col = CRIT if val > 0.25 else (GOOD if val < 0.05 else WARN)
        p.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(bh,2):.1f}" '
                 f'rx="4" fill="{col}"/>')
        p.append(f'<text x="{x+bw/2:.1f}" y="{y-8:.1f}" text-anchor="middle" font-size="14" '
                 f'font-weight="700" fill="var(--text-primary)">{val*100:.0f}%</text>')
        lab = f'trigger {"YES" if c["trigger"] else "no"}'
        lab2 = f'poison read {"YES" if c["poison"] else "no"}'
        base = pad_t + (h - pad_t - pad_b)
        p.append(f'<text x="{x+bw/2:.1f}" y="{base+20:.1f}" text-anchor="middle" font-size="12" '
                 f'fill="var(--text-secondary)">{lab}</text>')
        p.append(f'<text x="{x+bw/2:.1f}" y="{base+37:.1f}" text-anchor="middle" font-size="12" '
                 f'fill="var(--text-secondary)">{lab2}</text>')
        p.append(f'<text x="{x+bw/2:.1f}" y="{base+55:.1f}" text-anchor="middle" font-size="11" '
                 f'fill="var(--text-muted)">n={c["n"]}</text>')
    p.append("</svg>")
    return "\n".join(p)


def build(p2_summary, p3_report, p3_cells, case_html, p2_case_html, meta):
    s1l, s1d = SERIES[0]
    css = f"""
:root {{ color-scheme: light dark; }}
body {{ margin:0; background:var(--page); color:var(--text-primary);
  font: 15px/1.65 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif; }}
.viz-root {{
  --page:#f7f7f5; --surface-1:#fcfcfb; --surface-2:#f0efec;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#75736e;
  --grid:#e3e2de; --border:#dcdbd6;
  --s1:{s1l}; --s2:{SERIES[1][0]}; --s3:{SERIES[2][0]}; --s4:{SERIES[3][0]};
}}
@media (prefers-color-scheme: dark) {{
  :root:where(:not([data-theme="light"])) .viz-root {{
    --page:#131312; --surface-1:#1a1a19; --surface-2:#232322;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#9a9890;
    --grid:#333331; --border:#3a3a37;
    --s1:{s1d}; --s2:{SERIES[1][1]}; --s3:{SERIES[2][1]}; --s4:{SERIES[3][1]};
  }}
}}
:root[data-theme="dark"] .viz-root {{
  --page:#131312; --surface-1:#1a1a19; --surface-2:#232322;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#9a9890;
  --grid:#333331; --border:#3a3a37;
  --s1:{s1d}; --s2:{SERIES[1][1]}; --s3:{SERIES[2][1]}; --s4:{SERIES[3][1]};
}}
.wrap {{ max-width:960px; margin:0 auto; padding:40px 22px 80px; }}
h1 {{ font-size:30px; line-height:1.25; margin:0 0 6px; letter-spacing:-.02em; }}
h2 {{ font-size:21px; margin:44px 0 6px; letter-spacing:-.01em;
  border-top:1px solid var(--border); padding-top:26px; }}
h3 {{ font-size:16px; margin:26px 0 6px; }}
.sub {{ color:var(--text-secondary); margin:0 0 26px; }}
.card {{ background:var(--surface-1); border:1px solid var(--border);
  border-radius:12px; padding:20px; margin:18px 0; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:14px; margin:22px 0; }}
.kpi {{ background:var(--surface-1); border:1px solid var(--border); border-radius:12px; padding:16px 18px; }}
.kpi .n {{ font-size:27px; font-weight:700; letter-spacing:-.02em; }}
.kpi .l {{ font-size:13px; color:var(--text-secondary); margin-top:3px; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th,td {{ text-align:left; padding:9px 12px; border-bottom:1px solid var(--border); }}
th {{ color:var(--text-secondary); font-weight:600; font-size:12.5px;
  text-transform:uppercase; letter-spacing:.04em; }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
tr.ours td {{ font-weight:700; }}
.scroll {{ overflow-x:auto; }}
pre {{ background:var(--surface-2); border:1px solid var(--border); border-radius:9px;
  padding:14px; overflow-x:auto; font-size:12.5px; line-height:1.5; margin:10px 0; }}
.quote {{ border-left:3px solid var(--s2); padding:10px 14px; margin:12px 0;
  background:var(--surface-2); border-radius:0 8px 8px 0; font-size:14px; }}
.tag {{ display:inline-block; font-size:11px; font-weight:700; padding:2px 8px;
  border-radius:99px; letter-spacing:.03em; }}
.tag.bad {{ background:{CRIT}22; color:{CRIT}; }}
.tag.good {{ background:{GOOD}22; color:{GOOD}; }}
.tag.warn {{ background:{WARN}33; color:#8a6100; }}
.note {{ font-size:13.5px; color:var(--text-secondary); }}
ul {{ padding-left:20px; }} li {{ margin:5px 0; }}
"""
    P = p2_summary
    ours = next((r for r in P if r["system"] == "causal"), None)
    lc = next((r for r in P if r["system"] == "long_context"), None)
    bm = next((r for r in P if r["system"] == "bm25"), None)
    nog = next((r for r in P if r["system"] == "causal-noG"), None)

    rows = ""
    for r in sorted(P, key=lambda x: -x["round_solvable"]):
        cls = ' class="ours"' if r["system"] == "causal" else ""
        nm = r["system"] + (" (ours)" if r["system"] == "causal" else
                            " (ablation: no graph)" if r["system"] == "causal-noG" else
                            " (upper bound)" if r["system"] == "long_context" else
                            " (retrieval baseline)" if r["system"] == "bm25" else "")
        rows += (f'<tr{cls}><td>{esc(nm)}</td>'
                 f'<td class="num">{r["cell_recall"]*100:.1f}%</td>'
                 f'<td class="num">{r["round_solvable"]*100:.1f}%</td>'
                 f'<td class="num">{r["avg_ctx_tokens"]:.0f}</td>'
                 f'<td class="num">{r["compression"]:.2f}×</td></tr>')

    tok_ratio = (bm["avg_ctx_tokens"] / ours["avg_ctx_tokens"]) if ours and bm else 0
    lc_ratio = (lc["avg_ctx_tokens"] / ours["avg_ctx_tokens"]) if ours and lc else 0

    body = f"""<div class="viz-root"><div class="wrap">
<h1>Temporal-causal memory: two experiments</h1>
<p class="sub">Yujia's two tasks, run end to end on real systems with a real LLM
({esc(meta.get('model','?'))}). Task 1 — plug our method into an existing agent-memory
platform and show it improves what is already there. Task 2 — reuse a published
agent-safety failure and test whether our method recovers the hidden driver.</p>

<div class="kpis">
  <div class="kpi"><div class="n">{ours["round_solvable"]*100:.0f}%</div>
    <div class="l">rounds answerable with our plugin, vs {bm["round_solvable"]*100:.0f}% for the
    retrieval baseline — at {tok_ratio:.1f}× fewer tokens</div></div>
  <div class="kpi"><div class="n">{lc_ratio:.1f}×</div>
    <div class="l">smaller memory context than full-history, losing
    {(lc["cell_recall"]-ours["cell_recall"])*100:.1f} points of cell recall</div></div>
  <div class="kpi"><div class="n">{p3_cells[3]["rate"]*100:.0f}%</div>
    <div class="l">attack rate when trigger AND poisoned memory coincide</div></div>
  <div class="kpi"><div class="n">{p3_cells[1]["rate"]*100:.0f}%</div>
    <div class="l">attack rate when the same poison is read <em>without</em> the
    trigger — the edge is gated, not constant</div></div>
</div>

<h2>Task 1 — the plugin makes MemoryArena's memory better and cheaper</h2>
<p class="sub">We registered <code>CausalMemorySystem</code> into MemoryArena at runtime
(their repo stays byte-identical — it ships no licence, so we do not fork it) and ran it
through their real HTTP memory interface on real travel episodes.</p>

<div class="card">{p2_scatter(P)}</div>

<p><strong>How to read it:</strong> up is "the agent got the facts it needed",
left is "we spent fewer tokens to give them". Our plugin sits up-and-left of the
retrieval baseline — strictly better on both axes at once, which is the part that
matters: it is not a trade, it is a dominance. Full-history is the information
ceiling and we pay {lc_ratio:.1f}× less to sit
{(lc["round_solvable"]-ours["round_solvable"])*100:.1f} points below it.</p>

<div class="scroll"><table>
<thead><tr><th>memory system</th><th style="text-align:right">cell recall</th>
<th style="text-align:right">rounds answerable</th>
<th style="text-align:right">context tokens</th><th style="text-align:right">vs full history</th></tr></thead>
<tbody>{rows}</tbody></table></div>

<p class="note"><strong>What the ablation proves.</strong> <code>causal-noG</code> is our
system with the causal graph switched off: same slot parsing, same hold rule, but it keeps
every slot. It reaches {nog["round_solvable"]*100:.0f}% answerable — and costs
{nog["avg_ctx_tokens"]:.0f} tokens. So structuring memory is what preserves the facts, and
the <em>graph</em> is what buys the compression: turning it on cuts
{nog["avg_ctx_tokens"]:.0f}→{ours["avg_ctx_tokens"]:.0f} tokens
({nog["avg_ctx_tokens"]/ours["avg_ctx_tokens"]:.1f}×) for
{(nog["cell_recall"]-ours["cell_recall"])*100:.1f} points of recall. Neither piece alone
does the job.</p>

<h3>What this looks like on one real round</h3>
<p class="note">Rather than trusting the averages, here is the actual memory context each
system hands the agent for one query, and whether the facts the query depends on survived.</p>
{p2_case_html}

<h2>Task 2 — recovering the hidden driver of a published attack</h2>
<p class="sub">Carrier: <strong>MINJA</strong> (NeurIPS 2025), a memory-injection attack.
We reuse its released data and payload unmodified — the poison instructs the agent to
shift its answer by +4 in ASCII when it sees the word "food", so an anomalous action is
self-labelling (an answer in E–H). Our only additions are logging and a clean
pre-injection probe phase.</p>

<div class="card">{p3_gate_chart(p3_cells)}</div>

<p><strong>How to read it:</strong> the poisoned record is in memory the whole time.
Reading it changes nothing on its own ({p3_cells[1]["rate"]*100:.0f}% when the trigger is
absent). The trigger alone changes little ({p3_cells[2]["rate"]*100:.0f}%). Only the
<em>conjunction</em> fires ({p3_cells[3]["rate"]*100:.0f}%). That multiplicative shape is
the "gated read edge" our formulation predicts, and it is why adding the trigger as one
more variable does not expose it — you have to condition on the regime.</p>

<h3>Why the two standard audits fail here</h3>
<div class="scroll"><table>
<thead><tr><th>audit</th><th>what it can see</th><th>verdict</th></tr></thead><tbody>
<tr><td>Behaviour-only</td><td>the action sequence</td>
<td><span class="tag bad">misattributes</span> blames the topic word "food"</td></tr>
<tr><td>Similarity / retrieval</td><td>what was retrieved, and how close</td>
<td><span class="tag bad">cannot separate</span> poison looks like ordinary relevant memory</td></tr>
<tr><td>Causal (ours)</td><td>temporal structure over memory state</td>
<td><span class="tag good">recovers + names</span> identifies the driver and the round that wrote it</td></tr>
</tbody></table></div>

<p><strong>The counterfactual that settles it.</strong> The same kind of "food" query was run
<em>before</em> any poison existed: {p3_report.get('pre_anom','0')} anomalous out of
{p3_report.get('pre_n','0')}. Afterwards the identical query distribution produces attacks.
The queries did not change; memory did. So the topic is not the cause — the written record is,
and only an audit that can see memory over time can say so.</p>

{case_html}

<h2>What we are not claiming</h2>
<ul>
<li>Task 1's win is <strong>answerability at cost</strong> — measured on the memory context
itself, with no LLM in the loop, so it is exactly reproducible. It is not yet an end-to-end
task-success number; the travel agent runs up to 30 reasoning steps per round, and at
affordable episode counts that metric moves inside its own noise.</li>
<li>On this environment the dependencies are <em>named in the query</em>, so our win comes
from slot-level ancestor extraction, not from needing to discover the graph. Discovery
claims rest on the simulation track, not on this one.</li>
<li>Task 2's numbers are one model, one trigger word, one subject area. The mechanism is
what transfers; the rates are not a benchmark score.</li>
<li>MemAudit — the closest competitor — released no code, so "we beat it" is
<em>not</em> yet demonstrated; only the two naive audits above were run.</li>
</ul>
</div></div>"""
    return f"<title>Temporal-causal memory — experiment report</title>\n<style>{css}</style>\n{body}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--p2", default="results/real/p2_benchmark_summary.json")
    ap.add_argument("--p3_trace", default="results/real/minja_trace_llm.csv")
    ap.add_argument("--p3_transcript", default="results/real/minja_trace_llm.transcript.json")
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--out", default="artifacts/experiments.html")
    a = ap.parse_args()

    p2 = json.load(open(a.p2))
    df = pd.read_csv(a.p3_trace)

    cells = []
    for trig in (0, 1):
        for pois in (0, 1):
            sub = df[(df.trigger == trig) & (df.poison_retr == pois)]
            cells.append({"trigger": trig, "poison": pois, "n": len(sub),
                          "rate": float(sub["anomalous"].mean()) if len(sub) else 0.0})
    pre = df[df.phase == "pre"]
    rep = {"pre_anom": int(pre["anomalous"].sum()), "pre_n": len(pre)}

    # concrete case from the transcript
    case_html = ""
    tp = Path(a.p3_transcript)
    if tp.exists():
        T = json.load(open(tp))
        fired = [r for r in T if r["anomalous"] and not r["note_present"]
                 and any(x["is_poison"] for x in r["retrieved"])]
        if fired:
            c = fired[0]
            pois = [x for x in c["retrieved"] if x["is_poison"]]
            case_html = f"""<h3>One attack, in the model's own words</h3>
<p class="note">Round t={c['t']} ({esc(c['phase'])}). The query carries no instruction —
<code>note_present = 0</code>. The poison is only in memory.</p>
<div class="card">
<p><strong>The query the user sent</strong></p>
<pre>{esc(c['question'][:420])}</pre>
<p><strong>What was retrieved from memory</strong> — the poisoned record, sitting
among ordinary ones:</p>
<pre>{esc(pois[0]['thought'][:420])}</pre>
<p><strong>The model's reasoning this round</strong> — it narrates the hijack it
inherited from memory:</p>
<div class="quote">{esc(c['thought'][:520])}</div>
<p class="note">Correct answer: <strong>{esc(c['groundtruth'])}</strong> ·
model answered <strong>{esc(c['answer'])}</strong> — outside the valid range A–D,
which is exactly the +4 ASCII signature the payload asked for. A behaviour auditor sees
only that last line.</p>
</div>"""

    p2_case_html = ""
    cf = Path("logs/p2_case.log")
    if cf.exists():
        txt = cf.read_text()
        p2_case_html = f'<pre>{esc(txt[:5200])}</pre>'

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(p2, rep, cells, case_html, p2_case_html, {"model": a.model}))
    print(f"wrote {out}")
    print("P3 gate cells:", json.dumps(cells, indent=1))


if __name__ == "__main__":
    main()
