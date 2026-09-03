"""Every non-oracle baseline, all trained on the same (H, S0, I, A, S1, R) data.

A learner returns a *structural* plan: which objects to touch, with which op,
manual or automatic, which fields.  Values are then computed by the shared
executor (core.plan_to_txns) from the domain's local rules and from whatever
regime parameters the learner's history reads make recoverable.  A learner
that does not read history therefore cannot recover hidden parameters.

  exact_kv         the query is a KV update; nothing else is written
  source_union     union of every impact template ever seen for this source type
  source_regime    lookup table keyed by source + visible categorical fields
  knn              transition kNN over episode-level features, copies templates
  flat             per-object black-box classifier on slot-position features
  flat_est         the same with the history parser's regime estimates added
  gnn              permutation-equivariant message passing over the link graph
  gnn_est          the same with regime estimates added
  superset         learned skeleton with every edge forced on (conservative)
  program          strongest relational learner: typed paths + witness stats +
                   regime estimates + 1-hop neighbour context, iterated once
  graph            learned causal graph: typed-path skeleton + per-edge gated
                   mechanism (decision tree over local deltas and regime
                   estimates) + propagation through the executor
  rh_oracle        runtime-history oracle: true mechanism, parameters parsed from H
  oracle           the gold plan
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

from .core import (Episode, FallbackTracker, Obj, State, Tracker, execute_intervention,
                   hop_distances, plan_to_txns, restricted_est)
from .features import (dict_equalities, est_linked_vector, est_vector, global_history, label_of,
                       neighborhood_overlap, numeric_slots, numeric_vector, own_history, param_names,
                       parse_label, path_types, shares_tokens, sibling_ranks, source_new_fields,
                       witness_vector)


def candidates(ep: Episode) -> List[Obj]:
    return [o for oid, o in sorted(ep.S0.objects.items()) if oid != ep.I["object_id"]]


def all_reads(ep: Episode) -> dict:
    return {"objects": sorted(ep.S0.objects), "records": [r["rid"] for r in ep.H]}


def objects_only(ep: Episode, oids) -> dict:
    return {"objects": sorted(set(oids) | {ep.I["object_id"]}), "records": []}


def plan_from_labels(labels: Dict[str, str]) -> List[dict]:
    plan = []
    for oid, label in labels.items():
        for item in parse_label(label):
            plan.append({"object_id": oid, **item})
    return plan


class Learner:
    name = "base"

    def fit(self, domain, train: List[Episode]) -> None:
        pass

    def predict(self, domain, ep: Episode) -> dict:
        raise NotImplementedError


# ----------------------------------------------------------------- trivial

class ExactKV(Learner):
    name = "exact_kv"

    def predict(self, domain, ep):
        return {"plan": [], "reads": objects_only(ep, [])}


class Oracle(Learner):
    name = "oracle"

    def predict(self, domain, ep):
        return {"txns": ep.A, "reads": ep.required_reads}


class RuntimeHistoryOracle(Learner):
    name = "rh_oracle"

    def predict(self, domain, ep):
        prov: Dict[str, list] = {}
        est = domain.infer_params(ep.H, ep.S0, prov)
        tr = FallbackTracker(est)
        post = ep.S0.copy()
        _rc, txns, tr = execute_intervention(domain, est, post, ep.I, tr)
        records = sorted({rid for pk in tr.consulted for rid in prov.get(pk, [])})
        return {"txns": txns, "reads": {"objects": list(tr.read_objects), "records": records}}


# ------------------------------------------------------------ lookup tables

class SourceUnion(Learner):
    name = "source_union"

    def fit(self, domain, train):
        self.table: Dict[tuple, Dict[tuple, Counter]] = defaultdict(lambda: defaultdict(Counter))
        for ep in train:
            paths = path_types(ep.S0, ep.I["object_id"])
            key = (ep.S0.get(ep.I["object_id"]).type, ep.I["op"])
            for c in candidates(ep):
                p = paths.get(c.id)
                if p is None:
                    continue
                self.table[key][p][label_of(ep, c.id)] += 1

    def predict(self, domain, ep):
        paths = path_types(ep.S0, ep.I["object_id"])
        key = (ep.S0.get(ep.I["object_id"]).type, ep.I["op"])
        labels = {}
        for c in candidates(ep):
            p = paths.get(c.id)
            counts = self.table.get(key, {}).get(p) if p is not None else None
            if not counts:
                continue
            positive = Counter({k: v for k, v in counts.items() if k != "none"})
            if positive:
                labels[c.id] = positive.most_common(1)[0][0]
        return {"plan": plan_from_labels(labels), "reads": objects_only(ep, list(labels))}


class SourceRegimeTable(Learner):
    name = "source_regime"

    def _fine_key(self, domain, ep, c, p):
        cat = domain.categorical_fields().get(c.type, [])
        return (ep.S0.get(ep.I["object_id"]).type, ep.I["op"], p, c.status,
                tuple(str(c.fields.get(f)) for f in cat))

    def fit(self, domain, train):
        self.fine: Dict[tuple, Counter] = defaultdict(Counter)
        self.coarse: Dict[tuple, Counter] = defaultdict(Counter)
        for ep in train:
            paths = path_types(ep.S0, ep.I["object_id"])
            for c in candidates(ep):
                p = paths.get(c.id)
                if p is None:
                    continue
                lab = label_of(ep, c.id)
                self.fine[self._fine_key(domain, ep, c, p)][lab] += 1
                self.coarse[(ep.S0.get(ep.I["object_id"]).type, ep.I["op"], p)][lab] += 1

    def predict(self, domain, ep):
        paths = path_types(ep.S0, ep.I["object_id"])
        labels = {}
        for c in candidates(ep):
            p = paths.get(c.id)
            if p is None:
                continue
            counts = self.fine.get(self._fine_key(domain, ep, c, p)) or \
                self.coarse.get((ep.S0.get(ep.I["object_id"]).type, ep.I["op"], p))
            if not counts:
                continue
            lab = counts.most_common(1)[0][0]
            if lab != "none":
                labels[c.id] = lab
        return {"plan": plan_from_labels(labels), "reads": objects_only(ep, list(labels))}


# -------------------------------------------------------------- vocabularies

def would_change(domain, scratch: State, c_now: Obj, label: str, tr) -> float:
    """Simulate the declared local value rule for the label's first non-empty
    payload on the scratch state and report whether it differs from the
    object's current value (1 / 0), or -1 when the rule gives no value."""
    for it in parse_label(label):
        try:
            obj = scratch.get(c_now.id)
            payload = domain.local_payload(scratch, obj, it["op"], it.get("fields"), tr)
        except Exception:
            return -1.0
        if not payload:
            continue
        return 1.0 if any(c_now.fields.get(k) != v for k, v in payload.items()) else 0.0
    return -1.0


