"""Hidden Mechanism v3 (HM3): learned hidden mechanism -> causal memory
maintenance -> executable downstream repair.

Package layout
  core.py        object/state/transaction engine, receipts, episodes, metrics
  dgp_travel.py  time/resource/provider-policy/bundle network
  dgp_shopping.py compatibility factor graph, promo hypergraph, cart re-optimisation
  dgp_search.py  non-monotone evidence aggregation under trust/window/dedup gates
  dgp_formal.py  versioned scope binding, shadowing, dynamic proof DAG
  generate.py    episode generator with witness coverage enforced by construction
  learners.py    every non-oracle baseline sharing the same training data
  gate.py        zero-API development gate (8 checks)
  run_det.py     deterministic replication over seeds
  llm.py         DeepSeek full-runtime arm (selection x serialization)
"""
