# Paper draft — Appendix (2026-09-22, for Yujia to cut)

Companion to `docs/paper-draft-method-2026-09-21.md` and `docs/paper-draft-experiments-2026-09-20.md`. Every
protocol item names the code object that implements it. Costs are summed from the ledgers on disk on 2026-09-22.

## A Benchmark protocol

**Generator.** `code/hm3/domains.py` (Travel, Shopping32, Search, Formal), `code/hm3/generate.py`. An episode is
(H, S_0, I, A, S_1, R): a sampled world of 6–24 typed objects, a history of prior interventions and their
consequences written as records (one record per write event; kinds: user intervention, automatic environment
effect, manual transaction), one test intervention I, the oracle repair A, the post-state S_1 and the required
records R (the generator's over-counting list of witnesses that determine A). Hidden per-entity policies
(`Episode.params`) are never shown; they are recoverable only from outcome witnesses in H. Entities with the same id
share a policy.

**Splits.** Per seed: 200 training episodes (seed + 100), 60–64 evaluation episodes. Dev seeds 0/1/2 were used for
every design decision; test seeds 30/31/32 are reserved and were run once per frozen configuration. Episode ids and
topology hashes are disjoint across splits (gate C2).

**Zero-API gate (dev seeds; `hm3.gate`; thresholds frozen in `docs/hidden-mechanism-v3-preregistration.md` §5).**

| check | threshold |
|---|---|
| C1 cue leak | the cue and I contain no downstream id and no gate vocabulary: 0 leaks |
| C2 split separation | train/dev/test ids pairwise disjoint; topology-hash overlap 0 |
| C3 history load-bearing | flipping a relevant hidden parameter changes the gold in ≥ 0.8 of episodes; regenerated-H pairs with different gold ≥ 0.5 (≥ 10 pairs) |
| C4 killers fail | exact-key, source-union, source-regime, kNN and superset readers each ≤ 0.50 dev EES |
| C5 identifiable | oracle and required-history oracle dev EES = 1.0 |
| C6 non-idempotent | the oracle plan plus one same-value write to an unaffected object fails 100 % of episodes |
| C7 structure > black box | the graph's EES above flat, flat_est, GNN, GNN_est on ≥ 2/3 dev seeds and on the mean |
| C8 program ran | the relational program learner has a result; tie if within 0.05 |

API runs were allowed only where C1–C7 passed (Travel, Search; Shopping passes with the Shopping32 variant used
throughout). Disclosure: before the C4 threshold was written, Travel had a smoke run of 80/120 training episodes.

**Metric.** EES (`core.score_plan`): the emitted transaction set executes legally against S_0 (revisions, tokens,
fees) and the resulting state equals S_1; a collateral write or a missed write both fail. Secondary: affected-object
F1, value accuracy, legality, collateral rate, reads (objects + records shown).

**History growth (`hm3.scaling.augment_split`).** Target 100 or 500 records; distractor types A (stale clones of the
consulted witnesses, re-chained to the values at the start of the real history), B (a renamed copy of the same world
with fresh prior interventions: agreeing witnesses), C (a renamed copy with perturbed parameters: conflicting
witnesses under the same names and keys), D (an unrelated world). Mixed conditions use A–D; c100 uses C only.
Foreign objects get ids disjoint from S_0 and foreign segments are placed before the real history; `validate`
asserts per episode that the original objects, I, A, R and the parser's consulted keys are unchanged, and drops an
episode after five failed retries (one drop on Travel seed 32, so those cells have 63 evaluation episodes).

## B Method protocol

**Replay oracle (`hm3.replay`).** `ExecutorOracle` re-runs the deterministic executor on (S_0, I) with the visible
subset of records; `LLMOracle(repeats=3)` calls the actor at temperature 0 with the same serialization as the panel
and takes the majority with early stopping. `minimal_sufficient` is ddmin: remove halves, then quarters, and so on,
restart at the coarsest granularity after a success, stop when no block can be removed; it returns the set and the
replay count. Discovery is run only on training episodes whose full read is correct.

**Frontier model (`hm3.replay.FrontierModel`, `FrontierSelect`).** Features per record (`record_features`,
categorical only: numeric state features overfit and were dropped): the typed path from the cue's object to the
object the record's segment is keyed to; record kind and changed fields; the segment signature (multiset of
kind:type:fields); the relation of the record's object to the keyed object; the segment's recency among segments
sharing its key and among those sharing key and signature; the record's position in its segment. Classifier:
`HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, min_samples_leaf=8)` with balanced class weights
(the decision-tree variant is the ablation). Selection: reach objects from the cue over instance links whose type
pair has positive support in the discovered anchor paths; read the whole segment of any record with p_θ ≥ τ (τ = 0.3
in the reported arm, 0.5 as the token trade-off); show the reached objects, the read records' referents and their
one-hop links. Fitted per condition on that condition's own 200 training logs; the native-fit ablation fits once on
the native logs.

**Localisation (`hm3.replay_localise`).** Incidents as in `hm3.provenance`: one required witness minimally corrupted
so that the plan changes. Candidate orders: structural trace (records keyed to objects on typed paths from the cue to
the anomalous objects, nearest first, most recent first), read set then history, BM25 against the anomaly, history
order. Search: prefix doubling then binary search over the ordered candidates; the test replaces the prefix by its
reference version and replays; the answer is the last record of the shortest restoring prefix. Reported: replays per
incident (median per seed, mean).

