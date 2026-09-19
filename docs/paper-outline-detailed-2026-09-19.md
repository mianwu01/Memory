# Detailed paper outline with the results we have (2026-09-19)

For Yujia's abstract. Every number is traceable: `docs/hm3-results-package-2026-09-19.md` (summary tables),
`docs/hm3-history-scaling-results-2026-09-18.md` (full log), `results/e0v2/summary.md`, `docs/hidden-mechanism-v3-results.md`.
Status labels: **have** = frozen result on held-out data; **partial** = running or single-seed; **missing** = not run.

## 0. The insight in one paragraph (what the abstract should say)

An agent's memory should be organized by the causal structure of how past information reaches future
decisions, and that structure is gated by access: a stored record matters only in the regime in which it is
written, held, or read. Estimating dependencies conditioned on the access regime recovers gated read edges that
pooled temporal discovery misses. The estimated structure then does two things a retriever, a ledger, or a
full-context reader does not. Forward, it selects a read set whose size stays flat as the history grows, and it
keeps a real LLM actor working when the history accumulates conflicting or stale evidence about the same entities,
at one to three percent of the tokens. Backward, the same structure traces an anomalous action to the specific
past record that caused it, and replacing that record with a clean version restores the action, while replacing
matched controls does not. The advantage has a boundary: when the history is short enough to read in full, reading
everything is still best, and in a domain whose objects are fully interconnected the structure adds little.

## 1. Introduction

Paragraph goals and what supports each.

| paragraph | goal | supporting material | status |
|---|---|---|---|
| P1 | Long-lived agents must reuse past information selectively and must be able to trace memory-induced errors to their source. | motivation; MemoryArena/MINJA/AgentPoison settings | have |
| P2 | Existing memory systems treat history as content to store and retrieve (retrieval, summaries, ledgers, modern agent memories); none represents *how* a past record reaches a future decision, so they cannot bound reads or attribute errors. | related-work positioning | have |
| P3 | Thesis: memory is mediated long-lag dependence through a persistent variable, gated by write/hold/read regimes; what to remember is the causal frontier; the estimated structure serves both selection and provenance. | formulation (§2) | have |
| P4 | Contributions: (a) formulation and identification of access-gated memory dependencies; (b) a benchmark with hidden mechanisms, non-idempotent repairs and controlled history growth where lookup provably fails the gate; (c) forward selection: flat reads, robustness to conflicting evidence, real-actor crossover; (d) backward provenance with intervention validation; (e) boundaries. | §3–§5 | have |

Main observation to state up front: full-context actors are robust to volume and fragile to conflict; structure-guided
reading is robust to both; structure also yields intervention-validated provenance.

## 2. Setting and formulation (theory we actually have)

- **Temporal SCM with a memory carrier.** Variables evolve over time inside episodes; a memory carrier for a pair
  (cue at t0, task variable at t1) is a persistent variable through which every active path passes, an
  interventional definition (D "memory carrier"). External memory modules are the special case with identity
  dynamics and gated write/read edges. *(have: definitions in `causal_memory_formulation.tex`)*
- **Access regimes and gated edges.** Write, hold and read edges are active only in their regime; the dependence
  structure is regime-conditional. *(have: assumptions A-gated, A-regime)*
- **Causal frontier lemma.** Under Markov and faithfulness the causal frontier F_t(Y) (past nodes with an edge into
  an ancestor of the task variables) is the unique minimum set that screens the future task variables from the rest
  of the past; a planner can condition on F_t alone; the frontier updates online by adding new nodes only.
  *(have: Lemma with proof; this is the theoretical basis for "what to remember" and for flat reads)*
- **Trustworthy memory.** Value correspondence, structure correspondence on the memory index set, and selection
  soundness (report no carrier when long-lag dependence comes from selection alone). *(have: definition)*
- **Identification statement (empirical, controlled).** Pooled and additive-regime estimators cannot recover gated
  read edges because the hold regime freezes the carrier (near-deterministic chains kill the tests) and pooling mixes
  regimes; conditioning on the regime restores recovery. *(have: E0 v2, §4.1; no theorem beyond the lemma —
  say "we show" for the lemma and "we demonstrate" for identification)*