def type_consistent_predict(clf, rows, types, allowed: Dict[str, set]) -> List[str]:
    """Argmax over the labels that were ever observed for the object's type."""
    if not rows:
        return []
    proba = clf.predict_proba(np.array(rows))
    classes = list(clf.classes_)
    out = []
    for prow, t in zip(proba, types):
        best, best_p = "none", -1.0
        for lab, pr in zip(classes, prow):
            if lab != "none" and lab not in allowed.get(t, set()):
                continue
            if pr > best_p:
                best, best_p = lab, pr
        out.append(best)
    return out


class Vocab:
    def __init__(self, domain, train: List[Episode]):
        self.types = sorted({o.type for ep in train for o in ep.S0.objects.values()})
        self.ops = sorted({r["op"] for ep in train for r in ep.R} | set(domain.OPS) |
                          {r["op"] for ep in train for r in ep.H})
        self.src_ops = sorted({ep.I["op"] for ep in train})
        self.slots = numeric_slots(domain)
        self.labels = sorted({label_of(ep, c.id) for ep in train for c in candidates(ep)} | {"none"})
        self.allowed: Dict[str, set] = defaultdict(set)
        for ep in train:
            for c in candidates(ep):
                self.allowed[c.type].add(label_of(ep, c.id))
        self.paths = [p for p, _ in Counter(
            p for ep in train for p in path_types(ep.S0, ep.I["object_id"]).values()).most_common(96)]
        self.names = param_names(domain)
        self.rels = domain.relation_names()

    def onehot(self, vocab, value):
        return [1.0 if value == v else 0.0 for v in vocab]


