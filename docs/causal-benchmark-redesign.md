# Four-task causal benchmark redesign

## Decision

Original MemoryArena Travel remains useful as a structured-memory compression
harness, but it cannot identify whether learned causal structure is necessary:
the current query names the earlier traveler and almost always identifies the
source day/slot.  The same audit also shows that original Shopping is state
tracking, Search is static retrieval/aggregation, and Formal Reasoning has
implicit dependencies but no interventions or counterfactual gold.

We therefore keep the MemoryArena runner and memory interfaces, leave its
unlicensed upstream checkout untouched, and redesign all four task semantics in
an isolated layer under `code/causal_benchmarks/`.

| Original carrier | Failure mode | Redesigned task | Intervention and hidden propagation |
|---|---|---|---|
| Travel | query-explicit source-cell lookup | `dynamic_travel` | delay/closure/deadline → transfer, attraction, dinner, check-in |
| Shopping | compatibility structure stated in each step | `dynamic_shopping` | cancellation/price/policy → compatibility chain and budget ledger |
| Search | static subquery retrieval and aggregation | `dynamic_search` | retraction/version/trust → claim, answer and monitoring brief |
| Math/physics | implicit dataflow but no edit semantics | `causal_formal` | parameter/definition/axiom correction → lemmas and theorems |

These are deterministic, zero-LLM prototypes and are not yet MemoryArena server
registrations.  The admission T0 and the train-only six-arm T1 are now complete.
T1 learned selectors generalize beyond matched generic retrieval, but none beats
the strongest task-specific domain baseline; consequently none currently counts
as evidence that learned causal structure is necessary.

## Common protocol

Every episode follows `causal-memory-benchmark/v1` and separates runtime-visible
history/state/query from evaluator-only graph, active gated edges, affected nodes,
required reads and counterfactual post-state.  The query exposes one intervention
key/value but never enumerates its descendants.  Natural-language parsing is
separated from propagation by providing an oracle semantic parse in T0.

All four tasks implement:

- `generate_dataset(episodes, seed)`;
- `audit_dataset(dataset)`;
- Exact-KV, which changes only the query-explicit cell;
- an independent oracle simulator that recomputes the post-state without reading
  evaluator gold;
- active/inactive regime cases and unaffected negative controls.

For T1, completed transitions are runtime-visible only on train.  The common
`runtime_view` removes evaluator `gold` from every method view and exposes no
outcome on dev/test.  Every task uses unseen entities/templates/values and at
least one held-out regime combination, six selection arms, and an orthogonal
selection-by-serialization audit.  Value decoding is shared and deterministic,
so task endpoints isolate selection sufficiency rather than end-to-end equation
or language learning.

The complete admission rules are in `docs/causal-benchmark-protocol.md`.

## Unified zero-LLM T0

Command:

```bash
PYTHONPATH=code python3 code/causal_benchmarks/run_suite.py \
  --episodes 120 --seed 17 \
  --out results/development/causal_benchmarks/suite_t0.json
```

The unified run validates 480 episodes against the common schema:

| Task | Propagation-required | Query downstream leakage | Exact-KV affected recall | Exact-KV task success | Oracle affected recall/state accuracy | Admission |
|---|---:|---:|---:|---:|---:|---|
| Dynamic Travel | 80.00% | 0 | 46.86% | 20.00% | 100% / 100% | PASS |
| Dynamic Shopping | 100.00% | 0 | 16.53% | 0.00% | 100% / 100% | PASS |
| Dynamic Search | 66.67% | 0 | 50.00% | 33.33% | 100% / 100% | PASS |
| Causal Formal | 83.33% | 0 | 39.44% | 16.67% | 100% / 100% | PASS |

“Task success” is the domain endpoint: exact post-state for Travel/Shopping/Formal
and final-answer accuracy for Search.  Affected recall/state accuracy are the
cross-task primary metrics.  Full-state accuracy is deliberately secondary
because sparse unchanged cells make a failed Exact-KV system look deceptively
strong.

This PASS means only that the candidate has measurable propagation headroom over
the direct dictionary update.  It does not mean a learned graph has won.