- Failure modes named as experimental arms: frozen-variable regime, selection, policy confounding, latent
  confounders. *(have: text; selection and confounding are stated boundaries, not experiments)*

## 3. Method

1. **Regime-conditioned structure estimation.** Regime-GRACE: per-regime coefficients on the write/hold/read
   indicators with a penalized gated-edge model; baselines pooled ridge, additive-regime, PCMCI+, interaction model
   with HC0 errors, per-regime fits, shuffled-regime controls. *(have: `code/regime_grace.py`, `code/e0v2`)*
2. **Structure for an agent task (HM3 instantiation).** From training trajectories, learn a typed-path skeleton
   (which linked objects change after which upstream change) with a gated local decision per template, and a
   history parser that attributes every hidden policy key to its latest outcome witness (provenance map).
   *(have: `code/hm3/learners.py::LearnedGraph`)*
3. **Forward selection.** Read set = objects reached along the skeleton from the intervention source, plus the
   witness records attributed to their policy keys, plus the witnesses' referents and one-hop neighbours
   (graph_closed); optional whole-witness-segment variant (graph_seg). Records go to the executor or to the LLM
   actor in a fixed serialization. *(have)*
4. **Backward provenance through the same artifact.** Given the anomalous objects only, walk the skeleton back
   toward the source, collect the witnesses attributed to the policy keys on the path, re-rank by leave-one-record-out
   effect on the anomalous decisions, add candidates for keys whose witness went silent; validate by replacing the
   top records with clean versions and re-running the forward method. The forward and backward passes use one fitted
   graph, identified by its hash. *(have: `code/hm3/provenance.py`)*
5. **Controls that isolate the structure.** Same executor, same serialization, same budget; only the read set
   changes: learned skeleton, three re-wired skeletons of matched sparsity, BM25 top-K, lexical top-K, recency-K,
   ledger lookups, oracle. *(have)*

## 4. Experiments: what each one is, the main result, the observation

### 4.1 Controlled identification (E0 v2) — status: have

- Type: simulated temporal SCM with a gated memory carrier, n = 32 variables, T = 10,000, 5 seeds × 3 noise levels,
  frozen judgement criteria.
- Result: regime-conditioned estimation recovers the gated read edges in 5/5 seeds at every noise level (C1 PASS);
  no pooled or additive arm reaches the bar in any seed (C2); every shuffled-regime control fails (C3); the honest
  baselines that also pass are per-regime fits and the HC0 interaction model (C4). At σ = 0: regime-conditioned
  cell-memory F1 1.00; pooled ridge 0.43; additive 0.43; PCMCI 0.41; shuffled 0.54–0.63.
- Observation: what matters is conditioning on the access regime; the specific estimator is secondary.
- Figure: gate heat-map (`results/e0v2/fig_gate_heatmap.svg`) and one table.

### 4.2 The HM3 benchmark and the deterministic panel — status: have (Travel 3 seeds; four domains 3 seeds at native)

- Type: four task families modelled on MemoryArena (Travel, Shopping, Search, Formal) with hidden per-entity
  policies recoverable only from outcome witnesses; the query names only the source; repairs are non-idempotent
  transactions (revision, token, fee); metric EES = executable exact success. A zero-API gate (C1–C8) certifies that
  query leaks nothing, history is load-bearing, and every lookup/kNN killer fails.
- Result, four domains, fresh test seeds (EES): learned graph 0.88 / 0.76 / 1.00 / 0.72 (Travel / Shopping v3.2 /
  Search / Formal); best lookup or kNN 0.30 / 0.46 / 0.41 / 0.14; black-box GNN 0.74 / 0.71 / 0.46 / 0.26; relational
  program learner 0.67 / 0.78 / 0.99 / 0.89; oracle 1.00.
- Observation: explicit structure is required (every lookup, kNN and black-box arm is far below); the graph form
  wins where dependencies chain across objects (Travel), ties on Shopping and Search, and loses to the program
  learner on Formal. State this honestly: "composable relational structure with regimes read from history".
