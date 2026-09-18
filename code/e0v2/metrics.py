"""Three-level scoring for E0 v2.

  edge      is  i -> j @ l  found at all             (P / R / F1)
  cell      is  i -> j @ l  found in regime u        (P / R / F1, the primary)
  coef      |beta_hat_ij^(u) - beta_ij^(u)|  over true cells (linear SCMs only)

Every level is also reported restricted to the memory system's own targets
(slots and readouts), because the distractor block is active in every regime
and would otherwise dominate the counts.  ``gate_exact`` is the fraction of true
memory edges whose full on/off pattern across regimes is reproduced exactly.
"""
from __future__ import annotations

import numpy as np

from .scm import K, REGIMES

TYPES = ("write", "hold", "read", "distractor")


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else (1.0 if fn == 0 else 0.0)
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"P": round(p, 4), "R": round(r, 4), "F1": round(f, 4), "tp": tp, "fp": fp, "fn": fn}


def _score(pred: np.ndarray, true: np.ndarray) -> dict:
    return _prf(int((pred & true).sum()), int((pred & ~true).sum()), int((~pred & true).sum()))


def evaluate(truth_coef: np.ndarray, etype: dict, est, mem_mask: np.ndarray,
             mechanism: str = "linear", coef_override: np.ndarray | None = None) -> dict:
    true_cells = truth_coef != 0
    true_edges = true_cells.any(-1)
    pred_cells = est.active.astype(bool)
    pred_edges = pred_cells.any(-1)
    mem_c = np.broadcast_to(mem_mask[None, None, :, None], true_cells.shape)
    mem_e = np.broadcast_to(mem_mask[None, None, :], true_edges.shape)
    out = {
        "edge": _score(pred_edges, true_edges),
        "cell": _score(pred_cells, true_cells),
        "edge_mem": _score(pred_edges[mem_e], true_edges[mem_e]),
        "cell_mem": _score(pred_cells[mem_c], true_cells[mem_c]),
        "n_pred_edges": int(pred_edges.sum()),
        "n_pred_cells": int(pred_cells.sum()),
    }
    # typed recall
    for t in TYPES:
        es = [(i, j, l) for (i, j, l), tt in etype.items() if tt == t]
        if not es:
            continue
        e_found = [bool(pred_edges[i, l - 1, j]) for (i, j, l) in es]
        c_tot = sum(int(true_cells[i, l - 1, j].sum()) for (i, j, l) in es)
        c_hit = sum(int((true_cells[i, l - 1, j] & pred_cells[i, l - 1, j]).sum()) for (i, j, l) in es)
        c_fp = sum(int((~true_cells[i, l - 1, j] & pred_cells[i, l - 1, j]).sum()) for (i, j, l) in es)
        out[f"recall_edge_{t}"] = round(float(np.mean(e_found)), 4)
        out[f"recall_cell_{t}"] = round(c_hit / c_tot, 4) if c_tot else None
        out[f"fp_cell_{t}"] = c_fp
        out[f"missed_edge_{t}"] = [f"{i}->{j}@{l}" for (i, j, l), f in zip(es, e_found) if not f]
    # gate pattern on true memory edges
    mem_edges = [(i, j, l) for (i, j, l), tt in etype.items() if tt in ("write", "hold", "read")]
    exact, ham = [], []
    for (i, j, l) in mem_edges:
        tv, pv = true_cells[i, l - 1, j], pred_cells[i, l - 1, j]
        exact.append(bool(np.array_equal(tv, pv)))
        ham.append(float((tv == pv).mean()))
    out["gate_exact"] = round(float(np.mean(exact)), 4)
    out["gate_hamming_acc"] = round(float(np.mean(ham)), 4)
    # coefficient recovery
    if mechanism == "linear":
        coef = est.coef if coef_override is None else coef_override
        coef = np.where(pred_cells, coef, 0.0)
        err = np.abs(coef - truth_coef)
        out["coef_mae_true_cells"] = round(float(err[true_cells].mean()), 4)
        out["coef_mae_true_cells_mem"] = round(float(err[true_cells & mem_c].mean()), 4)
        out["coef_max_abs_false_cell_mem"] = round(float(err[~true_cells & mem_c].max()), 4)
    return out


def heatmap_rows(truth_coef, etype, est, names, coef_override=None):
    """Per memory edge: truth and estimate across the K regimes."""
    coef = est.coef if coef_override is None else coef_override
    coef = np.where(est.active.astype(bool), coef, 0.0)
    rows = []
    order = {"write": 0, "hold": 1, "read": 2}
    for (i, j, l), t in sorted(etype.items(), key=lambda kv: (order.get(kv[1], 9), kv[0])):
        if t not in order:
            continue
        rows.append({"edge": f"{names[i]}->{names[j]}@{l}", "type": t,
                     "truth": [round(float(v), 3) for v in truth_coef[i, l - 1, j]],
                     "est": [round(float(v), 3) for v in coef[i, l - 1, j]]})
    return {"regimes": REGIMES, "rows": rows}
