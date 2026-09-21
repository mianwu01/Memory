# Structure alignment: reproducible results

This report separates discovery controls, parser-free retrieval, and actual LLM calls.
Complete adjacency means no learned type filtering; given instance links remain.

## Fixed-task discovery controls

| domain / history | arm | n | executor EES | records | same complete input |
|---|---|---:|---:|---:|---:|
| shopping32/100 | complete/parser | 192 | 0.974 | 9.7 | 192/192 |
| shopping32/100 | query_only/parser | 192 | 0.161 | 3.4 | 0/192 |
| shopping32/100 | grace_open/parser | 192 | 0.974 | 9.7 | 192/192 |
| shopping32/100 | grace_open_x3/parser | 192 | 0.974 | 9.7 | 192/192 |
| shopping32/100 | permuted_17/matched | 192 | 0.401 | 9.7 | 64/192 |
| shopping32/100 | random_17/matched | 192 | 0.094 | 9.7 | 0/192 |
| shopping32/500 | complete/parser | 192 | 0.979 | 9.7 | 192/192 |
| shopping32/500 | query_only/parser | 192 | 0.167 | 3.4 | 0/192 |
| shopping32/500 | grace_open/parser | 192 | 0.979 | 9.7 | 192/192 |
| shopping32/500 | grace_open_x3/parser | 192 | 0.979 | 9.7 | 192/192 |
| shopping32/500 | permuted_17/matched | 192 | 0.406 | 9.7 | 64/192 |
| shopping32/500 | random_17/matched | 192 | 0.089 | 9.7 | 0/192 |
| shopping32/c100 | complete/parser | 192 | 0.979 | 9.2 | 192/192 |
| shopping32/c100 | query_only/parser | 192 | 0.156 | 3.3 | 0/192 |
| shopping32/c100 | grace_open/parser | 192 | 0.979 | 9.2 | 192/192 |
| shopping32/c100 | grace_open_x3/parser | 192 | 0.979 | 9.2 | 192/192 |
| shopping32/c100 | permuted_17/matched | 192 | 0.401 | 9.2 | 64/192 |
| shopping32/c100 | random_17/matched | 192 | 0.057 | 9.2 | 0/192 |
| shopping32/native | complete/parser | 192 | 0.974 | 6.9 | 192/192 |
| shopping32/native | query_only/parser | 192 | 0.161 | 2.7 | 0/192 |
| shopping32/native | grace_open/parser | 192 | 0.974 | 6.9 | 192/192 |
| shopping32/native | grace_open_x3/parser | 192 | 0.974 | 6.9 | 192/192 |
| shopping32/native | permuted_17/matched | 192 | 0.755 | 6.9 | 93/192 |
| shopping32/native | random_17/matched | 192 | 0.583 | 6.9 | 29/192 |
| travel/100 | complete/parser | 191 | 1.000 | 6.4 | 191/191 |
| travel/100 | query_only/parser | 191 | 0.037 | 0.1 | 0/191 |
| travel/100 | grace_open/parser | 191 | 1.000 | 6.4 | 191/191 |
| travel/100 | grace_open_x3/parser | 191 | 1.000 | 6.4 | 128/191 |
| travel/100 | permuted_17/matched | 191 | 0.838 | 6.4 | 94/191 |
| travel/100 | random_17/matched | 191 | 0.068 | 6.4 | 0/191 |
| travel/500 | complete/parser | 190 | 1.000 | 6.5 | 190/190 |
| travel/500 | query_only/parser | 190 | 0.037 | 0.1 | 0/190 |
| travel/500 | grace_open/parser | 190 | 1.000 | 6.5 | 190/190 |
| travel/500 | grace_open_x3/parser | 190 | 1.000 | 6.5 | 127/190 |
| travel/500 | permuted_17/matched | 190 | 0.811 | 6.5 | 93/190 |
| travel/500 | random_17/matched | 190 | 0.042 | 6.5 | 0/190 |
| travel/c100 | complete/parser | 190 | 1.000 | 6.4 | 190/190 |
| travel/c100 | query_only/parser | 190 | 0.037 | 0.1 | 0/190 |
| travel/c100 | grace_open/parser | 190 | 1.000 | 6.4 | 190/190 |
| travel/c100 | grace_open_x3/parser | 190 | 1.000 | 6.4 | 127/190 |
| travel/c100 | permuted_17/matched | 190 | 0.800 | 6.4 | 94/190 |
| travel/c100 | random_17/matched | 190 | 0.047 | 6.4 | 0/190 |
| travel/native | complete/parser | 192 | 1.000 | 5.6 | 192/192 |
| travel/native | query_only/parser | 192 | 0.052 | 0.1 | 0/192 |
| travel/native | grace_open/parser | 192 | 1.000 | 5.6 | 192/192 |
| travel/native | grace_open_x3/parser | 192 | 1.000 | 5.6 | 128/192 |
| travel/native | permuted_17/matched | 192 | 0.891 | 5.6 | 102/192 |
| travel/native | random_17/matched | 192 | 0.292 | 5.6 | 11/192 |

