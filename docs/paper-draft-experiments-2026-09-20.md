# Paper draft — Experiments section (2026-09-20, for Yujia to cut)

Companion to `docs/paper-outline-detailed-2026-09-19.md`. Every number is copied from the results package
(`docs/hm3-results-package-2026-09-19.md`) and the discovery deliverable (`docs/yujia-causal-bridge-2026-09-20.md`);
nothing here is new. Figures: `results/real/hm3/figures/scaling_travel.pdf`, `scaling_shopping32.pdf`,
`substrate_travel_arena.pdf` (script `code/hm3/figures.py`), `results/real/hm3/provenance/figures/case_travel_s30_test000.pdf`,
`results/e0v2/fig_gate_heatmap.svg`. Terminology follows the 9/20 decision: the recovered edges are *temporal
dependency structure* identified from observational logs; the causal reading is carried by the controlled
simulation, the re-wired controls and the clean-replacement tests.

## 5 Experiments

We ask three questions. **Q1** Can the dependency structure that the method consumes be recovered from an
agent's own event logs, with established discovery algorithms? **Q2** Does reading through that structure keep an
actor's memory reads flat and its decisions correct as the history grows and as it accumulates conflicting evidence?
**Q3** Does the same structure, walked backward, locate the record that caused an anomalous action?

### 5.1 Setup

**Benchmark.** HM3 instantiates the formulation of §2 as four task families modelled on MemoryArena (Travel, Shopping,
Search, Formal). Each episode carries a history H of prior records, a query naming only the source of a change, and a
hidden per-entity policy (for Travel: a provider's automatic rebooking rule and buffer, a hotel's late-arrival rule, a
restaurant's late-seating rule, a vendor's bundle linkage) that is recoverable only from outcome witnesses in H. The
agent must emit the repair transactions; these are non-idempotent (revision numbers, tokens, fees), so a wrong read
produces a wrong action rather than a near miss. The metric is EES, executable exact success: the emitted transaction
set executes legally and leaves the world in the reference state. A zero-API gate (C1–C8) certifies on every domain
that the query leaks nothing, that the history is load-bearing, and that every lookup and nearest-neighbour killer
fails. Dev seeds 0/1/2 were used for design; every number below is on reserved test seeds 30/31/32 unless marked dev.

**History growth.** Native episodes hold about 13 records. We extend them to 50, 100 and 500 records with four
distractor types drawn from the same generator (unrelated chains, duplicates, stale witnesses, conflicting witnesses
about the same entities); condition c100 uses conflicting witnesses only. The structure is fitted once, on the seed's
native training episodes, and evaluated on every length: long histories change the evidence, and the mechanism stays
fixed.

**Arms.** *Structure* reads the objects and records reached through the fitted type-level skeleton unrolled over the
instance links (graph_seg keeps each reached witness's whole segment). Deterministic baselines use the same executor
and change only the read set: three re-wired skeletons, BM25 top-16, lexical top-16, recency top-16, a relational
program learner and a kNN reader that read everything, and source-regime and exact-key lookups. Actor baselines give
DeepSeek-V4-Flash (thinking disabled, 16k output cap) either the full history or the structure-selected records in
the same verbose serialization, under a terminating prompt (v1) and a ledger-first prompt (v2). Memory-system baselines
are Mem0 (raw mode), A-Mem, and MemoryArena's own long-context, BM25 and A-Mem memory classes.

### 5.2 Q1 — Recovering the structure

**Controlled identification (E0).** In a simulated temporal SCM with a gated memory carrier (32 variables, T = 10,000,
five seeds, three noise levels) regime-conditioned estimation recovers the gated read edges in 5/5 seeds at every
noise level; pooled and additive estimators fail in every seed, and every shuffled-regime control fails. At σ = 0 the
regime-conditioned cell-memory F1 is 1.00 against 0.43 for pooled ridge, 0.43 additive, 0.41 PCMCI, 0.54–0.63 shuffled.
Per-regime least squares and an interaction model with HC0 errors also pass, so the finding is about conditioning on
the access regime and the estimator is secondary.

**From the agent's own logs.** We then take the HM3 event logs as they are written (one row per record, one binary
indicator per object type, user interventions exogenous, 200 training episodes per seed) and run, without tuning, the
reference GRACE implementation (open skeleton at its formula penalty and at 3× and 10×; PCMCI+ skeleton), PCMCI+ with
partial-correlation and G-squared tests, and pooled lagged regression with FDR control. Table 1 reports edge precision
and recall against the interventional skeleton, six seeds.

