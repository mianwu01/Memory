# Handoff — causal-memory project, transferring workspace (2026-08-27)

Read this first. `docs/session-status-2026-08-27.md` has the blow-by-blow;
this file is what you need to pick the work up somewhere else.

---

## 1. What the project claims, and which claims are actually backed

| Claim | Status | Evidence |
|---|---|---|
| Regime-conditioned discovery recovers a **gated** edge that standard moves miss | ✅ backed | `results/regime_grace_e0.json` — blind 0/2, regime-as-a-node 0/2, ours **2/2** at every σ |
| A **discovered** graph beats a hand-written one for memory selection | ✅ backed | `results/real/p2_benchmark_v2.csv` — learned 1.000/1.000 @1558 tok vs hand patch 0.993/0.973 @1896 |
| The plugin integrates into a real agent-memory platform | ✅ backed | runtime registration, MemoryArena tree byte-identical |
| Detection → **gating** the driven actions is actionable | ✅ backed | `results/real/causal_gate.json` — 100% prevented, regime halves collateral 35.6%→13.7% |
| We beat MemAudit **at detection** | ❌ **false, do not claim** | their CMIS gets AUC 0.962 here; we are not better at ranking records |
| Our advantage over MemAudit is **structural** (temporal ancestry + dual use) | ⚠️ argued, not yet measured | needs a task only ancestry can do; see §4 |
| The plugin improves **task success** (PS/SPS/SR) | ❌ **no data** | zero episodes ever completed end-to-end |
| MINJA's memory-hijack reproduces, and we recover its hidden driver | ❌ **unresolved** | first runs negative; the reproduction bug is fixed but the rerun never finished |

**The one-line version for Yujia:** the memory/efficiency branch (his Part 2) is
done and positive; the method itself (regime conditioning) is now implemented and
validated on simulation; the trustworthiness branch (Part 3) has a working
gate and a working baseline comparison, but the *hidden-driver recovery* result
is still open because the attack has not yet been made to land on a real LLM.

---

## 2. Environment — reproduce this before anything else

```bash
export CUDA_VISIBLE_DEVICES=""            # MANDATORY, see §5
export TMPDIR=$PWD/.tmp                   # /tmp was 100% full on the old node
export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897
export OPENAI_API_KEY=<the DeepSeek key in ../deepseek_apikey.md>
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export HF_HOME=<a cpfs path with room>
pip install socksio                       # httpx needs it; ALL_PROXY is socks5
```

Gotchas that cost hours here:
- **`key.txt` is dead.** OpenAI, OpenRouter and DeepSeek all reject it. The live
  key is in `deepseek_apikey.md`.
- **`deepseek-v4-*` are reasoning models.** Too small a `max_tokens` and they burn
  the whole budget on hidden reasoning and return **empty content** with
  `finish_reason='length'` — which looks exactly like a parse failure. Use ≥6000.
- **curl works where Python hangs**: curl speaks socks natively, httpx needs `socksio`.
- MemoryArena's env server binds **8001** even though its configs say 8005. Use
  **8123** for the memory server (8000 was taken by another tenant).
- `benchmarks/MemoryArena` has **no LICENSE**. Do not fork, patch or redistribute
  it. We register into it at runtime; keep `git -C benchmarks/MemoryArena status
  --porcelain` empty (the downloaded flights CSV is the only permitted extra).
- travel needs `clean_Flights_2022.csv` (305 MB, Google Drive link in
  `benchmarks/MemoryArena/setup_travel.md`) at
  `env/env_systems/travel_planner_env/database/flights/`.

---

## 3. What each file does

**Method**
- `code/regime_grace.py` — **the method**. Multiplicative-gate estimator: fits
  coefficients per regime, reports edges significant in any regime, flags those
  whose coefficient moves with the regime. `evaluate_on_e0()` reproduces the
  headline simulation table. Run: `python3 code/regime_grace.py`.
- `code/travel_grace_discovery.py` — runs GRACE over travel episodes, exports a
  type-level slot graph. Handles multi-trial pooling by unfolding windows **within**
  each episode (never across boundaries).

**P2 — memory / efficiency**
- `code/arena_causal_memory.py` — the plugin. Graph modes: `rule` (query names),
  `learned` (discovered graph), `+ include_scaffold`, `+ ablate_graph`.
