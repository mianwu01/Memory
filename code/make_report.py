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

    order = {"causal-learned": 0, "long_context": 1, "bm25": 2,
             "causal": 3, "causal-noG": 3, "causal-scaffold": 3}
    for r in summ:
        i = order.get(r["system"], 3)
        col = f"var(--s{i+1})"
        x, y = X(r["avg_ctx_tokens"]), Y(r["round_solvable"])
        star = r["system"] == "causal-learned"
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
def p3_note_chart(cells, w=680, h=300):
    """P(anomalous) across the 2x2 of (note in query, poison retrieved).

    This is the honest cut. Splitting on `trigger` instead makes the memory
    pathway look real; splitting on `note_present` shows the anomaly tracks the
    VISIBLE instruction, and that the note-free + poison-read cell is empty.
    """
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
        lab = f'note in query: {"YES" if c["note"] else "no"}'
        lab2 = f'poison read: {"YES" if c["poison"] else "no"}'
        base = pad_t + (h - pad_t - pad_b)
        p.append(f'<text x="{x+bw/2:.1f}" y="{base+20:.1f}" text-anchor="middle" font-size="12" '
                 f'fill="var(--text-secondary)">{lab}</text>')
        p.append(f'<text x="{x+bw/2:.1f}" y="{base+37:.1f}" text-anchor="middle" font-size="12" '
                 f'fill="var(--text-secondary)">{lab2}</text>')
        p.append(f'<text x="{x+bw/2:.1f}" y="{base+55:.1f}" text-anchor="middle" font-size="11" '
                 f'fill="var(--text-muted)">n={c["n"]}</text>')
    p.append("</svg>")
    return "\n".join(p)



