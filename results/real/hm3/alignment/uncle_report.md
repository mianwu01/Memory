# Official UnCLe extension: frozen-config results

NeurIPS 2025 official implementation, fixed NC8 settings: 1,000 reconstruction + 2,000 joint epochs. Each episode is separately fitted on 512 randomized-read trials. New Travel seeds 60/61/62, first four episodes each. No LLM calls or cross-episode amortization.

The output is a model-based summary dependency score, not a proven causal graph. Fixed top-k curves are not identification of causal parents. AP uses the finite held-out flip reference (64 contexts per gate), not population graph truth.

| score | k | correct / episodes | matched random correct / sets | paired Δ [95% CI] | macro AP |
|---|---:|---:|---:|---|---:|
| uncle_permutation | 2 | 2/12 | 2/36 | +0.111 [-0.083, +0.333] | 0.901 |
| uncle_permutation | 4 | 4/12 | 5/36 | +0.194 [-0.028, +0.417] | 0.901 |
| uncle_permutation | 8 | 11/12 | 16/36 | +0.472 [+0.278, +0.639] | 0.901 |
| uncle_parameter | 2 | 3/12 | 5/36 | +0.111 [-0.194, +0.417] | 0.860 |
| uncle_parameter | 4 | 3/12 | 5/36 | +0.111 [-0.167, +0.390] | 0.860 |
| uncle_parameter | 8 | 10/12 | 14/36 | +0.444 [+0.139, +0.722] | 0.860 |

PCMCI-G² reference on these same inputs: 7/12 correct, mean 3.83 selected records. This is not fixed-k and is not an equal-budget superiority comparison.

Post-hoc executor references: full read 12/12 correct; empty read 0/12.

Raw history averages 20.58 records. Summed per-episode runtime (includes diagnostics/controls) is 1585.6s; concurrent jobs mean this is not elapsed wall time.

Three random controls are averaged within each episode before bootstrap. Intervals condition on the evaluated seeds. Matching uses cl100k_base as a proxy and may have residuals; the JSON records residuals and coincident controls. No best-k or best-method selection replaces the full table.

LCM (2026) was source-checked but not run on this panel: public checkpoints support only 12 variables. TGES (2025) was not run because its stated Gaussian-data guarantees do not apply directly. These exclusions are not negative experimental results.

## Post-hoc equal-record-budget attribution

PCMCI-G² score ranking uses ascending MCI p values, descending test statistic, then stable record order. All methods use the same records and full object context. This matches record count, not exact token count; it is a score selector, not a threshold-identified graph.

| records read | PCMCI-G² ranking | UnCLe permutation | UnCLe parameter |
|---:|---:|---:|---:|
| 2 | 2/12 | 2/12 | 3/12 |
| 4 | 5/12 | 4/12 | 3/12 |
| 8 | 11/12 | 11/12 | 10/12 |

At 8 records, PCMCI-G² ranking and UnCLe permutation are both correct 11/12 with identical success/failure indicators. There is no demonstrated incremental utility of UnCLe over this same-budget statistical ranking. A useful dependence-informed ranking result is not evidence for choosing the neural estimator as the paper's main contribution.