**Observational estimators (`hm3.tcd_logs`, `hm3.grace_logs`).** Logs as written: one row per record, one binary
write indicator per object type, cues exogenous, trial-respecting windows. Pooled lagged ridge regression with BH-FDR
(α = 0.05); PCMCI+ (tigramite, ParCorr and G², τ_max = 3); GRACE reference implementation (causalts 0.26) with an
open skeleton at its formula penalty and at 3× and 10×, and on the PCMCI+ skeleton. No tuning toward any result;
every estimator reported.

## C Actor protocol

**Model and settings.** DeepSeek-V4-Flash through the OpenAI-compatible endpoint, temperature 0, thinking disabled
(`thinking: disabled`, `reasoning_effort: none`), `max_tokens` 16,384 on every reported cell (the 4,096-cap runs
are superseded), one format-only repair turn when the reply has no fenced JSON block, semantic failures terminal.
Verbose serialization on every arm (state as JSON with policy metadata and the visible records). Costs at the
endpoint's rates: $2.5 / M uncached input, $0.25 / M cached input, $10 / M output.

**Prompt v1 (terminating).** System prompt `hm3.llm.SYSTEM`: the memory is transactional and non-idempotent; every
transaction quotes the expected revision; automatic objects must not be written but their new values must be used;
visible rules are deterministic and hidden policies must be inferred from the history; answer as an analysis (one
line per object: stale | unchanged | automatic with the evidence) followed by a fenced JSON array of transactions.
Then the domain's operation card (`OP_CARDS[domain]`: object types and fields, allowed ops, visible rules, which
policies are hidden), the state, the visible records and the intervention.

**Prompt v2 (ledger-first).** v1 plus `SYSTEM_V2_SUFFIX`: step A, a policy ledger quoting record ids per entity and
stating each policy with its number, or "no evidence"; step B, propagate from the source in dependency order with
the arithmetic written, marking each object stale / automatic / unchanged; step C, revision and cancellation checks;
then the JSON block. (A v3 suffix with an explicit most-recent-wins conflict rule exists in the code and is not
reported.)

**Arms per cell.** full (every record), graph_seg (parser-based structure, whole witness segments), frontier_exec
(parser-free, executor-replay-fitted), frontier_llm (parser-free, actor-replay-fitted); each cell is one episode ×
one arm; arms are paired on episodes. Paired bootstrap (4,000 resamples, `panel_summary.boot`) for every difference; per-seed effects
reported alongside the pooled ones.

**Call-to-call variance probe.** 12 training episodes × 3 identical full-history calls per prompt
(`results/real/hm3/replay_llm/noise_probe_{v1,v2}.json`): correctness differs across calls in 0.58 (v1) and 0.25 (v2)
of episodes.

## D Costs

API spend by experiment family (cells = actor calls with a scored decision; from the ledgers on disk):

| family | cells | cost |
|---|---:|---:|
| actor panels, seed 30, both prompts, 16k cap (`long_out`) | 3,625 | $301 |
| seed replication, seeds 31/32 (`seeds`; before the 9/22 completion runs) | 2,131 | $197 |
| MemoryArena substrate port (`arena`) | 2,316 | $203 |
| memory-system baselines Mem0 / A-Mem (`memsys`) | 810 | $213 |
| history-scaling panels, 4k cap, superseded (`scaling`, `scaling_v2`, `scaling_v3`, `scaling_v4pro`) | 7,168 | $445 |
| parser-free selector cells (`frontier_llm`, `keysel`) | 1,270 | $66 |
| actor-level provenance (`provenance_llm*`) | 659 | $20 |
| earlier rounds and shards (`round2–4`, `shards`) | 1,639 | $31 |
| read-intervention discovery with the actor, single call (v1 / v2) | 394 / 397 replays | $7 / $11 |
| read-intervention discovery with the actor, k = 3 (v1 / v2, 187 episodes each) | 2,930 / 3,258 replays | $56 / $93 |
| **total** | | **≈ $1,640** |

Executor replays (discovery, length sweep, localisation, ladders) cost no API calls: about 14–28 replays per training
episode, 200 episodes per condition and seed, on CPU.

## E Reproduction

`code/hm3/`: `replay.py` (oracles, ddmin, frontier model, selection), `replay_length.py` (E1b), `replay_llm.py` (E2),
`replay_localise.py` (E3), `replay_sweep.py` (p_θ sweeps and ladders), `llm.py` (actor panels), `panel_summary.py`
(paired summaries), `provenance.py` / `provenance_llm.py`, `tcd_logs.py` / `grace_logs.py`, `arena_run.py`
(substrate port), `memsys_llm.py`, `figures.py` / `replay_figures.py` / `frontier_composition_figure.py` /
`method_figure.py`. Results: `results/real/hm3/{replay,replay_llm,frontier_llm,seeds,long_out,arena,memsys,
provenance*,tcd}/`, development runs under `results/development/hm3/`. Shard launcher `code/hm3/autodl_shards.sh`
(one API key per shard, resumable from the ledger).
