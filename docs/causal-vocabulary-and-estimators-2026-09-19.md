# What "temporal causal graph" means in this paper, and which estimators we actually run (2026-09-19)

Written for the abstract and the method section after the question "what causal discovery method are we using?".
Every claim below is checked against the code and results on branch `claude/hm3-handoff-2026-09-18`.

## 1. Short answer

We do not contribute a causal-discovery algorithm. Update 2026-09-19 evening: on HM3's own event logs an off-the-shelf pooled temporal estimator does recover the type-level propagation skeleton (see the added row below and `docs/bridge-plan-2026-09-19.md` §3.1); what it does not recover is the gating, and on the MemoryArena/MINJA logs it recovers nothing.
We contribute (a) a formulation of memory as a gated temporal causal process with the causal-frontier lemma,
(b) evidence that the access regime must be represented to recover gated memory edges, (c) a learned propagation
structure for agent tasks estimated from **interventional** training trajectories and conditioned on the access
regime, and (d) forward selection and backward provenance on that structure, validated by intervention.

"Temporal causal process" is the modelling object and is fine as written. "Temporal causal graph" is defensible
with the definition in §3 below; "causal discovery" as a contribution should not appear.

## 2. The estimators, layer by layer

| layer | what is estimated | how | causal status |
|---|---|---|---|
| E0 (controlled SCM) | lagged edges x_i(t−l) → x_j(t) and whether each is gated by the access regime u_t | per-regime lagged regression (ridge, BH-FDR); an edge is reported if significant in any regime and flagged gated if its coefficient changes across regimes (`code/regime_grace.py::fit_regime_conditioned`); per-regime GRACE and an HC0 interaction model give the same result | temporal structure learning of the Granger / structural-VAR family under the SCM assumptions of the formulation; ground truth known, recovery measured against it |
| HM3 (agent tasks) | a type-level skeleton of typed relational paths along which a change propagates, plus a regime-gated local decision per path template, plus a parser that attributes each hidden policy key to its latest outcome witness (`code/hm3/learners.py::LearnedGraph`) | supervised from training episodes in which every episode is a known intervention on one source object with the observed propagation of changes (S0 → S1); templates with support ≥ 2, decision trees on the gate features | structure learning from interventional data: edges are propagation effects of known interventions, gated by the event kind (source / auto / txn) and by regime estimates read from history |
| HM3 logs, observational (added 2026-09-19) | type-level skeleton: which object type's write is followed by which type's write | pooled lagged regression with BH-FDR over one binary variable per object type, one row per record, user interventions exogenous (`code/hm3/tcd_logs.py`); PCMCI+ as the second estimator | observational temporal structure learning of the Granger family; recall 1.0 against the interventional skeleton on 6/6 seeds in Travel and Shopping32 (precision 0.2–0.5), PCMCI+ recall 0.4; the same graph drives selection (EES 1.00) and provenance (top-3 0.91–1.00); the round-activation encoding used in Travel implicit-v1 degenerates to self-loops on the same logs |
| provenance | the records responsible for an anomalous action | backward walk on the same fitted skeleton, leave-one-record-out re-ranking, validation by replacing candidates with clean versions and re-running | interventional test of the attribution |
| MINJA (observational logs) | record-exposure → anomalous-action edges with the trigger as regime | the E0 estimator on exposure indicators | no edges recovered in 10/10 runs under sparse exposure: reported as a boundary, no discovery claim |

PCMCI+ and official GRACE appear as baselines in E0 (pooled: fail; per-regime GRACE: equal to per-regime
regression). The paused Travel implicit-v1 ran PCMCI+ with GRACE refinement on a slot-activation time series; GRACE
returned the PCMCI+ skeleton unchanged and the graph's time axis did not match the runtime, which is why that
version is not used.

## 3. Definition to put in the introduction

> We call the learned structure a temporal causal graph in the following sense: its nodes are records and objects
> indexed by time, its edges are propagation effects estimated from trajectories in which the upstream change is a
> known intervention, its edges are gated by the access regime under which a record is written, held or read, and
> its predictions are checked by intervention — recovery against a known ground truth in the controlled setting,
> re-wired-topology controls in the agent tasks, and clean-replacement tests for provenance. On our generated agent tasks the type-level skeleton is also recovered from the event logs alone by a pooled
> temporal estimator; the gating is not. We do not claim identification from the observational logs of the
> public benchmarks we tried (MemoryArena Travel, MINJA), where the same estimators return self-loops or nothing.

## 4. Why GRACE is not the estimator

1. **E0 v2, criterion C4.** Regime-conditioned GRACE and plain per-regime regression with FDR both recover the
   gated read edges in 5/5 seeds at every noise level. Once the regime is observed, per-regime regression is the
   maximum-likelihood estimator by construction. GRACE kept about 9 % false positives on distractor cells at the
   chosen penalty and needed 2–4× more samples in the read-rarity sweep; its only advantage was at 1000 variables
   without screening. Pooled GRACE (the official external arm) fails like every pooled method, which is the point E0
   makes. Decision (2026-09-18): E0 is the "regime conditioning is necessary" evidence; per-regime regression + FDR
   is the estimator; GRACE stays as an appendix row; no estimator-novelty claim.
2. **No fixed variable set in the agent tasks.** GRACE and PCMCI+ estimate one adjacency over a fixed set of time
   series. Each HM3 episode has different objects; what transfers is type-level and relational (which typed path a
   change propagates along, gated by regime). Forcing the data into a slot-activation series was tried in Travel
   implicit-v1 and produced twelve mostly self-dependency edges with a training/runtime time mismatch.
3. **No power on observational logs.** MINJA's regime-conditioned fit selected no edges in 10/10 runs (about 19
   trigger rounds against up to 12 candidates); a different estimator would not change that.

## 5. Sentences for the method section

- E0: "We estimate lagged dependencies separately within each access regime and report an edge as gated when its
  coefficient changes across regimes; pooled and additive-regime estimators, PCMCI+, and pooled GRACE serve as
  baselines."
- Agent tasks: "From training trajectories in which each episode records a known intervention and the changes that
  followed, we learn a typed propagation skeleton with a regime-gated local decision per path, and a parser that
  attributes each hidden policy to its latest outcome witness. The same fitted structure is used forward for
  selection and backward for provenance."
- Boundary: "We do not claim causal identification from observational agent logs; on MINJA the regime-conditioned
  estimator recovers no edges under sparse exposure."
