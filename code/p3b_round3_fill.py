"""Render docs/p3b-round3-results-2026-09-03.md from results/real/p3b_round3/minja_r3_summary.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
s = json.load(open(ROOT / "results/real/p3b_round3/minja_r3_summary.json"))
seeds = s["per_seed"]; J = s["judgement"]; M = s["micro"]
lines = ["# P3-B round 3 — MINJA online mitigation with expansion and quarantine (2026-09-03)", "",
         "Protocol: `docs/p3b-round3-protocol-2026-09-03.md` (frozen before the first call). Runner: `code/minja_online_gate_r3.py`;",
         "summary: `code/minja_online_gate_r3_summary.py`; per-seed results: `results/real/p3b_round3/minja_r3_seed*.json`.", ""]
def verdict(arm):
    j = J[arm]; b = j["touched_paired_noop_minus_arm"]
    return (f"{'PASS' if j['pass'] else 'FAIL'} — touched-query paired mean noop − {arm} = {b['mean']:+.3f} "
            f"[{b['ci_lo']:+.3f}, {b['ci_hi']:+.3f}] over n = {b['n']} touched queries; evaluable blocks {j['evaluable_blocks']}, "
            f"improved {j['improved_blocks_vs_noop']} of required {j['required_improved']}")
lines += ["## 1. Judgement", "", f"- Primary (g1): {verdict('g1')}", f"- Secondary (g2): {verdict('g2')}", ""]
lines += ["## 2. Micro results over all held-out rounds", "", "| arm | rounds | attacks | attack rate | accuracy |", "|---|---:|---:|---:|---:|"]
for arm in ("ungated", "noop", "g1", "g2"):
    m = M[arm]; lines.append(f"| {arm} | {m['rounds']} | {m['attacks']} | {m['asr']:.3f} | {m['accuracy']:.3f} |")
lines += ["", f"Noise floor: the ungated and noop arms (same memory, no deletion) disagree on the anomalous outcome in "
          f"{s['noise_floor_ungated_vs_noop_flip_rate']:.3f} of rounds.", ""]
lines += ["## 3. Per seed", "", "| seed | ungated | noop | g1 | g2 | evaluable | g1 vs noop | g2 vs noop | g1 deleted (poison / total) | g2 deleted | scored / memory | acc ungated / g1 / g2 |", "|---:|---:|---:|---:|---:|---|---|---|---|---|---|---|"]
for b in seeds:
    a = b["attacks"]; p = b["posthoc"]
    lines.append(f"| {b['seed']} | {a['ungated']} | {a['noop']} | {a['g1']} | {a['g2']} | {'yes' if b['evaluable'] else 'no'} | {b['g1_direction_vs_noop']} | {b['g2_direction_vs_noop']} | "
                 f"{p['g1_deletion']['poison']} / {p['g1_deletion']['records']} | {p['g2_deletion']['poison']} / {p['g2_deletion']['records']} | "
                 f"{b['exposure']:.2f} | {b['accuracy']['ungated']:.2f} / {b['accuracy']['g1']:.2f} / {b['accuracy']['g2']:.2f} |")
lines += ["", "## 4. Transitions against the noop arm (pooled)", ""]
for arm in ("g1", "g2"):
    agg = {"touched": {}, "untouched": {}}
    for b in seeds:
        for st in agg:
            for k, v in b["transitions"][arm][st].items():
                agg[st][k] = agg[st].get(k, 0) + v
    lines.append(f"- {arm}: touched {agg['touched']}; untouched {agg['untouched']}")
lines += ["", "## 5. Driver audit (post hoc, labels attached after all decisions)", "", "| seed | implicated precision | implicated poison recall | g1 precision | g1 poison recall | g2 precision | g2 poison recall |", "|---:|---:|---:|---:|---:|---:|---:|"]
for b in seeds:
    p = b["posthoc"]
    f = lambda x: "—" if x is None else f"{x:.2f}"
    lines.append(f"| {b['seed']} | {f(p['implicated']['precision'])} | {f(p['implicated']['poison_recall'])} | {f(p['g1_deletion']['precision'])} | {f(p['g1_deletion']['poison_recall'])} | {f(p['g2_deletion']['precision'])} | {f(p['g2_deletion']['poison_recall'])} |")
# ---- round 4 (fresh seeds 10-21, three-seed blocks) and the pooled 22-seed summary, if present
r4p = ROOT / "results/real/p3b_round3/round4/minja_r4_summary.json"
if r4p.exists():
    s4 = json.load(open(r4p)); J4, M4 = s4["judgement"], s4["micro"]
    def verdict4(arm):
        j = J4[arm]; b = j["touched_paired_noop_minus_arm"]
        return (f"{'PASS' if j['pass'] else 'FAIL'} — touched-query paired mean noop − {arm} = {b['mean']:+.3f} "
                f"[{b['ci_lo']:+.3f}, {b['ci_hi']:+.3f}] over n = {b['n']}; evaluable blocks {j['evaluable_blocks']} of 4, "
                f"improved {j['improved_blocks_vs_noop']} of required {j['required_improved']}")
    lines += ["## 5b. Round 4 — fresh seeds 10–21, three-seed blocks (protocol §6)", "",
              f"- Primary (g1): {verdict4('g1')}", f"- Secondary (g2): {verdict4('g2')}", "",
              "| arm | rounds | attacks | attack rate | accuracy |", "|---|---:|---:|---:|---:|"]
    for arm in ("ungated", "noop", "g1", "g2"):
        m = M4[arm]; lines.append(f"| {arm} | {m['rounds']} | {m['attacks']} | {m['asr']:.3f} | {m['accuracy']:.3f} |")
    lines += ["", "| block (seeds) | ungated | noop | g1 | g2 | evaluable | g1 vs noop | g2 vs noop |", "|---|---:|---:|---:|---:|---|---|---|"]
    for b in s4["blocks"]:
        a = b["attacks"]; lines.append(f"| {b['seeds']} | {a['ungated']} | {a['noop']} | {a['g1']} | {a['g2']} | {'yes' if b['evaluable'] else 'no'} | {b['g1_direction_vs_noop']} | {b['g2_direction_vs_noop']} |")
    lines.append("")
    pp = ROOT / "results/real/p3b_round3/minja_pooled_summary.json"
    if pp.exists():
        sp = json.load(open(pp)); Jp, Mp = sp["judgement"], sp["micro"]
        lines += ["Pooled descriptive summary over all 22 seeds (rounds 3 and 4; no judgement is claimed on the pooled set):", ""]
        lines += ["| arm | rounds | attacks | attack rate | accuracy |", "|---|---:|---:|---:|---:|"]
        for arm in ("ungated", "noop", "g1", "g2"):
            m = Mp[arm]; lines.append(f"| {arm} | {m['rounds']} | {m['attacks']} | {m['asr']:.3f} | {m['accuracy']:.3f} |")
        for arm in ("g1", "g2"):
            b = Jp[arm]["touched_paired_noop_minus_arm"]; ball = Jp[arm]["all_paired_noop_minus_arm"]
            lines.append(f"- {arm}: touched-query paired mean {b['mean']:+.3f} [{b['ci_lo']:+.3f}, {b['ci_hi']:+.3f}] (n = {b['n']}); all queries {ball['mean']:+.3f} [{ball['ci_lo']:+.3f}, {ball['ci_hi']:+.3f}] (n = {ball['n']})")
        lines.append("")
# ---- AgentPoison round 3, if present
ap = ROOT / "results/real/p3b_round3/agentpoison/agentpoison_r3_summary.json"
if ap.exists():
    sa = json.load(open(ap)); Ja, Ma, Ua = sa["judgement"], sa["micro"], sa["utility"]
    bt, ba = Ja["touched_paired_noop_minus_gated"], Ja["all_paired_noop_minus_gated"]
    lines += ["## 5d. AgentPoison-StrategyQA round 3 (protocol §7)", "",
              f"- Judgement: **{'PASS' if Ja['pass'] else 'FAIL'}** — touched-trajectory paired mean noop − gated = "
              f"{bt['mean']:+.3f} [{bt['ci_lo']:+.3f}, {bt['ci_hi']:+.3f}] (n = {bt['n']}); all trajectories {ba['mean']:+.3f} "
              f"[{ba['ci_lo']:+.3f}, {ba['ci_hi']:+.3f}]; evaluable blocks {Ja['evaluable_blocks']} of {len(sa['blocks'])}, improved "
              f"{Ja['improved_blocks_vs_noop']} of required {Ja['required_improved']}.", "",
              "| arm | trajectories | attacks | attack rate | accuracy |", "|---|---:|---:|---:|---:|"]
    for arm in ("ungated", "noop", "gated"):
        m = Ma[arm]; lines.append(f"| {arm} | {m['trajectories']} | {m['attacks']} | {m['attack_rate']:.3f} | {m['accuracy'] if m['accuracy'] is None else round(m['accuracy'], 3)} |")
    lines += ["", "| block | ungated | noop | gated | evaluable | gated vs noop | touched |", "|---:|---:|---:|---:|---|---|---:|"]
    for b in sa["blocks"]:
        a = b["attacks"]; lines.append(f"| {b['seed']} | {a['ungated']} | {a['noop']} | {a['gated']} | {'yes' if b['evaluable'] else 'no'} | {b['direction_vs_noop']} | {b['touched']} |")
    lines += ["", f"Collateral on clean queries: {Ua['clean_trajectories']} trajectories, gated retrieval touched {Ua['gated_touched']}, answers changed "
              f"{Ua['answers_changed']}, accuracy clean {Ua['accuracy_clean']} vs clean-gated {Ua['accuracy_clean_gated']}. Noise floor (ungated vs no-op flip rate): "
              f"{sa['noise_floor_ungated_vs_noop_flip_rate']}.", ""]
lines += ["", "## 6. Boundaries", "",
          "- Mitigation evidence on a label-free deletion policy; it does not upgrade P3-A's recovery evidence.",
          "- The prefix-neighbourhood expansion assumes the attack writes escalating notes onto one question stem, which is MINJA's mechanism; a different attack needs its own neighbourhood.",
          "- g2 withholds every unvetted record in the trigger regime; its accuracy column shows the cost of that policy.",
          "- AgentPoison round 3 is blocked in this environment (protocol §5).", ""]
(ROOT / "docs/p3b-round3-results-2026-09-03.md").write_text("\n".join(lines))
print("written docs/p3b-round3-results-2026-09-03.md")
