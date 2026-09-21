# Claude session → Codex sessions: what happened on this side (2026-09-22)

Read this before touching `docs/paper-draft-*.md`, `docs/full-status-method-experiments-paper-2026-09-21.md` or
`results/real/hm3/seeds/`. Your commit 19213fd was merged into this checkout as 0723691 (no conflicts). Everything
below sits on top of that merge. Nothing here has been pushed: the store file `~/.git-credentials-tts` was emptied
by git after GitHub rejected the token at 16:01 on 9/21, so the user must re-add a token before either side pushes.

## 1. Experiments this side ran after your branch point (all complete, tables frozen)

- **v1 actor panel, Travel seeds 31/32, 500 records**: the four shards that had stopped on a 12-dollar budget were
  run to completion. Pooled v1 500-record row is now n = 190 (full 0.16 / links+parser 0.37 / frontier_exec 0.20;
  links+parser − full +0.21 [+0.14, +0.29]; previously +0.22 at n = 180).
- **v2 actor panel, Travel seeds 31/32, c100 and 500** (full / graph_seg / frontier_exec): complete. Pooled with
  seed 30: structure − full +0.37 [+0.29, +0.46] at c100 and +0.35 [+0.27, +0.43] at 500, sign on every seed;
  frontier_exec − full +0.24 / +0.16 (seeds 31/32 only, n = 127; seed 30 has no v2 frontier_exec cell). The
  full-history v2 arm hits the 16k cap in 120/190 and 138/190 cells: these rows are reported with cap rates and are
  not headlines, in line with your Shopping v2 ruling.
- **Seed-32 episode `travel-s32-test-010`** is dropped by `augment_split` (validator fails five retries), so every
  augmented seed-32 cell has 63 episodes by construction. The earlier "numpy import" traceback in those shard logs
  was a relaunch with a stale scratchpad PYTHONPATH, not a data failure.
- Summaries: `results/real/hm3/seeds/panel_summary_travel_2026-09-22.{md,json}` and per-seed files beside it.
  Ledgers under `results/real/hm3/seeds/*/shards/*/llm_ledger.jsonl`; old shard logs kept as `shard.log.pre-resume-*`.

## 2. Documents this side wrote or changed

| file | state after reconciliation |
|---|---|
| `paper-draft-method-2026-09-21.md` | **Rewritten 9/22 under your protocol**: Observation 1 replaces Proposition 1; O(k log n) withdrawn, measured counts only; monotone use stated as a property of HM3's witness layout; randomised gates + PCMCI+ (G²) is Procedure A (the established-algorithm discovery), ddmin is Procedure B; §3.6 carries the attribution rules and the complete-graph control; template vs mechanism reference (stay→bundle vs dinner→bundle) named. Your amended version was the input; this supersedes it. |
| `paper-draft-experiments-2026-09-20.md` | **Rewritten 9/22 morning, before your branch was seen; NOT yet reconciled.** It still attributes forward gains to "structure", calls Proposition 1 a proposition, and has no complete-graph control, no read-gate PCMCI table, no Progressive Search / RoomEnv / source-audit boundaries. That rewrite is the next task on this side; do not cite this file's §5.2 until it is done. Its tables 5–9 and the ablation rows are numerically correct. |
| `paper-draft-appendix-2026-09-22.md` | New: gate C1–C8, augmentation A–D, replay oracles, frontier-model config, prompts v1/v2, actor settings, cost table (~$1,640 through 9/22 morning, before your runs), reproduction pointers. Needs your runs' costs and protocols added. |
| `paper-internal-review-2026-09-22.md` | New: items 1–12 from the morning pass, items 13–18 added after the merge (attribution, withdrawn statements, Procedure A, v2 rows, new boundaries, open questions for Yujia). |
| `full-status-method-experiments-paper-2026-09-21.md` | Your correction header kept verbatim; a "Reconciliation" section inserted right after it with the active six-point claim set; §4.9 holds the frozen tables; §7 plan and §8 files updated. |
| `yujia-method-v2-2026-09-22.md` | Your status note replaced by a reconciled one (six points, ends with "method vs validation instrument is Yujia's call"); claim 1 retitled; final v1/v2 numbers filled in. |

## 3. What this side accepts from your audit, and what it does not

Accepted and now in the drafts: complete-graph equivalence (1,531/1,531) and the attribution rule; withdrawal of the
O(k log n) bound; Proposition 1 → Observation 1; monotone use as a data property; v2 rows as cap-limited; the
randomised-gate + PCMCI result as the discovery step; Progressive Search, RoomEnv and the two failed source audits as
boundaries; template_reference vs mechanism_reference.

Not accepted as stated: "read interventions are only an audit instrument". Neither session has Yujia's ruling; the
drafts are written so both readings work, and the one-pager asks her. Also: the frontier_exec v1 numbers (+0.11 under
conflicting witnesses, parity elsewhere, best arm on Shopping) are parser-free and replay-fitted and are kept as
results of that selector; your 23-episode component_key2 diagnostic is reported beside them as a non-discovery hand
rule, not as a replacement for the 190-episode panels.

## 4. Things you should know before running anything

- This machine is Python 3.12; launch shards with `PYLIB= bash code/hm3/autodl_shards.sh …` (empty PYLIB). The
  script resumes from the ledger and counts prior spend toward `--budget_usd`, so a resume needs a higher cap.
- `pgrep -f hm3.llm` matches a bash loop whose command line contains that string; check liveness by ledger mtime.
- `code/hm3/llm.py` now has your `component_key2` selection mode; `scaling_learners()` includes `ComponentKeySelect`.
  This side did not change any code after the merge.
- Do not push to `claude/artifact-ordering-inzyf3`.

## 5. Next on this side (in order)

1. Reconcile the experiments draft (§5.2 identification with Procedure A table and the complete-graph control; rename
   "structure" arms to "instance links + parser"; v2 rows with cap rates; boundaries from your audit).
2. Add your protocols and costs to the appendix.
3. Commit; push once the token is restored.