Matching uses cl100k_base as a token proxy, not the provider's tokenizer. Residuals and all three wrong-graph permutations are in the JSON. Executor comparisons share the full state for value computation; actor comparisons actually restrict visible object context.

## Fresh-seed parser-free retrieval

This rule uses supplied component membership and temporal evidence; it is not a discovery algorithm.

| domain / history | n | key2 | response2 | component2 | component2 − key2 [95% CI] | records key2 → component2 |
|---|---:|---:|---:|---:|---|---|
| shopping32/500 | 192 | 0.958 | 0.870 | 1.000 | +0.042 [+0.016, +0.073] | 37.4 → 30.7 |
| shopping32/c100 | 192 | 1.000 | 0.932 | 1.000 | +0.000 [+0.000, +0.000] | 30.1 → 27.3 |
| shopping32/native | 192 | 0.995 | 0.995 | 0.995 | +0.000 [+0.000, +0.000] | 13.4 → 13.4 |
| travel/500 | 192 | 0.812 | 0.875 | 0.901 | +0.089 [+0.047, +0.130] | 20.1 → 21.4 |
| travel/c100 | 192 | 0.880 | 0.896 | 0.922 | +0.042 [+0.010, +0.073] | 18.5 → 19.9 |
| travel/native | 192 | 1.000 | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 11.6 → 11.9 |

Intervals condition on the three frozen seeds; they do not estimate uncertainty over arbitrary new environments. Component preference can benefit from HM3's disconnected foreign-component augmentation.

## LLM diagnostic (v1, verbose, 16k output cap)

Exact duplicate inputs within an episode share one call. Every pair uses the intersection of completed episodes, never mismatched denominators.

| domain / history | arm | completed | EES | first-call truncations | Δ vs no-type-filter [95% CI] |
|---|---|---:|---:|---:|---|
| travel/500 | bm25_16 | 23 | 0.130 | 5 | -0.348 [-0.522, -0.174], n=23 |
| travel/500 | complete/key2 | 23 | 0.217 | 3 | -0.261 [-0.478, -0.043], n=23 |
| travel/500 | complete/parser | 23 | 0.478 | 0 | +0.000 [+0.000, +0.000], n=23 |
| travel/500 | component2 | 23 | 0.304 | 0 | -0.174 [-0.391, +0.043], n=23 |
| travel/500 | full | 23 | 0.304 | 4 | -0.174 [-0.391, +0.043], n=23 |
| travel/500 | grace_open_x3/parser | 23 | 0.348 | 0 | -0.130 [-0.261, -0.043], n=23 |
| travel/500 | permuted_17/matched | 23 | 0.304 | 1 | -0.174 [-0.304, -0.043], n=23 |
| travel/500 | permuted_29/matched | 23 | 0.391 | 1 | -0.087 [-0.304, +0.087], n=23 |
| travel/500 | permuted_43/matched | 23 | 0.348 | 0 | -0.130 [-0.261, -0.043], n=23 |
| travel/500 | query_only/parser | 23 | 0.043 | 0 | -0.435 [-0.609, -0.261], n=23 |
| travel/500 | random_17/matched | 23 | 0.174 | 4 | -0.304 [-0.478, -0.130], n=23 |
| travel/500 | recency_16 | 23 | 0.261 | 0 | -0.217 [-0.478, +0.043], n=23 |
| travel/c100 | bm25_16 | 23 | 0.261 | 2 | -0.130 [-0.304, +0.043], n=23 |
| travel/c100 | complete/key2 | 23 | 0.348 | 0 | -0.043 [-0.261, +0.174], n=23 |
| travel/c100 | complete/parser | 23 | 0.391 | 1 | +0.000 [+0.000, +0.000], n=23 |
| travel/c100 | component2 | 23 | 0.565 | 0 | +0.174 [-0.043, +0.391], n=23 |
| travel/c100 | full | 23 | 0.217 | 4 | -0.174 [-0.391, +0.043], n=23 |
| travel/c100 | grace_open_x3/parser | 23 | 0.304 | 1 | -0.087 [-0.217, +0.000], n=23 |
| travel/c100 | permuted_17/matched | 23 | 0.304 | 1 | -0.087 [-0.217, +0.043], n=23 |
| travel/c100 | permuted_29/matched | 23 | 0.391 | 1 | +0.000 [-0.174, +0.174], n=23 |
| travel/c100 | permuted_43/matched | 23 | 0.304 | 1 | -0.087 [-0.217, +0.000], n=23 |
| travel/c100 | query_only/parser | 23 | 0.000 | 0 | -0.391 [-0.565, -0.217], n=23 |
| travel/c100 | random_17/matched | 23 | 0.435 | 0 | +0.043 [-0.217, +0.304], n=23 |
| travel/c100 | recency_16 | 23 | 0.304 | 0 | -0.087 [-0.261, +0.043], n=23 |

