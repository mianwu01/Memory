# Experiments, plan, and paper: status on 2026-09-20 (five days to the 9/25 deadline)

One page for the user and for Yujia. Every number is traceable: the results package
(`docs/hm3-results-package-2026-09-19.md`) gives the file behind each row; the bridge plan
(`docs/bridge-plan-2026-09-19.md`) gives the day-by-day log and the two-session rules; the formulation mapping
(`docs/hm3-formulation-mapping-2026-09-20.md`) gives the sample / variable / time-step / regime definitions.

## 1. The paper in one paragraph

An agent's memory should be organised by the temporal dependency structure of how past information reaches future
decisions. We formulate memory as a gated temporal causal process (write, hold, read regimes on a stationary graph)
and show that the causal frontier is the unique minimal set to retain. We ask three questions. Q1, can the structure be
recovered? In a controlled process with known ground truth, conditioning on the access regime recovers gated memory
edges that pooled and additive estimators miss; on the event logs of our agent benchmark, an off-the-shelf pooled
temporal estimator recovers the propagation skeleton from the logs alone, and the encoding used by earlier
public-benchmark attempts is the reason those attempts returned self-loops. Q2, is the structure useful forward? On a
benchmark with hidden per-entity mechanisms and non-idempotent repairs, and on the same mechanism transplanted onto
MemoryArena's real flights, hotels and restaurants with memory routed through MemoryArena's own memory-system
interface, structure-guided reading costs one to three percent of a full-context actor's tokens at every history
length, keeps the required records as histories grow to 500 records, and leads full context and every retrieval or
memory-system baseline once the history holds a hundred records or more. Q3, is the same structure useful backward?
Walking the same fitted graph backward from an anomalous action locates the corrupted record in the top three in
0.91 to 1.00 of incidents, and replacing that record restores the action while random, similar, and recent records do
not. Boundaries: at native length full context is as good or better; in the fully connected Shopping domain the
accuracy advantage is absent (cost remains); provenance fails in Shopping; the actor's own execution bounds the absolute
levels; no causal-discovery algorithm is contributed and no identification from the observational logs of the public
benchmarks we tried is claimed.

## 2. What is done (with the headline numbers)