def source_numeric_delta(ep: Episode) -> float:
    src = ep.S0.get(ep.I["object_id"])
    for k, v in ep.I["payload"].items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and isinstance(src.fields.get(k), (int, float)):
            return float(v - src.fields[k])
    return 0.0


# ------------------------------------------------------------------- kNN

class TransitionKNN(Learner):
    name = "knn"

    def __init__(self, k: int = 5):
        self.k = k

    def _vec(self, ep):
        v = self.vocab
        src = ep.S0.get(ep.I["object_id"])
        counts = Counter(o.type for o in ep.S0.objects.values())
        return np.array(v.onehot(v.types, src.type) + v.onehot(v.src_ops, ep.I["op"]) +
                        [source_numeric_delta(ep)] + [float(counts.get(t, 0)) for t in v.types] +
                        global_history(ep.H, v.ops), dtype=float)

    def fit(self, domain, train):
        self.vocab = Vocab(domain, train)
        self.X = np.stack([self._vec(ep) for ep in train])
        self.mu, self.sd = self.X.mean(0), self.X.std(0) + 1e-6
        self.X = (self.X - self.mu) / self.sd
        self.maps = []
        for ep in train:
            paths = path_types(ep.S0, ep.I["object_id"])
            self.maps.append({paths[c.id]: label_of(ep, c.id) for c in candidates(ep) if c.id in paths})

    def predict(self, domain, ep):
        x = (self._vec(ep) - self.mu) / self.sd
        idx = np.argsort(((self.X - x) ** 2).sum(1))[:self.k]
        paths = path_types(ep.S0, ep.I["object_id"])
        labels = {}
        for c in candidates(ep):
            p = paths.get(c.id)
            votes = Counter(self.maps[i].get(p, "none") for i in idx)
            lab = votes.most_common(1)[0][0]
            if lab != "none":
                labels[c.id] = lab
        return {"plan": plan_from_labels(labels), "reads": all_reads(ep)}


# ------------------------------------------------------- flat black box

class FlatBlackBox(Learner):
    def __init__(self, use_est: bool = False):
        self.use_est = use_est
        self.name = "flat_est" if use_est else "flat"

    def _rows(self, domain, ep, est=None):
        v = self.vocab
        src = ep.S0.get(ep.I["object_id"])
        base = v.onehot(v.types, src.type) + v.onehot(v.src_ops, ep.I["op"]) + [source_numeric_delta(ep)] + \
            global_history(ep.H, v.ops)
        ids = sorted(ep.S0.objects)
        rows, oids = [], []
        for c in candidates(ep):
            pos = ids.index(c.id)
            row = [1.0 if pos == i else 0.0 for i in range(48)] + v.onehot(v.types, c.type) + \
                [1.0 if c.status == "active" else 0.0] + numeric_vector(c, v.slots) + \
                own_history(ep.H, c.id) + base
            if self.use_est:
                row += est_vector(domain, est, c, ep.S0, v.names)
            rows.append(row)
            oids.append(c.id)
        return rows, oids

    def fit(self, domain, train):
        from sklearn.ensemble import HistGradientBoostingClassifier
        self.vocab = Vocab(domain, train)
        X, y = [], []
        for ep in train:
            est = domain.infer_params(ep.H, ep.S0) if self.use_est else None
            rows, oids = self._rows(domain, ep, est)
            X += rows
            y += [label_of(ep, o) for o in oids]
        self.clf = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08, min_samples_leaf=4,
                                                  random_state=0)
        self.clf.fit(np.array(X), np.array(y))

    def predict(self, domain, ep):
        est = domain.infer_params(ep.H, ep.S0) if self.use_est else None
        rows, oids = self._rows(domain, ep, est)
        pred = type_consistent_predict(self.clf, rows, [ep.S0.get(o).type for o in oids], self.vocab.allowed)
        labels = {o: lab for o, lab in zip(oids, pred) if lab != "none"}
        return {"plan": plan_from_labels(labels), "reads": all_reads(ep)}


# ------------------------------------------------- equivariant predictor

