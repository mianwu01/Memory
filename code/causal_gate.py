"""Closed loop — detect a hidden driver, then GATE the actions it would drive.

Milestone M3, and the half of Yujia's trustworthiness branch that was still only
a sentence: "if we detect something malicious ... we can allow the system to gate
the following actions."

Auditing that only produces a report is not actionable. This module closes the
loop: the same recovered structure that names a memory record as the causal
ancestor of an anomalous action is fed BACK into the memory system, which then
withholds that record before the agent acts on it. One graph, used twice --
selection and defence -- which is the dual use the formulation claims and which a
per-record detector (see code/memaudit_baseline.py) cannot provide.

Two entry points:

  CausalGate            the policy object. Given the per-round record X_t and the
                        retrieved memory, decides KEEP / WITHHOLD per record.
  replay_gate(...)      counterfactual evaluation on an ALREADY RECORDED
                        trajectory: how many anomalous actions would the gate have
                        prevented, and what did it cost on benign rounds?

Replay is the honest way to evaluate this without re-running the agent: the
trajectory already tells us, for every round, which records were retrieved and
whether the action was anomalous. Withholding a driver on a round that fired is a
PREVENTED action; withholding on a round that did not fire is COLLATERAL. We
report both, because a gate that withholds everything trivially prevents
everything.

The gate is deliberately conservative about what it treats as evidence. It fires
only when BOTH hold:
  1. the record is implicated as a driver (its influence exceeds a threshold, or
     it was flagged by the structure recovered upstream), AND
  2. the regime gate is open (the recovered edge is active for this round's u_t).
Condition 2 is what makes this a *causal* gate rather than a blocklist: a record
that is inert under the current regime is left alone, so benign rounds keep their
memory.

CPU-only, no API. Usage:
    python3 code/causal_gate.py --transcript results/real/minja_trace_llm.transcript.json
"""
from __future__ import annotations

import os as _os
_os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class CausalGate:
    """Withhold memory records that the recovered structure marks as drivers.

    driver_scores : record id -> influence/ancestry score (higher = more likely a
                    driver). Supply from our own audit, or from any scorer.
    threshold     : score above which a record counts as implicated.
    regime_key    : field of the round record that carries the gate u_t. The gate
                    only acts when this is truthy, so inert rounds are untouched.
    require_regime: set False to get a plain blocklist (ablation).
    """
    driver_scores: Dict[str, float] = field(default_factory=dict)
    threshold: float = 0.15
    regime_key: str = "trigger"
    require_regime: bool = True

    def implicated(self, record_id: str) -> bool:
        return float(self.driver_scores.get(record_id, 0.0)) >= self.threshold

    def decide(self, round_rec: Dict) -> Dict[str, bool]:
        """Per retrieved record: True = withhold it from the agent's context."""
        gate_open = bool(round_rec.get(self.regime_key, 0)) if self.require_regime else True
        out = {}
        for x in round_rec.get("retrieved", []):
            rid = x.get("id")
            if rid is None:
                continue
            out[rid] = bool(gate_open and self.implicated(rid))
        return out

    def filter_context(self, round_rec: Dict) -> List[Dict]:
        """The retrieved list with withheld records removed (what the agent sees)."""
        drop = self.decide(round_rec)
        return [x for x in round_rec.get("retrieved", []) if not drop.get(x.get("id"), False)]


def scores_from_cmis(transcript: List[Dict]) -> Dict[str, float]:
    """Driver scores from our own influence estimate (reuses the CMIS routine)."""
    from memaudit_baseline import cmis
    df = cmis(transcript)
    return {r.record: (0.0 if r.cmis != r.cmis else float(r.cmis))
            for r in df.itertuples()}