| # | Experiment | Setting | Headline | Status |
|---|---|---|---|---|
| Q1a | E0 v2, controlled SCM | n = 32 variables, T = 10,000, 5 seeds × 3 noise levels | regime-conditioned estimation recovers gated read edges 5/5 seeds at every noise; pooled / additive / PCMCI+ / pooled GRACE fail; per-regime OLS suffices (estimator is not the contribution) | complete, frozen |
| Q1b | TCD on HM3 event logs | one binary variable per object type, interventions exogenous, pooled lagged ridge + FDR; PCMCI+ as second estimator | recall 1.0 of the interventional skeleton on 6/6 seeds in Travel and Shopping32 (precision 0.2–0.5); PCMCI+ recall 0.4; the MemoryArena-style "activated in round s" encoding degenerates to self-loops on the same logs | complete (9/19) |
| Q1c | Public-benchmark negatives | MemoryArena Travel (PCMCI+/GRACE on slot activations), MINJA (regime-conditioned on exposure) | 12 edges, 10 self-loops; 0 edges in 10/10 runs | complete (earlier) |
| Q2a | HM3 deterministic ladder | Travel and Shopping32, dev and test seeds, native / 50 / 100 / 500 records, same executor, only the read set changes | structure-guided reads: EES 1.00 (Travel) / 0.97–0.99 (Shopping) at every length with 12 / 21 reads; observational-graph selection identical; BM25-16 0.90 → 0.04 (Travel), 0.98 → 0.05 (Shopping); recency-16 0.94 → 0.32; re-wired skeletons 0.04–0.56; parser-free selection 0.80–0.89 / 0.95–0.97 at 500 records | complete |
| Q2b | HM3 learned graph vs learners | four domains, fresh test seeds | learned graph 0.88 / 0.76 / 1.00 / 0.72 (Travel / Shopping / Search / Formal); best lookup 0.30 / 0.46 / 0.41 / 0.14; program learner 0.67 / 0.78 / 0.99 / 0.89 | complete (earlier) |
| Q2c | Real actor, synthetic ids | DeepSeek-V4-Flash, 16k output cap, verbose serialization both sides, two prompts, 64 episodes | Travel, terminating prompt: conflicting witnesses +0.19 [+0.06, +0.32], 500 records +0.17 [+0.03, +0.32], 100 records +0.08 (n.s.), native 0.48 vs 0.48; ledger-first prompt +0.22 / +0.44 / +0.18 / −0.23; Shopping: parity at 100, −0.19 at 500 (cost only); tokens 1–3 % of full | complete (9/20; earlier 4,096-cap rows are appendix-only) |
| Q2d | Substrate port | HM3 Travel on MemoryArena's real entities; memory through MemoryArena's `add_chunk` / `wrap_user_prompt` classes unmodified (BM25 top-3 and top-16, long-context, A-Mem k = 5); 64 episodes, both prompts | ours − long-context (v1 / v2): native +0.05 / +0.03 (n.s.); 100 +0.31 / +0.30; conflicting +0.12 / +0.27; 500 +0.20 / +0.48; ours − BM25-16 +0.14 to +0.55; ours 3.8–4.8k input tokens vs 7k–269k; default BM25 starved (0.02–0.08) | complete |
| Q2e | Recognised memory systems as selectors | Mem0 raw (OSS, verbatim records, embedding search), A-Mem (own note construction), both at 16k | Travel native: Mem0 0.27, A-Mem 0.34 (≈ our graph arms, 0.30 below full); Travel 100 records: Mem0 0.05, A-Mem 0.02 (required-record recall falls to 0.39 / cap hits); Shopping 100: Mem0 0.30, A-Mem 0.41 (≈ graph). Mem0's default extraction mode keeps 0–40 % of records: reported as a negative | complete |
| Q2f | Ablations | selector frozen on native data; serialization; whole-segment context; re-wired skeletons; prompt rule; single-distractor decomposition; stronger backbone; parser-free selection | gain survives freezing and serialization changes; disappears under re-wiring or retrieval; parser-free selection matches at ≤ 100 records and lags at 500; decomposition and prompt-rule rows are 4,096-cap runs (appendix) | complete |
| Q3a | Backward provenance, deterministic | one required witness corrupted per episode; auditor sees anomalous objects only; Travel test seeds 30/31/32, native and 500 records | top-3 hit 0.98–1.00 (native), 0.94–0.98 (500); clean replacement restores at the same rates; random-3 / similar / recent 0.00–0.05; BM25-on-anomaly 0.14–0.60; same numbers with the observational (logs-only) graph | complete |
| Q3b | Backward provenance, actor level | 52 incidents, graph_seg/verbose, 16k, both prompts | v1: top-3 replaced − corrupted +0.13 [+0.00, +0.27], − random-3 +0.17 [+0.02, +0.31]; v2: +0.35 [+0.19, +0.50], +0.29 [+0.12, +0.46]; top-3 − clean −0.02 under both | complete (16k rerun 9/20 replaces the 4,096-cap row) |
| Q3c | Case figure | travel-s30-test-000 | rendered: history, dependency path with hidden keys, trace ranking, clean replacement | complete (`results/real/hm3/provenance/figures/`) |
| S | Setting mapping | sample / variable / time step / regime / carrier / frontier for HM3; variable-set consistency across episodes, conditions, regimes, domains | written | complete (`docs/hm3-formulation-mapping-2026-09-20.md`) |

## 3. Claims withdrawn or narrowed this week, so they do not come back

- The actor-level "+0.28 / +0.24 and robust to conflicting evidence" numbers were an artifact of a 4,096-token output
  cap (truncated first attempt, empty repair scored 0) and of a prompt whose ledger step never terminates over 100
  records. The same-serialization 16k panels replace them; the conflict effect survives at about two thirds of its
  size and holds under both prompts.
- The compact, witness-only graph context understated the structure by 0.1–0.3; the paper compares verbose against
  verbose with the witness's segment kept.
- Shopping supports the cost claim only; the accuracy advantage is Travel-specific.
- The native-length crossover in favour of full context is prompt-dependent on synthetic ids (v2 −0.23, v1 parity) and
  absent on real entities (parity).