*Table 1. Type-edge precision / recall against the interventional skeleton; AP = average precision of the true edges
in the estimator's gate ranking.*

| estimator | Travel (5 true edges) | Shopping (3) | gate-ranking AP, Travel / Shopping |
|---|---|---|---|
| pooled regression + FDR | 0.21–0.23 / 1.00 | 0.50 / 1.00 | — |
| GRACE, open skeleton, formula λ | 0.19 / 1.00 | 0.50 / 1.00 | 0.47–0.63 / 0.70–1.00 |
| GRACE, open skeleton, 3×λ | 0.24–0.29 / 0.80–1.00 | 0.50–0.60 / 1.00 | 0.56–0.62 / 0.92–1.00 |
| GRACE, open skeleton, 10×λ | 0.40–0.75 / 0.40–0.80 | 1.00 / 0.33–0.67 | 0.59–0.77 / 0.87–1.00 |
| GRACE on a PCMCI+ skeleton | 0.20 / 0.40 | 0 / 0 | 0.27–0.50 / 1.00 |
| PCMCI+ (ParCorr; G²) | 0.20 / 0.40; 0.25–0.40 / 0.40 | 0 / 0 | — |

Every estimator recovers the head of the Travel chain (flight → transfer → stay) on every seed; GRACE places these two
edges at gate ranks 1 and 2 of 30. The conditional-independence tests then attribute the tail (dinner, activity,
bundle) to the flight at lag 2–3 and prune the mediating edges: the intermediate writes are deterministic functions
of the flight write, so conditioning on the earlier write makes the later one redundant. This is the faithfulness
failure that E0 documents for the hold regime, observed here on agent logs, and partial correlation and G-squared
agree on it. The open-skeleton GRACE keeps the mediating edges and ranks them behind the lag-2/3 shortcuts. On
Shopping the CI tests return the empty graph (every write follows the cart within one step); GRACE with an open
skeleton and the regression recover all three edges.

**Does the recovered structure serve the pipeline?** Selection cares about reach: a lag-l type edge is unrolled over l
instance hops. Plugging each recovered graph into the unchanged selector (Table 2) gives the reference EES on Travel
for every estimator except the over-penalised GRACE, and the GRACE record sets coincide with the interventional
skeleton's in 63–64 of 64 test episodes. On Shopping the CI skeletons are too sparse to select with; GRACE with an
open skeleton and the regression match the reference. The same graphs walked backward (§5.4) give provenance numbers
identical to the reference.

*Table 2. Deterministic EES with the selector driven by each recovered graph (Travel test seeds; native / 100 / c100 / 500).*

| graph | Travel | Shopping (native / 100 / 500) |
|---|---|---|
| interventional skeleton (reference) | 1.000 at every length, 11–12 reads | 0.972 / 0.972 / 0.983 |
| pooled regression | 1.000 | 0.972 / 0.972 / 0.983 |
| GRACE open, formula λ or 3× | 1.000 | 0.972 / 0.972 / 0.983 |
| GRACE on a PCMCI+ G² skeleton | 1.000 (lag-unrolled) | 0.167 / 0.167 / 0.142 |
| PCMCI+ ParCorr | 1.000 | 0.439 / 0.439 / 0.550 |
| GRACE open, 10× | 0.87 | 0.394 / 0.400 / 0.142 |
| BM25 top-16 | 0.92 / 0.03 / 0.04 / 0.04 | 0.983 / 0.556 / 0.050 |

### 5.3 Q2 — Forward: reading through the structure as the history grows

**Deterministic layer (same executor, only the read set changes; Travel test seeds, 60 episodes each).** The learned
skeleton reads 11.2 → 12.1 objects from native to 500 records with required-record recall 1.00 and EES 1.00 at every
length. BM25 top-16 falls from 0.92 to 0.03, lexical top-16 likewise, recency top-16 from 0.93 to 0.30; the three
re-wired skeletons score 0.05 → 0.03; the program learner that reads everything stays at 0.71 → 0.68 with 1,125 reads
at 500 records. The learned graph with its gate fitted on native training histories gives 0.88 / 0.86 / 0.85 / 0.80 at
native / 50 / 100 / 500. The preregistered predictions hold: reads flat (ratio 1.09), EES stable within 0.05 except
under conflicting witnesses (−0.07 [−0.12, −0.03]), fixed-K retrieval loses required records (recall 0.97 → 0.64),
full-history readers grow linearly. Shopping: graph_select 0.97–0.98 at every length; BM25 top-16 0.98 → 0.05.

