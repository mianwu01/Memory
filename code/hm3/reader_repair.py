"""One fixed, parser-free precedent correction; evaluate before making any claim.

Component preference is an explicit non-CD baseline. Instance membership is
observed metadata. It can benefit from how HM3 builds foreign components, so a
gain here must not be attributed to discovery or generalized to arbitrary stores.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .core import segments
from .domains import get_domain
from .generate import generate_split
from .keysel import _neighbours, key_precedent_records
from .scaling import augment_split
from .structure_alignment import CONDITIONS, execute_reads, ordered_reads, response_precedent_records
from .tcd_logs import TCDSelect, adjacency_reads, type_vocab


def component_precedent_records(domain, ep, objects, n_prec=2):
    """Prefer same-key evidence in the query component; then generic same-key fallback.

    For each key take at most n_prec segments. Within-component segments are
    preferred; remaining slots use the most recent same-key segments elsewhere.
    This bounded rule was specified before the fresh test seeds were evaluated.
    """
    S0, segs = ep.S0, segments(ep.H)
    component = set(objects)
    cats = domain.categorical_fields()
    chosen, processed = set(), set()
    for oid in objects:
        obj = S0.get(oid)
        for field in cats.get(obj.type, []):
            value = obj.fields.get(field)
            key = (obj.type, field, value)
            if value is None or key in processed:
                continue
            processed.add(key)
            same = {o.id for o in S0.objects.values()
                    if o.type == obj.type and o.fields.get(field) == value}
            near = {x: _neighbours(S0, x) for x in same}
            candidates = []
            for si, seg in enumerate(segs):
                if not seg or seg[0]["kind"] != "intervention":
                    continue
                src = seg[0]["object_id"]
                # Stimulus may occur further upstream than one object hop; the
                # target record provides the observed response in that case.
                touched = {r["object_id"] for r in seg[1:]} & same
                responding = touched | {x for x in same if src != x and src in near[x]}
                if responding:
                    local = bool(responding & component)
                    candidates.append((local, si))
            if candidates:
                for _, si in sorted(candidates, reverse=True)[:n_prec]:
                    chosen.update(r["rid"] for r in segs[si])
            else:
                chosen.update(key_precedent_records(domain, ep, [oid], n_prec))
    return [r["rid"] for r in ep.H if r["rid"] in chosen]


class ComponentKeySelect(TCDSelect):
    """Drop-in, no-discovery comparator for the existing deterministic runner."""

    name = "component_key2"

    def __init__(self):
        super().__init__(records="key", n_prec=2, lag_aware=True)
        self.name = "component_key2"

    def fit(self, domain, train):
        types = type_vocab(train)
        self.adj = {(a, b): 1 for a in types for b in types if a != b}

    def select(self, domain, ep):
        objects = adjacency_reads(ep, self.adj)
        ids = component_precedent_records(domain, ep, objects, 2)
        return ordered_reads(ep, objects, ids)


def evaluate(args):
    result = {"config": vars(args), "runs": {}}
    out = Path(args.out)
    if out.exists():
        old = json.loads(out.read_text())
        if old["config"] != vars(args):
            raise ValueError("different existing config")
        result = old
    for name in args.domains:
        domain = get_domain(name)
        for seed in args.seeds:
            native = generate_split(domain, seed, args.split, args.n_eval)
            types = type_vocab(native)
            adj = {(a, b): 1 for a in types for b in types if a != b}
            for condition in args.conditions:
                key = f"{name}/seed{seed}/{condition}"
                if key in result["runs"]:
                    continue
                target, mix = CONDITIONS[condition]
                eps, aug = (native, {}) if condition == "native" else augment_split(domain, native, target, mix, f"{args.split}{seed}")
                rows = []
                for ep in eps:
                    objects = adjacency_reads(ep, adj)
                    choices = {
                        "key2": key_precedent_records(domain, ep, objects, 2),
                        "response2": response_precedent_records(domain, ep, objects, 2),
                        "component2": component_precedent_records(domain, ep, objects, 2),
                    }
                    arm_scores = {}
                    for arm, ids in choices.items():
                        reads = ordered_reads(ep, objects, ids)
                        score = execute_reads(domain, ep, reads)
                        arm_scores[arm] = {"ees": bool(score["ees"]), "n_records": len(ids),
                                           "required_read_recall": score["required_read_recall"], "reads": reads}
                    rows.append({"episode": ep.id, "arms": arm_scores})
                summary = {a: {m: float(np.mean([r["arms"][a][m] for r in rows]))
                               for m in ("ees", "n_records", "required_read_recall")}
                           for a in ("key2", "response2", "component2")}
                result["runs"][key] = {"n": len(eps), "augmentation": aug, "summary": summary, "rows": rows}
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(result, indent=1))
                print(json.dumps({"cell": key, "n": len(eps), "summary": summary}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--domains", nargs="+", default=["travel", "shopping32"])
    p.add_argument("--seeds", nargs="+", type=int, required=True)
    p.add_argument("--split", choices=["dev", "test"], required=True)
    p.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=["native", "c100", "500"])
    p.add_argument("--n-eval", type=int, default=64)
    p.add_argument("--out", required=True)
    evaluate(p.parse_args())