- `code/arena_serve_causal.py` — starts MemoryArena's server with our factories
  registered at runtime. Stubs absent optional SDKs; pins CUDA off.
- `code/arena_p2_benchmark.py` — answerability-at-cost over real episodes, no LLM.
- `code/arena_e2e_score.py` — **PS/SPS/SR via MemoryArena's own evaluator**. Refuses
  to rank arms that completed different episode sets.
- `code/p2_case_study.py` — prints one round's context per system, side by side.

**P3 — trustworthiness**
- `code/minja_causal_audit.py` — runs the MINJA-QA trajectory, records X_t,
  appends each round to disk as it goes.
- `code/minja_causal_analysis.py` — the three audits. **Refuses to declare driver
  recovery without the note-free ∧ poison-retrieved cell.**
- `code/memaudit_baseline.py` — MemAudit reimplementation (CMIS + consistency graph).
- `code/causal_gate.py` — the closed loop: detect → withhold → replay-evaluate.
- `code/p3_case_study.py` — one attack in the model's own words.

**Reporting**
- `code/make_report.py` → `artifacts/experiments.html`. Regenerate after any new result.

---

## 4. Priority queue for the next workspace

1. **Finish the P3 rerun.** The reproduction bug is fixed but unverified.
   ```bash
   python3 -u code/minja_causal_audit.py --backend openai --model deepseek-v4-flash \
     --file_name nutrition_test --num_templates 6 --num_pre 8 --num_test 12 \
     --num_benign 25 --extra_benign_subjects 0 --inject_attempts 3 --seed 0 \
     --out results/real/minja_trace_v2.csv --verbose
   python3 code/minja_causal_analysis.py --trace results/real/minja_trace_v2.csv
   ```
   **Pre-registered criterion:** the `DECISIVE note-free rounds with poison
   retrieved` cell must exceed 0.2. Below that it is still a negative result and
   the carrier should change — do not reinterpret after the fact.
2. **Get PS/SPS/SR.** Start both servers, run `run_travel.py` per arm to a common
   episode set, then `python3 code/arena_e2e_score.py`. Budget ~20 min/episode/arm;
   two arms (`causal-learned`, `long_context`) is enough for a first result.
3. **Run the pure-discovery arm** (`causal-learned-pure`, already registered). This
   is the honest version of the P2 claim — no query-name oracle. Expect a larger
   context; the question is how much answerability survives.
4. **Make the structural claim measurable.** We assert MemAudit cannot name the
   write round. Build the task that shows it: score methods on *which round wrote
   the driver*, where a per-record detector has no answer to give.
5. Optional: the `hint` feedback loop (`travel_causal-learned-hint.json`, M2) —
   note it changes the data-generating process, so it is its own regime.

---

## 5. Why the last session was killed, and how not to repeat it

The node flagged the session for GPU use. The only trace anywhere is the `pynvml`
warning that `import torch` emits, and torch reported CUDA unavailable, so no
kernel ran — but **importing torch probes the driver over NVML**, which is enough
for a watchdog. `arena_serve_causal.py` was the one launcher that never pinned
`CUDA_VISIBLE_DEVICES`, and it pulls torch in transitively through MemoryArena's
`memory_systems`. All entry points now set it before any import. **Keep that.**

Also: `minja_causal_audit.py` used to write its CSV only at the end, so the kill
destroyed 35 rounds of real-LLM data. It now appends per round. Prefer that
pattern for anything long-running.

---

## 6. Standing honesty constraints (these have already caught real errors)

- Anything that **beats an information upper bound is a bug** until proven
  otherwise. A `json.dumps` `ensure_ascii` default once made our system look
  better than full-history; it was an encoding artifact.
- `poison_retr` is **collinear with** `note_present` in this environment. Pooled
  and trigger-conditioned estimates both manufacture a convincing gated edge that
  is not there. Only the note-free cell discriminates.
- travel's dependencies are **named in the query**, so discovery is not *necessary*
  for recall here. The P2 win is slot-level selection plus the learned scaffold;
  necessity claims belong to the simulation track.
- The dilution sweep (`minja_dilution_sweep.py`) has only ever run against the
  offline stand-in. It is a synthetic diagnostic, not a measurement.