- Table: the four-domain table.

### 4.3 History-length scaling, deterministic (Travel, dev seeds 0/1/2, 60 episodes each; test seeds 30/31/32 confirm) — status: have

- Type: each episode's history is grown to 50 / 100 / 500 records with four frozen distractor types (stale versions,
  agreeing duplicates, conflicting witnesses about the same entities, unrelated worlds); the original chain, the
  intervention, the oracle repair and the required reads are unchanged, so lengths are paired. Validity is asserted
  per episode (Travel drops 0–2 %).
- Result (native → 500): graph_select 1.00 → 1.00 with 11.4 → 12.4 reads; re-wired skeletons 0.43 / 0.04 / 0.04
  throughout; BM25 top-16 0.90 → 0.04; recency-16 0.94 → 0.32; learned graph 0.87 → 0.85; program learner 0.68 flat
  while reading 53 → 1125 records. Preregistered P1–P4 all hold; required-record recall of fixed-K retrieval
  0.97 → 0.64.
- Observation: the value comes from the correct topology (re-wired controls fail at every length) and reads stay
  flat by construction of the frontier; fixed-K retrieval loses the required records as distractors grow.
- Figure: EES and reads versus history length, one line per arm.

### 4.4 Real LLM actor (DeepSeek-V4-Flash, thinking off; Travel test seed 30 with seed 31 replication) — status: have

- Type: the actor receives (history, state, intervention) under a selection × serialization cell and must emit the
  repair transactions; 64 episodes per condition; paired bootstrap intervals on the same episodes.
- Main result (graph_closed/compact minus full/verbose): native −0.33 [−0.47, −0.19]; 100 records +0.28
  [+0.16, +0.41]; 500 records +0.24 [+0.10, +0.38]; seed 31: −0.34 and +0.22. Graph input 2.2–2.8k tokens at all
  lengths; full 8k → 51k → 240k. BM25-16 and recency-16 are at or below full at long lengths. A selector frozen on
  native training data gives the same conclusion (+0.27 / +0.24). Program-learner selection: native 0.20 ≈ graph
  0.22; 500 records 0.27 vs graph 0.37 (n.s.). Stronger backbone (DeepSeek-V4-Pro): native −0.10 [−0.28, +0.08],
  500 records +0.07 [−0.09, +0.22]. Whole-segment selection narrows the native gap to −0.11 (verbose).
- Decomposition (100 records, one distractor type at a time, graph vs full): conflicting witnesses 0.32 vs 0.08
  (+0.24 [+0.11, +0.37]); unrelated worlds 0.27 vs 0.48; at 500 unrelated records (240k tokens) 0.33 vs 0.41
  (−0.10 [−0.24, +0.06]); agreeing duplicates 0.35 vs 0.44; stale versions 0.36 vs 0.41. Stating the
  latest-record-wins rule in the prompt leaves full at 0.08.
- Observation (the sentence for the abstract): a full-context actor survives pure volume and collapses under
  conflicting evidence about the same entities; structure-guided reading resolves the conflict at read time and
  stays at 0.3 or above at 1–3 % of the tokens; when the history is short enough to read, reading everything is
  still best (crossover). Assumption to state: the current world's own witnesses are the most recent for their keys.
- Figures: crossover plot (EES vs history length for graph, full, BM25, recency, with token counts on a second axis);
  decomposition bar chart.

### 4.5 Backward provenance through the same graph (Travel, reserved test seeds 30/31/32) — status: have

- Type: one required witness per episode is minimally corrupted so the parser reads a different policy value;
  incident = the forward method's plan changes and fails; the auditor sees only the anomalous objects; controls are
  three matched random records, the most similar non-ancestor record, the most recent record, and non-graph
  baselines (recency, BM25 against the anomaly, source heuristic); validation is clean replacement and re-execution.
