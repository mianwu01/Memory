# HM3 integration verification (2026-09-19)

This note records the independent integration audit of
`origin/claude/hm3-handoff-2026-09-18` at `8521493` into a branch based on
`fcc0805`. No paid API calls were made.

## Integration

- Common ancestor confirmed: `9e0373c`.
- The handoff contains the stated 14 historical commits plus one verification-package commit.
- The only shared-path conflicts were `docs/HANDOFF.md` and
  `docs/hidden-mechanism-v3-preregistration.md`.
- The run-linked HM3 preregistration from the handoff remains at its original path.
- The independently reconstructed origin document is preserved as
  `docs/hidden-mechanism-v3-preregistration-reconstructed-origin.md`.

## Artifact and credential checks

- `sha256sum -c results/real/hm3/ARTIFACT_HASHES.sha256`: 110/110 files passed.
- `python3 -m compileall -q code/hm3 code/e0v2`: passed.
- An independent scan for embedded Bearer tokens, `sk-` keys, and assigned API keys over the
  HM3/E0 code, handoff document, and HM3 result tree found zero hits.

## Summary reproduction

The documented command

```bash
cd code
PYTHONPATH=. python3 -m hm3.report \
  --det ../results/real/hm3/round2/det_test2.json
```

reproduced the fresh-seed table, including graph EES of 0.883 on Travel, 0.800 on Shopping,
1.000 on Search, 0.717 on Formal, and 0.756 on Shopping v3.2.

## Independent deterministic rerun

The main lookup, learned-graph, runtime-history-oracle, and oracle arms were rerun from the
generator on test seeds 20--22, with train seeds 120--122, across Travel, Shopping, Search,
Formal, and Shopping v3.2. This covered 15 domain/seed runs and 105 learner cells.
The rerun artifact is
`results/real/hm3/round2/det_test2.graph-rerun.verify.json`.

Comparison against `results/real/hm3/round2/det_test2.json` found:

- zero mismatches in all stored per-episode rows;
- zero mismatches in EES, legality, exact action set, affected precision/recall/F1,
  collateral transactions, value accuracy, required-read recall, read count, regret,
  plan count, and illegal rate.

The first attempt to rerun all 15 learners was stopped because the flat/program histogram
gradient-boosting fits were still consuming roughly 64 CPU cores after several minutes on the
first domain/seed cell. The committed program/GNN artifacts passed the hash and summary checks,
but those expensive fits were not independently rerun in this audit.

## Gold-access audit

`run_det.run()` generates train and evaluation episodes from separate seeds and calls
`learner.fit(domain, train)` before evaluation. An AST check over every learner `predict()`
method found that only the explicitly named `Oracle` accesses `ep.A` or
`ep.required_reads`; no non-oracle prediction method accesses `ep.A`, `ep.S1`, `ep.R`, or
`ep.required_reads`. Training methods do use completed train transitions as specified.

The current interface still passes a complete `Episode` object to every predictor. A future
hardening change should introduce a runtime-only episode view so that the no-gold boundary is
enforced by type/interface rather than source inspection.

## Scientific boundary confirmed by the audit

- The deterministic controlled result that learned graph structure beats unstructured lookup
  and kNN is reproducible for the audited arms.
- `program_reg` remains a serious structured competitor and is better than graph on Formal;
  the evidence does not establish graph as the universally best structured representation.
- `graph_pooled` is not the requested pooled-regime or additive-regime ablation. Those arms,
  along with matched-sparsity wrong graphs, remain missing.
- API round 4 still fails non-inferiority: graph-closed/compact trails full/verbose by 0.190 on
  paired Travel cells and 0.104 on paired Search cells, while reducing input by 0.738 and 0.695.
- Same-artifact backward provenance with intervention controls remains untested.
