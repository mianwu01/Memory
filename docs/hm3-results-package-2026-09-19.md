# HM3 results package for the paper claim (2026-09-19, early morning)

Evidence log with every number's provenance: `docs/hm3-history-scaling-results-2026-09-18.md`.
Designs: `docs/hm3-history-scaling-design-2026-09-18.md`, `docs/hm3-provenance-design-2026-09-18.md`.
Branch `claude/hm3-handoff-2026-09-18`. Numbers marked (interim) come from runs still completing.

## Claim the evidence supports

> Access-conditioned temporal dependency structure keeps an agent's memory reads flat as the history
> grows, stays robust when the history accumulates conflicting or stale evidence about the same
> entities, and traces an anomalous action back to the record that caused it; matched retrieval,
> recency, ledger and full-context baselines do not.

What it does not support: that selection beats reading everything when the history is short enough to
read, or that the same holds in every domain (Shopping is a boundary in both directions).

## Layer 1 — controlled execution (deterministic, Travel, dev seeds 0/1/2)

Same executor, only the read set changes. EES = executable exact success.

| arm | native | 50 | 100 | 500 records | reads at 500 |
|---|---:|---:|---:|---:|---:|
| graph_select (learned skeleton) | 1.000 | 1.000 | 1.000 | 1.000 | 12.4 |
| wrong_select 1 / 2 / 3 (re-wired skeletons) | 0.43 / 0.04 / 0.04 | same | same | same | 5.9 / 2.2 / 2.8 |
| bm25_k16 | 0.90 | 0.32 | 0.04 | 0.04 | 21.2 |
| retrieval_k16 (lexical overlap) | 0.90 | 0.27 | 0.04 | 0.04 | 21.2 |
| recency_k16 | 0.94 | 0.71 | 0.47 | 0.32 | 21.3 |
| learned graph, gate fitted on native training histories (graph_nf, formal arm) | 0.87 ± 0.06 | 0.86 | 0.84 | 0.83 | 12.4 |
| learned graph, gate refitted per condition (ablation) | 0.87 ± 0.06 | 0.84 | 0.84 | 0.85 | 12.3 |
| program_reg (reads everything) | 0.68 | 0.66 | 0.68 | 0.68 | 1125 |
| knn (reads everything) | 0.32 | 0.39 | 0.33 | 0.32 | 1125 |
| source_regime / exact_kv lookups | 0.04 / 0.00 | same | same | same | 3.5 / 1 |

All rows are three dev seeds (0/1/2), 60 episodes each. The formal graph arm fits the gate once on the seed's
native training episodes and evaluates on the augmented histories (design amendment §9.6, approved 2026-09-19):
long histories change the evidence, not the mechanism. Refitting the gate per condition trains it on
foreign-witness-polluted regime estimates; that row is kept as the ablation. On the reserved test seeds
(30/31/32, 60 episodes each) graph_nf gives 0.88 / 0.86 / 0.85 / 0.80 at native / 50 / 100 / 500 with reads
11.2 → 12.1 and required-record recall 1.00. Preregistered predictions P1 (flat graph reads: 11.4 → 12.4, ratio
1.09), P2 (stable graph EES: paired −0.01 / −0.03 / −0.04 at 50 / 100 / 500, all within 0.05; the conflicting-witness
condition c100 alone exceeds it at −0.07 [−0.12, −0.03]), P3 (fixed-K retrieval loses required records: recall
0.97 → 0.64), P4 (full-history readers grow linearly: 53 → 1125 reads) all hold. Single-type conditions:
conflicting witnesses (c100) are the only type that moves the learned graph (0.83); sd ≤ 0.06 except
wrong_select_1 (0.26, seed-dependent re-wiring).
Shopping32 deterministic (second session audit, seed 0 so far, three-seed panel rerunning with the
augmentation fix): refitting the gate per condition collapses to 0.175 at 100 records (a high-variance tree fit on
polluted training estimates, 0.57 averaged over seeds at 100/500), while the native-fit gate stays at 0.77–0.81 on
the same evaluation episodes, i.e. at its native level. Shopping selection ladder (three dev seeds): graph_select 0.99 at every length, BM25-16 0.99 → 0.07 at 500,
recency-16 falls likewise; two of three re-wired skeletons coincide with the learned one (uninformative control),
the third scores 0.13. Test-seed Travel panel (seeds 30/31/32, 11 of 12 conditions done): graph 0.88 → 0.89,
program_reg 0.71 → 0.68 (reads everything), BM25-16 0.92 → 0.03, recency-16 0.93 → 0.30, graph_select 1.00,
re-wired 0.05 → 0.03.