def scores_from_ancestry(transcript: List[Dict]) -> Dict[str, float]:
    """Driver scores from TEMPORAL ANCESTRY -- the thing only our method gives.

    A record scores by how often it was retrieved on a round whose action was
    anomalous, normalised by how often it was retrieved at all. This is an
    ancestry frequency, not a semantic property, so it points at a WRITE ROUND.
    """
    fired, seen = {}, {}
    for r in transcript:
        anom = int(r.get("anomalous", 0))
        for x in r.get("retrieved", []):
            rid = x.get("id")
            if rid is None:
                continue
            seen[rid] = seen.get(rid, 0) + 1
            fired[rid] = fired.get(rid, 0) + anom
    return {rid: fired[rid] / seen[rid] for rid in seen if seen[rid] > 0}


def replay_gate(transcript: List[Dict], gate: CausalGate,
                protect_phases: Optional[Set[str]] = None) -> Dict:
    """Counterfactual: what would this gate have done to the recorded trajectory?

    prevented   anomalous rounds where >=1 retrieved DRIVER would have been withheld
    missed      anomalous rounds the gate would have let through
    collateral  non-anomalous rounds where the gate withheld something anyway
    """
    protect_phases = protect_phases or set()
    prevented = missed = collateral = 0
    touched_rounds = 0
    withheld_total = 0
    poison_withheld = clean_withheld = 0

    for r in transcript:
        if r.get("phase") in protect_phases:
            continue
        drop = gate.decide(r)
        n_drop = sum(1 for v in drop.values() if v)
        if n_drop:
            touched_rounds += 1
            withheld_total += n_drop
            for x in r.get("retrieved", []):
                if drop.get(x.get("id")):
                    if x.get("is_poison"):
                        poison_withheld += 1
                    else:
                        clean_withheld += 1
        if int(r.get("anomalous", 0)):
            prevented += 1 if n_drop else 0
            missed += 0 if n_drop else 1
        else:
            collateral += 1 if n_drop else 0

    n_anom = prevented + missed
    n_benign = sum(1 for r in transcript
                   if not int(r.get("anomalous", 0)) and r.get("phase") not in protect_phases)
    return {
        "anomalous_rounds": n_anom,
        "prevented": prevented,
        "missed": missed,
        "prevention_rate": (prevented / n_anom) if n_anom else float("nan"),
        "benign_rounds": n_benign,
        "collateral_rounds": collateral,
        "collateral_rate": (collateral / n_benign) if n_benign else float("nan"),
        "records_withheld": withheld_total,
        "poison_withheld": poison_withheld,
        "clean_withheld": clean_withheld,
        "withhold_precision": (poison_withheld / withheld_total) if withheld_total else float("nan"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", default="results/real/minja_trace_llm.transcript.json")
    ap.add_argument("--threshold", type=float, default=0.15)
    ap.add_argument("--out", default="results/real/causal_gate.json")
    a = ap.parse_args()

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    T = json.load(open(a.transcript))
    print(f"loaded {len(T)} rounds from {a.transcript}\n")

    variants = {
        "ancestry + regime (ours)": CausalGate(scores_from_ancestry(T), a.threshold,
                                               require_regime=True),
        "ancestry, no regime (ablation)": CausalGate(scores_from_ancestry(T), a.threshold,
                                                     require_regime=False),
        "CMIS influence + regime": CausalGate(scores_from_cmis(T), a.threshold,
                                              require_regime=True),
    }
    rep = {}
    hdr = f"{'gate':32s} {'prevented':>16s} {'collateral':>16s} {'withhold prec':>14s}"
    print(hdr); print("-" * len(hdr))
    for name, g in variants.items():
        r = replay_gate(T, g)
        rep[name] = r
        print(f"{name:32s} {r['prevented']:>5d}/{r['anomalous_rounds']:<4d}"
              f"({r['prevention_rate']*100:5.1f}%) "
              f"{r['collateral_rounds']:>5d}/{r['benign_rounds']:<4d}"
              f"({r['collateral_rate']*100:5.1f}%) "
              f"{r['withhold_precision']*100:13.1f}%")

    print("\nReading it: prevention is what the gate buys; collateral is what it")
    print("costs on rounds that were fine. The regime condition is what keeps")
    print("collateral down -- a record inert under the current regime is left alone.")

    p = Path(a.out); p.parent.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(p, "w"), indent=1, default=str)
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