## Scientific ranking and boundaries

1. **Dynamic Search is the only current hidden-from-query PASS at the task
   validity layer.** Episode-specific opaque descendants are recoverable from
   history provenance, not from the query surface.  Its learned arm is still a
   learned-gate + deterministic-provenance hybrid, not independent recovery of
   the full graph.
2. **Dynamic Shopping is PARTIAL.** It supplies real multihop state repair and
   budget/compatibility regimes, but `(kind, slot, visible regime)` defines a
   structured impact-template shortcut and the executable compatibility solver
   remains a mandatory baseline.
3. **Dynamic Travel is PARTIAL.** Its schedule intervention and gates are real,
   but a fixed small schema plus `source → train impact union` can reproduce the
   current learned write mask.
4. **Causal Formal is NO-GO for hidden-dependency necessity.** Mutable
   definitions and axiom gates support interventional change propagation, but
   `intervention.kind` exposes active/inactive gate status under a fixed topology.
   It remains a controlled execution/dataflow sanity task.

The four tasks should not be forced into one overbroad claim.  They provide one
primary state-world result, one constrained-system replication, and two boundary
cases that test provenance and program semantics.

## Unified train-only T1 (completed)

Command:

```bash
PYTHONPATH=code python3 code/causal_benchmarks/run_t1_suite.py \
  --episodes 120 --seed 17 \
  --out results/development/causal_benchmarks/suite_t1.json
```

The frozen matrix was run on all four tasks:

| Arm | Purpose |
|---|---|
| Exact-KV | the simple dictionary-update objection |
| domain structured solver | strongest hand-coded non-learned baseline |
| matched-budget lexical/embedding retrieval | generic retrieval baseline |
| learned type/regime graph | proposed method |
| oracle graph | selection/propagation upper bound |
| full state/history | context upper bound and cost reference |

All four novel-split audits pass, and all learned selectors beat the matched
generic retrieval arm in affected recall.  The decisive comparison is negative:

| Task | Learned affected recall | Matched generic recall | Learned/domain task success | Learned compact / full compact chars | Necessity |
|---|---:|---:|---:|---:|---|
| Dynamic Travel | 1.000 | 0.686 | 1.000 / 1.000 | 0.179 | FAIL |
| Dynamic Shopping | 1.000 | 0.219 | 1.000 / 1.000 | 0.225 | FAIL |
| Dynamic Search | 1.000 | 0.500 | 1.000 / 1.000 | 0.194 | FAIL |
| Causal Formal | 1.000 | 0.485 | 1.000 / 1.000 | 0.732 | FAIL |

Thus:

```text
all_novel_splits_pass = true
all_learned_beat_generic_retrieval = true
tasks_beating_domain_solver = []
tasks_supporting_causal_learning_claim = []
```

The planned ablations are also complete:

- graph selection versus compact serialization;
- learned edge structure versus hard-coded domain rules;
- active-gate positives versus inactive-gate/independent negatives;
- chain depth, distractor scale and unseen entity/template splits.

The go criterion was not met.  These tasks remain useful intervention-propagation
and dependency-aware state-maintenance benchmarks, and they demonstrate compact
train-only impact selection.  They do not establish causal-graph necessity.
Dynamic Search is blocked specifically by an explicit provenance parser;
Causal Formal by the executable program/dataflow graph; Travel and Shopping by
hand-coded schedule/compatibility solvers.  A future positive necessity test must
hide or make context-dependent the routing that these domain baselines currently
recover exactly, without weakening those baselines after seeing the result.

## Dev-only killer lookup admission audit

The stronger shortcut audit is reproducible without reading test gold:

```bash
PYTHONPATH=code python3 -m causal_benchmarks.run_killer_lookup_audit
```

It generates 120 episodes per task with base seed 17 and the fixed suite seed
offsets `0/1/2/3`, fits only on runtime-visible train transitions, freezes masks
on outcome-free dev views, and then scores only dev gold. Test episodes are
counted for the split audit but explicitly not scored. The artifact is
`results/development/causal_benchmarks/killer_lookup_dev_audit.json`.