- "Robustness to conflicting evidence" is stated for the terminating prompt at +0.19 in Travel, with the ledger-first
  prompt at +0.22; the single-distractor decomposition and the "latest record wins" prompt control are cap-limited runs
  and move to the appendix.
- Regime recovery is empirical identification in a controlled process; no theorem beyond the frontier lemma.

## 3b. Priority change after the 9/20 meeting with Yujia

Her verdict: the pipeline is complete; the word "causal" is defensible only if the structure comes from an established
causal discovery algorithm on the same logs; otherwise the agent-task structure is "temporal dependency structure"
and the causal claim stays with the controlled simulation. The highest priority is therefore one experiment: run
established temporal causal discovery (PCMCI+ with partial-correlation and G-squared tests; GRACE with a PCMCI+
skeleton and with an open skeleton at three sparsity levels) on the same event logs, compare the recovered graphs with
the interventional skeleton and with our regression estimator (edge precision / recall, seed stability), and plug each
recovered graph into the existing forward selection and backward provenance. First findings (Travel seed 0): every
established method recovers the head of the chain (flight → transfer → stay); conditional-independence tests attribute
the tail (dinner, activity, bundle) to the flight at lag 3 and prune the mediators, because the intermediate writes
are deterministic (the faithfulness failure E0 documents for the hold regime); GRACE with an open skeleton ranks the
five true edges first but its threshold under-sparsifies on binary indicators. A lag-aware unrolling of a pruned
graph still reaches every affected object (29/30 dev episodes), so the pruned graphs are usable for selection. The
six-seed sweeps are complete and stable. Downstream: on Travel, every recovered graph except the over-penalised GRACE
drives selection at the reference level (EES 1.000, 10–12 reads at every length) and the GRACE, G-squared and regression
graphs give the reference provenance numbers (top-3 0.91–1.00, restore equal, controls 0); on Shopping the CI skeletons
are too sparse to select with (0.10–0.44) while GRACE with an open skeleton matches the reference. So the structure the
pipeline consumes is obtainable from the logs by the reference GRACE implementation; the mediation caveat is stated.

## 4. Experiment plan to 9/25

| Day | Item | Owner | Depends on |
|---|---|---|---|
| 9/20 (tonight) | A-Mem column for the substrate table at 100 records (running, 36/64 under v1; v2 reuses the cached memory builds) | A | nothing |
| done 9/20 | **Causal-discovery bridge:** GRACE / PCMCI+ sweeps (6 seeds × 2 domains), edge P/R, selection ladders and provenance with each recovered graph; table in the package; figure for Yujia still to draw | A | — |
| done 9/20 | Actor-level provenance rerun at 16k with graph_seg/verbose (52 incidents × 4 arms × 2 prompts; replaces the 4,096-cap row) | A | — |
| 9/21 | Cost figure (input / output tokens vs history length, synthetic and substrate) and EES-vs-length figure with both prompts | A | nothing |
| done 9/20 | Substrate provenance on `travel_arena` (deterministic, seeds 30/31/32): top-3 0.88–0.96, restore equal, controls ≤ 0.05 | A | — |
| 9/22 | Freeze the main tables; results package final; every appendix row labelled with its cap and prompt | A | above |
| 9/22 | Paper outline → draft of §3 (method) and §4 (experiments) with the frozen tables | A | frozen tables |
| 9/23 | §1–§2 (intro, setting) using the formulation mapping; abstract per the four sentences below | A | draft §3–§4 |
| 9/24 | Yujia pass; fix what she flags; camera copy of figures | A + Yujia | draft |
| 9/25 | Submit | user | everything |

Not planned (and why): more HM3 domains (Yujia 8/21: one or two representative setups); more synthetic variants
(Yujia 9/04: simulation is sufficient); LightMem (its extracted facts do not map back to record ids); a port to
MemoryArena's original planning task (no propagation dynamics there, which is why HM3 exists); tuning PCMCI+.