class EquivariantGNN(Learner):
    def __init__(self, use_est: bool = False, hidden: int = 64, epochs: int = 40, seed: int = 0):
        self.use_est = use_est
        self.name = "gnn_est" if use_est else "gnn"
        self.hidden, self.epochs, self.seed = hidden, epochs, seed

    def _graph(self, domain, ep, est=None):
        v = self.vocab
        ids = sorted(ep.S0.objects)
        index = {oid: i for i, oid in enumerate(ids)}
        src = ep.S0.get(ep.I["object_id"])
        ctx = v.onehot(v.src_ops, ep.I["op"]) + [source_numeric_delta(ep)]
        feats = []
        for oid in ids:
            o = ep.S0.get(oid)
            row = v.onehot(v.types, o.type) + [1.0 if o.status == "active" else 0.0] + \
                numeric_vector(o, v.slots) + [1.0 if oid == src.id else 0.0] + own_history(ep.H, oid) + ctx
            if self.use_est:
                row += est_vector(domain, est, o, ep.S0, v.names)
            feats.append(row)
        edges = []  # (src index, dst index, relation index)
        for oid in ids:
            for rel, targets in ep.S0.get(oid).links.items():
                if rel not in v.rels:
                    continue
                r = v.rels.index(rel)
                for t in targets:
                    if t in index:
                        edges.append((index[oid], index[t], r))
                        edges.append((index[t], index[oid], r + len(v.rels)))
        return np.array(feats, dtype=np.float32), edges, ids

    def fit(self, domain, train):
        import torch
        import torch.nn as nn
        torch.manual_seed(self.seed)
        self.vocab = Vocab(domain, train)
        graphs = []
        for ep in train:
            est = domain.infer_params(ep.H, ep.S0) if self.use_est else None
            f, e, ids = self._graph(domain, ep, est)
            labels = [self.vocab.labels.index(label_of(ep, oid)) if oid != ep.I["object_id"] else -1 for oid in ids]
            graphs.append((f, e, np.array(labels)))
        allf = np.concatenate([g[0] for g in graphs])
        self.mu, self.sd = allf.mean(0), allf.std(0) + 1e-6
        n_rel = 2 * len(self.vocab.rels)
        d_in, h, n_out = allf.shape[1], self.hidden, len(self.vocab.labels)

        class Net(nn.Module):
            def __init__(s):
                super().__init__()
                s.inp = nn.Linear(d_in, h)
                s.self_w = nn.ModuleList([nn.Linear(h, h) for _ in range(3)])
                s.rel_w = nn.ModuleList([nn.Linear(h + n_rel, h) for _ in range(3)])
                s.out = nn.Sequential(nn.Linear(h, h), nn.ReLU(), nn.Linear(h, n_out))

            def forward(s, x, edges):
                hcur = torch.relu(s.inp(x))
                if edges:
                    e = torch.tensor(edges, dtype=torch.long)
                    src_i, dst_i, rel_i = e[:, 0], e[:, 1], e[:, 2]
                    rel_onehot = torch.nn.functional.one_hot(rel_i, n_rel).float()
                for layer in range(3):
                    agg = torch.zeros_like(hcur)
                    if edges:
                        msg = s.rel_w[layer](torch.cat([hcur[src_i], rel_onehot], 1))
                        agg = agg.index_add(0, dst_i, msg)
                        deg = torch.zeros(hcur.shape[0]).index_add(0, dst_i, torch.ones(len(dst_i)))
                        agg = agg / deg.clamp(min=1).unsqueeze(1)
                    hcur = torch.relu(s.self_w[layer](hcur) + agg)
                return s.out(hcur)

        self.net = Net()
        opt = torch.optim.Adam(self.net.parameters(), lr=3e-3)
        weights = torch.ones(n_out)
        weights[self.vocab.labels.index("none")] = 0.3
        lossf = nn.CrossEntropyLoss(weight=weights, ignore_index=-1)
        rng = random.Random(self.seed)
        for _ in range(self.epochs):
            order = list(range(len(graphs)))
            rng.shuffle(order)
            for i in order:
                f, e, y = graphs[i]
                x = torch.tensor((f - self.mu) / self.sd)
                loss = lossf(self.net(x, e), torch.tensor(y))
                opt.zero_grad()
                loss.backward()
                opt.step()
        self.net.eval()

    def predict(self, domain, ep):
        import torch
        est = domain.infer_params(ep.H, ep.S0) if self.use_est else None
        f, e, ids = self._graph(domain, ep, est)
        with torch.no_grad():
            logits = self.net(torch.tensor((f - self.mu) / self.sd), e)
        labels = {}
        for i, oid in enumerate(ids):
            if oid == ep.I["object_id"]:
                continue
            allowed = self.vocab.allowed.get(ep.S0.get(oid).type, set())
            best, best_v = "none", None
            for j, lab in enumerate(self.vocab.labels):
                if lab != "none" and lab not in allowed:
                    continue
                v = float(logits[i, j])
                if best_v is None or v > best_v:
                    best, best_v = lab, v
            if best != "none":
                labels[oid] = best
        return {"plan": plan_from_labels(labels), "reads": all_reads(ep)}


