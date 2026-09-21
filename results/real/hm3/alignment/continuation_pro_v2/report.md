# 9/22 frozen stronger-actor continuation

Synthetic HM3 Travel; actual LLM actor. This is a candidate randomized-read estimand, not recovery of the original memory-state temporal SCM or advisor approval for a pivot.

Actor: DeepSeek-V4-Pro; returned IDs: `{'DeepSeek-V4-Pro-0813': 1019, 'deepseek-v4-pro-0813': 1}`. Six frozen episodes, 128 training calls each, 3 fresh calls per validation arm. Recorded job rows: 1020/1020 (including failures).

The 120-second transport attempt is archived. v2 reuses completed responses, including wrong ones; only failed or interrupted requests were recovered with a 300-second timeout. A final overlay allows one retry of newly failed infrastructure calls, never a semantic failure. Reused rows are not independent new calls; all attempts remain in cost accounting.

## Independent actor checks

| arm | correct / completed calls | complete episodes | episode accuracy | records | input proxy tokens | truncated |
|---|---:|---:|---:|---:|---:|---:|
| bm25_matched | 1/18 | 6/6 | 0.056 | 8.000 | 5457.833 | 2 |
| full | 3/18 | 6/6 | 0.167 | 17.167 | 6304.500 | 1 |
| learned_top2 | 1/18 | 6/6 | 0.056 | 8.000 | 5392.667 | 0 |
| neutral_blocked | 7/18 | 6/6 | 0.389 | 12.500 | 5842.833 | 0 |
| query_only | 0/18 | 6/6 | 0.000 | 0.000 | 4584.333 | 1 |
| random_17 | 2/18 | 6/6 | 0.111 | 8.000 | 5392.500 | 1 |
| random_29 | 2/18 | 6/6 | 0.111 | 8.000 | 5392.500 | 3 |
| random_43 | 4/18 | 6/6 | 0.222 | 8.000 | 5392.833 | 1 |
| recency_matched | 2/18 | 6/6 | 0.111 | 8.000 | 5371.500 | 1 |
| source_blocked | 2/18 | 6/6 | 0.111 | 13.667 | 5948.667 | 1 |
| source_changed | 0/18 | 6/6 | 0.000 | 17.167 | 6304.500 | 1 |
| wrong_17 | 0/18 | 6/6 | 0.000 | 8.000 | 5392.667 | 1 |
| wrong_29 | 4/18 | 6/6 | 0.222 | 8.000 | 5392.500 | 1 |
| wrong_43 | 1/18 | 6/6 | 0.056 | 8.000 | 5392.667 | 3 |

Full-read failure categories (computed from recorded scores, without new actor calls): `{'illegal_transaction': 10, 'wrong_payload_values': 3, 'correct': 3, 'wrong_affected_objects': 1, 'format_or_action_schema': 1}`. These are output error categories, not causal explanations of the model's internal reasoning.

## Learned top-2 minus each control

Repeats are averaged within episode; intervals resample episodes within each of the three fixed seeds. Six episodes cannot support general claims about environments, models, or deployment.

| control | paired episodes | delta | 95% conditional interval |
|---|---:|---:|---|
| bm25_matched | 6 | 0.000 | [-0.1111111111111111, 0.1111111111111111] |
| full | 6 | -0.111 | [-0.27777777777777773, 0.05555555555555555] |
| learned_top2 | 6 | 0.000 | [0.0, 0.0] |
| neutral_blocked | 6 | -0.333 | [-0.611111111111111, -0.05555555555555555] |
| query_only | 6 | 0.056 | [0.0, 0.1111111111111111] |
| random_17 | 6 | -0.056 | [-0.16666666666666666, 0.05555555555555555] |
| random_29 | 6 | -0.056 | [-0.2222222222222222, 0.1111111111111111] |
| random_43 | 6 | -0.167 | [-0.38888888888888884, 0.05555555555555555] |
| recency_matched | 6 | -0.056 | [-0.2222222222222222, 0.1111111111111111] |
| source_blocked | 6 | -0.056 | [-0.16666666666666666, 0.05555555555555555] |
| source_changed | 6 | 0.056 | [0.0, 0.1111111111111111] |
| wrong_17 | 6 | 0.056 | [0.0, 0.1111111111111111] |
| wrong_29 | 6 | -0.167 | [-0.3888888888888889, 0.05555555555555555] |
| wrong_43 | 6 | 0.000 | [0.0, 0.0] |
| random_within_episode_mean | 6 | -0.093 | [-0.24074074074074073, 0.05555555555555555] |
| wrong_within_episode_mean | 6 | -0.037 | [-0.12962962962962962, 0.05555555555555555] |

