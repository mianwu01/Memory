# Detailed paper outline with the results we have (2026-09-19)

> Alignment correction (2026-09-21): this is a historical outline, not a frozen
> submission narrative. Claims attributing utility to learned topology must first
> pass the complete-type-graph and matched controls in
> `structure-alignment-protocol-2026-09-21.md`. Retain both memory utility and
> actionable auditing as research goals. Do not replace the latter with
> failure-only localisation or claim that a sufficient read set reveals intent.

For Yujia's abstract. Every number is traceable: `docs/hm3-results-package-2026-09-19.md` (summary tables),
`docs/hm3-history-scaling-results-2026-09-18.md` (full log), `results/e0v2/summary.md`, `docs/hidden-mechanism-v3-results.md`.
Status labels: **have** = frozen result on held-out data; **partial** = running or single-seed; **missing** = not run.

## 0. The insight in one paragraph (what the abstract should say)

An agent's memory should be organized by the causal structure of how past information reaches future
decisions, and that structure is gated by access: a stored record matters only in the regime in which it is
written, held, or read. Estimating dependencies conditioned on the access regime recovers gated read edges that
pooled temporal discovery misses. The estimated structure then does two things a retriever, a ledger, or a
full-context reader does not. Forward, it selects a read set whose size stays flat as the history grows, so a real LLM actor reads one to
three percent of the tokens at every history length, keeps working when the history holds conflicting evidence
about the same entities, and leads full context once the history reaches hundreds of records. Backward, the same structure traces an anomalous action to the specific
past record that caused it, and replacing that record with a clean version restores the action, while replacing
matched controls does not. The advantage has boundaries: when the history is short enough to read in full, reading everything is as good
or better; at a hundred records of consistent history a full-context actor matches the structure; and in a domain
whose objects are fully interconnected the structure adds little.

## 1. Introduction

Paragraph goals and what supports each.

| paragraph | goal | supporting material | status |
|---|---|---|---|
| P1 | Long-lived agents must reuse past information selectively and must be able to trace memory-induced errors to their source. | motivation; MemoryArena/MINJA/AgentPoison settings | have |
| P2 | Existing memory systems treat history as content to store and retrieve (retrieval, summaries, ledgers, modern agent memories); none represents *how* a past record reaches a future decision, so they cannot bound reads or attribute errors. | related-work positioning | have |
| P3 | Thesis: memory is mediated long-lag dependence through a persistent variable, gated by write/hold/read regimes; what to remember is the causal frontier; the estimated structure serves both selection and provenance. | formulation (§2) | have |
| P4 | Contributions: (a) formulation and identification of access-gated memory dependencies; (a′) recovery of the propagation skeleton from an agent's own event logs by an off-the-shelf temporal estimator, and the variable definition under which it fails; (b) a benchmark with hidden mechanisms, non-idempotent repairs and controlled history growth where lookup provably fails the gate; (c) forward selection: flat reads at one to three percent of the tokens, a real-actor edge under conflicting evidence and at 500 records, and the crossover at short histories; (d) backward provenance with intervention validation; (e) boundaries. | §3–§5 | have |

Main observation to state up front: structure-guided reading costs one to three percent of the tokens at every history
length, holds up under conflicting evidence where a full-context actor drops (0.29–0.33 vs 0.14 with a terminating
prompt), and leads at hundreds of records; the same structure yields intervention-validated provenance. (The earlier
numbers were inflated by an output-cap and prompt artifact; the effect is about two thirds of them; see §4.4.)

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
- **Setting mapping (2026-09-20).** Sample / variable / time step / regime / memory carrier / frontier for HM3, and
  whether the variable set is the same across episodes, conditions, regimes and domains: `docs/hm3-formulation-mapping-2026-09-20.md` §1–§2,
  with the setting-section sentences in §5.
- **Causal vocabulary (settled 2026-09-19, see `docs/causal-vocabulary-and-estimators-2026-09-19.md`).** "Temporal
  causal process" is the modelling object. "Temporal causal graph" is used with an explicit definition: edges are
  propagation effects estimated from trajectories whose upstream change is a known intervention, gated by the access
  regime, and checked by intervention (ground-truth recovery in E0, re-wired controls and clean-replacement tests in
  the agent tasks). No causal-discovery algorithm is contributed and no identification from observational agent
  logs is claimed; MINJA is the negative result for that case.