## Structure learning (E0 v2, controlled, five seeds × three noise levels)

`results/e0v2/summary.md` (second session, completed 2026-09-18 20:22): regime-conditioned estimation
recovers the gated read edges in 5/5 seeds at every noise level (C1 PASS); no pooled or additive arm reaches
the bar in any seed (C2 PASS); every shuffled-regime control fails (C3 PASS); the honest baselines that also
pass are the per-regime fits and the HC0 interaction model (C4), i.e. what is needed is conditioning on the
access regime, not the specific estimator. E0a verdict: PASS.

## Layer 2 — real actor (DeepSeek-V4-Flash, thinking off, prompt v2, test seed 30, 63–64 episodes)

Paired differences of graph_closed/compact against full/verbose on the same episodes.
"v2" histories carry uniform record labels (the first round marked foreign records; see log §3.5).

| history | graph EES | full EES | graph − full [95% CI] | graph tokens | full tokens |
|---|---:|---:|---|---:|---:|
| native (≈13 records) | 0.22 | 0.53 | −0.33 [−0.47, −0.19] | 2.3k | 8k |
| 100 mixed distractors (v2) | 0.36 | 0.08 | +0.28 [+0.16, +0.41] | 2.6k | 51k |
| 500 mixed distractors (v2) | 0.37 | 0.13 | +0.24 [+0.10, +0.38] | 2.6k | 240k |
| second test seed 31, native | 0.35 | 0.67 | −0.34 [−0.50, −0.16] | | |
| second test seed 31, 500 | 0.30 | 0.08 | +0.22 [+0.10, +0.35] | | |

BM25 top-16 and recency-16 sit at or below full history at 100 and 500 (v2: −0.05/+0.03 at 100, −0.11/−0.10 at 500 against full/verbose).
Selector fitted on native histories only: +0.27 / +0.24 (same conclusion).
Whole-witness-segment selection (graph_seg) narrows the native gap to −0.11 [−0.27, +0.05] in verbose
form and keeps +0.25 at 500. DeepSeek-V4-Pro: native −0.10 [−0.28, +0.08], 500 +0.07 [−0.09, +0.22].

### What makes the long history hard (single-distractor decomposition, Travel, 100 records)

| distractor type | graph EES | full EES | graph − full |
|---|---:|---:|---|
| conflicting witnesses about the same entities (C) | 0.32 | 0.08 | +0.24 [+0.11, +0.37] |
| same, with the conflict rule stated in the prompt (v3) | — | 0.08 | full unchanged (+0.00) |
| unrelated worlds, pure volume (D), 100 records | 0.27 | 0.48 | −0.22 [−0.38, −0.06] |
| unrelated worlds, pure volume, 500 records (240k tokens) | 0.33 | 0.41 | −0.10 [−0.24, +0.06] |
| agreeing duplicate witnesses (B) | 0.35 | 0.44 | −0.10 [−0.27, +0.10] |
| stale versions of the same records (A) | 0.36 | 0.41 | −0.05 [−0.22, +0.12] |

Reading: the full-context actor survives pure volume up to 240k tokens and collapses only when the
history holds conflicting evidence about the same entities. Telling it the latest-wins rule does not
help. The learned structure resolves the conflict at read time (parser-attributed latest witness) and
stays at 0.3 or above. So the actor-level claim is two-fold: cost (1–3 % of the tokens at similar
accuracy under pure volume) and robustness (+0.24 to +0.29 under conflicting evidence).
Assumption to state: the current world's own witnesses are the most recent records for the keys the task consults; for other keys foreign witnesses can be the latest, which is what perturbs a refitted gate.