Discovery consumed 768 completed training requests, 4656132 input tokens and 1102387 output tokens. These costs belong to the learned method. The table's reduced selected input does not establish total cost savings; no cross-episode amortization is demonstrated.

## Frozen source audit: all cases

The first segment is externally labeled disallowed; the final segment is a separate-source deletion control. These groups need not have equal record/token sizes. Source labels describe a constructed scenario, not a discovered real violation. The diagnostic rule additionally requires an inferred threshold edge from that source. Three repeats do not establish statistical significance.

| episode | full | blocked source | neutral deletion | source changed | source edge | diagnostic rule |
|---|---:|---:|---:|---:|---|---|
| travel-s70-test-000 | 0/3 | 0/3 | 0/3 | 0/3 | False | False |
| travel-s70-test-001 | 1/3 | 0/3 | 2/3 | 0/3 | False | False |
| travel-s71-test-000 | 0/3 | 0/3 | 1/3 | 0/3 | False | False |
| travel-s71-test-001 | 1/3 | 1/3 | 2/3 | 0/3 | False | False |
| travel-s72-test-000 | 1/3 | 1/3 | 2/3 | 0/3 | False | False |
| travel-s72-test-001 | 0/3 | 0/3 | 0/3 | 0/3 | False | False |

The frozen +15-minute treatment translates both ends of historical time deltas. It can preserve difference-based policies such as pickup-minus-arrival, so an unchanged output under this treatment is not evidence of absent reliance. Full-read instability already prevents the intended normal-correct-output demonstration.

There is no independent authorized retrieval tool in HM3. Blocking was executed as a read intervention; abstention is only a proposed fallback, not an implemented and independently validated safety controller. Relabeling identical content is not counted as an independently validated safe substitute.

## Native memory-output variants

Same tasks, actor, visible state, and output rules. The primary actor_v2 inputs restore exactly the shared state/query/system text after an insertion-order audit; cached native memories are unchanged, earlier actor outputs remain archived and excluded. Native top-8 entries are not equal records or tokens; A-Mem link expansion can include more entries. Native failures are separate from actor errors. This is not a strict matched-budget superiority comparison.

| system | memory-completed episodes | complete actor episodes | correct / calls | write/read model calls | memory tokens in / out | actor tokens in / out |
|---|---:|---:|---:|---:|---:|---:|
| mem0 | 6/6 | 6/6 | 2/18 | 26 | 227087 / 4393 | 88716 / 72902 |
| amem | 5/6 | 5/6 | 5/15 | 49 | 69820 / 11020 | 165066 / 32322 |
| lightmem | 5/6 | 5/6 | 0/15 | 24 | 22787 / 159 | 69813 / 60322 |

## Original-state representation and evidence limits

| episode | segment transitions | numeric fields | changing fields |
|---|---:|---:|---:|
| travel-s70-test-000 | 2 | 60 | 9 |
| travel-s70-test-001 | 5 | 59 | 12 |
| travel-s71-test-000 | 7 | 57 | 21 |
| travel-s71-test-001 | 5 | 58 | 16 |
| travel-s72-test-000 | 3 | 60 | 13 |
| travel-s72-test-001 | 4 | 57 | 17 |

These short trajectories do not provide enough independent transitions to justify estimating a full field-level SCM. Padding holds or pooling different object identities/regimes does not solve that problem. No new field-SCM recovery claim is made.

Read-gate fitting uses oracle correctness labels for each episode and all 128 actor calls, with no amortized transfer. Gate directions are constrained by the known randomized experiment. Top-2 is a score ranking, including deterministic ties under constant outcomes; it is not a set of identified causal parents. G² asymptotic calibration may be poor in sparse conditional tables. API latency, mask coverage, coincident selections, and all failures remain in artifacts.

A positive diagnostic is insufficient for Yujia's complete requirement: original temporal structure, independent memory utility, reliable correct-output auditing, and a representative real agent setting must connect under one defensible method.
