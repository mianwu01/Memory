# Causal benchmark redesign protocol

This protocol replaces the assumption that a strong result against BM25 or full
history demonstrates causal memory.  Every candidate task must pass the same
zero-LLM falsification gates before an end-to-end run is authorized.

## Observable/runtime contract

A runtime may read only:

- `history`: natural-language observations and writes available before the query;
- `memory_state`: the materialized pre-intervention state;
- `query.text` and its parsed single intervention.

The parsed intervention has one cross-task representation:

```json
{"node": "opaque state key", "old_value": "...", "new_value": "...", "kind": "..."}
```

The evaluator alone owns `gold`: the interventional graph, active gated edges,
counterfactual affected nodes, required reads, and post-intervention state.  No
runtime selector or decoder may read `gold`.

All prototypes emit `causal-memory-benchmark/v1` episodes with train/dev/test
splits.  Natural-language parsing and causal propagation are evaluated as
separate layers: an oracle semantic parse is permitted for the propagation T0 so
that parser failure cannot be mistaken for a causal-memory failure.

## Admission criteria

1. **C1 — no query-time oracle.** A query-only parser must not enumerate the
   downstream affected set.  The query may reveal the intervention key and new
   value, but not its descendants.
2. **C2 — repeated mechanism.** Multiple independent trajectories share a stable
   or explicitly regime-conditioned transition mechanism that can be learned on
   train and applied to unseen instances.
3. **C3 — interventional gold.** A deterministic simulator or independent
   intervention supplies edges, non-edges, affected state and post-state.
4. **C4 — staged headroom over simple systems.** T0 is only a cheap rejection
   gate: Exact-KV must leave measurable headroom and the independent oracle must
   solve the task.  Before a learned-method result is admitted, structured query
   parsing, the strongest domain solver and matched-budget retrieval must also
   leave measurable headroom.  Beating a deliberately lossy BM25 configuration
   is insufficient.
5. **C5 — mapping boundary.** If natural language to variable mapping is part of
   the scientific claim, test it separately.  A benchmark with a provided schema
   can support propagation claims but not a claim that variables were discovered
   from language.

## Required baselines and metrics

Every task must implement at least:

- **Exact-KV:** apply only the explicit intervention key/value;
- **Oracle propagation:** use the simulator mechanism and all required state;
- later, **query-aware structured retrieval**, **matched-budget lexical/embedding
  retrieval**, **learned graph**, and **oracle graph**.

Accordingly, `admission.pass` in the current deterministic reports means
**T0 candidate admission only**.  It is not final admission of the causal-learning
claim and does not certify an advantage over domain solvers or matched retrieval.

Primary T0 metrics are affected-node precision/recall, accuracy restricted to
affected state, full-state accuracy, and the fraction of episodes that genuinely
require propagation.  End-to-end runs add task success, unaffected-state
preservation, tokens, cost and latency.

## Stop rules

- Reject or redesign a candidate if query-only/Exact-KV solves at least 95% of
  propagation episodes.
- Do not call a graph result causal if its advantage disappears against an exact
  structured baseline at the same selected-cell or token budget.
- Graph selection and compact serialization must be separate ablations.
- A task that tests provenance or logical dataflow but not an intervention must be
  labelled dependency memory, not causal propagation.

## API failure accounting

Provider/runtime failures and method failures are different estimands and must not
be silently exchanged.

- Retry and leave unscored only transport exceptions, provider 5xx/rate-limit,
  empty/truncated completion, invalid JSON syntax, or a type-level response that
  cannot be interpreted at all.
- A parseable response that omits required update nodes, adds forbidden nodes, or
  returns the wrong value is a **semantic endpoint failure**.  It is written once,
  scored as such, and is not retried until a passing answer appears.
- Reports show result rows, semantic-scored rows, unscored engineering rows and
  per-class retry events separately.  `endpoint_success` never uses engineering
  missing rows as zero, while confirmatory completion requires the preregistered
  coverage policy.
- Raw response hashes, request/prompt/seed/model identity and every paid attempt
  remain in an append-only ledger.  No gold repair or oracle post-state may be
  inserted into a model response.

The 2026-08-31 six-arm v1 predates this stricter split: it retried node-set contract
mismatches together with schema/engineering errors.  Its valid-only endpoint score
is therefore conditional decoder evidence, not one-call reliability; the original
artifacts remain unchanged.

## Strongest-baseline audit

`domain_solver` must mean the strongest gold-free executable method already
available to the agent, not a deliberately conservative potential-descendant set.
Before freezing, every task must also test these structured shortcuts when
applicable:

- source → observed train impact union;
- source + runtime-visible regime → impact-template table;
- query `(task,node,kind)` → fixed affected template;
- public-schema k-hop reachability and executable task-card/provenance program.

If one of these matches the learned arm, the result may support structured or
dependency-aware maintenance, but not learned hidden-structure necessity.
