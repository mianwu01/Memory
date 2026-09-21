"""Observational temporal causal discovery on HM3's own event logs, and its use for selection.

Question (the bridge between the TCD line and the HM3 line): if we treat the HM3 training
histories as plain agent logs -- an ordered sequence of write events, no intervention labels,
no typed links, no parser -- does an off-the-shelf temporal causal discovery method recover
the type-level propagation skeleton that the interventional learner uses?  And if its graph
is used for selection, does it keep the reads flat and the executor correct?

Encodings (the variable definition is the experimental factor):
  event    one row per history record; x[t, type] = 1 if record t writes an object of that
           type (the log as an event series; lags are in write order)
  segment  one row per intervention segment; x[s, type] = 1 if any object of that type was
           written in segment s (the MemoryArena-style "activated in round s" encoding)

Estimators:
  pooled   lagged ridge regression per target with BH-FDR (regime_grace helpers; the pooled
           arm of E0), windows unfolded within each training episode and stacked
  pcmci    PCMCI+ (tigramite, analysis_mode='multiple') when the library is importable

The recovered type graph is compared with the interventional skeleton (LearnedGraph
templates projected to type pairs) and used by TCDSelect: breadth-first over the instance
links from the intervention source, following a link only when the type pair is a
recovered edge; records by the parser (tcd_select) or by same-key precedent (tcd_key_select).

Usage:
  PYTHONPATH=<pylib>:. python3 -m hm3.tcd_logs --domains travel shopping32 --seeds 0 1 2 \
      --out ../results/development/hm3/tcd/tcd_graphs_dev.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from .core import Episode, FallbackTracker, State, execute_intervention, restricted_est, segments
from .learners import Learner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from regime_grace import _bh, _lagged_design, _ridge_with_se  # noqa: E402


# ------------------------------------------------------------------ panels

def type_vocab(eps: List[Episode]) -> List[str]:
    return sorted({o.type for ep in eps for o in ep.S0.objects.values()})


def event_panel(eps: List[Episode], types: List[str], encoding: str = "event") -> List[Tuple[np.ndarray, np.ndarray]]:
    """Returns (X, exogenous) per trial.  ``exogenous`` marks the rows that are user
    interventions (queries): the log labels them, they are inputs to the system rather than
    responses to earlier writes, so they serve as predictors but never as targets."""
    idx = {t: i for i, t in enumerate(types)}
    trials = []
    for ep in eps:
        rows, exo = [], []
        if encoding == "event":
            for r in ep.H:
                v = np.zeros(len(types))
                if r["object_id"] in ep.S0.objects:
                    v[idx[ep.S0.get(r["object_id"]).type]] = 1.0
                rows.append(v)
                exo.append(r["kind"] == "intervention")
        else:
            for seg in segments(ep.H):
                v = np.zeros(len(types))
                for r in seg:
                    if r["object_id"] in ep.S0.objects:
                        v[idx[ep.S0.get(r["object_id"]).type]] = 1.0
                rows.append(v)
                exo.append(False)
        if len(rows) > 1:
            trials.append((np.array(rows), np.array(exo, bool)))
    return trials


# --------------------------------------------------------------- estimators

def fit_pooled(trials: List[np.ndarray], types: List[str], max_lag: int = 2, alpha: float = 0.05) -> dict:
    """Pooled lagged ridge regression with BH-FDR; windows never cross a trial boundary."""
    n = len(types)
    edges = {}
    for j in range(n):
        Ds, ys, cols = [], [], None
        for X, exo in trials:
            D, y, cols = _lagged_design(X, j, max_lag, valid=~exo)
            if len(y):
                Ds.append(D)
                ys.append(y)
        if not Ds:
            continue
        D = np.vstack(Ds)
        y = np.concatenate(ys)
        fit = _ridge_with_se(D, y)
        if fit is None:
            continue
        beta, _se, pval = fit
        keep = _bh(pval, alpha)
        for c, (i, l) in enumerate(cols):
            if keep[c]:
                edges[(types[i], types[j], l)] = {"coef": float(beta[c]), "p": float(pval[c])}
    return {"estimator": "pooled_lagged_ridge_fdr", "max_lag": max_lag, "alpha": alpha,
            "n_rows": int(sum(int((~exo).sum()) for _X, exo in trials)), "n_trials": len(trials),
            "edges": {f"{a}->{b}@{l}": v for (a, b, l), v in edges.items()}}


def fit_pcmci(trials: List[np.ndarray], types: List[str], max_lag: int = 2, alpha: float = 0.05) -> Optional[dict]:
    try:
        from tigramite import data_processing as pp
        from tigramite.independence_tests.parcorr import ParCorr
        from tigramite.pcmci import PCMCI
    except Exception as exc:  # pragma: no cover - optional dependency
        return {"estimator": "pcmci_plus", "error": f"{type(exc).__name__}: {exc}"}
    # tigramite has no per-row target mask; the exogenous rows stay in the series (documented);
    # trials shorter than the window cannot contribute and are dropped
    data = {k: X for k, (X, _exo) in enumerate(trials) if len(X) > max_lag + 1}
    if not data:
        return {"estimator": "pcmci_plus", "error": "no trial longer than max_lag + 1"}
    try:
        df = pp.DataFrame(data, analysis_mode="multiple", var_names=types)
        pcmci = PCMCI(dataframe=df, cond_ind_test=ParCorr(), verbosity=0)
        res = pcmci.run_pcmciplus(tau_min=1, tau_max=max_lag, pc_alpha=alpha)
    except Exception as exc:
        return {"estimator": "pcmci_plus", "error": f"{type(exc).__name__}: {exc}"}
    graph, val = res["graph"], res["val_matrix"]
    edges = {}
    n = len(types)
    for i in range(n):
        for j in range(n):
            for l in range(1, max_lag + 1):
                if graph[i, j, l] == "-->":
                    edges[f"{types[i]}->{types[j]}@{l}"] = {"coef": float(val[i, j, l]),
                                                            "p": float(res["p_matrix"][i, j, l])}
    return {"estimator": "pcmci_plus", "max_lag": max_lag, "alpha": alpha, "n_trials": len(trials),
            "edges": edges}


def type_edges_with_lag(fit: dict) -> Dict[Tuple[str, str], int]:
    """Type pairs with a positive lagged dependence and the smallest lag at which it appears."""
    out: Dict[Tuple[str, str], int] = {}
    for k, v in (fit or {}).get("edges", {}).items():
        a, rest = k.split("->")
        b, lag = rest.split("@")
        if a != b and v["coef"] > 0:
            out[(a, b)] = min(out.get((a, b), 99), int(lag))
    return out


def positive_type_edges(fit: dict) -> Set[Tuple[str, str]]:
    """Type pairs with a positive lagged dependence (a writes, then b writes), self-pairs excluded."""
    out = set()
    for k, v in (fit or {}).get("edges", {}).items():
        a, rest = k.split("->")
        b = rest.split("@")[0]
        if a != b and v["coef"] > 0:
            out.add((a, b))
    return out


def skeleton_type_edges(g) -> Set[Tuple[str, str]]:
    """Interventional skeleton projected to type pairs along each template."""
    out = set()
    for ptype, template in g.skeleton:
        prev = ptype
        for _rel, ctype in template:
            if prev != ctype:
                out.add((prev, ctype))
            prev = ctype
    return out


def compare(edges: Set[Tuple[str, str]], ref: Set[Tuple[str, str]]) -> dict:
    tp = len(edges & ref)
    return {"n": len(edges), "n_ref": len(ref), "tp": tp,
            "precision": tp / len(edges) if edges else None, "recall": tp / len(ref) if ref else None,
            "missing": sorted(f"{a}->{b}" for a, b in ref - edges),
            "extra": sorted(f"{a}->{b}" for a, b in edges - ref)}


# ---------------------------------------------------------------- selection

def adjacency_reads(ep: Episode, adj, max_expansions: int = 400) -> List[str]:
    """Objects reachable from the source over instance links under a recovered type graph.

    ``adj`` is either a set of type pairs (each edge is followed one instance hop) or a dict
    {(a, b): lag}: an edge a->b at lag l means "a write on a type-a object is followed within l steps
    by a write on a type-b object", and is unrolled to the type-b objects within l link hops of the
    type-a object (so a lag-3 edge flight->dinner reaches the dinner through transfer and stay even
    when the mediating edges were pruned)."""
    S0 = ep.S0
    src = ep.I["object_id"]
    lags = adj if isinstance(adj, dict) else {e: 1 for e in adj}
    rev: Dict[str, List[str]] = defaultdict(list)
    for o in S0.objects.values():
        for ts in o.links.values():
            for t in ts:
                rev[t].append(o.id)

    def nbrs(o):
        return [t for ts in S0.get(o).links.values() for t in ts if t in S0.objects] + rev.get(o, [])

    seen = [src]
    frontier = [src]
    budget = max_expansions
    while frontier and budget > 0:
        a = frontier.pop(0)
        at = S0.get(a).type
        for (ta, tb), lag in lags.items():
            if ta != at:
                continue
            # objects of type tb within `lag` hops of a
            layer, visited = [a], {a}
            for _ in range(lag):
                nxt = []
                for o in layer:
                    for c in nbrs(o):
                        budget -= 1
                        if c not in visited:
                            visited.add(c)
                            nxt.append(c)
                            if S0.get(c).type == tb and c not in seen:
                                seen.append(c)
                                frontier.append(c)
                layer = nxt
    return seen


class TCDSelect(Learner):
    """tcd_select / tcd_key_select: the type graph is estimated by observational TCD on the
    native training logs (fit_native); selection follows instance links restricted to the
    recovered type pairs; records by the parser or by same-key precedent."""

    fit_native = True

    def __init__(self, records: str = "parser", estimator: str = "pooled", encoding: str = "event",
                 max_lag: int = 3, alpha: float = 0.05, n_prec: int = 2, lag_aware: bool = False,
                 graphs_file: Optional[str] = None):
        """estimator: pooled | pcmci | grace_<mode> (grace modes are read from graphs_file, written by
        hm3.grace_logs, keyed by domain/seed; lag_aware unrolls a lag-l type edge over l instance hops)."""
        self.records, self.estimator, self.encoding = records, estimator, encoding
        self.max_lag, self.alpha, self.n_prec = max_lag, alpha, n_prec
        self.lag_aware, self.graphs_file = lag_aware, graphs_file
        base = "tcd_select" if records == "parser" else "tcd_key_select"
        suffix = "" if (estimator == "pooled" and encoding == "event") else f"_{estimator}_{encoding}"
        self.name = base + suffix + ("_lag" if lag_aware else "")
        self._domain_seed = None

    def fit(self, domain, train):
        self.types = type_vocab(train)
        trials = event_panel(train, self.types, self.encoding)
        if self.estimator == "pooled":
            self.fit_result = fit_pooled(trials, self.types, self.max_lag, self.alpha)
        elif self.estimator == "pcmci":
            self.fit_result = fit_pcmci(trials, self.types, self.max_lag, self.alpha)
        elif self.estimator.startswith("grace"):
            # precomputed by hm3.grace_logs (its own library environment); keyed by the training split
            ep0 = train[0]
            key = f"{ep0.domain}/seed{ep0.seed - (100 if ep0.seed >= 100 else 0)}"
            graphs = json.load(open(self.graphs_file))["runs"]
            self.fit_result = graphs[key]["encodings"][self.encoding][self.estimator]
        else:
            raise KeyError(self.estimator)
        if self.fit_result is None or "error" in self.fit_result:
            print(f"[{self.name}] estimator failed: {self.fit_result}", flush=True)
        self.adj = type_edges_with_lag(self.fit_result) if self.lag_aware else positive_type_edges(self.fit_result)

    def select(self, domain, ep: Episode) -> dict:
        objs = adjacency_reads(ep, self.adj)
        if self.records == "parser":
            prov: Dict[str, list] = {}
            domain.infer_params(ep.H, ep.S0, prov)
            recs: Set[str] = set()
            for oid in objs:
                for name, key in domain.param_keys_for(ep.S0.get(oid), ep.S0):
                    recs.update(prov.get(f"{name}[{key}]", []))
            order = {r["rid"]: i for i, r in enumerate(ep.H)}
            records = sorted(recs, key=lambda r: order[r])
        else:
            from .keysel import key_precedent_records
            records = key_precedent_records(domain, ep, objs, self.n_prec)
        return {"objects": sorted(objs), "records": records}

    def predict(self, domain, ep):
        reads = self.select(domain, ep)
        est = restricted_est(domain, ep.H, ep.S0, reads["records"])
        tr = FallbackTracker(est)
        post = ep.S0.copy()
        try:
            _rc, txns, tr = execute_intervention(domain, est, post, ep.I, tr)
        except Exception:
            txns = []
        return {"txns": txns, "reads": reads}


# ------------------------------------------------------------------- driver

def run(domains: List[str], seeds: List[int], n_train: int, out: str, max_lag: int = 3, alpha: float = 0.05,
        train_seed_offset: int = 0) -> dict:
    from .domains import get_domain
    from .generate import generate_split
    from .learners import LearnedGraph
    results = {"config": {"domains": domains, "seeds": seeds, "n_train": n_train, "max_lag": max_lag,
                          "alpha": alpha}, "runs": {}}
    for dname in domains:
        domain = get_domain(dname)
        for seed in seeds:
            t0 = time.time()
            train = generate_split(domain, seed + train_seed_offset, "train", n_train)
            types = type_vocab(train)
            g = LearnedGraph()
            g.fit(domain, train)
            ref = skeleton_type_edges(g)
            entry = {"types": types, "skeleton_type_edges": sorted(f"{a}->{b}" for a, b in ref),
                     "n_templates": len(g.skeleton), "encodings": {}}
            for enc in ("event", "segment"):
                trials = event_panel(train, types, enc)
                fits = {"pooled": fit_pooled(trials, types, max_lag, alpha),
                        "pcmci": fit_pcmci(trials, types, max_lag, alpha)}
                encs = {"n_trials": len(trials), "mean_T": float(np.mean([len(x) for x, _e in trials]))}
                for name, fit in fits.items():
                    if fit is None or "error" in fit:
                        encs[name] = fit
                        continue
                    pos = positive_type_edges(fit)
                    fit["positive_type_edges"] = sorted(f"{a}->{b}" for a, b in pos)
                    fit["self_edges"] = sorted(k for k in fit["edges"] if k.split("->")[0] == k.split("->")[1].split("@")[0])
                    fit["vs_skeleton"] = compare(pos, ref)
                    encs[name] = fit
                entry["encodings"][enc] = encs
            entry["seconds"] = time.time() - t0
            results["runs"][f"{dname}/seed{seed}"] = entry
            ev = entry["encodings"]["event"]["pooled"]["vs_skeleton"]
            sg = entry["encodings"]["segment"]["pooled"]["vs_skeleton"]
            print(f"{dname}/seed{seed}: skeleton {len(ref)} type edges; event/pooled P={ev['precision']} R={ev['recall']} "
                  f"extra={ev['extra']} missing={ev['missing']}; segment/pooled P={sg['precision']} R={sg['recall']}", flush=True)
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            json.dump(results, open(out, "w"), indent=1, default=str)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="+", default=["travel", "shopping32"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--n_train", type=int, default=200)
    ap.add_argument("--max_lag", type=int, default=3)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--train_seed_offset", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    run(a.domains, a.seeds, a.n_train, a.out, a.max_lag, a.alpha, a.train_seed_offset)