# ---------------------------------------------------- learned causal graph

def follow_template(state: State, start: str, template: tuple) -> List[str]:
    """Objects reachable from ``start`` along a typed relation path."""
    frontier = [start]
    for rel, typ in template:
        nxt = []
        for oid in frontier:
            o = state.get(oid)
            if rel.startswith("~"):
                base = rel[1:]
                targets = [x.id for x in state.objects.values() if oid in x.links.get(base, [])]
            else:
                targets = o.linked(rel)
            nxt += [t for t in targets if t in state.objects and state.get(t).type == typ]
        frontier = list(dict.fromkeys(nxt))
    return [x for x in frontier if x != start]


class LearnedGraph(Learner):
    """Type-level skeleton of typed paths along which effects propagate, and a
    per-path gated local mechanism fitted from training outcomes."""

    name = "graph"
    MAX_TEMPLATE_HOPS = 3

    def __init__(self, min_support: int = 2, max_depth: int = 5, superset: bool = False):
        self.min_support = min_support
        self.max_depth = max_depth
        self.superset = superset
        if superset:
            self.name = "superset"

    def _feat(self, domain, p: Obj, p_new: dict, c: Obj, state: State, est: dict, pkind: str,
              wc: float = -1.0) -> List[float]:
        v = self.vocab
        pslots = [(t, f) for t, f in v.slots if t == p.type]
        cslots = [(t, f) for t, f in v.slots if t == c.type]
        pv = numeric_vector(p, pslots, p_new)
        cv = numeric_vector(c, cslots)
        row = [a - b for a in pv for b in cv] + pv + cv + [1.0 if c.status == "active" else 0.0] + \
            [shares_tokens(c, p_new, p.id)] + [1.0 if pkind == k else 0.0 for k in ("source", "auto", "txn")]
        row += dict_equalities(c, p_new) + neighborhood_overlap(c, state) + sibling_ranks(c, state, v.slots)
        row += est_vector(domain, est, c, state, v.names) + est_vector(domain, est, p, state, v.names)
        row += est_linked_vector(domain, est, c, state, v.names, p)
        row += [self._code(est.get(n, {}).get("global")) for n in v.names]
        row.append(wc)
        return row

    @staticmethod
    def _code(val):
        if val is None:
            return -1.0
        if isinstance(val, str):
            return float({"propagate": 0, "ignore": 1}.get(val, 2))
        return float(val)

    def _closest_changed_ancestor(self, ep: Episode, changed: Dict[str, str], dist_src: dict, c: str):
        best = None
        for a in changed:
            if a == c:
                continue
            paths = path_types(ep.S0, a, self.MAX_TEMPLATE_HOPS)
            if c not in paths:
                continue
            cand = (len(paths[c]), dist_src.get(a, 99), a, paths[c])
            if best is None or cand[:2] < best[:2]:
                best = cand
        return best

    def fit(self, domain, train):
        from sklearn.tree import DecisionTreeClassifier
        self.vocab = Vocab(domain, train)
        positives: Dict[tuple, list] = defaultdict(list)   # (ptype, template) -> [(ep_idx, a, c, pkind, label)]
        episode_info = []
        for ei, ep in enumerate(train):
            src = ep.I["object_id"]
            labels = {c.id: label_of(ep, c.id) for c in candidates(ep)}
            changed = {oid: lab for oid, lab in labels.items() if lab != "none"}
            changed[src] = "source"
            dist_src = hop_distances(ep.S0, src)
            est = domain.infer_params(ep.H, ep.S0)
            new_fields = {oid: ep.S1.get(oid).fields for oid in changed}
            for c in changed:
                if c == src:
                    continue
                best = self._closest_changed_ancestor(ep, changed, dist_src, c)
                if best is None:
                    continue
                _, _, a, template = best
                pk = "source" if a == src else ("auto" if "auto" in changed[a] and "txn" not in changed[a] else "txn")
                positives[(ep.S0.get(a).type, template)].append((ei, a, c, pk, labels[c]))
            episode_info.append((ep, changed, new_fields, est))
        self.skeleton = {k: v for k, v in positives.items() if len(v) >= self.min_support}
        self.majority = {k: Counter(r[4] for r in v).most_common(1)[0][0] for k, v in self.skeleton.items()}
        # features: positives, then negatives along skeleton templates (reachable objects that did not change);
        # the would-change term simulates the declared local value rule at the post-state
        data: Dict[tuple, list] = defaultdict(list)
        trackers = [FallbackTracker(info[3]) for info in episode_info]
        for key, rows in self.skeleton.items():
            for ei, a, c, pk, lab in rows:
                ep, changed, new_fields, est = episode_info[ei]
                wc = would_change(domain, ep.S1, ep.S0.get(c), self.majority[key], trackers[ei])
                data[key].append((self._feat(domain, ep.S0.get(a), new_fields[a], ep.S0.get(c), ep.S0, est, pk, wc), lab))
        for ei, (ep, changed, new_fields, est) in enumerate(episode_info):
            src = ep.I["object_id"]
            for a in changed:
                pk = "source" if a == src else ("auto" if "auto" in changed[a] and "txn" not in changed[a] else "txn")
                for key in self.skeleton:
                    ptype, template = key
                    if ptype != ep.S0.get(a).type:
                        continue
                    for c in follow_template(ep.S0, a, template):
                        if c == src or c in changed:
                            continue
                        wc = would_change(domain, ep.S1, ep.S0.get(c), self.majority[key], trackers[ei])
                        data[key].append(
                            (self._feat(domain, ep.S0.get(a), new_fields[a], ep.S0.get(c), ep.S0, est, pk, wc), "none"))
        self.models = {}
        for key, rows in data.items():
            X = np.array([r[0] for r in rows])
            y = np.array([r[1] for r in rows])
            if len(set(y)) == 1:
                self.models[key] = ("const", y[0])
            else:
                tree = DecisionTreeClassifier(max_depth=self.max_depth, min_samples_leaf=2, random_state=0)
                tree.fit(X, y)
                self.models[key] = ("tree", tree)

    def _predict_label(self, key, feat) -> str:
        if self.superset:
            return self.majority[key]
        kind, model = self.models[key]
        if kind == "const":
            return model
        return str(model.predict(np.array([feat]))[0])

    def predict(self, domain, ep):
        prov: Dict[str, list] = {}
        est = domain.infer_params(ep.H, ep.S0, prov)
        scratch = ep.S0.copy()
        src = ep.I["object_id"]
        domain.apply_intervention_payload(scratch, ep.I)
        scratch.get(src).revision += 1
        tr = FallbackTracker(est)
        decided: Dict[str, str] = {}
        evaluated = {src}
        worklist = [(src, "source")]
        plan = []
        budget = 400
        expansions: Dict[str, int] = {}
        while worklist and budget > 0:
            a, pkind = worklist.pop(0)
            expansions[a] = expansions.get(a, 0) + 1
            if expansions[a] > 3:
                continue
            p = scratch.get(a)
            for (ptype, template) in self.skeleton:
                if ptype != p.type:
                    continue
                for c in follow_template(scratch, a, template):
                    if c == src:
                        continue
                    if c in decided:
                        # an already-decided object reached again through a new parent:
                        # refresh its automatic value and let it propagate once more
                        items = parse_label(decided[c])
                        if items and all(it["kind"] == "auto" for it in items):
                            cobj = scratch.get(c)
                            for it in items:
                                try:
                                    domain.apply_payload(scratch, cobj, it["op"],
                                                         domain.local_payload(scratch, cobj, it["op"], it.get("fields"), tr))
                                except Exception:
                                    pass
                            worklist.append((c, "auto"))
                        continue
                    budget -= 1
                    cobj = scratch.get(c)
                    evaluated.add(c)
                    wc = would_change(domain, scratch, cobj, self.majority[(ptype, template)], tr)
                    lab = self._predict_label((ptype, template),
                                              self._feat(domain, p, p.fields, cobj, scratch, est, pkind, wc))
                    if lab == "none":
                        continue
                    decided[c] = lab
                    items = parse_label(lab)
                    for it in domain.execution_order(scratch, [{"object_id": c, **it} for it in items]):
                        try:
                            payload = domain.local_payload(scratch, cobj, it["op"], it.get("fields"), tr)
                            domain.apply_payload(scratch, cobj, it["op"], payload)
                            cobj.revision += 1
                        except Exception:
                            pass
                        plan.append({"object_id": c, "op": it["op"], "kind": it["kind"], "fields": it.get("fields", [])})
                    kind = "auto" if all(it["kind"] == "auto" for it in items) else "txn"
                    worklist.append((c, kind))
        # values of decided objects are computed from their neighbours: those are reads too
        read_objs = set(evaluated)
        for oid in decided:
            for targets in ep.S0.get(oid).links.values():
                read_objs.update(t for t in targets if t in ep.S0.objects)
        records = set()
        for oid in evaluated:
            for name, key in domain.param_keys_for(ep.S0.get(oid), ep.S0):
                records.update(prov.get(f"{name}[{key}]", []))
        return {"plan": plan, "reads": {"objects": sorted(read_objs), "records": sorted(records)}}