- Result: top-1 hit 0.55–0.65, top-3 hit 0.98–1.00; replacing the top-3 restores execution 0.98–1.00, replacing
  three matched random records 0.00, the similar non-ancestor 0.00, recency 0.00; BM25 baseline top-3 0.29–0.60;
  at 500 records top-3 0.94–0.98. Actor level (52 incidents): clean 0.42, corrupted 0.17, top-3 replaced 0.48,
  random-3 0.27 (its prompt is identical to the corrupted one, so it measures call-to-call variance); net effect
  +0.21 [+0.04, +0.37], replaced ≥ clean (+0.06 [−0.13, +0.25]).
- Observation: the same structure that selects also attributes, and the attribution is behaviourally causal.
- Figure: the case figure Yujia asked for — one incident with the write/hold/read/action events, what each selector
  read, the trace, and the effect of replacing each candidate record.

### 4.6 Boundaries and negative results — status: have

- Shopping32: selection advantage at long histories holds after the augmentation fix (64 episodes: native −0.07
  [−0.21, +0.08]; 100 records +0.25 [+0.11, +0.39]; 500 records +0.25 [+0.14, +0.38]; BM25 +0.19 / −0.03), so
  Shopping joins Travel for the selection claim. Provenance fails there because 19 of 24 corruptions silence the
  parser's witness for the key (BM25 finds the record lexically, replacing it restores ≤ 0.08). The re-wired-graph
  control is uninformative in Shopping (the cart is fully connected within two hops).
- MINJA (8,400 tests, label-free): the structure arm selected no edges in 10/10 runs and the frequency heuristic
  matched random deletion; an identification boundary for sparse record exposure. AgentPoison: label-free
  localization 1/2 directly, 2/2 after frozen cluster expansion; a case, not a statistic.
- Native-length loss of selection is real (−0.33 flash, −0.10 Pro).
- Artifacts found and fixed during review: foreign-record labeling in the first API round (relabeled, rerun);
  superset-based wrong-graph control (replaced by the selection ladder); Shopping augmentation drops (fallback).

### 4.7 Missing or partial (say so in the paper or drop)

- Shopping three-seed deterministic panels: ladder done (graph_select 0.99 at all lengths, BM25 0.99 → 0.07), main
  panel being rerun with the augmentation fix; Travel test-seed panel 11/12 conditions done and consistent with dev
  (graph 0.88 → 0.89, BM25 0.92 → 0.03, recency 0.93 → 0.30).
- Transfer to the original MemoryArena actor and the modern agent-memory systems (Mem0, A-Mem, LightMem): not run
  (A-Mem installed, LightMem source-only, no embeddings endpoint for Mem0/dense). Present as future work or as a
  small appendix if time permits.
- Search and Formal history scaling: not run (Travel and Shopping only).

## 5. Related work and limitations

- Agent memory systems (retrieval, summaries, ledgers, Mem0/A-Mem/LightMem): store and retrieve content; no
  dependency structure, no read bound, no attribution.
- Temporal causal discovery (PCMCI+, GRACE-style penalized models): the estimators we condition on regimes.
- Causal representation learning: identification under nonstationarity and auxiliary variables; our regimes play the
  role of the auxiliary variable.
- Memory poisoning and provenance (MINJA, AgentPoison): our backward pass is the provenance counterpart.
- Limitations: generator-based evidence with a public-benchmark port pending; the recency assumption on the current
  world's witnesses; domain dependence (Shopping); LLM call-to-call variance at native length; policy confounding
  and selection are stated, not tested.

## 6. Candidate contribution sentences (for Yujia to rewrite)

1. We formulate agent memory as gated long-lag causal dependence and show that the causal frontier is the unique
   minimum memory.
2. We demonstrate that conditioning on the access regime recovers gated memory edges that pooled temporal discovery
   misses.
3. We build a benchmark with hidden mechanisms, non-idempotent repairs and controlled history growth in which lookup
   provably fails and structure is measurably required.
4. We show that structure-guided reading keeps reads flat and keeps a real actor working under conflicting evidence
   at one to three percent of the tokens, with an honest crossover at short histories.
5. We show that the same structure yields intervention-validated provenance from an anomalous action to its causal
   record.
