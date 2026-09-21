# Paper draft — Experiments section (2026-09-20, revised 2026-09-22 for the read-intervention method; for Yujia to cut)

Companion to `docs/paper-draft-method-2026-09-21.md` (method, §3), `docs/paper-outline-detailed-2026-09-19.md`
(intro, setting, related work) and `docs/full-status-method-experiments-paper-2026-09-21.md` (every number with its
file). Numbers below are copied from that status page; nothing here is new. Figures: `results/real/hm3/figures/
{method_schematic,replay_length,replay_localise,frontier_composition,scaling_travel,scaling_shopping32,
substrate_travel_arena}.pdf`, `results/real/hm3/provenance/figures/case_travel_s30_test000.pdf`,
`results/e0v2/fig_gate_heatmap.svg`. Terminology: "causal" refers to do(read), the intervention the memory system
performs on its own reads at replay time (§3.2), and to the controlled simulation; edges recovered from the logs'
observational distribution are *temporal dependency structure* and are kept as the comparison that Proposition 1
predicts. Appendix material (protocols, prompts, costs) is in `docs/paper-draft-appendix-2026-09-22.md`.

## 5 Experiments

We ask four questions. **Q1** Is the read frontier of an agent's decisions identifiable from read interventions on
its own logs, and is it identifiable from the logs' observational distribution? **Q2** Does reading the frontier keep
memory flat as the history grows and protect the actor from conflicting evidence, with and without a hand-written
parser? **Q3** Does the same primitive, run backward, locate the record that caused an anomalous action? **Q4** Is the
frontier a property of the world or of the actor?

### 5.1 Setup

**Benchmark.** HM3 instantiates the formulation of §2 as four task families modelled on MemoryArena (Travel, Shopping,
Search, Formal). Each episode carries a history H of prior records, a cue naming only the source of a change, and a
hidden per-entity policy (for Travel: a provider's automatic rebooking rule and buffer, a hotel's late-arrival rule, a
restaurant's late-seating rule, a vendor's bundle linkage) that is recoverable only from outcome witnesses in H. The
agent must emit the repair transactions; these are non-idempotent (revision numbers, tokens, fees), so a wrong read
produces a wrong action rather than a near miss. The metric is EES, executable exact success: the emitted transaction
set executes legally and leaves the world in the reference state. A zero-API gate (C1–C8, Appendix A) certifies on
every domain that the cue leaks nothing, that the history is load-bearing, and that every lookup and nearest-neighbour
killer fails. Dev seeds 0/1/2 were used for design; every number below is on reserved test seeds 30/31/32 unless
marked dev. Each seed has 200 training episodes (replays and fitting) and 60–64 evaluation episodes.

**History growth.** Native episodes hold 13–18 records. We extend them to 100 and 500 records with four distractor
types drawn from the same generator (stale clones of the consulted witnesses, agreeing witnesses from a renamed copy
of the world, conflicting witnesses under the same names and keys, and an unrelated world); condition c100 uses
conflicting witnesses only. The original objects, cue, oracle and required records are unchanged by augmentation, so
lengths are paired samples.

