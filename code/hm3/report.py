"""Markdown tables from the merged deterministic results, the gate report and the LLM summary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .run_det import summarize

ORDER = ["exact_kv", "source_union", "source_regime", "knn", "flat", "flat_est", "gnn", "gnn_est", "superset",
         "program", "program_reg", "graph", "graph_pooled", "rh_oracle", "oracle"]


def det_table(results: dict, metric: str = "ees") -> str:
    summ = summarize(results)
    domains = list(summ)
    lines = ["| method | " + " | ".join(domains) + " |", "|---|" + "---:|" * len(domains)]
    for m in ORDER:
        row = [m]
        for d in domains:
            v = summ[d].get(m, {}).get(metric)
            row.append("—" if v is None else f"{v[0]:.3f} ± {v[1]:.3f}")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def det_detail(results: dict, domain: str) -> str:
    summ = summarize(results)[domain]
    cols = ["ees", "exact_action_set", "affected_f1", "collateral_txns", "value_accuracy", "required_read_recall",
            "n_reads", "illegal_rate", "regret"]
    lines = ["| method | " + " | ".join(cols) + " |", "|---|" + "---:|" * len(cols)]
    for m in ORDER:
        if m not in summ:
            continue
        row = [m]
        for c in cols:
            v = summ[m].get(c)
            row.append("—" if v is None else f"{v[0]:.2f}")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def gate_table(gate: dict) -> str:
    domains = list(gate["domains"])
    checks = list(next(iter(gate["domains"].values()))["checks"])
    lines = ["| check | " + " | ".join(domains) + " |", "|---|" + "---|" * len(domains)]
    for c in checks:
        row = [c]
        for d in domains:
            row.append("PASS" if gate["domains"][d]["checks"][c]["pass"] else "FAIL")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("| **api_allowed** | " + " | ".join("yes" if gate["domains"][d]["api_allowed"] else "no" for d in domains) + " |")
    return "\n".join(lines)


def llm_table(summary: dict, domain: str) -> str:
    cols = ["n", "ees", "exact_action_set", "affected_f1", "collateral_txns", "value_accuracy", "input_tokens",
            "output_tokens", "cost", "parse_ok"]
    lines = ["| selection / serialization | " + " | ".join(cols) + " |", "|---|" + "---:|" * len(cols)]
    for key, v in summary["cells"].items():
        d, sel, ser = key.split("/")
        if d != domain:
            continue
        row = [f"{sel} / {ser}"]
        for c in cols:
            x = v[c]
            row.append(f"{x:.3f}" if isinstance(x, float) else str(x))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--det", nargs="*", default=[])
    ap.add_argument("--gate", default=None)
    ap.add_argument("--llm", default=None)
    ap.add_argument("--domain", default=None)
    a = ap.parse_args()
    for p in a.det:
        r = json.load(open(p))
        print(f"### {p} — EES (mean ± sd over seeds)\n")
        print(det_table(r))
        for d in summarize(r):
            print(f"\n#### {d}\n")
            print(det_detail(r, d))
    if a.gate:
        print("\n### gate\n")
        print(gate_table(json.load(open(a.gate))))
    if a.llm:
        s = json.load(open(a.llm))
        for d in sorted({k.split("/")[0] for k in s["cells"]}):
            print(f"\n### LLM {d}\n")
            print(llm_table(s, d))