## 3. Method

1. **Regime-conditioned structure estimation (E0).** Lagged regression fitted separately within each access
   regime with false-discovery control; an edge is gated when its coefficient changes across regimes. Baselines:
   pooled ridge, additive-regime, PCMCI+, pooled GRACE, HC0 interaction model, shuffled-regime controls. Per-regime
   GRACE gives the same recovery and is an appendix row; the estimator is not a contribution (E0 v2 criterion C4).
   *(have: `code/regime_grace.py`, `code/e0v2`)*
2a. **Structure from the logs (added 2026-09-19).** The training histories as plain event logs (one binary variable per
   object type, interventions exogenous, no links, no parser); pooled lagged regression with FDR recovers the full
   type skeleton on 6/6 seeds in Travel and Shopping32 (recall 1.0), PCMCI+ recall 0.4; the MemoryArena-style
   round-activation encoding degenerates to self-loops on the same data. The recovered graph drives selection
   (EES 1.00, 12 reads, identical to the interventional skeleton) and provenance (§4.5). *(have: `code/hm3/tcd_logs.py`)*
2. **Structure for an agent task (HM3 instantiation).** From training trajectories in which every episode is a
   known intervention on one source object with the observed propagation of changes, learn a typed-path skeleton
   (which linked objects change after which upstream change) with a regime-gated local decision per template, and a
   history parser that attributes every hidden policy key to its latest outcome witness (provenance map). This is
   structure learning from interventional data, not observational discovery; GRACE/PCMCI+ do not apply because
   episodes share no fixed variable set. *(have: `code/hm3/learners.py::LearnedGraph`)*
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
  throughout; BM25 top-16 0.90 → 0.04; recency-16 0.94 → 0.32; learned graph with the gate fitted on native
  training histories (formal arm) 0.87 → 0.83 on dev and 0.88 → 0.80 on the reserved test seeds, with the
  per-condition refit as an ablation (0.87 → 0.85 on dev; on Shopping the refit collapses at 100 records while the
  native-fit gate stays at its native level); program learner 0.68 flat while reading 53 → 1125 records.
  Preregistered P1–P4 all hold for the formal arm (P2 paired shifts −0.01 / −0.03 / −0.04; the conflicting-witness
  condition alone reaches −0.07); required-record recall of fixed-K retrieval 0.97 → 0.64.
- Observation: the value comes from the correct topology (re-wired controls fail at every length) and reads stay
  flat by construction of the frontier; fixed-K retrieval loses the required records as distractors grow. The gate is
  a mechanism model: fit it once on clean histories; refitting it on long histories trains it on foreign witnesses
  for keys the task never consults (audited per episode; the augmentation itself never flips the oracles).
- Figure: EES and reads versus history length, one line per arm.

### 4.4 Real LLM actor (DeepSeek-V4-Flash, thinking off; Travel test seed 30) — status: have, revised 2026-09-19

- Type: the actor receives (history, state, intervention) under a selection × serialization cell and must emit the
  repair transactions; 53–64 episodes per condition; paired bootstrap intervals on the same episodes; two prompts
  (v1 plain, v2 ledger-first) and a 16,384-token output cap after the audit (`docs/bridge-plan-2026-09-19.md` §3.3;
  one summary command `hm3.panel_summary`).
- Audit: the first version of this table ran at a 4,096-token cap, where a truncated first attempt scored 0 after an
  empty format repair (full history truncated in 56/64 and 58/63 cells at 100/500 records), and prompt v2's
  policy-ledger step does not terminate over 100+ records (a repeated probe loops to the cap every time). Both factors
  are now controlled.
- Main result (graph_closed/compact minus full/verbose): native −0.33 [−0.47, −0.19] (v2); 100 records +0.05
  [−0.09, +0.19] (v2) and +0.00 [−0.14, +0.14] (v1); 500 records +0.17 [+0.05, +0.30] (v2) and +0.13 [+0.00, +0.25]
  (v1); conflicting witnesses only (c100) +0.13 [−0.02, +0.27] (v2) and +0.00 [−0.10, +0.10] (v1). Graph input
  1.5–1.8k tokens and output 0.6–1.3k at all lengths; full 27k–70k at 100 and 123k–261k at 500 with 16k output when it
  fails to terminate. BM25-16 and recency-16 are at 0.02–0.09 at long lengths.