The stop rule is triggered when a source-union or query-signature lookup covers
all truly affected nodes on at least 95% of propagation dev episodes. This uses
mask sufficiency rather than exact match because the decoder may safely write an
over-selected node back to its old value.

| Task | Source union: sufficient / exact / P / specificity / write fraction | Query signature: sufficient / exact / P / specificity / write fraction | Stop |
|---|---:|---:|---:|
| Dynamic Travel | 1.000 / 0.900 / 0.986 / 0.992 / 0.168 | 1.000 / 0.900 / 0.986 / 0.992 / 0.168 | TRIGGERED |
| Dynamic Shopping | 1.000 / 0.667 / 0.903 / 0.983 / 0.167 | 1.000 / 0.667 / 0.903 / 0.983 / 0.167 | TRIGGERED |
| Dynamic Search | 1.000 / 0.000 / 0.231 / 0.757 / 0.295 | 1.000 / 0.167 / 0.385 / 0.803 / 0.250 | TRIGGERED |
| Causal Formal | 1.000 / 0.833 / 0.889 / 0.969 / 0.323 | 1.000 / 1.000 / 1.000 / 1.000 / 0.295 | TRIGGERED |

Formal is the clearest surface shortcut: the query signature recovers the exact
mask. Search is different: a graph-free type union does not identify the correct
opaque route, but selecting all current claim/answer/brief nodes still creates a
sufficient mask at 25--30% of state. Search can therefore retain an efficiency
and precision question, but endpoint sufficiency alone cannot establish hidden
routing necessity. Overall, all four tasks fail this stricter necessity
admission while remaining valid intervention-propagation stress tests.

## P1 simulation v2 status

The separate known-DGP simulation is also complete:

```bash
python3 code/yujia_simulation_v2.py \
  --episodes 240 --delta 10 --seeds 5 \
  --out results/development/yujia_simulation_v2.json
```

| Family | Pooled overall/read F1 | Regime-conditioned overall/read F1 | Grouped-proxy fallback |
|---|---:|---:|---:|
| Linear observed | 0.580 / 0.647 | 1.000 / 1.000 | — |
| MLP observed | 0.516 / 0.533 | 1.000 / 1.000 | — |
| MLP latent-confounded | 0.447 / 0.409 | 0.800 / 0.667 | 1.000 / 1.000 |

This validates nonlinear regime-conditioned recovery under generator-owned
mechanisms.  The latent arm deliberately does not score edges incident to the
unobserved `h` as recoverable by an observed-only estimator.  Its perfect grouped
result is a measured-proxy fallback formed from two noisy measurements, not
latent-variable identification and not evidence of agent-memory utility.

## Real API six-arm v1

The decoder dev v9 gate completed 96/96 calls.  The frozen test then completed
288/288 request rows (4 tasks × 12 novel-test episodes × 6 arms) and 309 ledger
events with a ledger-derived cost of `$6.607622`.  Integrity and full-scope audits
are complete.  Four full-state rows remain unscored missing after the frozen
attempt budget, so the summary correctly reports `experiment_complete=false`
instead of turning them into semantic zeroes.

The learned arm has selection F1 and valid-only endpoint success of 1.0 on every
task, while using 71,381 input tokens versus full-state's 175,735.  This is real
API execution/efficiency evidence conditional on a valid response.  It is not a
causal-necessity result:

- the API v1 `domain_solver` accidentally used conservative potential
  reachability rather than the strongest executable T1 domain solver;
- the task shortcuts above remain;
- the v1 retry policy combined type/format errors with node-set semantic contract
  errors.  Of 25 error attempts, 24 were node-set mismatches; 11 requests later
  became valid under retry.  Therefore valid-only endpoint success is not a
  one-call reliability estimate.

The immutable result lineage and complete matrix are documented in
[`causal-api-six-arm-v1-results.md`](causal-api-six-arm-v1-results.md).  A later
protocol must repair failure taxonomy and strongest baselines before any new API
claim is frozen.