**Actor layer (Figure 2; Table 3).** With the same serialization on both sides and a 16k output cap, the structure
reads 3.8–4.4k input tokens at every length while the full-history actor reads 27k at 100 records and 123k at 500
(v1), up to 261k under v2 where 50 of 63 cells hit the cap. Under the terminating prompt the two arms tie at native
length (0.48 vs 0.48) and at 100 mixed records (+0.08 [−0.06, +0.22]); under conflicting witnesses the full-history
actor drops to 0.14 while the structure holds 0.33 (+0.19 [+0.06, +0.32]); at 500 records +0.17 [+0.03, +0.32].
Under the ledger-first prompt the full-history actor is better at native length (−0.23 [−0.39, −0.06]) and the
structure leads by +0.18, +0.22 and +0.44 at 100, c100 and 500. Affected-object F1 and value accuracy move with EES
in every row.

*Table 3. Travel actor, EES, 64 paired episodes, 16k cap, verbose serialization on both sides.*

| history | prompt | full history (cells at cap) | structure | difference [95% CI] |
|---|---|---:|---:|---|
| native (≈13) | v1 | 0.48 (0/64) | 0.48 | +0.00 [−0.16, +0.14] |
| native (≈13) | v2 | 0.66 (6/62) | 0.44 | −0.23 [−0.39, −0.06] |
| 100 mixed | v1 | 0.25 (5/64) | 0.33 | +0.08 [−0.06, +0.22] |
| 100 mixed | v2 | 0.20 (45/64) | 0.37 | +0.18 [+0.04, +0.32] |
| 100 conflicting | v1 | 0.14 (3/63) | 0.33 | +0.19 [+0.06, +0.32] |
| 100 conflicting | v2 | 0.19 (38/63) | 0.44 | +0.22 [+0.07, +0.39] |
| 500 mixed | v1 | 0.16 (5/63) | 0.33 | +0.17 [+0.03, +0.32] |
| 500 mixed | v2 | 0.11 (50/63) | 0.56 | +0.44 [+0.30, +0.57] |

**Replicated on three test seeds and with the parser-free selector** (Table 3b; seeds 30/31/32, v1, pooled paired
comparison, n = 180–192). The structure − full-history effect is +0.13 [+0.04, +0.21], +0.16 [+0.08, +0.24] and
+0.22 [+0.13, +0.30] at 100, c100 and 500 records, with the sign on every seed. The replay-fitted parser-free selector
(§3.3, Algorithm 2 with the executor as π) is +0.11 [+0.04, +0.18] over full history under conflicting witnesses at
6k tokens, at parity elsewhere, and 0.06–0.18 below the parser-based structure; on Shopping it is the best arm at
100 and 500 records under both prompts (v2: +0.22 [+0.06, +0.38] over the structure at 100, +0.25 [+0.11, +0.39]
over full history at 500).

**Shopping is a boundary for the accuracy claim of the parser-based structure.** With a terminating prompt a full-context actor matches the structure
at 100 records (0.48 vs 0.50) and beats it at 500 (0.52 vs 0.36, −0.19); under v2 the structure leads at 500 (0.53 vs
0.30). What holds in Shopping at every prompt is cost: 7–11k input tokens against 26k–106k. The Shopping mechanism is
a star around the cart, so the witness's own segment carries most of the world and a reader that terminates can use
all of it.

**Real entities and the benchmark's memory interface (Figure 3).** We instantiate the Travel mechanism on MemoryArena's
flights, hotels and restaurants and route every arm through its memory classes (long-context, BM25 top-3 and top-16,
A-Mem), with the structure reading through the same add/wrap interface. The pattern is unchanged: ours − long-context
is +0.05 (n.s.) at native and +0.31, +0.12, +0.20 at 100, c100, 500 under v1 (+0.03, +0.30, +0.27, +0.48 under v2),
at 3.8–4.8k tokens against 6.9k–269k; BM25 top-16 collapses from 0.28 to 0.02–0.05 as the history grows and the
default top-3 is starved at every length; A-Mem reads 0.11–0.14 at native and 0.02–0.06 at 100 records.