- Parser-free selection (records by same-key precedent, no domain parser) is at parity with the parser-based graph
  at the actor level (+0.11 / −0.05 / +0.02 at 100 / 500 / c100) at 1.5× its input.
- Same-serialization panel (verbose both sides, segment kept, 16k; the panel to quote, 2026-09-20): graph_seg/verbose
  vs full/verbose under the terminating prompt v1: 100 records 0.33 vs 0.25 (+0.08 [−0.06, +0.22]); conflicting
  witnesses 0.33 vs 0.14 (+0.19 [+0.06, +0.32]); 500 records 0.33 vs 0.16 (+0.17 [+0.03, +0.32]); native 0.48 vs
  0.48 (v1) and 0.44 vs 0.66 (−0.23 [−0.39, −0.06], v2). Shopping32 (same serialization, terminating prompt v1, 16k): 100
  records parity (0.48 vs 0.48–0.50); 500 records full 0.53 vs graph_closed/verbose 0.48 (−0.05) and graph_seg/verbose
  0.34 (−0.19 [−0.34, −0.03]); the v2 gains there (+0.17 / +0.23) are the full arm's non-termination. Shopping supports
  the cost claim only. Under v2 the same pairs are +0.18 / +0.22 / +0.44 (full does not terminate).
  The compact witness-only arm understated the structure by 0.1–0.3.
- Partial credit (v1, 16k, 500 records): value accuracy +0.17 [+0.03, +0.31], affected F1 +0.09 [+0.01, +0.17];
  at 100 and c100 ≈ 0. Failure modes with the right records in context are execution errors (auto/txn protocol,
  buffer arithmetic, collateral writes), so the actor band is bounded by the actor; the same-serialization
  comparison (graph_seg/verbose vs full/verbose) is pending and replaces the compact-vs-verbose one.
- Observation (the sentence for the abstract): structure-guided reading costs one to three percent of the tokens at
  every length; under conflicting evidence about the same entities a full-context actor drops from 0.25 to 0.14 while
  the structure stays at 0.29–0.33; at hundreds of records the structure leads; at a hundred records of consistent
  history the two are at parity; when the history is short enough to read, reading everything is as good or better. The
  witness must be given with the intervention that produced it, in the same form as the full history. A ledger-first
  prompt helps the short structured context and breaks the long full context, so both prompts are reported.
- Withdrawn from the main text (4,096-cap runs): the single-distractor decomposition, the prompt-v3 rule, the
  V4-Pro and whole-segment rows, and the Shopping32 actor rows (Shopping32 16k rerun pending). They may appear in the
  appendix labelled cap-limited.
- Figures: cost plot (input/output tokens vs history length per arm) and EES vs history length with both prompts.

### 4.4b Substrate: real entities and the benchmark's memory interface — status: have (2026-09-20)

- Type: the Travel mechanism on MemoryArena's real flights, accommodations and restaurants (`travel_arena`), memory
  routed through MemoryArena's own `add_chunk` / `wrap_user_prompt` classes unmodified (BM25 at its default top-3 and at
  top-16, long-context, A-Mem at its default k = 5), ours behind the same interface; 64 episodes, 16k cap, both prompts.
- Result (ours − long-context, v1 / v2): native +0.05 / +0.03 (n.s.); 100 records +0.31 / +0.30; conflicting +0.12 /
  +0.27; 500 records +0.20 / +0.48; ours − BM25 top-16 +0.14 to +0.55; ours reads 3.8–4.8k tokens against 7k–269k.
- Observation: the synthetic-panel pattern holds on real entities through the benchmark's interface, and the native-length
  crossover does not appear there. Boundary: the task mechanism is ours; the entities, interface and baselines are the
  benchmark's; this is not the original MemoryArena planning task.
- Table: the substrate table in the results package.

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
- Same test with the observational graph (pooled TCD on the event logs, `hm3.provenance --graph tcd`): top-3
  0.96–0.98 at native and 0.91–1.00 at 500 records, clean replacement restores at the same rates, controls 0–0.05
  (`results/real/hm3/tcd/provenance/`). One graph, fitted from logs, forward and backward.
- Figure: the case figure Yujia asked for — one incident with the write/hold/read/action events, what each selector
  read, the trace, and the effect of replacing each candidate record.