Recorded accounting cost: $15.9670. Unique completed inputs: 430. Infrastructure failures: 0.

## Established discovery on randomized read gates: candidate redesign

12 fresh native Travel episodes (seeds 50/51/52), independently fitted per episode; fixed deterministic executor only. 512 randomized training masks and 64 independent flip-effect contexts per gate. The lag is trial input → next-row outcome, not the original agent's evolving write timeline. No claim of amortized deployment, LLM transfer, or latent-state recovery.

| estimator | selected-read correct | mean selected records | matched random correct | paired Δ vs per-episode random mean [95% CI] | empirical flip P / R (macro) |
|---|---:|---:|---:|---|---|
| pcmci_parcorr | 7/12 | 3.42 | 9/36 | +0.333 [+0.111, +0.528] | 0.967 / 0.757 |
| grace_pcmci_g2 | 11/12 | 3.83 | 9/36 | +0.667 [+0.500, +0.806] | 0.958 / 0.792 |

Random controls are averaged within each episode: 36 sets are NOT 36 independent episodes. Matching preserves record count and object context; token lengths are approximate cl100k_base matches. Coincident learned/random sets remain in the analysis. Finite flip sensitivity is not a complete causal ground truth; omitted rare dependencies can still matter.
Mean raw history: 18.25 records. Total unique executor contexts (training + diagnostics + controls): 16622; summed episode runtime: 210.1s (excluding the post-hoc skeleton audit).

- pcmci_parcorr: 30/36 exact proxy-token matches; max absolute residual 3 tokens; 9 coincident controls. Failed episodes: travel-s50-test-003, travel-s51-test-000, travel-s51-test-001, travel-s51-test-002, travel-s52-test-003. Spurious lagged edges into randomized gates across fits: 24.
- grace_pcmci_g2: 31/36 exact proxy-token matches; max absolute residual 11 tokens; 8 coincident controls. Failed episodes: travel-s50-test-003. Spurious lagged edges into randomized gates across fits: 91.

Only incoming outcome edges are used by the selector. The other inferred edges are not hidden from the artifacts; the spurious gate-target edges explicitly rule out claiming accurate full-graph recovery.

Post-hoc attribution check (same inputs/settings; no GRACE refit): PCMCI-G² alone is correct 11/12, and returns exactly the same outcome-parent sets as GRACE on 12/12 episodes. Full read: 12/12; empty read: 0/12. **There is no demonstrated incremental benefit of the GRACE refinement.** The ParCorr vs GRACE+G² comparison also changes the CI test and alpha, so it is not a neural-refinement ablation.

## Correct-output source audit: not established

- source_reliance_demo: Failed to establish LLM source dependence: baseline and all three interventions were correct 3/3.
- actor_source_audit: Failed independent validation: full context was correct 0/3, subset 2/3, and blocked source 1/3. No stable normal-correct-output audit demonstrated.

Source authorization was externally supplied in a controlled scenario. Neither experiment supports hidden-thought recovery or deception detection. No replacement case was sought after the frozen independent validation failed.

## Recorded cost and remaining evidence gaps

Accounting uses legacy configured token rates, not provider billing. The interrupted interface pilot is preserved separately; in-flight unlogged calls and connectivity checks may add cost.

- actor_source_audit: 39 recorded rows, $0.5105.
- actor_v1_closed: 430 recorded rows, $15.9670.
- actor_v1_pilot: 301 recorded rows, $10.6868.
- source_reliance_demo: 12 recorded rows, $0.1829.

The new actor diagnostic covers BM25, recency, query-only, complete/discovered type filters and matched controls, not fresh Mem0/A-Mem/LightMem runs. Those named-system comparisons, a stable LLM auditing demonstration, and advisor agreement on the read-gate estimand remain open. These artifacts do not establish a submission-ready causal-memory claim.