**Modern memory systems as selectors.** Mem0 in raw mode (verbatim records, its embedding search, top-16) reaches
0.27 at native and 0.05 at 100 records on Travel (required-record recall 0.79 → 0.39) and 0.53 / 0.30 on Shopping.
A-Mem with its own note construction and evolution reaches 0.34 / 0.02 on Travel and 0.61 / 0.41 on Shopping, at 13–17
write-side LLM calls per native episode and about 98 per 100-record episode. Mem0's default extraction mode keeps
0–40 % of records and is reported as a negative for that mode.

### 5.4 Q3 — Backward: tracing an anomalous action to its cause

One required witness is minimally corrupted; the auditor sees only the anomalous objects and walks the same fitted
graph backward (SHA recorded), ranking candidate records by their position on the path. Table 4 gives the
deterministic result; Figure 4 shows one incident end to end.

*Table 4. Provenance, Travel test seeds 30/31/32, 60 episodes each.*

| metric | native | 500 records |
|---|---|---|
| incidents / episodes | 52–56 / 60 | 54–57 / 60 |
| top-1 hit | 0.52–0.61 | 0.46–0.65 |
| top-3 hit | 0.96–0.98 | 0.91–1.00 |
| EES restored after replacing the top-3 with clean versions | 0.96–0.98 | 0.91–1.00 |
| same, three matched random records / most similar non-ancestor | 0.00 / 0.00–0.02 | 0.00 / 0.00 |
| BM25 against the anomaly, top-3 | 0.29–0.60 | 0.14–0.36 |

The numbers are identical whether the graph is the interventional skeleton, the regression graph, GRACE 3× or GRACE on
a G² skeleton, and they hold on the real-entity substrate (top-3 0.88–0.96). At the actor level (seed 30, 52
incidents, four arms, 16k) replacing the top-3 with clean versions brings the actor back to its clean-history level
under both prompts (top-3 − clean −0.02): v1 top-3 − corrupted +0.13 [+0.00, +0.27], top-3 − random-3 +0.17 [+0.02,
+0.31]; v2 +0.35 [+0.19, +0.50] and +0.29 [+0.12, +0.46]. The random-3 arm's prompt is identical to the corrupted
one, so the difference is net of call-to-call variance. Shopping fails this test: 19 of 24 corruptions silence the
parser's witness for the key, BM25 finds the record lexically, and replacing it restores ≤ 0.08.

### 5.5 What produces the gain

Each row changes one thing (Travel; deterministic rows use the same executor, actor rows are 64 paired episodes).

| variant | isolates | result |
|---|---|---|
| three re-wired skeletons, same executor | topology vs any sparse structure | 0.43 / 0.04 / 0.04 vs 1.00, every length |
| BM25-16, lexical-16, recency-16, same executor | retrieval instead of structure | 0.90 → 0.04, 0.90 → 0.04, 0.94 → 0.32 |
| gate fitted on native histories vs refitted per condition | training-side pollution | Travel 0.87 → 0.83 vs 0.87 → 0.85; Shopping refit collapses to 0.18 at 100 records, native-fit stays 0.77–0.81 |
| closed read set vs whole witness segment (actor, verbose) | how much context around a witness | closed 0.25 / 0.32 / 0.25 vs segment 0.33 / 0.33 / 0.33 at 100 / c100 / 500 (v1) |
| single distractor types at 100 records (actor, v1) | what makes long history hard | conflicting witnesses move the full-history actor (0.25 → 0.14); unrelated, duplicate and stale records do not |
| recovered graph instead of the interventional skeleton | source of the structure | identical selection and provenance (Tables 2, 4) |
| prompt v1 vs v2 | prompt design | both directions reported; v2 raises every arm's variance and the full-history actor's cap hits |

The gain survives freezing the selector, changing the graph's source and changing the prompt; it disappears when the
topology is re-wired or replaced by retrieval; it is produced by conflicting evidence and by history length.

### 5.6 Boundaries

Reading everything is better than selecting when the history is short enough to read (native length under v2).
The accuracy advantage is specific to chained mechanisms (Travel); Shopping keeps only the cost advantage and fails
provenance. Conditional-independence discovery prunes mediators on deterministic logs and returns nothing on
Shopping; the pipeline tolerates this on Travel because it consumes reach rather than mediation. MINJA (8,400
label-free tests) is an identification boundary: sparse record exposure yields no edges. Runs whose output cap
truncated the actor (4,096 tokens) inflated the earlier headline and are superseded throughout.