### 4.6 Boundaries and negative results — status: have

- Shopping32 (revised 2026-09-20): the earlier +0.25 rows were output-cap truncation. With a terminating prompt and
  the same serialization, a full-context actor matches the structure at 100 records and beats the segment-context
  graph at 500 (0.53 vs 0.34, −0.19 [−0.34, −0.03]); the structure's accuracy advantage is Travel-specific and the
  Shopping actor claim is cost only (7–11k vs 26k–103k input tokens). Provenance fails there because 19 of 24 corruptions silence the
  parser's witness for the key (BM25 finds the record lexically, replacing it restores ≤ 0.08). The re-wired-graph
  control is uninformative in Shopping (the cart is fully connected within two hops).
- MINJA (8,400 tests, label-free): the structure arm selected no edges in 10/10 runs and the frequency heuristic
  matched random deletion; an identification boundary for sparse record exposure. AgentPoison: label-free
  localization 1/2 directly, 2/2 after frozen cluster expansion; a case, not a statistic.
- Native-length loss of selection is real (−0.33 flash, −0.10 Pro).
- Artifacts found and fixed during review: foreign-record labeling in the first API round (relabeled, rerun);
  superset-based wrong-graph control (replaced by the selection ladder); Shopping augmentation drops (fallback);
  per-condition gate refitting replaced by the native-fit gate after a per-episode audit traced every EES shift of
  the deterministic graph to the regime-estimate feature block (three channels, all from foreign witnesses on
  unconsulted keys); the same mechanism explains the actor arm's gain under long histories.

### 4.7 Missing or partial (say so in the paper or drop)

- Shopping three-seed deterministic panels: ladder done (graph_select 0.99 at all lengths, BM25 0.99 → 0.07), main
  panel being rerun with the augmentation fix; Travel test-seed panel 11/12 conditions done and consistent with dev
  (graph 0.88 → 0.89, BM25 0.92 → 0.03, recency 0.93 → 0.30).
- Modern agent-memory systems: **A-Mem and Mem0 (raw mode) complete** on Travel and Shopping at native and 100 records (numbers in the package Boundaries and in the experiments draft §5.3). Earlier text kept for the record: A-Mem was run as a read-budget-matched selector arm on Travel and
  Shopping at native and 100 records (each history record written as a note with A-Mem's own LLM note construction
  and evolution, top-16 by its embedding search, same actor prompt as the other fixed-K arms, write-side LLM tokens
  reported separately). LightMem is deferred: its pipeline rewrites records into extracted facts, so retrieved
  items cannot be mapped back to record ids for a matched arm without a design decision. Mem0 and dense retrieval
  are not run (no embeddings endpoint; a local embedder now works, so both are possible later). Transfer to the
  original MemoryArena actor: not run.
- Search and Formal history scaling: not run (Travel and Shopping only).


### 4.8 Ablations: what is actually responsible for the gain — status: have (Travel actor unless noted)

> Revised 2026-09-19: rows marked (4096) are output-cap-limited runs and are superseded by §4.4's 16k panels; the conflicting-witness rows no longer support a robustness claim.

Each row changes one thing against the main comparison (graph_closed/compact vs full/verbose, 64 paired episodes).