Session B (the collaborator's machine, Python 3.12, cannot run the memory-system arms): nothing assigned; all its
tasks are complete and merged. If it has capacity, the deterministic substrate provenance run on 9/21 is CPU-only and
could go there (command in the bridge plan once written).

## 5. Paper structure and which evidence carries each section

| Section | Content | Evidence |
|---|---|---|
| Abstract | four sentences: the insight (memory as gated temporal dependence; frontier); recovery (controlled process; logs of the agent benchmark; failure of the round-activation encoding); forward utility (cost at every length, lead from 100 records, on synthetic ids and on real entities through the benchmark's memory interface); backward utility (intervention-validated provenance) with the boundaries | §2 rows Q1a–b, Q2c–d, Q3a |
| 1 Introduction | long-lived agents must read selectively and trace memory-induced errors; existing memory systems store and retrieve content and cannot bound reads or attribute errors; thesis; contributions (formulation and frontier lemma; recovery of the skeleton from logs and the encoding that breaks it; benchmark with hidden mechanisms and controlled history growth; forward selection with cost and long-history lead, including the substrate port; intervention-validated provenance; boundaries) | — |
| 2 Setting and formulation | temporal SCM with memory carrier; access regimes; frontier lemma; trustworthy memory; identification statement (empirical); the mapping of sample / variable / time step / regime / carrier / frontier onto the benchmark; where the instance departs from the formulation | `causal_memory_formulation.tex`, formulation mapping |
| 3 Method | regime-conditioned estimation (E0); structure from logs (pooled lagged regression, PCMCI+); interventional skeleton and gated local decisions (HM3); forward selection (graph_seg) and the parser-free variant; backward provenance; controls that isolate the structure | `code/regime_grace.py`, `code/hm3/{tcd_logs,learners,keysel,provenance}.py` |
| 4.1 Controlled identification | E0 v2 table, gate heat-map | Q1a |
| 4.2 The benchmark and deterministic panel | four-domain table; history-length ladder; observational-graph selection; parser-free selection | Q2a–b, Q1b |
| 4.3 Real actor | same-serialization 16k panel, both prompts, Travel and Shopping; cost; boundaries | Q2c |
| 4.4 Substrate | real entities and the benchmark's memory systems | Q2d, Q2e |
| 4.5 Provenance | deterministic table; observational-graph row; actor-level row; case figure | Q3a–c |
| 4.6 Ablations and negatives | frozen selector, serialization, segment context, re-wired, prompt, parser-free, backbone; MINJA and Travel implicit-v1 negatives; Shopping boundary | Q2f, Q1c |
| 5 Related work | agent memory systems (retrieval, summaries, A-Mem, Mem0, LightMem); temporal causal discovery; causal representation learning with auxiliary variables; memory poisoning and provenance | — |
| 6 Limitations | generator-based mechanism; recency assumption on the current world's witnesses; domain dependence; actor call-to-call variance; selection and confounding stated, untested | — |

## 6. Open decisions

1. Framing for Yujia (unchanged from the bridge plan §4): TCD as the method (A) or interventional structure learning
   as the method (B); whether HM3 counts as a memory task or a simulation in her three-part scheme; and whether the
   substrate port satisfies her "inject into an existing repo" request. Recommendation: (A) with the honest sentence
   that the gates come from the interventional fit, since the logs-only skeleton recovery now exists.
2. Abstract wording: split recovery from utility; replace "latent temporal process" with "the temporal process
   underlying the trajectory"; drop the write-policy clause; name E0's and HM3's regimes separately.
3. Commit of the working tree (all of this week's code, results and documents are uncommitted on
   `claude/hm3-handoff-2026-09-18`).

Deliverable for Yujia (9/20 verdict): `docs/yujia-causal-bridge-2026-09-20.md` (one diagram, three number groups).

Update 9/20 late: figures rendered (`results/real/hm3/figures/scaling_travel.pdf`, `scaling_shopping32.pdf`,
`substrate_travel_arena.pdf`; script `code/hm3/figures.py`); experiments-section draft written
(`docs/paper-draft-experiments-2026-09-20.md`); GRACE gate-ranking AP added to the recovery table (Travel 0.47–0.77,
Shopping 0.70–1.00; the chain head ranks 1–2, the stay → tail edges rank 5–21 behind the lag-2/3 shortcuts). The
earlier sentence that GRACE ranks all five true edges first was wrong and is corrected everywhere.

**Superseded as the entry point (2026-09-21):** the whole picture, including the method redesign (read interventions) and the new E1–E3 rows, is in `docs/full-status-method-experiments-paper-2026-09-21.md`.
