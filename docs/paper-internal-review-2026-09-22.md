# Internal review pass (2026-09-22)

Scope: the three paper-text drafts (`paper-draft-method-2026-09-21.md`, `paper-draft-experiments-2026-09-20.md`,
`paper-draft-appendix-2026-09-22.md`) against the status page (`full-status-method-experiments-paper-2026-09-21.md`)
and the Yujia one-pager (`yujia-method-v2-2026-09-22.md`). Each item is either fixed in place or listed for the
writer. Numbers were checked by grep across the five files; section references were checked against the revised
experiments numbering (§5.2 identification, §5.3 forward, §5.4 backward, §5.5 actor-specific, §5.6 ablations,
§5.7 boundaries).

## Fixed in this pass

1. Experiments draft restructured around the method: read-intervention discovery (executor and actor) is now the
   first result of §5.2, the observational estimators follow as Proposition 1's instance; E1b, the parser-free ladder,
   E3 localisation, the actor-specific frontier, the noise probe and the LLM-fitted-selector negative are in. The
   ablation table has six new rows (native-fit vs own-logs p_θ, record vs segment level, balanced vs unbalanced,
   executor vs actor labels, k = 1 vs k = 3 oracle, localisation orders). Boundaries expanded from eight lines to
   seven paragraphs.
2. Method draft cross-references resolve: §5.2 (frontier = skeleton up to no-read edges; PCMCI+/GRACE instance;
   14–28 replays), §5.3 (read/accuracy trade-off, reported in Table 4 and §5.7), §5.5 (actor frontier differs). No
   change needed.
3. Appendix: bootstrap resamples corrected to 4,000 (`panel_summary.boot`); Shopping32 gate confirmed PASS on
   C1–C8 (`hidden-mechanism-v3-results.md` §7.3); FDR named as BH.
4. Seed-32 episode `travel-s32-test-010` is dropped by `augment_split` (validator fails five retries), so every
   augmented seed-32 cell has 63 evaluation episodes by construction. Recorded in Appendix A; not a run failure.

## For the writer (not changed)

5. **Dev vs test numbers in the one-pager.** The Yujia page quotes E1b from the dev seeds (replays 15 → 22 → 27,
   frontier 2.7 → 3.0); the experiments draft quotes the test seeds (13.6 → 19.3 → 25.2, frontier 2.5 → 2.7). Both are
   on the status page (§4.2 dev, §4.7 test). The paper should quote test and may cite dev in the appendix.
6. **Two "frontier" numbers for E1a.** Status §4.1 gives 2.6–2.7 (Travel, 200 episodes, dev) and §4.7 gives 2.51 at
   native on test (60 episodes). The draft uses "2–3 records" in prose and the dev table in Table 1; say "dev" in the
   caption (done) and keep the test E1b numbers for the growth claim.
7. **Coverage of the executor frontier by the actor's.** Single-call: 0.20 / 0.43; k = 3 shards: 0.25–0.70; extended
   k = 3: 0.26 / 0.48. The paper quotes only the extended k = 3 numbers (Table 2, §5.5); the shard-level ones stay on
   the status page.
8. **Actor panel Table 6 at full n (resolved 16:30).** The v1 500-record cells were run to completion; the row is
   now n = 190 (0.16 / 0.37 / 0.20; structure − full +0.21 [+0.14, +0.29], previously +0.22 at n = 180). Draft, status
   page and one-pager updated.
9. **Prompt v2 replication (resolved 16:30).** Table 6b written from `panel_summary_travel_2026-09-22`: structure −
   full +0.37 / +0.35 at c100 / 500 (n = 190), parser-free +0.24 / +0.16 over full on seeds 31/32 (n = 127). Note for
   the writer: seed 30 has no v2 frontier_exec cell, so the parser-free v2 row pools two seeds; say so in the caption
   (done).
10. **Vocabulary.** "causal" appears only for do(read) and E0; observational edges are "temporal dependency
    structure" throughout the three drafts (checked by grep: no "causal graph" / "causal edge" for the recovered
    graphs). The formulation's "causal frontier" is used for F_t; the method's object is the "π-frontier".
11. **Figures referenced but not yet numbered in the text**: Figure 1 should be `method_schematic`, 2a
    `replay_length`, 2b the actor panel (from `scaling_travel`), 3 `substrate_travel_arena`, 4 `replay_localise` or the
    provenance case, 5 `frontier_composition`. The E0 heat-map is an appendix figure.
12. **Style.** The drafts avoid the "X, not Y" construction except in three places: §5.2 ("in the affected set and
    not in the read frontier"; "rests on the intervention and not on the estimator") and §5.4 ("a boundary for the
    parser, not for the primitive"). Each carries content; rephrase at the writer's call.

## Reconciliation with the Codex audit branch (merged 2026-09-22, commit 0723691)

13. **Attribution.** The complete-type-graph control (1,531/1,531 identical inputs) means no forward result may be
    attributed to discovered type edges. Both drafts now say "instance links + parser" for graph_seg/graph_select
    and report the control in §5.2. The re-wired-skeleton ablation is kept as a topology check, not as evidence that
    discovery helps.
14. **Withdrawn statements.** Proposition 1 → Observation 1; the O(|F| log n) bound → measured counts; "exact for
    the executor" → holds on HM3 because of the validator's witness layout; "frontier = skeleton" → precision-1.0
    agreement of the type projection with the supervised template, with the mechanism reference (dinner → bundle)
    named beside it.
15. **Discovery step.** Randomised gates + PCMCI+ (G²) is presented as Procedure A (the established-algorithm
    version); ddmin as Procedure B. The audit's 12-episode result is in §5.2; its spurious gate-to-gate edges (24 and
    91) are stated.
16. **v2 rows.** Kept with cap-hit rates in the table; the prose leads with v1. Shopping v2 +0.25 is no longer a
    headline sentence.
17. **New boundaries.** Progressive Search (actor gate 15/30, self-loop graph, discovered = empty on 10/10, source
    audits failed), RoomEnv (learned = full under budget, +5.4 pp over complete on small only), component_key2 as a
    non-discovery hand rule that beats the parser-free frontier on the executor at long histories.
18. **Open for Yujia.** Method vs validation instrument; whether HM3 remains the carrier given item 13, or whether a
    setting where learned dependencies distinguish valid from invalid read paths (the audit's decision rule) is
    required before submission.