| variant | what it isolates | result |
|---|---|---|
| selector fitted only on native training data, evaluated on long histories | refitting the selector per condition | +0.27 at 100, +0.24 at 500 (main: +0.28, +0.24): the gain is not from refitting |
| compact vs verbose serialization, same graph selection | serialization / compression | native −0.33 (compact) vs −0.19 (verbose); at 100/500 compact ≥ verbose: serialization moves native by 0.1 and does not create the long-history gain |
| full history in compact vs verbose form | compression of the full context | +0.03 / +0.06 / −0.05 at native / 100 / 500: compressing full history does not rescue it |
| whole-witness-segment selection (graph_seg) | closure / how much context around a witness | native gap narrows to −0.11 (verbose); 500 records unchanged (+0.25) |
| three re-wired skeletons, same executor (deterministic ladder, three seeds) | topology vs any sparse structure | 0.43 / 0.04 / 0.04 vs 1.00 for the learned skeleton, at every length |
| BM25-16, lexical-16, recency-16, same executor | retrieval instead of structure | 0.90 → 0.04, 0.90 → 0.04, 0.94 → 0.32 from native to 500 records |
| relational program learner as the selector (actor) | graph vs another learned structure | native 0.20 vs 0.22; 500 records 0.27 vs 0.37 (−0.10 [−0.24, +0.05]) |
| prompt v3: latest-record-wins rule stated to the actor | prompt design | full context stays at 0.08 on conflicting witnesses; 0.13 → 0.05 at 500 mixed |
| single distractor types at 100 records | what makes long history hard | conflicting witnesses: full 0.08 vs graph 0.32; unrelated: 0.48 vs 0.27; duplicates 0.44 vs 0.35; stale 0.41 vs 0.36; unrelated at 500 records (240k tokens): 0.41 vs 0.33 |
| gate fitted on native histories vs refitted per condition (deterministic) | training-side pollution of the gate | Travel 0.87 → 0.83 (native-fit) vs 0.87 → 0.85 (refit, on dev); Shopping refit collapses at 100 records (0.175 on seed 0) while native-fit stays 0.77–0.81 |
| stronger backbone (DeepSeek-V4-Pro) | actor capacity | native −0.10 [−0.28, +0.08], 500 records +0.07 [−0.09, +0.22], full/verbose 0.38 → 0.17 |

Reading for the paper: the gain survives freezing the selector, changing serialization, compressing full context, and stating the conflict rule; it disappears when the topology is re-wired or replaced by retrieval; it is produced by conflicting evidence, and a stronger actor shrinks both the native loss and the long-history gain.

### 4.9 Case for the provenance figure — status: have (figure rendered 2026-09-20: `results/real/hm3/provenance/figures/case_travel_s30_test000.{pdf,svg,png}`, script `code/hm3/case_figure.py`; panels: history with required witnesses and the corrupted record, dependency path with hidden keys and outcomes, trace ranking with baselines and clean-replacement results)

`docs/hm3-case-travel-s30-2026-09-19.md`: the first incident on test seed 30 by the preregistered rule (episode
travel-s30-test-000). The corrupted record is the provider's auto-rebook witness (`auto_rebook[P51]`); the auditor,
given only the anomalous transfer object, ranks that record first; replacing it alone restores execution, while the
matched random, most-similar non-ancestor and most-recent replacements do not. The document lists the full event
history with the required witnesses marked, the clean and corrupted plans, the structural and leave-one-out rankings,
the non-graph baselines' rankings on the same incident, and the actor-level arms.

## 5. Related work and limitations

- Agent memory systems (retrieval, summaries, ledgers, Mem0/A-Mem/LightMem): store and retrieve content; no
  dependency structure, no read bound, no attribution.
- Temporal causal discovery (PCMCI+, GRACE-style penalized models): the estimators we condition on regimes.
- Causal representation learning: identification under nonstationarity and auxiliary variables; our regimes play the
  role of the auxiliary variable.
- Memory poisoning and provenance (MINJA, AgentPoison): our backward pass is the provenance counterpart.
- Limitations: generator-based mechanism (the entity vocabulary, memory interface and baselines of the substrate panel are MemoryArena's, the task is ours); the recency assumption on the current
  world's witnesses; domain dependence (Shopping); LLM call-to-call variance at native length; policy confounding
  and selection are stated, not tested.

## 6. Candidate contribution sentences (for Yujia to rewrite)

1. We formulate agent memory as gated long-lag causal dependence and show that the causal frontier is the unique
   minimum memory.
   (Causal vocabulary: process and frontier are formal; the learned graph is causal in the interventional sense
   defined in §2; no discovery algorithm is claimed.)
2. We demonstrate that conditioning on the access regime recovers gated memory edges that pooled temporal discovery
   misses.
3. We build a benchmark with hidden mechanisms, non-idempotent repairs and controlled history growth in which lookup
   provably fails and structure is measurably required.
4. We show that structure-guided reading keeps reads flat and keeps a real actor working under conflicting evidence
   at one to three percent of the tokens, with an honest crossover at short histories.
5. We show that the same structure yields intervention-validated provenance from an anomalous action to its causal
   record.

Figures for §4.3/4.4/4.4b: `results/real/hm3/figures/{scaling_travel,scaling_shopping32,substrate_travel_arena}.pdf` (2026-09-20). Experiments-section draft: `docs/paper-draft-experiments-2026-09-20.md`.