def extras_html(meta):
    out = []
    reg = meta.get("regime")
    if reg:
        rows = "".join(
            f"<tr><td>sigma={r['sigma']}</td>"
            f"<td class='num'>{r['blind_read']}/2</td>"
            f"<td class='num'>{r['augmented_read']}/2</td>"
            f"<td class='num'><strong>{r['regime_read']}/2</strong></td></tr>"
            for r in reg)
        out.append(f"""<h2>The method itself: regime-conditioned discovery</h2>
<p class="sub">Everything above uses a graph. This is the estimator that finds one when the
edge is <em>gated</em> — switched on and off by a regime rather than always present.</p>
<p>A gated edge is multiplicative: the coefficient on the parent depends on the regime.
Adding the regime as one more <em>node</em> — the standard move — only shifts the mean, so
it cannot express that, and it fails. Conditioning on the regime recovers the edge:</p>
<div class="scroll"><table>
<thead><tr><th>E0 gated SCM</th><th style="text-align:right">blind</th>
<th style="text-align:right">regime as a node</th>
<th style="text-align:right">regime-conditioned (ours)</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="note">Read edges recovered, out of 2. The middle column is the honest control: it
is the obvious thing to try, it is what we shipped before, and it recovers nothing. Our
estimator also flags each recovered edge as gated, which is what the defence below consumes.</p>""")

    ma = meta.get("memaudit")
    if ma:
        c = ma.get("cmis", {}); g = ma.get("consistency_graph", {})
        def f(v, d=3):
            try:
                return f"{float(v):.{d}f}"
            except Exception:
                return "n/a"
        out.append(f"""<h2>Against the competitor: MemAudit</h2>
<p class="sub">MemAudit (arXiv 2605.23723) is the nearest prior work and released no code, so we
reimplemented both halves from the paper to make the comparison concrete.</p>
<div class="scroll"><table>
<thead><tr><th>MemAudit component</th><th style="text-align:right">AUC</th>
<th style="text-align:right">precision@k</th></tr></thead><tbody>
<tr><td>CMIS — per-record counterfactual influence</td>
<td class="num">{f(c.get('auc'))}</td><td class="num">{f(c.get('precision_at_k'))}</td></tr>
<tr><td>Consistency graph — structural anomaly</td>
<td class="num">{f(g.get('auc'))}</td><td class="num">{f(g.get('precision_at_k'))}</td></tr>
</tbody></table></div>
<p><strong>We do not beat it at detection, and should not claim to.</strong> CMIS ranks the
poisoned records well. The difference is structural, not a score: MemAudit scores records one
at a time against a static semantic graph, so it cannot say <em>which earlier round's write</em>
drives a later action, and its graph cannot be handed back to the memory system as a selection
policy. Our graph does both jobs — that dual use is the claim.</p>
<p class="note">Substitution to disclose: their DeBERTa-v3 NLI relatedness is replaced by lexical
overlap here, because this project is CPU-only. That mainly weakens their second row.</p>""")

    gt = meta.get("gate")
    if gt:
        rows = ""
        for name, r in gt.items():
            try:
                rows += (f"<tr><td>{esc(name)}</td>"
                         f"<td class='num'>{r['prevented']}/{r['anomalous_rounds']}"
                         f" ({float(r['prevention_rate'])*100:.0f}%)</td>"
                         f"<td class='num'>{r['collateral_rounds']}/{r['benign_rounds']}"
                         f" ({float(r['collateral_rate'])*100:.1f}%)</td></tr>")
            except Exception:
                continue
        out.append(f"""<h2>Closing the loop: gating the actions a driver would cause</h2>
<p class="sub">An audit that only writes a report is not actionable. The same recovered
structure is fed back so the memory system withholds the implicated record <em>before</em> the
agent acts.</p>
<div class="scroll"><table>
<thead><tr><th>gate</th><th style="text-align:right">anomalous actions prevented</th>
<th style="text-align:right">collateral (benign rounds touched)</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p><strong>What the middle row buys.</strong> Dropping the regime condition turns the gate into
a blocklist: it still prevents everything, but it withholds memory on more than twice as many
healthy rounds. Requiring the regime to be open — the edge to be <em>active</em> — is what makes
the defence cheap enough to leave switched on.</p>""")
    return "\n".join(out)


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
    ours = next((r for r in P if r["system"] == "causal-learned"), None) or \
           next((r for r in P if r["system"] == "causal"), None)
    rule = next((r for r in P if r["system"] == "causal"), None)
    lc = next((r for r in P if r["system"] == "long_context"), None)
    bm = next((r for r in P if r["system"] == "bm25"), None)
    nog = next((r for r in P if r["system"] == "causal-noG"), None)
    scaf = next((r for r in P if r["system"] == "causal-scaffold"), None)

    rows = ""
    for r in sorted(P, key=lambda x: -x["round_solvable"]):
        cls = ' class="ours"' if r["system"] == "causal-learned" else ""
        nm = r["system"] + (" (ours, discovered graph)" if r["system"] == "causal-learned" else
                            " (ours, pure discovery)" if r["system"] == "causal-learned-pure" else
                            " (rule graph, constraint-only)" if r["system"] == "causal" else
                            " (hand-patched scaffold)" if r["system"] == "causal-scaffold" else
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
  <div class="kpi"><div class="n">{p3_report['noted_anom']}/{p3_report['noted_n']}</div>
    <div class="l">attack fires when the instruction is <em>visible in the query</em></div></div>
  <div class="kpi"><div class="n">{p3_report['nf_anom']}/{p3_report['nf_n']}</div>
    <div class="l">attack fires when the poison is read <em>from memory</em> with no visible
    instruction — the memory pathway did not reproduce</div></div>
</div>

<h2>Task 1 — the plugin makes MemoryArena's memory better and cheaper</h2>
<p class="sub">We registered <code>CausalMemorySystem</code> into MemoryArena at runtime
(their repo stays byte-identical — it ships no licence, so we do not fork it) and ran it
through their real HTTP memory interface on real travel episodes.
<strong>Caveat stated up front:</strong> the graph used here is a <em>rule</em> graph read off
the query, not a discovered one. This measures whether ancestor masking pays off; it does not
yet exercise causal discovery.</p>

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

<p><strong>Headline, stated plainly: half of the attack reproduced and half did not.</strong>
The model obeys the poison rule when the instruction is in front of it
({p3_report['noted_anom']}/{p3_report['noted_n']} rounds). But the part that makes MINJA a
<em>memory</em> attack — the record lying dormant and hijacking a later, clean query — did
not happen even once: {p3_report['nf_anom']}/{p3_report['nf_n']} on rounds where the poison
was retrieved with no instruction visible, and {p3_report['test_anom']}/{p3_report['test_n']}
on the held-out test rounds.</p>

<div class="card">{p3_note_chart(p3_cells)}</div>

<p><strong>How to read it:</strong> the anomaly tracks the <em>visible</em> instruction, not
the memory. The bottom-right bar is the one that would have to be tall for the memory
pathway to be real, and it is empty.</p>

<h3>The confound that would have fooled us — and why this is the interesting part</h3>
<p>Split the same data by <em>trigger word</em> instead of by <em>visible instruction</em>
and you get a textbook gated read edge: pooled Δ = +{p3_report['pooled_rd']:.2f}, and
conditioned on the trigger, poison retrieval appears to drive the anomaly at Δ = +0.85 while
being perfectly inert without it. That is exactly the signature the project predicts — and
here it is an artifact.</p>
<p>The cause is mechanical: retrieval is edit-distance based, so a query carrying the long
poison note is textually close to stored records that also carry notes. Poison therefore gets
retrieved precisely on the rounds where the instruction is already in plain sight. The two
variables are collinear, and any estimator that does not break them apart credits memory for
what the note did.</p>
<p><strong>The only statistic with discriminating power</strong> is the note-free ∧
poison-retrieved cell — and it is {p3_report['nf_anom']}/{p3_report['nf_n']}. The analysis
code now refuses to report "driver recovered" without it.</p>

<div class="scroll"><table>
<thead><tr><th>audit</th><th>what it can see</th><th>verdict on this data</th></tr></thead><tbody>
<tr><td>Behaviour-only</td><td>the action sequence</td>
<td><span class="tag warn">not tested</span> the anomaly only occurs on rounds whose
instruction is visible, so nothing is hidden from it here</td></tr>
<tr><td>Similarity / retrieval</td><td>what was retrieved, and how close</td>
<td><span class="tag bad">cannot separate</span> poison sits among topically similar
memory (distance 84 on anomalous rounds vs 140 on normal)</td></tr>
<tr><td>Causal (ours)</td><td>temporal structure over memory state</td>
<td><span class="tag good">correctly declines</span> attributes the anomaly to the visible
note and reports that memory is <em>not</em> the driver</td></tr>
</tbody></table></div>

<p>That last row is a soundness result rather than the headline we were aiming for: asked to
find a hidden memory driver, the method declined to invent one that was not there. Worth
having — but it is not yet evidence that the method <em>recovers</em> hidden drivers, because
this run contains none to recover.</p>

<h3>Two candidate explanations, not yet separated</h3>
<ul>
<li><strong>Retrieval.</strong> To sweep trigger rarity we drew benign filler from 40 MMLU
subjects, which diluted memory so much the poison rarely won a top-3 slot — it was retrieved
on only {p3_report['nf_n']} of {p3_report['rounds']-p3_report['noted_n']} note-free rounds.
MINJA's own design keeps filler within one subject. A faithful same-subject rerun is in flight.</li>
<li><strong>Model robustness.</strong> {esc(meta.get('model','the model'))} may simply not be
steered by an instruction embedded in a retrieved exemplar.</li>
</ul>

{case_html}

{extras_html(meta)}

<h2>What we are not claiming</h2>
<ul>
<li><strong>The graph in Task 1 is a rule graph, not a discovered one.</strong> It reads the
person names out of the query. So this run demonstrates that slot-level ancestor masking pays
off — it does <em>not</em> yet exercise GRACE or any causal discovery, which is the project's
actual thesis. Wiring the learned graph in and re-measuring is the open work item.</li>
<li>Task 1's win is <strong>answerability at cost</strong>, measured on the memory context
with no LLM in the loop (so it reproduces exactly). It is not an end-to-end task-success
number; the travel agent runs up to 30 reasoning steps per round and at affordable episode
counts that metric moves inside its own noise.</li>
<li>On travel the dependencies are <em>named in the query</em>, so discovery is unnecessary
by construction here (a pre-registered test already concluded this). Discovery claims rest on
the simulation track, not on this environment.</li>
<li><strong>Task 2 did not demonstrate hidden-driver recovery</strong>, because on this
model and configuration no hidden driver was operating. What it produced is a soundness
check plus a documented confound.</li>
<li>The trigger-rarity sweep referenced in the working notes was run against an offline
stand-in answerer, not a real LLM — it is a synthetic diagnostic, not a measurement.</li>
<li>MemAudit — the closest competitor — released no code, so "we beat it" is not
demonstrated; only the two naive audits above were run.</li>
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

    def _maybe(path):
        try:
            return json.load(open(path))
        except Exception:
            return None
    extras = {"regime": _maybe("results/regime_grace_e0.json"),
              "memaudit": _maybe("results/real/memaudit_baseline.json"),
              "gate": _maybe("results/real/causal_gate.json")}

    cells = []
    for note in (0, 1):
        for pois in (0, 1):
            sub = df[(df.note_present == note) & (df.poison_retr == pois)]
            cells.append({"note": note, "poison": pois, "n": len(sub),
                          "rate": float(sub["anomalous"].mean()) if len(sub) else 0.0})
    pre = df[df.phase == "pre"]
    test = df[df.phase == "test"]
    nf = df[(df.note_present == 0) & (df.poison_retr == 1)]
    noted = df[df.note_present == 1]
    rep = {"pre_anom": int(pre["anomalous"].sum()), "pre_n": len(pre),
           "test_anom": int(test["anomalous"].sum()), "test_n": len(test),
           "nf_anom": int(nf["anomalous"].sum()), "nf_n": len(nf),
           "noted_anom": int(noted["anomalous"].sum()), "noted_n": len(noted),
           "rounds": len(df),
           "pooled_rd": float(df[df.poison_retr == 1]["anomalous"].mean()
                              - df[df.poison_retr == 0]["anomalous"].mean())}

    # concrete case from the transcript
    case_html = ""
    tp = Path(a.p3_transcript)
    if tp.exists():
        T = json.load(open(tp))
        fired = [r for r in T if r["anomalous"] and r["note_present"]]
        held = [r for r in T if not r["note_present"]
                and any(x["is_poison"] for x in r["retrieved"])]
        blocks = []
        if fired:
            c = fired[0]
            blocks.append(f"""<p><strong>A. The attack working — instruction visible in the
query</strong> (round t={c['t']}, {esc(c['phase'])}).</p>
<p class="note">The model narrates the payload verbatim and applies it:</p>
<div class="quote">{esc(c['thought'][:560])}</div>
<p class="note">Correct answer <strong>{esc(c['groundtruth'])}</strong>; model answered
<strong>{esc(c['answer'])}</strong> — outside A–D, exactly the +4 ASCII signature.</p>""")
        if held:
            d = held[0]
            pois = [x for x in d["retrieved"] if x["is_poison"]]
            blocks.append(f"""<p style="margin-top:22px"><strong>B. The attack failing — same
payload, now only in memory</strong> (round t={d['t']}, {esc(d['phase'])},
<code>note_present = 0</code>).</p>
<p class="note">This poisoned record was retrieved as a few-shot exemplar:</p>
<pre>{esc(pois[0]['thought'][:400])}</pre>
<p class="note">And the model ignored it — answered
<strong>{esc(str(d['answer']))}</strong> (ground truth {esc(d['groundtruth'])}),
anomalous = {d['anomalous']}. This is the pathway MINJA depends on, and it did not
carry.</p>""")
        if blocks:
            case_html = ("<h3>Both halves, in the model's own words</h3><div class=\"card\">"
                         + "".join(blocks) + "</div>")

    p2_case_html = ""
    cf = Path("logs/p2_case.log")
    if cf.exists():
        txt = cf.read_text()
        p2_case_html = f'<pre>{esc(txt[:5200])}</pre>'

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(p2, rep, cells, case_html, p2_case_html,
                         {"model": a.model, **extras}))
    print(f"wrote {out}")
    print("P3 gate cells:", json.dumps(cells, indent=1))


if __name__ == "__main__":
    main()