# ------------------------------------------------- relational program learner

class ProgramLearner(Learner):
    """Strongest relational baseline: a gradient-boosted classifier per
    candidate over typed path, witness statistics, regime estimates and 1-hop
    neighbour context; run twice so that neighbour values reflect the first
    pass's executed plan (iterative closure)."""

    def __init__(self, iterations: int = 3, regularised: bool = False):
        self.iterations = iterations
        self.regularised = regularised
        self.name = ("program_reg" if regularised else "program") if iterations > 1 else "program_1pass"

    def _row(self, domain, ep, c: Obj, paths, est, ctx_state: State, src_new: dict):
        v = self.vocab
        p = paths.get(c.id)
        row = [1.0 if p == q else 0.0 for q in v.paths] + [float(len(p)) if p is not None else 9.0]
        row += v.onehot(v.types, c.type) + [1.0 if c.status == "active" else 0.0]
        cvec = numeric_vector(c, v.slots)
        row += cvec
        src = ep.S0.get(ep.I["object_id"])
        svec = numeric_vector(src, v.slots, src_new)
        row += [a - b for a, b in zip(svec, cvec)]
        row += v.onehot(v.src_ops, ep.I["op"]) + [source_numeric_delta(ep)]
        row += witness_vector(domain, ep.H, ep.S0, c)
        row += est_vector(domain, est, c, ep.S0, v.names)
        row += [LearnedGraph._code(est.get(n, {}).get("global")) for n in v.names]
        for rel in v.rels:
            nb = c.linked(rel)
            if nb and nb[0] in ctx_state.objects:
                n = ctx_state.get(nb[0])
                row += numeric_vector(n, v.slots) + est_vector(domain, est, n, ep.S0, v.names) + \
                    [1.0 if n.status == "active" else 0.0, shares_tokens(c, n.fields, n.id)]
            else:
                row += [0.0] * len(v.slots) + [-1.0] * (len(v.names) * 3) + [0.0, 0.0]
        # parent-relative deltas: the neighbour nearest to the source, using its
        # context (possibly already updated) values
        dist = self._dist
        parent = None
        for rel in v.rels:
            for nb in c.linked(rel):
                if nb in ctx_state.objects and dist.get(nb, 99) < dist.get(c.id, 99):
                    if parent is None or dist[nb] < dist[parent]:
                        parent = nb
        if parent is not None:
            pobj = ctx_state.get(parent)
            pv = numeric_vector(pobj, v.slots)
            row += [a - b for a in pv for b in cvec] + [1.0] + dict_equalities(c, pobj.fields)
            row += est_linked_vector(domain, est, c, ep.S0, v.names, pobj)
        else:
            row += [0.0] * (len(v.slots) ** 2) + [0.0] + [-1.0] * 5 + [-1.0] * len(v.names)
        # the intervention source is the natural anchor for regime keys
        row += est_linked_vector(domain, est, c, ep.S0, v.names, src)
        row += neighborhood_overlap(c, ctx_state) + sibling_ranks(c, ctx_state, v.slots)
        lab = self.type_majority.get(c.type)
        row.append(would_change(domain, ctx_state, c, lab, FallbackTracker(est)) if lab else -1.0)
        return row

    def fit(self, domain, train):
        from sklearn.ensemble import HistGradientBoostingClassifier
        self.vocab = Vocab(domain, train)
        counts: Dict[str, Counter] = defaultdict(Counter)
        for ep in train:
            for c in candidates(ep):
                lab = label_of(ep, c.id)
                if lab != "none":
                    counts[c.type][lab] += 1
        self.type_majority = {t: cnt.most_common(1)[0][0] for t, cnt in counts.items()}
        X, y = [], []
        for ep in train:
            est = domain.infer_params(ep.H, ep.S0)
            paths = path_types(ep.S0, ep.I["object_id"])
            src_new = source_new_fields(ep, ep.I)
            self._dist = hop_distances(ep.S0, ep.I["object_id"])
            ctx0 = ep.S0.copy()
            domain.apply_intervention_payload(ctx0, ep.I)
            for c in candidates(ep):
                # closure context: neighbour values as they are after the repair;
                # the test-time passes converge towards it
                X.append(self._row(domain, ep, c, paths, est, ep.S1, src_new))
                y.append(label_of(ep, c.id))
        if self.regularised:
            # post-hoc variant (added after the test split had been scored): the default
            # configuration failed to fit its own training episodes on one Formal train
            # seed; smaller trees, a lower learning rate and L2 make the fit stable
            self.clf = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, min_samples_leaf=10,
                                                      l2_regularization=1.0, max_leaf_nodes=15, random_state=0)
        else:
            self.clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, min_samples_leaf=4,
                                                      random_state=0)
        self.clf.fit(np.array(X), np.array(y))

    def predict(self, domain, ep):
        est = domain.infer_params(ep.H, ep.S0)
        paths = path_types(ep.S0, ep.I["object_id"])
        src_new = source_new_fields(ep, ep.I)
        self._dist = hop_distances(ep.S0, ep.I["object_id"])
        ctx = ep.S0.copy()
        domain.apply_intervention_payload(ctx, ep.I)
        plan = []
        for _ in range(self.iterations):
            cands = candidates(ep)
            rows = [self._row(domain, ep, c, paths, est, ctx, src_new) for c in cands]
            pred = type_consistent_predict(self.clf, rows, [c.type for c in cands], self.vocab.allowed)
            labels = {c.id: lab for c, lab in zip(cands, pred) if lab != "none"}
            plan = plan_from_labels(labels)
            # execute the plan on a scratch copy to refresh neighbour context
            ctx = ep.S0.copy()
            txns, _info = plan_to_txns(domain, ep.S0, ep.I, plan, est)
            domain.apply_intervention_payload(ctx, ep.I)
            tr = FallbackTracker(est)
            for it in domain.execution_order(ctx, [dict(i, hops=0) for i in plan]):
                try:
                    o = ctx.get(it["object_id"])
                    domain.apply_payload(ctx, o, it["op"], domain.local_payload(ctx, o, it["op"], it.get("fields"), tr))
                except Exception:
                    pass
        return {"plan": plan, "reads": all_reads(ep)}


def make_learners(seed: int = 0) -> List[Learner]:
    return [
        ExactKV(), SourceUnion(), SourceRegimeTable(), TransitionKNN(),
        FlatBlackBox(False), FlatBlackBox(True), EquivariantGNN(False, seed=seed), EquivariantGNN(True, seed=seed),
        LearnedGraph(superset=True), ProgramLearner(3), ProgramLearner(3, regularised=True), LearnedGraph(),
        RuntimeHistoryOracle(), Oracle(),
    ]
