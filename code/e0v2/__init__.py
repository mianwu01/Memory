"""E0 v2: a small synthetic memory system with regime-gated edges, and the
estimators that try to recover both the edge and the regime that opens it.

Modules
  scm      generator + ground-truth gate table  a_ijl * g_ijl(u)
  linear   ridge/OLS arms: pooled, additive-u, interaction-u, per-regime
  gated    Hard-Concrete L0 gate family: pooled, per-regime, Regime-GRACE
  external PCMCI+ (tigramite) and the official causalts GRACE, when importable
  metrics  edge F1, edge x regime F1, gate-pattern match, coefficient error
  run      experiment driver (e0a / e0b / e0c / control)
  report   aggregate JSON -> markdown tables and the gate heatmap
"""
