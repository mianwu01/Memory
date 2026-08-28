"""M4 — learn a TYPE-LEVEL causal graph over travel's 7 slot types, from data.

Closes the loop the P2 results doc flags as open (`p2-memoryarena-plugin-results.md`
par.5 item 4): the shipped `causal` arm uses a hand-written rule graph that reads the
person names straight out of the query, so it never runs discovery. Here we run
discovery and emit a JSON graph that `arena_causal_memory.CausalMemorySystem`
consumes in `graph_mode="learned"`.

Design follows `docs/memoryarena-instantiation.md`:
  par.2.2  variables = the 7 slot types (v0 granularity)
  par.3    X_t^i     = option (i) constraint-activation indicator, or (ii) numeric price
  par.4    samples   = episodes, as i.i.d. TRIALS -- pooling, never concatenation
  par.5    output    = lag-wise adjacency A^(1..L) over slot types

MULTI-TRIAL POOLING (par.4 calls this "the first real code work item").
`run_cdnots_gated(df, ...)` takes one contiguous DataFrame and, inside, does
`prepare_data(df, max_lag)` -> `tensor.T.unfold(1, max_lag+1, 1)`
(causalts/grace/gated_discovery.py:329). Handing it 270 concatenated episodes would
manufacture max_lag windows per episode boundary that straddle two unrelated trials.
So we do NOT call it. We rebuild its Step 2/3 around a trial-aware dataset:

  * windows are unfolded WITHIN each trial and then concatenated
    (`build_windows` below), so no window ever spans a boundary;
  * the model's loss is a mean of per-window Gaussian NLL
    (causalts/grace/gated_discovery.py:676-681), so concatenating windows across
    trials IS "sum the NLL across episodes" up to a constant factor;
  * everything else -- GatedCausalDiscovery, the Hard-Concrete gates, the L0
    penalty, compute_lambda, skeleton masking, gate thresholding -- is the
    library's own code, imported, not reimplemented.

The CI skeleton comes from tigramite PCMCI+ in `analysis_mode='multiple'`, which is
natively multi-trial, and is also reported standalone as the baseline discovery
method so the GRACE graph is not taken on faith.

Usage:
  export HF_HOME=... CUDA_VISIBLE_DEVICES=""
  python3 code/travel_grace_discovery.py --spec cell_price --max_lag 3 \
      --out results/real/travel_typegraph.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from t0_travel import parse_episode  # noqa: E402

# The 7-slot travel schema (env/env_systems/travel_env.py:11)
SLOTS7 = ["current_city", "transportation", "breakfast", "attraction",
          "lunch", "dinner", "accommodation"]
DB = (ROOT / "benchmarks" / "MemoryArena" / "env" / "env_systems"
      / "travel_planner_env" / "database")


# --------------------------------------------------------------------------- #
# 1. value encodings                                                          #
# --------------------------------------------------------------------------- #

_PRICE_CACHE: Dict[str, Dict[Tuple[str, str], float]] = {}


def _load_price_tables() -> Dict[str, Dict[Tuple[str, str], float]]:
    """(name, city) -> price, for restaurants and accommodations.

    Plans render venues as "<Name>, <City>(<State>)"; the CSVs key city without the
    parenthetical, hence the strip. Match rate on the 270 episodes is 97.8-99.9%
    per slot (misses are venues absent from the shipped preview CSVs).
    """
    if _PRICE_CACHE:
        return _PRICE_CACHE
    r = pd.read_csv(DB / "restaurants" / "clean_restaurant_2022.csv")
    a = pd.read_csv(DB / "accommodations" / "clean_accommodations_2022.csv")
    _PRICE_CACHE["rest"] = {(str(n).strip(), str(c).strip()): float(p)
                            for n, c, p in zip(r["Name"], r["City"], r["Average Cost"])}
    _PRICE_CACHE["acc"] = {(str(n).strip(), str(c).strip()): float(p)
                           for n, c, p in zip(a["NAME"], a["city"], a["price"])}
    return _PRICE_CACHE


def _venue_key(v: str) -> Optional[Tuple[str, str]]:
    parts = v.rsplit(",", 1)
    if len(parts) != 2:
        return None
    return parts[0].strip(), re.sub(r"\(.*\)", "", parts[1]).strip()


def cell_price(slot: str, v: Optional[str], vocab=None) -> float:
    """Numeric encoding (instantiation doc par.3 option (ii)) of one plan cell.

    price for meals/accommodation, parsed "cost: N" for transportation, number of
    listed venues for attraction, and -- because current_city has no numeric
    attribute at all -- a corpus-wide ordinal id of the city string.
    """
    if not v or v == "-":
        return float("nan")
    tab = _load_price_tables()
    k = _venue_key(v)
    if slot == "accommodation":
        p = tab["acc"].get(k, float("nan")) if k else float("nan")
    elif slot in ("breakfast", "lunch", "dinner"):
        p = tab["rest"].get(k, float("nan")) if k else float("nan")
    elif slot == "transportation":
        m = re.search(r"cost:\s*([\d,]+)", v)
        p = float(m.group(1).replace(",", "")) if m else float("nan")
    elif slot == "attraction":
        p = float(len([x for x in v.split(";") if x.strip()]))
    else:
        p = float("nan")
    if np.isnan(p) and vocab is not None:
        p = float(vocab.setdefault(slot, {}).setdefault(v, len(vocab[slot])))
    return p


def cell_id(slot: str, v: Optional[str], vocab) -> float:
    """Identity encoding: a corpus-wide ordinal id of the raw cell string.

    Under this encoding "person t copied person u's cell" is exactly "equal value",
    so it is the encoding under which travel's dominant mechanism -- verbatim
    copying of the shared trip scaffold and of `join` constraints -- is expressible
    as a lagged dependence. It is ordinal-arbitrary for cells that are NOT copies,
    which is a real limitation and is reported as such.
    """
    if not v or v == "-":
        return float("nan")
    return float(vocab.setdefault(slot, {}).setdefault(v, len(vocab[slot])))


# --------------------------------------------------------------------------- #
# 2. trial construction -- a trial is one i.i.d. multivariate sequence         #
# --------------------------------------------------------------------------- #

def plans_of(ep) -> List[list]:
    """[base_person, traveler_1, ..., traveler_T] daily_plans, in round order."""
    row = ep["row"]
    return [row["base_person"]["daily_plans"]] + list(row["answers"])


def build_trials(eps, spec: str):
    """Return (trials, var_names, meta).

    trials : list of float arrays [T_i, d]; each is ONE i.i.d. sample.
    spec   :
      "ind"        v0, X_t^s = 1[slot s is a constraint target at round t]
                   (doc par.3 option (i), the constraint-activation mask A_t^s,
                   read off the query text -- no gold plans, no database).
                   trial = episode, T = 1 + n_travelers (t=0 is the base person,
                   which by construction has no constraints).
      "price"      v0, X_t^s = mean over days of the numeric encoding of slot s
                   (doc par.3 option (ii)).  trial = episode.
      "cell_price" v1-projected: the day index is treated as an extra TRIAL index
                   rather than as extra variables, so the variable set stays the 7
                   slot types (sample-efficient) while values stay at gold
                   (day, slot) granularity.  trial = (episode, day), 1350 trials.
      "cell_id"    same trials as cell_price, values = ordinal id of the raw cell
                   string (see cell_id docstring).
    """
    vocab: Dict[str, Dict[str, int]] = {}
    trials, meta = [], []
    for ep in eps:
        P = plans_of(ep)
        T = len(P)
        if spec == "ind":
            arr = np.zeros((T, len(SLOTS7)), dtype=float)
            for rd in ep["rounds"]:
                for sent in rd["sentences"]:
                    tc = sent.get("tgt_cell") or {}
                    if tc.get("slot") in SLOTS7:
                        arr[rd["t"], SLOTS7.index(tc["slot"])] = 1.0
            trials.append(arr)
            meta.append({"episode": ep["id"], "D": ep["D"], "T": T})
        elif spec == "price":
            arr = np.full((T, len(SLOTS7)), np.nan)
            for t, plan in enumerate(P):
                for j, s in enumerate(SLOTS7):
                    vals = [cell_price(s, d.get(s), vocab) for d in plan]
                    vals = [v for v in vals if not np.isnan(v)]
                    arr[t, j] = float(np.mean(vals)) if vals else np.nan
            trials.append(arr)
            meta.append({"episode": ep["id"], "D": ep["D"], "T": T})
        elif spec in ("cell_price", "cell_id"):
            f = (lambda s, v: cell_price(s, v, vocab)) if spec == "cell_price" \
                else (lambda s, v: cell_id(s, v, vocab))
            for di in range(len(P[0])):
                arr = np.full((T, len(SLOTS7)), np.nan)
                for t, plan in enumerate(P):
                    if di >= len(plan):
                        continue
                    for j, s in enumerate(SLOTS7):
                        arr[t, j] = f(s, plan[di].get(s))
                trials.append(arr)
                meta.append({"episode": ep["id"], "D": ep["D"], "T": T, "day": di + 1})
        else:
            raise ValueError(f"unknown spec {spec!r}")
    return trials, list(SLOTS7), meta


def preprocess(trials, center_by_trial: bool):
    """Mean-impute, optionally remove the per-trial mean, then global z-score.

    center_by_trial removes the trial-level common cause. On travel that common
    cause is huge and real: everyone in an episode is in the SAME city on the SAME
    day, so venue prices share a level. Without centering, every lagged correlation
    is that level and is (diagnostically) flat in lag; see par.3 of the results doc.
    """
    d = trials[0].shape[1]
    stacked = np.concatenate(trials, 0)
    gmean = np.nanmean(stacked, 0)
    gmean = np.where(np.isnan(gmean), 0.0, gmean)
    out = []
    for A in trials:
        A = A.astype(float).copy()
        idx = np.where(np.isnan(A))
        A[idx] = np.take(gmean, idx[1])
        if center_by_trial:
            A = A - A.mean(0, keepdims=True)
        out.append(A)
    S = np.concatenate(out, 0)
    mu, sd = S.mean(0), S.std(0)
    keep = sd > 1e-9                       # zero-variance vars are undefined here
    sd = np.where(keep, sd, 1.0)
    out = [(A - mu) / sd for A in out]
    return out, keep


# --------------------------------------------------------------------------- #
# 3. discovery                                                                 #
# --------------------------------------------------------------------------- #

def pcmci_plus_multi(trials, var_names, max_lag: int, pc_alpha: float = 0.05,
                     verbose: bool = False):
    """Baseline: tigramite PCMCI+ with analysis_mode='multiple' (native multi-trial).

    Returns (G [cause, effect, lag] int8, val_matrix, runtime_s).
    """
    from tigramite import data_processing as pp
    from tigramite.independence_tests.parcorr import ParCorr
    from tigramite.pcmci import PCMCI

    t0 = time.time()
    data_dict = {i: np.ascontiguousarray(A) for i, A in enumerate(trials)
                 if len(A) > max_lag}
    dframe = pp.DataFrame(data_dict, analysis_mode="multiple",
                          var_names=list(var_names))
    pcmci = PCMCI(dataframe=dframe, cond_ind_test=ParCorr(significance="analytic"),
                  verbosity=1 if verbose else 0)
    res = pcmci.run_pcmciplus(tau_min=1, tau_max=max_lag, pc_alpha=pc_alpha)
    g = res["graph"]                                   # strings, [i, j, lag]
    d = len(var_names)
    G = np.zeros((d, d, max_lag + 1), dtype=np.int8)
    for i in range(d):
        for j in range(d):
            for lag in range(min(g.shape[2], max_lag + 1)):
                s = str(g[i, j, lag]).strip()
                if s == "-->":
                    G[i, j, lag] = 1
                elif s == "<--":
                    G[j, i, lag] = 1
    return G, res.get("val_matrix"), time.time() - t0


def build_windows(trials, max_lag: int):
    """Multi-trial windowing: unfold WITHIN each trial, then concatenate windows.

    Mirrors causalts.grace.gated_discovery.prepare_data (:314-333) exactly, except
    that the unfold is per trial. Returns a TensorDataset of [n_windows, d, L+1];
    index -1 along the last axis is time t (the target), matching the library's
    get_loss (`target = obs[..., -1]`, :676).
    """
    import torch
    from torch.utils.data import TensorDataset

    chunks = []
    for A in trials:
        if len(A) <= max_lag:
            continue                       # too short to contribute a window
        tt = torch.tensor(np.asarray(A, dtype=np.float32))
        w = tt.T.unfold(1, max_lag + 1, 1).permute(1, 0, 2)   # [T-L, d, L+1]
        chunks.append(w)
    if not chunks:
        raise ValueError("no trial is longer than max_lag")
    return TensorDataset(torch.cat(chunks, 0))


def grace_multitrial(trials, var_names, max_lag: int, skeleton: np.ndarray,
                     gate_threshold: float = 0.5, max_epochs: int = 60,
                     patience: int = 10, model_seed: int = 0,
                     batch_size: Optional[int] = None, verbose: bool = True,
                     **model_kwargs):
    """GRACE step 2/3 (gated refinement) over a trial-respecting window set.

    This is `run_cdnots_gated`'s body from ":1905 Step 2" onward, with
    prepare_data(df) swapped for build_windows(trials). Step 1 (the CI skeleton)
    is supplied by the caller -- PCMCI+ multi-dataset -- because CDNOTS' own
    skeleton call also assumes one contiguous series.
    """
    import math
    import torch
    from torch.utils.data import DataLoader
    from causalts.grace.gated_discovery import (GatedCausalDiscovery, compute_lambda,
                                                _detect_accelerator, _silence_lightning)
    from pytorch_lightning import Trainer, seed_everything
    from pytorch_lightning.callbacks import EarlyStopping

    t0 = time.time()
    d = len(var_names)
    dataset = build_windows(trials, max_lag)
    N = len(dataset)
    n_possible = d * d * (max_lag + 1) - d
    density = float(skeleton.sum()) / n_possible if n_possible else 0.0
    lambda_l0 = compute_lambda(d, N, density)
    if batch_size is None:
        batch_size = max(32, min(N // 8, 256))
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    steps_per_epoch = math.ceil(N / batch_size)

    seed_everything(model_seed, workers=True)
    model_kwargs.setdefault("lambda_lag_group", 0.0)
    model = GatedCausalDiscovery(num_vars=d, max_lag=max_lag,
                                 lambda_l0=float(lambda_l0), normalize_l0=True,
                                 steps_per_epoch=steps_per_epoch, **model_kwargs)
    model.init_from_skeleton(skeleton)
    model.set_skeleton_mask(skeleton)

    _silence_lightning()
    trainer = Trainer(max_epochs=max_epochs, accelerator=_detect_accelerator(),
                      deterministic="warn",
                      callbacks=[EarlyStopping(monitor="train_loss", patience=patience,
                                               mode="min")],
                      enable_progress_bar=False, enable_model_summary=False,
                      logger=False, enable_checkpointing=False)
    trainer.fit(model, train_dataloaders=loader)
    _, gate_values = model.get_estimated_graph(threshold=None)   # [cause, effect, lag]
    G = (gate_values >= gate_threshold).astype(np.int8)
    np.fill_diagonal(G[:, :, 0], 0)
    if verbose:
        print(f"  GRACE: {N} windows from {len(trials)} trials, lambda_L0={lambda_l0:.4f}, "
              f"{int(G.sum())} gates open ({time.time()-t0:.1f}s)")
    return G, gate_values, time.time() - t0


# --------------------------------------------------------------------------- #
# 4. ground truth: project the 270 instance DAGs to the type level             #
# --------------------------------------------------------------------------- #

def type_level_ground_truth(eps, max_lag: int, min_count: int = 1):
    """(src_slot, tgt_slot, lag) counts parsed from the query text (doc par.5).

    An edge is true iff some episode has a constraint sentence whose target cell has
    slot `tgt` and whose source cell has slot `src` and belongs to the person who
    spoke `lag` rounds earlier.
    """
    from collections import Counter
    lagged, collapsed = Counter(), Counter()
    for ep in eps:
        name2round = {n: k for k, n in enumerate(ep["names"])}
        for rd in ep["rounds"]:
            for sent in rd["sentences"]:
                if not sent["is_dep"]:
                    continue
                sc = sent.get("src_cell") or {}
                tc = sent.get("tgt_cell") or {}
                sp = name2round.get(sc.get("person"))
                if sp is None or not sc.get("slot") or not tc.get("slot"):
                    continue
                lag = rd["t"] - sp
                collapsed[(sc["slot"], tc["slot"])] += 1
                if 1 <= lag <= max_lag:
                    lagged[(sc["slot"], tc["slot"], lag)] += 1
    d = len(SLOTS7)
    G = np.zeros((d, d, max_lag + 1), dtype=np.int8)
    for (a, b, l), n in lagged.items():
        if n >= min_count:
            G[SLOTS7.index(a), SLOTS7.index(b), l] = 1
    return G, lagged, collapsed


def persistence_stats(eps) -> Dict[str, Dict[str, float]]:
    """Per-slot copy statistics -- data-derived, no query parsing, no gold labels.

    `constant_rate` : fraction of (episode, day) trials in which every round carries
                      the SAME string for this slot. A slot at 1.0 has literally zero
                      within-trial variance, so no discovery method can orient an
                      edge on it -- and, for a memory system, one retained copy is
                      provably sufficient.
    `copy_rate`     : fraction of round-t cells (t>=1) equal to some earlier round's
                      cell in the same trial.
    """
    out = {}
    for s in SLOTS7:
        const_num = const_den = copy_num = copy_den = 0
        for ep in eps:
            P = plans_of(ep)
            for di in range(len(P[0])):
                vals = [(P[t][di].get(s) if di < len(P[t]) else None) for t in range(len(P))]
                vals = [v for v in vals if v and v != "-"]
                if not vals:
                    continue
                const_den += 1
                const_num += int(len(set(vals)) == 1)
                for i in range(1, len(vals)):
                    copy_den += 1
                    copy_num += int(vals[i] in vals[:i])
        out[s] = {"constant_rate": round(const_num / const_den, 4) if const_den else None,
                  "copy_rate": round(copy_num / copy_den, 4) if copy_den else None,
                  "n_trials": const_den}
    return out


def edge_list(G, var_names, W=None):
    out = []
    d, _, L = G.shape
    for i in range(d):
        for j in range(d):
            for l in range(L):
                if G[i, j, l]:
                    e = {"cause": var_names[i], "effect": var_names[j], "lag": int(l)}
                    if W is not None:
                        e["weight"] = round(float(W[i, j, l]), 4)
                    out.append(e)
    return out


def prf(pred: np.ndarray, true: np.ndarray, lag_min: int = 1):
    p = pred[:, :, lag_min:].astype(bool)
    t = true[:, :, lag_min:].astype(bool)
    tp = int((p & t).sum()); fp = int((p & ~t).sum()); fn = int((~p & t).sum())
    P = tp / (tp + fp) if tp + fp else float("nan")
    R = tp / (tp + fn) if tp + fn else float("nan")
    F = 2 * P * R / (P + R) if P and R and not np.isnan(P) and not np.isnan(R) else 0.0
    return {"TP": tp, "FP": fp, "FN": fn, "P": round(P, 3) if P == P else None,
            "R": round(R, 3) if R == R else None, "F1": round(F, 3)}


def collapse_slots(G):
    """[cause, effect, lag] -> slot-type adjacency ignoring lag (any lag >= 1)."""
    return (G[:, :, 1:].sum(axis=2) > 0).astype(np.int8)


def slot_ancestors(adj: np.ndarray, var_names) -> Dict[str, List[str]]:
    """Transitive closure of the slot-type adjacency, as {effect: [causes...]}."""
    d = len(var_names)
    reach = adj.astype(bool).copy()
    for _ in range(d):                        # Floyd-Warshall style closure
        new = reach | (reach @ reach)
        if (new == reach).all():
            break
        reach = new
    return {var_names[j]: sorted(var_names[i] for i in range(d) if reach[i, j])
            for j in range(d)}


# --------------------------------------------------------------------------- #
# 5. main                                                                      #
# --------------------------------------------------------------------------- #

def load_episodes(n: Optional[int] = None):
    from datasets import load_dataset
    ds = load_dataset("ZexueHe/memoryarena", "group_travel_planner")
    split = "test" if "test" in ds else list(ds.keys())[0]
    raw = [dict(r) for r in ds[split]]
    if n:
        raw = raw[:n]
    return [parse_episode(r) for r in raw]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default="cell_id",
                    choices=["ind", "price", "cell_price", "cell_id", "all"])
    ap.add_argument("--max_lag", type=int, default=3)
    ap.add_argument("--pc_alpha", type=float, default=0.05)
    ap.add_argument("--gate_threshold", type=float, default=0.5)
    ap.add_argument("--max_epochs", type=int, default=60)
    ap.add_argument("--episodes", type=int, default=None)
    ap.add_argument("--no_center", action="store_true",
                    help="keep the trial-level common cause (diagnostic only)")
    ap.add_argument("--skip_grace", action="store_true")
    ap.add_argument("--out", default="results/real/travel_typegraph.json")
    ap.add_argument("--export", default=None,
                    help="also write a flat plugin-consumable graph to this path")
    ap.add_argument("--export_spec", default="cell_id")
    ap.add_argument("--export_method", default="grace", choices=["grace", "pcmci_plus"])
    a = ap.parse_args()

    eps = load_episodes(a.episodes)
    print(f"episodes={len(eps)}  rounds={sum(len(e['rounds']) for e in eps)}")

    Gt, lagged, collapsed = type_level_ground_truth(eps, a.max_lag)
    print(f"ground-truth type-level edges (lag 1..{a.max_lag}): {int(Gt.sum())}")
    print("  collapsed (src->tgt, corpus count):",
          {f"{k[0]}->{k[1]}": v for k, v in sorted(collapsed.items(), key=lambda x: -x[1])})

    pstats = persistence_stats(eps)
    print("per-slot persistence (constant within (episode,day) trial / copy rate):")
    for s, v in pstats.items():
        print(f"    {s:16s} constant={v['constant_rate']}  copy={v['copy_rate']}")

    specs = ["ind", "price", "cell_price", "cell_id"] if a.spec == "all" else [a.spec]
    report = {"schema": "travel-type-level-slot-graph/v1",
              "created": time.strftime("%Y-%m-%d %H:%M:%S"),
              "max_lag": a.max_lag, "slots": SLOTS7,
              "n_episodes": len(eps),
              "persistence": pstats,
              "ground_truth_edges": edge_list(Gt, SLOTS7),
              "ground_truth_collapsed": {f"{k[0]}->{k[1]}": v for k, v in collapsed.items()},
              "specs": {}}

    for spec in specs:
        print(f"\n########## spec = {spec} ##########")
        trials, var_names, meta = build_trials(eps, spec)
        Z, keep = preprocess(trials, center_by_trial=not a.no_center)
        degenerate = [var_names[i] for i in range(len(var_names)) if not keep[i]]
        active_idx = [i for i in range(len(var_names)) if keep[i]]
        active = [var_names[i] for i in active_idx]
        print(f"  trials={len(trials)}  T={sorted({len(t) for t in trials})}  "
              f"windows={sum(max(0, len(t)-a.max_lag) for t in trials)}")
        print(f"  degenerate (zero variance after preprocessing): {degenerate}")
        Za = [A[:, active_idx] for A in Z]

        skel, valm, t_pc = pcmci_plus_multi(Za, active, a.max_lag, a.pc_alpha)
        # re-embed into the full 7-slot frame
        def embed(Gs):
            d = len(var_names)
            G = np.zeros((d, d, a.max_lag + 1), dtype=Gs.dtype)
            for ii, i in enumerate(active_idx):
                for jj, j in enumerate(active_idx):
                    G[i, j, :] = Gs[ii, jj, :]
            return G
        Gp = embed(skel)
        print(f"  PCMCI+ (multi-dataset, {len(Za)} datasets): {int(Gp.sum())} edges "
              f"({t_pc:.1f}s)  eval vs GT: {prf(Gp, Gt)}")
        for e in edge_list(Gp, var_names):
            print("    PCMCI+ ", e)

        entry = {"n_trials": len(trials),
                 "n_windows": int(sum(max(0, len(t) - a.max_lag) for t in trials)),
                 "degenerate_slots": degenerate,
                 "center_by_trial": not a.no_center,
                 "pcmci_plus": {"edges": edge_list(Gp, var_names),
                                "eval": prf(Gp, Gt), "runtime_s": round(t_pc, 1)}}

        if not a.skip_grace:
            if int(skel.sum()) == 0:
                print("  GRACE: skeleton is empty -> every gate is hard-masked shut; "
                      "the gated refinement can only return the empty graph. "
                      "Running with a FULL skeleton instead so GRACE's L0 gates, "
                      "not PCMCI+, decide the edges.")
                full = np.ones((len(active), len(active), a.max_lag + 1), dtype=np.int8)
                full[:, :, 0] = 0
                skel_use, skel_src = full, "full (PCMCI+ returned empty)"
            else:
                skel_use, skel_src = skel, "pcmci_plus"
            Gg_s, Wg_s, t_g = grace_multitrial(
                Za, active, a.max_lag, skel_use,
                gate_threshold=a.gate_threshold, max_epochs=a.max_epochs)
            Gg = embed(Gg_s)
            Wg = np.zeros((len(var_names), len(var_names), a.max_lag + 1))
            for ii, i in enumerate(active_idx):
                for jj, j in enumerate(active_idx):
                    Wg[i, j, :] = Wg_s[ii, jj, :]
            print(f"  GRACE  : {int(Gg.sum())} edges  eval vs GT: {prf(Gg, Gt)}")
            for e in edge_list(Gg, var_names, Wg):
                print("    GRACE  ", e)
            entry["grace"] = {"edges": edge_list(Gg, var_names, Wg),
                              "eval": prf(Gg, Gt), "runtime_s": round(t_g, 1),
                              "skeleton_source": skel_src,
                              "gate_threshold": a.gate_threshold,
                              "pooling": "per-trial unfold, windows concatenated; "
                                         "NLL is a mean over windows so the loss sums "
                                         "across episodes with no cross-trial lag term"}
            adj = collapse_slots(Gg)
        else:
            adj = collapse_slots(Gp)

        for meth, G in [("pcmci_plus", Gp)] + ([("grace", Gg)] if not a.skip_grace else []):
            ad = collapse_slots(G)
            entry[meth]["slot_adjacency_any_lag"] = {
                var_names[j]: sorted(var_names[i] for i in range(len(var_names)) if ad[i, j])
                for j in range(len(var_names))}
            entry[meth]["slot_ancestors"] = slot_ancestors(ad, var_names)
        entry["slot_ancestors"] = slot_ancestors(adj, var_names)
        report["specs"][spec] = entry

    out = ROOT / a.out if not Path(a.out).is_absolute() else Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nwrote {out}")

    if a.export:
        spec, meth = a.export_spec, a.export_method
        s = report["specs"][spec]
        lag_cov = sum(v for k, v in lagged.items()) / max(1, sum(collapsed.values()))
        flat = {
            "schema": "travel-type-level-slot-graph/v1",
            "source": (f"{meth} on spec={spec}, max_lag={a.max_lag}, "
                       f"{len(eps)} episodes, {s['n_trials']} trials, "
                       f"{s['n_windows']} windows, center_by_trial={s['center_by_trial']}"),
            "created": report["created"],
            "slots": SLOTS7,
            "max_lag": a.max_lag,
            "edges": s[meth]["edges"],
            "slot_ancestors": s[meth]["slot_ancestors"],
            "slot_adjacency_any_lag": s[meth]["slot_adjacency_any_lag"],
            # slots whose value is IDENTICAL across every round of a trial: the
            # learned self-edge chain plus zero within-trial variance means one
            # retained copy provably reconstructs every round's value.
            "persistent_slots": [k for k, v in pstats.items()
                                 if (v["constant_rate"] or 0) >= 0.99],
            "lag_coverage": round(lag_cov, 4),
            "eval_vs_query_ground_truth": s[meth]["eval"],
            "notes": ("query-parsed ground truth covers only the explicit constraint "
                      "edges; it does not contain the shared-trip scaffold, so "
                      "scaffold self-edges score as FP against it. See "
                      "docs/p2-grace-integration-results.md."),
        }
        ep = ROOT / a.export if not Path(a.export).is_absolute() else Path(a.export)
        ep.parent.mkdir(parents=True, exist_ok=True)
        with open(ep, "w") as f:
            json.dump(flat, f, indent=2)
        print(f"wrote plugin graph {ep}  (persistent_slots={flat['persistent_slots']}, "
              f"lag_coverage={flat['lag_coverage']})")


if __name__ == "__main__":
    main()