**Policies and replay.** π is either the deterministic executor (the reference reader with the world's parser) or
DeepSeek-V4-Flash at temperature 0 with thinking disabled and a 16k output cap, under a terminating prompt (v1) or a
ledger-first prompt (v2), reading a verbose serialization of the state and the visible records. A replay re-runs π on
a logged episode with a chosen subset of records visible and scores the decision (§3.2). For the language model the
replay oracle is the majority of k = 3 identical calls, with early stopping.

**Arms.** *Structure (parser)* reads the objects and records reached through the fitted type skeleton unrolled over
instance links (graph_seg keeps each reached witness's whole segment). *Frontier (parser-free)* reads {m : p_θ ≥ 0.3}
at segment level plus the referents' one-hop closure, with p_θ a gradient-boosted classifier on categorical record
features fitted to the frontiers discovered by Algorithm 1 on the condition's own 200 training logs (§3.3);
`frontier_exec` uses the executor's replays, `frontier_llm` the actor's own. *Key-precedent* is a parser-free hand
rule (the latest same-key segment for each reached object). Deterministic baselines use the same executor and change
only the read set: three re-wired skeletons, BM25 top-16, lexical top-16, recency top-16, a relational program learner
and a kNN reader that read everything, and source-regime and exact-key lookups. Actor baselines give the model the
full history in the same serialization. Memory-system baselines are Mem0 (raw mode), A-Mem, and MemoryArena's own
long-context, BM25 and A-Mem memory classes. Observational discovery baselines are pooled lagged regression with FDR,
PCMCI+ (ParCorr, G²) and the reference GRACE implementation, run on the logs as written.

### 5.2 Q1 — Identifying the frontier

**Read interventions with the executor as π (E1a; Table 1).** On 200 native training episodes per seed the discovered
π-frontier is 2–3 records out of 14–19, found in 14 replays per episode. Projecting the anchor paths of the discovered
records to type pairs recovers the interventional skeleton at precision 1.0 on every seed; the one edge missing in
each domain (stay → activity in Travel, cart → promo in Shopping) is the edge whose child has no hidden policy, so
nothing has to be *read* for it: it is in the affected set and not in the read frontier, which is the formulation's
distinction observed. The frontier is a strict subset of the generator's required-record list in 165 of 200 episodes:
what the actor needs is what is identified.

*Table 1. Discovery by read interventions, three dev seeds, 200 training episodes each.*

| domain | records / episode | π-frontier | replays / episode | type projection vs interventional skeleton |
|---|---:|---:|---:|---|
| Travel | 18.5 | 2.6–2.7 | 14.0–14.1 | 4/5 edges, precision 1.0 every seed |
| Shopping | 13.8–14.5 | 2.1–2.2 | 13.4–13.9 | 2/3 edges, precision 1.0 |

**Read interventions with the language model as π (E2; Table 2).** The same algorithm with the actor as the oracle
(Travel seed 30, 187 training episodes, both prompts, k = 3 votes) can label only the episodes where the full read is
correct by majority (29 % under v1, 39 % under v2). On those 55–73 episodes the actor's own replays recover the same
four type edges as the executor's at precision 1.0, with 41–48 calls per episode. The actor's structure is therefore
identifiable from interventions it performs on its own reads, without a parser and without any assumption on the
write process.

*Table 2. Discovery with the actor as π (Travel seed 30, k = 3 majority oracle).*

| | prompt v1 | prompt v2 |
|---|---|---|
| episodes processed / usable (full read correct by majority) | 187 / 55 | 187 / 73 |
| actor frontier (mean, median) vs executor frontier on the same episodes | 3.09, 3 vs 2.27 | 2.92, 3 vs 2.48 |
| replays per usable episode (p90); model calls | 22.1 (57); 48 | 19.3 (34); 41 |
| type projection vs interventional skeleton | 4/5, precision 1.0 | 4/5, precision 1.0 |
| edge support (flight→transfer, transfer→stay, stay→dinner, stay→bundle) | 146, 39, 13, 2 | 200, 34, 11, 2 |
| cost | $60 | $102 |

**Observational discovery on the same logs (Proposition 1's instance; Table 3).** We take the event logs as written
(one row per record, one binary indicator per object type, cues exogenous, 200 training episodes per seed, six seeds)
and run the observational estimators without tuning. Every estimator recovers the head of the Travel chain (flight →
transfer → stay); GRACE places these two edges at gate ranks 1 and 2 of 30. The conditional-independence tests then
attribute the tail (dinner, activity, bundle) to the flight at lag 2–3 and prune the mediating edges: the intermediate
writes are deterministic functions of the flight write, so conditioning on the earlier write makes the later one
redundant, which is Proposition 1. On Shopping the CI tests return the empty graph (every write follows the cart
within one step). The controlled study (E0; 32 variables, T = 10,000, five seeds, three noise levels) shows the same
thing in a simulated SCM with a gated carrier: regime-conditioned estimation recovers the gated read edges in 5/5
seeds at every noise level and pooled, additive and PCMCI estimators fail (F1 0.43 / 0.43 / 0.41 against 1.00 at
σ = 0); read interventions are the constructive form of that conditioning.

*Table 3. Type-edge precision / recall of observational estimators against the interventional skeleton, six seeds.*

| estimator | Travel (5 true edges) | Shopping (3) | gate-ranking AP, Travel / Shopping |
|---|---|---|---|
| pooled regression + FDR | 0.21–0.23 / 1.00 | 0.50 / 1.00 | — |
| GRACE, open skeleton, formula λ | 0.19 / 1.00 | 0.50 / 1.00 | 0.47–0.63 / 0.70–1.00 |
| GRACE, open skeleton, 3×λ | 0.24–0.29 / 0.80–1.00 | 0.50–0.60 / 1.00 | 0.56–0.62 / 0.92–1.00 |
| GRACE, open skeleton, 10×λ | 0.40–0.75 / 0.40–0.80 | 1.00 / 0.33–0.67 | 0.59–0.77 / 0.87–1.00 |
| GRACE on a PCMCI+ skeleton | 0.20 / 0.40 | 0 / 0 | 0.27–0.50 / 1.00 |
| PCMCI+ (ParCorr; G²) | 0.20 / 0.40; 0.25–0.40 / 0.40 | 0 / 0 | — |
| read interventions (executor, Table 1) | 1.00 / 0.80 | 1.00 / 0.67 | — |

**Does a recovered graph serve the pipeline?** Selection consumes reach: a lag-l type edge is unrolled over l instance
hops. Plugging each recovered graph into the unchanged parser-based selector gives the reference EES on Travel for
every estimator except the over-penalised GRACE (1.000 at every length; GRACE's record sets coincide with the
skeleton's in 63–64 of 64 episodes); on Shopping the CI skeletons are too sparse to select with (0.14–0.44) and GRACE
with an open skeleton and the regression match the reference (0.972 / 0.972 / 0.983). The same graphs walked backward
give provenance numbers identical to the reference (§5.4). The estimators differ in what they identify while
selecting the same reads, which is why the paper's claim rests on the intervention and not on the estimator.

### 5.3 Q2 — Forward: reading the frontier as the history grows

**Replays grow with log n, the frontier does not (E1b; Figure 2a).** Running Algorithm 1 on the same training
episodes at 18, 100 and 500 records (60 episodes × 3 test seeds): the Travel frontier is 2.5 / 2.7 / 2.7 records
and the replays 13.6 / 19.3 / 25.2 (p90 23 / 32 / 42); Shopping 2.2 records at every length with 14.4 / 18.5 / 20.9
replays. Records grow 27–34×, replays 1.5–1.9×, and every augmented episode keeps a sufficient full read.

**Deterministic layer (same executor, only the read set changes; Table 4).** The parser-based skeleton reads
11.2 → 12.1 objects from native to 500 records with required-record recall 1.00 and EES 1.00 at every length; BM25
top-16 falls from 0.92 to 0.03, recency top-16 from 0.93 to 0.30, the three re-wired skeletons score 0.05 → 0.03, the
program learner that reads everything stays at 0.71 → 0.68 with 1,125 reads at 500 records. The replay-fitted
parser-free selector holds 0.91–0.97 on Travel at every length and 0.98–0.99 on Shopping at 100 and 500 records, on
par with the parser at the same read count on Shopping and at a higher read count on Travel (§5.7). The
preregistered predictions hold: reads flat, EES stable within 0.05 except under conflicting witnesses, fixed-K
retrieval loses required records (recall 0.97 → 0.64), full-history readers grow linearly.

*Table 4. Deterministic EES on test seeds (reads = objects + records in parentheses).*

| arm | Travel native / 100 / c100 / 500 | Shopping native / 100 / 500 |
|---|---|---|
| structure, parser (graph_select) | 1.000 / 1.000 / 1.000 / 1.000 (11–12) | 0.972 / 0.972 / 0.978 (19–22) |
| frontier, parser-free, replay-fitted (segment level, τ = 0.3) | 0.972 / 0.939 / 0.910 / 0.949 (23 → 133) | 0.894 / 0.989 / 0.983 (18–25) |
| frontier, τ = 0.5 (token trade-off) | 0.967 / 0.922 / 0.899 / 0.933 (20 → 93) | 0.878 / 0.956 / 0.972 (17–24) |
| frontier, native-fit ablation (record level) | 0.944 / 0.660 / 0.596 / 0.523 | 0.856 / 0.894 / 0.933 |
| key-precedent hand rule (parser-free) | 0.994 / 0.938 / 0.916 / 0.798 | 1.000 / 0.994 / 0.967 |
| BM25 top-16 | 0.917 / 0.034 / 0.039 / 0.039 | 0.983 / 0.556 / 0.050 |
| recency top-16 | 0.93 → 0.30 | — |
| re-wired skeletons (three) | 0.05 → 0.03 | — |

**Actor layer (Figure 2b; Tables 5 and 6).** With the same serialization on both sides and a 16k output cap, the
parser-based structure reads 3.6–4.4k input tokens at every length while the full-history actor reads 27k at 100
records and 123k at 500 (v1), up to 261k under v2 where 50 of 63 cells hit the cap. On seed 30 (Table 5) the two arms
tie at native length under v1 and the full-history actor is better at native length under v2; under conflicting
witnesses and at 500 records the structure leads under both prompts. Pooled over three test seeds (Table 6, v1,
n = 190–192 paired episodes) the structure − full-history effect is +0.13, +0.16 and +0.21 at 100, c100 and 500
records with the sign on every seed (500 records: +0.17 / +0.31 / +0.14) and every interval excluding zero. Under
the ledger-first prompt (Table 6b) the effect is larger, +0.37 at c100 and +0.35 at 500 records, again on every seed
(+0.22 / +0.50 / +0.40 and +0.44 / +0.33 / +0.29). The parser-free replay-fitted selector is
+0.11 [+0.04, +0.18] over full history under conflicting witnesses at 6k tokens, at parity elsewhere, and trails the
parser-based structure by 0.03–0.06 at ≤ 100 records and by 0.17 at 500, where it over-selects (15.7k tokens).
Under v2 it is +0.24 and +0.16 over full history at c100 and 500 (seeds 31/32, n = 127) and 0.15–0.21 below the
structure.
Affected-object F1 and value accuracy move with EES in every row.

*Table 5. Travel actor, seed 30, 64 paired episodes, 16k cap, verbose serialization on both sides.*

| history | prompt | full history (cells at cap) | structure (parser) | structure − full [95% CI] |
|---|---|---:|---:|---|
| native | v1 | 0.48 (0/64) | 0.48 | +0.00 [−0.16, +0.14] |
| native | v2 | 0.66 (6/62) | 0.44 | −0.23 [−0.39, −0.06] |
| 100 mixed | v1 | 0.25 (5/64) | 0.33 | +0.08 [−0.06, +0.22] |
| 100 mixed | v2 | 0.20 (45/64) | 0.37 | +0.18 [+0.04, +0.32] |
| 100 conflicting | v1 | 0.14 (3/63) | 0.33 | +0.19 [+0.06, +0.32] |
| 100 conflicting | v2 | 0.19 (38/63) | 0.44 | +0.22 [+0.07, +0.39] |
| 500 mixed | v1 | 0.16 (5/63) | 0.33 | +0.17 [+0.03, +0.32] |
| 500 mixed | v2 | 0.11 (50/63) | 0.56 | +0.44 [+0.30, +0.57] |

*Table 6. Travel actor pooled over test seeds 30/31/32, prompt v1, 16k cap (tokens: full / structure / frontier).*

| history | full | structure (parser) | frontier_exec (parser-free) | structure − full | frontier − full | frontier − structure | tokens |
|---|---:|---:|---:|---|---|---|---|
| native | 0.42 | 0.40 | 0.38 | −0.02 [−0.11, +0.07] | −0.05 [−0.14, +0.04] | −0.03 [−0.11, +0.06] | 6.5k / 3.6k / 3.1k |
| 100 mixed | 0.24 | 0.37 | 0.30 | **+0.13 [+0.04, +0.21]** | +0.07 [−0.02, +0.15] | −0.06 [−0.16, +0.04] | 26.8k / 4.0k / 5.6k |
| 100 conflicting | 0.16 | 0.33 | 0.27 | **+0.16 [+0.08, +0.24]** | **+0.11 [+0.04, +0.18]** | −0.06 [−0.14, +0.02] | 26.8k / 4.0k / 6.0k |
| 500 mixed | 0.16 | 0.37 | 0.20 | **+0.21 [+0.14, +0.29]** | +0.04 [−0.02, +0.11] | −0.17 [−0.24, −0.09] | 123k / 4.1k / 15.7k |

*Table 6b. Travel actor, prompt v2, pooled over test seeds 30/31/32 (structure and full, n = 190) and over seeds
31/32 for the parser-free arm (n = 127; seed 30 has no v2 frontier_exec cell), 16k cap.*

| history | full (cells at cap) | structure (parser) | frontier_exec (parser-free) | structure − full | frontier − full | frontier − structure | tokens |
|---|---:|---:|---:|---|---|---|---|
| 100 conflicting | 0.14 (120/190) | 0.51 | 0.35 | **+0.37 [+0.29, +0.46]** | **+0.24 [+0.15, +0.33]** | −0.21 [−0.31, −0.10] | 69k / 4.3k / 6.5k |
| 500 mixed | 0.11 (138/190) | 0.46 | 0.27 | **+0.35 [+0.27, +0.43]** | **+0.16 [+0.08, +0.24]** | −0.15 [−0.26, −0.03] | 259k / 4.4k / 20k |

Per seed (30 / 31 / 32) the structure − full effect is +0.22 / +0.50 / +0.40 at c100 and +0.44 / +0.33 / +0.29 at
500 records. The full-history actor hits the 16k output cap in 63–73 % of v2 cells at these lengths, which is part
of what the ledger-first prompt does to a long context and is reported as such (§5.7).

**Shopping (Table 7).** Under the terminating prompt the parser-based structure matches the full-history actor at
100 records and trails it at 500 (0.36 vs 0.52), so for the parser-based arm Shopping carries a cost claim only
(7–11k tokens against 26k–106k). The replay-fitted parser-free selector is the best of the three arms at both lengths
under both prompts, significantly above the structure at 500 under v1 and at 100 under v2, and above full history at
500 under v2, at 6 % of the full-history tokens. The Shopping mechanism is a star around the cart, so the witness's
own segment carries most of the world; p_θ is precise there (Table 4), and the accuracy claim on Shopping belongs to
the replay-fitted selector.

*Table 7. Shopping actor, seed 30, 64 paired episodes, 16k cap.*

| history | prompt | full | structure (parser) | frontier_exec (parser-free) | frontier − full | frontier − structure |
|---|---|---:|---:|---:|---|---|
| 100 | v1 | 0.48 | 0.50 | 0.56 | +0.08 [−0.08, +0.23]; affected F1 +0.17 [+0.06, +0.28] | +0.06 [−0.06, +0.19] |
| 500 | v1 | 0.52 | 0.36 | 0.56 | +0.05 [−0.09, +0.19] | **+0.20 [+0.03, +0.38]** |
| 100 | v2 | 0.42 | 0.34 | 0.56 | +0.14 [−0.02, +0.30]; affected F1 +0.22 [+0.09, +0.35] | **+0.22 [+0.06, +0.38]** |
| 500 | v2 | 0.30 | 0.53 | 0.55 | **+0.25 [+0.11, +0.39]** | +0.02 [−0.12, +0.16] |

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

### 5.4 Q3 — Backward: localising the cause of an anomalous action

**Localisation by replay (E3; Table 8, Figure 4).** One required witness is minimally corrupted and the actor's plan
goes wrong. Algorithm 3 orders the candidate records and finds, by prefix doubling and binary search with
clean-replacement replays, the record whose replacement restores the reference plan. Every order localises (replacing
the whole history always restores the plan), so the comparison is the number of replays. On the chained domain the
structural prior puts the causing record first in most incidents at every length (median 1–2 replays) while the
lexical and history orders grow with log n (8 → 13 → 18). On Shopping at native length the lexical order is as good
as the structural one (the anomalous line's own records are the cause and share its tokens); at 500 records the
structural order is back to 2–6 against 18.

*Table 8. Replays to localise the causing record (median per seed 30/31/32; mean over incidents in parentheses).*

| condition | incidents | structural trace | read set, then history | BM25 against the anomaly | history order |
|---|---:|---|---|---|---|
| Travel native | 161 | 1 / 1 / 2 (2.5) | 4 / 4 / 4 (3.8) | 6 / 7.5 / 4 (5.3) | 8 / 8 / 7.5 (7.1) |
| Travel 100 | 169 | 1 / 1 / 2 (3.0) | 4 / 6 / 4 (4.8) | 13 / 13 / 13 (10.2) | 13 / 13 / 13 (13.1) |
| Travel c100 | 169 | 1 / 1 / 2 (3.6) | 4 / 6 / 4 (5.2) | 13 / 13 / 13 (10.2) | 13 / 13 / 13 (13.1) |
| Travel 500 | 168 | 1 / 1 / 2 (3.0) | 4 / 6 / 4 (4.7) | 18 / 18 / 18 (13.9) | 18 / 18 / 18 (17.9) |
| Shopping native | 85 | 4 / 4 / 4 (4.1) | 6.5 / 6 / 6 (5.4) | 3 / 4 / 3 (3.6) | 6 / 6 / 6 (6.1) |
| Shopping 500 | 62 | 4 / 6 / 2 (8.1) | 6 / 8 / 6 (10.1) | 18 / 18 / 18 (15.7) | 18 / 18 / 18 (18.0) |

**Parser-based provenance (Table 9).** The auditor sees only the anomalous objects and walks the fitted graph backward,
ranking candidate records by their position on the path. The numbers are identical whether the graph is the
interventional skeleton, the regression graph, GRACE 3× or GRACE on a G² skeleton, and they hold on the real-entity
substrate (top-3 0.88–0.96). At the actor level (seed 30, 52 incidents, four arms, 16k) replacing the top-3 with clean
versions brings the actor back to its clean-history level under both prompts (top-3 − clean −0.02): v1 top-3 −
corrupted +0.13 [+0.00, +0.27], top-3 − random-3 +0.17 [+0.02, +0.31]; v2 +0.35 [+0.19, +0.50] and +0.29 [+0.12,
+0.46]. The random-3 arm's prompt is identical to the corrupted one, so the difference is net of call-to-call
variance. Shopping fails this parser-based test (19 of 24 corruptions silence the parser's witness for the key,
replacing it restores ≤ 0.08) and passes localisation by replay (Table 8): Shopping is a boundary for the parser, not
for the primitive.

*Table 9. Parser-based provenance, Travel test seeds 30/31/32, 60 episodes each.*

| metric | native | 500 records |
|---|---|---|
| incidents / episodes | 52–56 / 60 | 54–57 / 60 |
| top-1 hit | 0.52–0.61 | 0.46–0.65 |
| top-3 hit | 0.96–0.98 | 0.91–1.00 |
| EES restored after replacing the top-3 with clean versions | 0.96–0.98 | 0.91–1.00 |
| same, three matched random records / most similar non-ancestor | 0.00 / 0.00–0.02 | 0.00 / 0.00 |
| BM25 against the anomaly, top-3 | 0.29–0.60 | 0.14–0.36 |

### 5.5 Q4 — The frontier is actor-specific

**Composition (Figure 5).** On the episodes where both are defined, the actor's frontier overlaps the executor's by
0.26 (v1) to 0.48 (v2) and is identical in 10 of 55 and 14 of 73 episodes. The two disagree on *which* witness carries
the provider's rule: the actor keys it on the stay's own transaction record in 0.84 of its episodes, the executor on
the flight intervention that opened the segment in 0.03. Both projections give the same type edges (Table 2); the
record-level frontier differs. This is why Algorithm 2 fits p_θ on the actor's own replays when the actor is the
deployed policy, and it is what D trust needs for edits that are specific to the actor.

**Call-to-call variance.** Twelve training episodes replayed three times with the identical full history disagree in
their correctness in 7/12 under v1 and 3/12 under v2. Consequently the single-call discovery's non-monotone pairs
(a superset wrong where a subset was right: 12.5 % under v1, 4.8 % under v2) are within call-to-call variance and are
not reported as a conflicting-evidence effect; the k = 3 oracle is the one used throughout, and the same variance
bounds every actor number in the paper (the provenance random-3 arm nets it out).

**Selector fitted on the actor's replays (negative).** p_θ fitted on the 55 / 73 majority-vote frontiers reads 8–10
records at native length and, in the actor panel (Travel seed 30, own prompt), scores 0.17 / 0.21 at c100 and
0.16 / 0.17 at 500 records against 0.33–0.56 for the parser-based structure: parity with full history everywhere,
affected F1 and value accuracy above full under v2 (+0.21, +0.19 at c100), over-selection at 500 (27–37k tokens). The
actor's structure is identifiable from its own replays (Table 2); 55–73 noisy episodes do not yet yield a selector
that competes with one fitted on 200 exact executor replays. The executor-fitted selector is the paper's parser-free
arm.

### 5.6 What produces the gain

Each row changes one thing. Deterministic rows use the same executor; actor rows are paired episodes.

| variant | isolates | result |
|---|---|---|
| three re-wired skeletons, same executor | topology vs any sparse structure | 0.43 / 0.04 / 0.04 vs 1.00, every length |
| BM25-16, lexical-16, recency-16, same executor | retrieval instead of structure | 0.90 → 0.04, 0.90 → 0.04, 0.94 → 0.32 |
| structure from a recovered graph instead of the interventional skeleton | source of the structure | identical selection and provenance (Tables 3, 9) |
| gate fitted on native histories vs refitted per condition (parser) | training-side pollution | Travel 0.87 → 0.83 vs 0.87 → 0.85; Shopping refit collapses to 0.18 at 100 records, native-fit 0.77–0.81 |
| p_θ fitted on native logs vs the condition's own logs (parser-free) | where the interventional labels are taken | Travel 0.66 / 0.60 / 0.52 vs 0.84 / 0.81 / 0.79 at 100 / c100 / 500 (record level) |
| p_θ record level vs segment level, τ = 0.3 (Travel 500, dev) | how much context around a selected record | 21 records, EES 0.78 vs 69 records, EES 0.95; frontier recall 0.97 vs 0.99 |
| p_θ balanced vs unbalanced classes (Travel 500, dev) | precision against recall of the frontier | precision 0.13 / recall 0.97 / EES 0.78 vs precision 0.57 / recall 0.73 / EES 0.53 |
| p_θ from executor replays vs from the actor's replays (actor, Travel c100 / 500) | source of the interventional labels | 0.25 / 0.21 vs 0.17 / 0.16 (v1) |
| replay oracle k = 1 vs k = 3 (actor discovery) | oracle noise | usable episodes 0.29 / 0.30 vs 0.29 / 0.39; executor-frontier coverage 0.20 / 0.43 vs 0.26 / 0.48 |
| localisation order: structural / read set / BM25 / history (Travel) | the prior against the log n search | median 1–2 / 4–6 / 4–13 / 8–18 replays |
| closed read set vs whole witness segment (actor, verbose) | context around a witness | closed 0.25 / 0.32 / 0.25 vs segment 0.33 / 0.33 / 0.33 at 100 / c100 / 500 (v1) |
| single distractor types at 100 records (actor, v1) | what makes long history hard | conflicting witnesses move the full-history actor (0.25 → 0.14); unrelated, duplicate and stale records do not |
| prompt v1 vs v2 | prompt design | both directions reported; v2 raises every arm's variance and the full-history actor's cap hits |

The gain survives freezing the selector, changing the graph's source, removing the parser and changing the prompt;
it disappears when the topology is re-wired or replaced by retrieval; it is produced by conflicting evidence and by
history length; the parser-free arm loses accuracy exactly where p_θ loses precision (Travel at 500 records).

### 5.7 Boundaries

**Amortisation is the weak link.** The replay-verified frontier is 2–3 records and does not grow with the history
(§5.3), but p_θ recovers it at recall ≥ 0.96 on Travel at 500 records only by reading 12–80 records: the categorical
features do not separate the true same-key segment from the conflicting same-key distractors, which are built to look
identical up to the value. The executor tolerates the extras (latest witness wins; EES 0.87–0.95), the actor does not
(15.7k tokens, −0.18 against the parser at 500 records). Where the model is precise (unbalanced classes) it misses the
frontier and EES drops to 0.53. Shopping does not over-select. This is a feature-representation problem for long
histories with adversarial same-key distractors and it does not touch the identification claim; path-conditioned
recency and per-key latest-segment features are the obvious next step.

**Discovery needs a correct full read.** A sufficient set exists only where the policy is right with everything
visible: 29–39 % of native episodes for this actor, which caps what the actor's own replays can label. Non-monotone
episodes are the cost driver (up to 57 replays at p90).

**The actor is noisy at temperature 0.** The same call disagrees with itself in 25–58 % of episodes, so the oracle
must vote, single-call non-monotonicity cannot be read as a conflicting-evidence effect, and every actor interval in
the paper carries this variance. The selector fitted on the actor's own 55–73 replays is a negative result at this
sample size (§5.5).

**Reading everything wins when the history is short enough to read.** At native length under the ledger-first prompt
the full-history actor is better than any selector by 0.23; every selection claim in the paper is a long-history
claim.

**The parser-based accuracy claim is specific to chained mechanisms.** On Shopping the parser-based structure keeps
only the cost claim and fails parser-based provenance; the replay-fitted selector and localisation by replay recover
both claims there. The paper reports both layers.

**Observational discovery is the wrong tool on deterministic logs.** CI tests prune mediators and return nothing on
Shopping (Proposition 1); the pipeline tolerates this on Travel because it consumes reach rather than mediation.
MINJA (8,400 label-free tests) is an identification boundary: sparse record exposure yields no edges.

**Superseded runs.** Runs whose output cap truncated the actor (4,096 tokens) inflated an earlier headline and are
replaced throughout by the 16k-cap, same-serialization panels.