Shopping32 (actor, v3 histories after the augmentation fix, 64 episodes, no drops): native −0.07 [−0.21, +0.08];
100 records graph 0.50 vs full 0.25, +0.25 [+0.11, +0.39]; 500 records graph 0.55 vs full 0.30, +0.25 [+0.14, +0.38];
BM25-16 +0.19 at 100 and −0.03 at 500; recency-16 +0.14 and +0.11. So the long-history selection advantage holds in
Shopping as well; the re-wired-graph control is uninformative there (two of three re-wirings read the same set as the
learned skeleton because the cart is fully connected within two hops), and provenance remains a boundary (below).

## Layer 3 — backward provenance through the same graph artifact (Travel, test seeds 30/31/32)

Forward selection and backward trace use one fitted graph (SHA recorded). One required witness is
minimally corrupted; the auditor sees only the anomalous objects.

| metric | seed 30 | seed 31 | seed 32 | at 500 records |
|---|---:|---:|---:|---:|
| incidents / episodes | 52/60 | 48/60 | 42/60 | 45–51 |
| top-1 hit | 0.62 | 0.65 | 0.55 | 0.53–0.64 |
| top-3 hit | 1.00 | 0.98 | 0.98 | 0.94–0.98 |
| EES restored after replacing top-3 with clean versions | 1.00 | 0.98 | 0.98 | 0.94–0.98 |
| same for 3 matched random records | 0.00 | 0.00 | 0.00 | 0.00 |
| most similar non-ancestor record | 0.00 | 0.00 | 0.00 | 0.00 |
| BM25-against-anomaly baseline, top-3 hit | 0.46 | 0.29 | 0.60 | 0.14–0.36 |

Actor-level version (all 52 incidents, graph_seg/verbose): clean history 0.42, corrupted 0.17, top-3
replaced 0.48, random-3 replaced 0.27; top-3 − random-3 +0.21 [+0.04, +0.37], top-3 − corrupted +0.31
[+0.15, +0.46], top-3 − clean +0.06 [−0.13, +0.25]. The random-3 arm's prompt is identical to the corrupted one (the graph reads ≈6 records
and the top-3 are excluded), so it measures the actor's call-to-call variance; the +0.22 is net of it. Shopping32 fails the provenance test: 19 of 24 corruptions
silence the parser's witness for the key, so a witness-based trace cannot reach the record; BM25 finds
it lexically but replacing it restores ≤ 0.08. Reported as a boundary.

## Boundaries and open items

- Native-length loss of selection (−0.33 flash, −0.10 Pro) is real; frame as the crossover.
- Shopping: selection advantage now holds at long histories (v3); provenance stays a boundary; the re-wired
  control is uninformative in this domain.
- Program-learner selection arm: native 0.20 vs graph 0.22 (−0.02 [−0.14, +0.11]); 500 records 0.27 vs
  graph 0.37 (−0.10 [−0.24, +0.05]) and vs full 0.13 (+0.14). Competitive selector; graph edges it out at
  length without significance.
- Shopping augmentation dropped 27 % of episodes at 500 records (state-dependent promo witnesses); fixed with a
  no-interleave fallback (0 drops, 17/64 episodes fall back); the v3 actor conditions above use it; the second
  session is rerunning the deterministic Shopping conditions with it.
- Three-seed Shopping panels, test-seed deterministic panels and E0 v2: second session, in progress.
- Per-condition gate refitting replaced by the native-fit gate after the second session's per-episode audit: the
  augmentation itself is clean (oracle and runtime-history oracle never flip); the only feature block that changes is
  the regime estimate, through three channels (foreign witnesses define keys the real history never witnessed,
  foreign witnesses override real ones for keys the task does not consult, and Travel's late-flag state inference
  reads foreign stays with the same hotel name); the native-fit gate removes the training-side effect, the
  evaluation-side effect on c100 remains and is reported.
- Assumption stated precisely: the current world's own witnesses are the most recent for the keys the task
  consults; for unconsulted keys foreign witnesses can be the latest.
- Mem0 / dense not run (no embeddings endpoint; user decision). A-Mem installed, LightMem source-only
  (Python < 3.12 required); both belong to the MemoryArena layer.
