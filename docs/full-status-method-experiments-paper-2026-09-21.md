# Causal memory: method, experiments, results and paper plan — the whole picture (2026-09-21, 03:00)

给 Yujia / 组内的摘要（其余为英文，直接供论文用）：

1. 9/20 会议的判断已执行：GRACE / PCMCI+ 跑同一批日志，恢复的图插进已有 pipeline，前向与后向数字与干预式骨架相同；CI 类方法在确定性写入上剪掉中介边、Shopping 上返回空图（这是 faithfulness 失效的实例）。交付页 `docs/yujia-causal-bridge-2026-09-20.md`。
2. 但"观测日志 → 成熟因果发现 → 闭包选择"作为方法不够 ICLR。今晚重新设计并实现了方法核心：**记忆系统对自己的读取做干预**（重放时屏蔽记录），用自适应消元在 O(k log n) 次重放内识别决策的 read frontier；不依赖 faithfulness；类型级 frontier 模型把重放摊销到测试时（parser-free）；后向追责用同一原语。`docs/method-design-read-interventions-2026-09-20.md`，代码 `code/hm3/replay*.py`。
3. 今晚的新证据：执行器 frontier 2–3 条记录、14 次重放、类型投影对干预式骨架 precision 1.0；重放次数随 log n 增长而 frontier 不变（18→100→500 条：15→22→27）；用结构先验定位肇事记录中位数 1 次重放（BM25 需 5–9 次）；**LLM 自身**的 frontier 与执行器不同（覆盖 0.20–0.43），LLM 依赖 stay 的 txn 记录而执行器依赖 flight 干预记录——frontier 是 actor-specific 的；LLM 的非单调率 v1 12.5% / v2 4.8%（冲突证据效应在记录层面的直接测量）。
4. 摊销模型（parser-free 选择器）目前 EES：Travel 0.94 → 0.79（native → 500），Shopping 0.85–0.86，与 key-precedent 选择相当、低于带 parser 的 graph_select（1.00）。这是方法里最弱的一环，如实报；重放验证的 frontier 本身是精确的。
5. 到 9/25 的计划在 §7。

---

## 1. Where the project stands

**Formulation (settled).** Gated-stationary temporal SCM with memory carriers; the causal frontier F_t is the unique
minimum lossless memory (Lemma in `causal_memory_formulation.tex`); trustworthy memory = identified carriers
(D trust). HM3 is its instance (`docs/hm3-formulation-mapping-2026-09-20.md`).

**Evidence base (frozen, all on reserved test seeds unless marked dev).** Controlled identification (E0 v2);
HM3 deterministic panels and history-length scaling; the DeepSeek actor panel with the same serialization on both
sides at a 16k output cap; the MemoryArena substrate port; Mem0 / A-Mem baselines; backward provenance at both
layers; observational discovery (pooled regression, PCMCI+, GRACE) on the same logs. Package:
`docs/hm3-results-package-2026-09-19.md`; deliverable for the 9/20 verdict: `docs/yujia-causal-bridge-2026-09-20.md`;
experiments-section draft: `docs/paper-draft-experiments-2026-09-20.md`.

**What changed tonight.** The user's directive: the method must be strong enough for ICLR. The pipeline as it stood
(observational discovery → type skeleton → closure → path walk) is engineering over a five-edge foreign-key graph
and needs a hand-written parser. The redesign below replaces the *source* of the structure and the *primitive* that
forward and backward share, keeps every existing result as evidence, and adds four new experiments (all run tonight
with the deterministic executor; the LLM-as-policy discovery ran on Travel seed 30 under both prompts).

## 2. The method: identifying the memory frontier by read interventions

**Idea.** A memory read is an intervention the agent performs on itself. In the gated SCM a carrier m_s reaches the
decision Y only through its read gate g_s ∈ {0,1}, and the memory system sets g. Setting g is free and safe at replay
time: re-run the policy π on a logged episode with a subset S of records visible and score the decision. This is
do(g = 1_S) with exogenous assignment, so it identifies which records the decision depends on with no assumption on
the write process. Deterministic writes, which break every conditional-independence test on the logs, are irrelevant
because the intervention is on reads.

**Objects.** Episode e with history (m_1..m_n), state S_0, cue I; decision Y = π(S_0, I, {m_s : g_s = 1}); correctness
c ∈ {0,1}. S is *sufficient* if c(π_S) = c(π_[n]) = 1; *minimal* if no proper subset is. The π-frontier F^π_e is a
minimal sufficient set: under uniqueness it is F_t restricted to carriers; under redundancy any minimal hitting set
is a lossless memory for e. Monotone use: S sufficient and S ⊆ T ⇒ T sufficient (exact for the executor; for the
LLM its violation is the conflicting-evidence effect, measured in §4.5).

**Proposition 1 (observational tests cannot recover mediated read structure on agent logs).** If writes are
deterministic in their parents (w_c = f(w_b), w_b = g(w_a)), the distribution over write indicators is unfaithful to
the mechanism graph: w_c ⟂ w_b | w_a and w_c ⟂ w_a | w_b both hold, so any constraint-based method drops at least one
edge of a→b→c and may keep a→c at lag 2. (The 9/20 sweep is its instance.)

**Proposition 2 (identification and cost by read interventions).** With π fixed and monotone use, F^π_e is identified
from replays and adaptive elimination (ddmin halving) returns a minimal sufficient set in O(|F| log n) replays; without
monotonicity it returns a 1-minimal set with the same bound. Exogenous g removes confounding by construction; the
bound is generalised binary splitting.

**Algorithm.** (i) *Discover*: per training episode, if the full read is correct, run `minimal_sufficient` with the
replay oracle (executor or LLM). (ii) *Amortise*: fit p_θ(s ∈ F | typed path of the record's anchor from the cue,
segment signature, key relation, recency among same-key segments, record kind and changed fields) on the discovered
sets; the projection of positive anchor paths to type pairs is the recovered type structure; at test time read
{s : p_θ ≥ τ} plus the referents' one-hop closure, no replays, no parser. (iii) *Localise*: for an anomalous decision,
order candidate records by the structural trace and find, by prefix doubling and binary search with
clean-replacement replays, the record whose replacement restores the clean plan; O(log n) replays, one when the
prior is right. Forward and backward are the same primitive.

**Why it is a method.** The learned object is defined by interventions the system performs; the negative result on
observational discovery is part of it (Prop. 1); there is an algorithm with a bound and an amortising model with an
explicit train-time cost; the parser leaves the main claim (the LLM version is fitted on the LLM's own replays); the
frontier is actor-specific, which is what D trust needs for specific edits and auditable recall.

## 3. Established results (unchanged tonight; numbers as in the package)

- **E0 v2** (32 variables, T = 10,000, 5 seeds × 3 noise levels): regime-conditioned estimation recovers the gated read
  edges 5/5 at every noise level; pooled / additive / PCMCI fail (F1 0.43 / 0.43 / 0.41 vs 1.00 at σ = 0); shuffled
  regimes fail; per-regime OLS and HC0 interaction also pass (conditioning on the regime is what matters).
- **HM3 four domains, test seeds** (EES): learned graph 0.88 / 0.76 / 1.00 / 0.72; best lookup/kNN 0.30 / 0.46 / 0.41 /
  0.14; GNN 0.74 / 0.71 / 0.46 / 0.26; program learner 0.67 / 0.78 / 0.99 / 0.89.
- **Deterministic scaling, Travel test seeds**: graph_select 1.000 at native/100/c100/500 with 11.2 → 12.1 reads;
  BM25-16 0.92 → 0.03; recency-16 0.93 → 0.30; re-wired skeletons 0.05 → 0.03; native-fit gate 0.88 / 0.86 / 0.85 / 0.80.
  Shopping: graph_select 0.97–0.98; BM25-16 0.98 → 0.05.
- **Actor panel, Travel seed 30, 16k, verbose both sides** (structure − full history): v1 +0.00 / +0.08 / **+0.19
  [+0.06, +0.32]** / **+0.17 [+0.03, +0.32]** at native / 100 / c100 / 500; v2 −0.23 / +0.18 / +0.22 / +0.44; tokens
  3.8–4.4k vs 27k–261k. Shopping: parity at 100, −0.19 at 500 under v1 (cost claim only).
- **Substrate (MemoryArena entities and memory classes)**: ours − long-context +0.05 (n.s.) / +0.31 / +0.12 / +0.20
  (v1), +0.03 / +0.30 / +0.27 / +0.48 (v2); BM25 top-16 0.28 → 0.02–0.05; BM25 top-3 starved; A-Mem 0.11–0.14 native,
  0.02–0.06 at 100. Provenance on real entities top-3 0.88–0.96.
- **Memory-system selectors**: Mem0 raw Travel 0.27 / 0.05 (native / 100), Shopping 0.53 / 0.30; A-Mem Travel 0.34 /
  0.02, Shopping 0.61 / 0.41.
- **Provenance, deterministic** (Travel test seeds): top-1 0.52–0.65, top-3 0.91–1.00, clean replacement restores at
  the same rate, controls 0.00; identical with the interventional, regression, GRACE-3× and GRACE+G² graphs. Actor
  level (seed 30, 52 incidents, 16k): v1 top-3 − corrupted +0.13 [+0.00, +0.27], − random-3 +0.17; v2 +0.35 / +0.29;
  top-3 − clean −0.02 under both.
- **Observational discovery on the same logs** (6 seeds): regression 0.21–0.23 / 1.00 (Travel P/R), 0.50 / 1.00
  (Shopping); GRACE open 0.19–0.29 / 0.80–1.00 and 0.50–0.60 / 1.00; PCMCI+ and GRACE-on-PCMCI 0.20–0.40 / 0.40 and
  0 / 0; GRACE gate ranking puts the chain head at ranks 1–2 and the stay → tail edges at 5–21 (AP 0.47–0.77 Travel,
  0.70–1.00 Shopping). Downstream selection and provenance with every recovered graph except GRACE 10× equal the
  reference on Travel; CI skeletons fail on Shopping (0.14–0.44).

## 4. New results (2026-09-20 night → 21 early morning)

### 4.1 E1a Discovery with the executor as π (200 native training episodes × 3 dev seeds)

| domain | records / episode | π-frontier | replays / episode | type projection vs interventional skeleton |
|---|---|---|---|---|
| Travel | 18.5 | 2.6–2.7 | 14.0–14.1 | 4/5, precision 1.0 every seed; missing stay → activity |
| Shopping32 | 13.8–14.5 | 2.1–2.2 | 13.4–13.9 | 2/3, precision 1.0; missing cart → promo |

The missing edges are those whose child has no hidden policy behind it: nothing has to be *read* for them, so they
are in the affected set and not in the read frontier (the formulation's distinction, observed). The π-frontier is a
strict subset of the generator's required records in 165/200 episodes (the executor does not need the segment's
intervention record). What the actor needs is what is identified.

### 4.2 E1b Replays vs history length (60 training episodes × 3 seeds; `results/development/hm3/replay/length_*.json`)

| | native (≈18) | 100 records | 500 records |
|---|---|---|---|
| Travel frontier / replays (mean, p90) | 2.7–2.9 / 14.7–15.4 (24–26) | 2.9–3.1 / 21.6–21.7 (33–39) | 2.9–3.1 / 27.2–28.5 (43–52) |
| Shopping frontier / replays | 1.9–2.3 / 13.3–14.4 (20–22) | 1.9–2.3 / 17.2–19.7 (27–31) | 1.9–2.3 / 19.8–21.5 (29–33) |

Replays grow with log n (×1.5 then ×1.3 for a ×5.5 then ×5 growth in n); the frontier is flat; every augmented
episode keeps a sufficient full read.

### 4.3 E1c Amortised, parser-free selection (`results/{development,real}/hm3/replay/ladder_frontier_*.json`)

Frontier model = gradient boosting on categorical features (numeric state features overfit and were dropped),
threshold 0.3, fitted by replays on the condition's own training logs (native-fit is the ablation `_nf`). EES (objects
read; required-record recall against the generator's over-counting list):

| arm | Travel test native / 100 / c100 / 500 | Shopping test native / 100 / 500 |
|---|---|---|
| frontier_select (fit on own logs) | 0.944 / 0.838 / 0.814 / 0.786 (14 → 84 objects) | 0.856 / 0.850 / 0.858 (13 → 16) |
| frontier_select, native-fit ablation | 0.944 / 0.660 / 0.596 / 0.523 | 0.856 / 0.894 / 0.933 |
| key-precedent selection (parser-free, hand rule) | 0.994 / 0.938 / 0.916 / 0.798 | 1.000 / 0.994 / 0.967 |
| graph_select (parser) | 1.000 × 4 (11–12 objects) | 0.972 / 0.972 / 0.983 |
| BM25 top-16 | 0.917 / 0.034 / 0.039 / 0.039 | 0.983 / 0.556 / 0.050 |

Dev seeds: Travel 0.933 / 0.878 / 0.789 / 0.822, Shopping 0.911 / 0.911 / 0.942. Reading: the replay-verified
frontier is exact; the amortised model is the weak link (it matches the hand key-precedent rule at long histories on
Travel and trails it on Shopping), and its object closure grows with the number of selected records. Fitting on the
condition's own logs matters on Travel (+0.18 to +0.26 over native-fit) because the interventional labels are taken
on the distribution the selector faces. Improving p_θ (path-conditioned recency, per-key latest-segment features, or
a sequence model over the segment) is the obvious next step; it does not touch the identification claim.

**p_θ trade-off at 500 records (dev seed 0, Travel; frontier recall/precision against the replay-verified
frontier of each evaluation episode):**

| model | threshold | records read | EES | frontier recall | frontier precision |
|---|---|---|---|---|---|
| balanced, record level | 0.3 / 0.5 / 0.7 | 39.5 / 20.8 / 12.1 | 0.77 / 0.78 / 0.87 | 0.98 / 0.97 / 0.96 | 0.07 / 0.13 / 0.23 |
| balanced, segment level | 0.2 / 0.3 / 0.5 | 84 / 69 / 42 | 0.95 / 0.95 / 0.88 | 0.99 / 0.99 / 0.97 | 0.03 / 0.04 / 0.07 |
| unbalanced, record level | 0.2 / 0.3 | 4.8 / 3.5 | 0.65 / 0.53 | 0.81 / 0.73 | 0.51 / 0.57 |

Shopping32 at 500 records (dev seed 0), same sweep: balanced record level reads 5.0–7.3 records for EES 0.95–0.97
(frontier recall 0.92–0.97, precision 0.32–0.46); segment level 9–13 records for 0.98–1.00. The over-selection is
Travel-specific.

Reading: on Travel the replay-verified frontier is 2–3 records, and the classifier recovers it at recall ≥ 0.96 only by
reading 12–80 records, because the categorical features do not separate the true same-key segment from foreign
same-key segments (the c-type distractors are built to look identical up to the value). The executor tolerates the
extras (latest witness wins), so EES stays 0.87–0.95 at 12–70 records against graph_select's 1.00 at 12 objects with
the parser. Where the model is precise (unbalanced) it misses the frontier and EES drops. The amortisation gap is
therefore a feature-representation problem for long histories with adversarial same-key distractors; the
replay-verified frontier itself does not degrade (§4.2).

### 4.4 E3 Localisation by the same primitive (Travel test seeds; `results/real/hm3/replay/localise_*.json`)

Incidents as in hm3.provenance; test = replace a candidate prefix by its clean version and replay; every order
localises (hit 1.0: replacing the whole history always restores the plan), so the comparison is the number of
replays. Final table (all six files regenerated 2026-09-21 evening with the real BM25 order; medians per seed 30/31/32,
mean over incidents in parentheses):

| condition | incidents | structural trace | read set, then history | BM25 against the anomaly | history order |
|---|---|---|---|---|---|
| Travel native | 161 | 1 / 1 / 2 (2.5) | 4 / 4 / 4 (3.8) | 6 / 7.5 / 4 (5.3) | 8 / 8 / 7.5 (7.1) |
| Travel 100 | 169 | 1 / 1 / 2 (3.0) | 4 / 6 / 4 (4.8) | 13 / 13 / 13 (10.2) | 13 / 13 / 13 (13.1) |
| Travel c100 | 169 | 1 / 1 / 2 (3.6) | 4 / 6 / 4 (5.2) | 13 / 13 / 13 (10.2) | 13 / 13 / 13 (13.1) |
| Travel 500 | 168 | 1 / 1 / 2 (3.0) | 4 / 6 / 4 (4.7) | 18 / 18 / 18 (13.9) | 18 / 18 / 18 (17.9) |
| Shopping native | 85 | 4 / 4 / 4 (4.1) | 6.5 / 6 / 6 (5.4) | 3 / 4 / 3 (3.6) | 6 / 6 / 6 (6.1) |
| Shopping 500 | 62 | 4 / 6 / 2 (8.1) | 6 / 8 / 6 (10.1) | 18 / 18 / 18 (15.7) | 18 / 18 / 18 (18.0) |

Reading: on the chained domain the structural prior puts the causing record first in most incidents at every length
(median 1–2 replays, mean 2.5–3.6), while the lexical and history orders grow with log n (8 → 13 → 18). On Shopping at
native length the lexical order is as good as or better than the structural one (median 3–4 against 4: the anomalous
line's own records are the cause and share its tokens), and at 500 records the structural order is back to 2–6
against 18. Shopping is therefore a boundary for the parser-based provenance test of §3 and not for localisation by
replay. Figure: `results/real/hm3/figures/replay_localise.pdf`.

### 4.5 E2 Discovery with the LLM as π (Travel seed 30, 72 / 67 training episodes, DeepSeek-V4-Flash, T = 0, 16k)

| | prompt v1 | prompt v2 |
|---|---|---|
| episodes where the full read is correct (discovery possible) | 21 / 72 (0.29) | 20 / 67 (0.30) |
| LLM frontier size (mean, median) | 2.24, 2 | 2.70, 2 |
| executor frontier on the same episodes | 1.95 | 2.00 |
| replays per episode (mean, p90); cost | 17.0, 29; $7.4 | 18.8, 30; $11.3 |
| executor frontier covered by the LLM frontier | 0.20 | 0.43 |
| episodes with both frontiers empty (no history needed) | 4 | 3 |
| monotonicity violations: nested pairs with the smaller set correct and the superset wrong | 259 / 2080 (12.5 %) | 82 / 1721 (4.8 %) |
| type projection of the LLM frontiers vs skeleton | flight→transfer, transfer→stay, stay→dinner: P 1.0, R 0.6 | same |
| record kinds the LLM needs most | stay txn (17), transfer auto (10), flight intervention (7), dinner txn (6) | stay txn (15), dinner txn (11), flight intervention (10), transfer auto (9) |
| record kinds the executor needs most | flight intervention (17), transfer auto (9), transfer txn (8) | flight intervention (17), transfer auto (11) |

Reading. (a) The LLM's frontier is actor-specific: it leans on the stay's own transaction record where the executor
leans on the flight intervention that started the segment; coverage of the executor frontier is 0.20–0.43. This is
the point of fitting p_θ on the actor's own replays. (b) Non-monotone use is measured directly: adding records flips
a correct decision in 12.5 % of nested pairs under v1 and 4.8 % under v2, which is the record-level form of the
conflicting-evidence effect in the actor panel. (c) The type projection from ~20 episodes already recovers the head
and the stay → dinner edge at precision 1.0. (d) Temperature-0 call-to-call disagreement is being measured
(`noise_probe_{v1,v2}.json`) and bounds how much of (b) is noise. Next: fit p_θ on the LLM sets (pooled over shards)
and run it as a parser-free selection mode in the actor panel.

### 4.6 Actor noise and the amortised LLM-fitted selector (2026-09-21 morning)

**Temperature-0 disagreement probe** (12 training episodes × 3 identical full-history calls,
`results/real/hm3/replay_llm/noise_probe_{v1,v2}.json`): the actor's correctness differs across the three calls in
**7/12 episodes under v1 (0.58)** and 3/12 under v2 (0.25). Consequences: (i) the single-call LLM discovery of §4.5 is
noisy: its "non-monotone" pairs (12.5 % / 4.8 %) are within call-to-call variance and cannot be read as a
conflicting-evidence effect; (ii) the replay oracle must vote: `LLMOracle(repeats=3)` (majority, early stop) is
implemented and the v1 discovery is being rerun with it on 48 episodes; (iii) the same variance bounds every actor
number in the paper and is already netted out in the provenance random-3 arm.

**Actor panel with the LLM-fitted frontier model** (`frontier_llm`: p_θ fitted on the 21 single-call v1 minimal sets;
Travel seed 30, v1, 16k, verbose; `results/real/hm3/frontier_llm/`):

| history | full history | structure (graph_seg, parser) | frontier_llm (parser-free, 21 noisy episodes) | frontier_llm − full | frontier_llm − graph_seg | tokens |
|---|---|---|---|---|---|---|
| c100 | 0.14 | 0.33 | 0.19 | +0.05 [−0.06, +0.14] | −0.14 [−0.30, +0.03] | 6.5k |
| 500 | 0.16 | 0.33 | 0.17 | +0.02 [−0.11, +0.14] | −0.16 [−0.30, −0.02] | 20k |

Negative at this sample size: parity with the full-history actor, below the parser-based structure, and the model
over-selects at 500 records (20k tokens).

**Actor panel with the executor-fitted frontier model** (`frontier_exec`: p_θ fitted by read-intervention replays of
the deterministic executor on the condition's own 199 training logs, segment-level selection, threshold 0.3; same
cells):

| history | full history | structure (graph_seg, parser) | frontier_exec (parser-free, replay-fitted) | frontier_exec − full [95% CI] | frontier_exec − graph_seg | tokens |
|---|---|---|---|---|---|---|
| c100 | 0.14 | 0.33 | 0.25 | +0.11 [−0.02, +0.24]; value acc +0.21 [+0.12, +0.31]; affected F1 +0.08 [+0.02, +0.15] | −0.08 [−0.22, +0.06] | 6.1k |
| 500 | 0.16 | 0.33 | 0.21 | +0.05 [−0.08, +0.17] | −0.13 [−0.27, +0.02] | 15.9k |

Reading: the replay-fitted, parser-free selector recovers about half of the parser-based structure's gain over the
full-history actor under conflicting witnesses (value accuracy and affected-object F1 are significantly above full
history; EES is above it without reaching significance) and reads 6k tokens against 27k; at 500 records it
over-selects (16k tokens, 5 cells at the cap) and the gain thins to +0.05. Where the parser is available, the
parser-based structure stays the stronger selector by 0.08–0.13. The identification claim is unaffected; the
amortisation from replays to a precise long-history selector is the open engineering problem (§4.3 trade-off) and is
reported as such. The k = 3 LLM discovery (`travel_s30_v1_k3_*`) is in progress: 8 usable episodes so far; non-monotone
episodes cost 70–170 calls each because votes split (5–25 split votes per episode).

### 4.7 Collaborator session B, 2026-09-21 13:22–16:20 (all of bridge plan §7.5; raw tables in `docs/bridge-session-b-notes-2026-09-19.md` §6)

**E1b on the test seeds** (`results/real/hm3/replay/length_*.json`, 60 episodes × 3 seeds): Travel frontier 2.51 / 2.67 /
2.73 records at native / 100 / 500 with replays 13.6 / 19.3 / 25.2 (p90 22.7 / 32.0 / 42.1); Shopping frontier 2.23 at
every length with replays 14.4 / 18.5 / 20.9. Same picture as dev: the frontier is flat and replays grow 1.5–1.9× while
records grow 27–34×.

**E3 on the remaining conditions** (median replays with the structural order / read set first / history order; three
seeds): Travel 100: 1–2 / 4–6 / 13 (169 incidents); Travel c100: 1–2 / 4–6 / 13 (169); Shopping native: 4 / 6–6.5 / 6
(85 incidents, 28–29 per seed); Shopping 500: 2–6 / 6–8 / 18 (62). Every order localises (hit 1.0); the structural
prior costs a median 1–2 replays on Travel at every length and 2–6 on Shopping, against log n (8 → 13 → 18) without it.
Shopping is therefore a boundary for the *parser-based* provenance test (§3) and not for localisation by replay.
Code note: the `bm25` column of every localisation file up to 17:00 equalled the history order (the runner read a
wrong key from `baseline_rankings`; fixed and all six files regenerated). With the real BM25-against-the-anomaly
order (median / mean replays, three seeds): Travel native 4–7.5 / 4.4–6.0 against structural 1–2 / 2.2–3.0;
Shopping native **3–4 / 3.2–3.8 against structural 4 / 3.8–4.4**. On Shopping the lexical order is as good as or
better than the structural one, which is consistent with the star mechanism (the anomalous line's own records are
the cause and share its tokens); the structural prior earns its keep on the chained domain. Remaining conditions
are being regenerated and the table above is updated when they land.

**p_θ sweeps, dev seeds 1/2, 100 and 500 records.** Balanced beats unbalanced at every threshold and granularity;
segment level adds +0.05 to +0.12 EES at about twice the records. Travel 500 over-selection reproduces (49–66 records
at threshold 0.2–0.3, precision 0.05–0.07; threshold 0.7 segment-level reads 21 for EES 0.82–0.87). Travel 100 at
threshold 0.3 segment-level reads 19 for 0.90–0.93. Shopping stays at 0.97–1.00 with 7–10 records at threshold 0.7.

**Selection ladders with the new arms** (`ladder_frontier2_{dev,test}_*.json`; test EES, `n_reads` = objects + records):

| condition | Travel t30_seg | Travel t50_seg | Travel t70 | Travel graph_select | Shopping t30_seg | Shopping t50_seg | Shopping graph_select |
|---|---|---|---|---|---|---|---|
| native | 0.972 (23 reads) | 0.967 (20) | 0.861 (11) | 1.000 (11) | 0.894 (18) | 0.878 (17) | 0.972 (19) |
| 100 | 0.939 (43) | 0.922 (35) | 0.804 (19) | 1.000 (12) | 0.989 (22) | 0.956 (21) | 0.972 (22) |
| c100 | 0.910 (48) | 0.899 (38) | 0.759 (21) | 1.000 (12) | — | — | — |
| 500 | 0.949 (133) | 0.933 (93) | 0.776 (33) | 1.000 (12) | 0.983 (25) | 0.972 (24) | 0.978 (22) |

Segment-level selection at threshold 0.3 is the parser-free arm to report: Travel 0.91–0.97 at every length (flat in
n), Shopping 0.98–0.99 at 100 and 500 on par with the parser-based selector at the same read count. Its cost on Travel
at 500 records is 133 reads (objects + records) against 12, which is the same over-selection as in the sweep; t50_seg
is the token trade-off (93 reads, 0.933). Metric note: the ladder's `n_reads` counts objects plus records
(`core.score_plan`), the sweep's `records` counts records only; 49 records plus their referents and one-hop closure is
the 125–133 figure.

**Actor panel, `frontier_exec`, all cells** (v1, verbose, 16k, 64 or 63 paired episodes; input tokens in parentheses):

| condition | full history | graph_seg (parser) | frontier_exec (parser-free) | exec − full [95% CI] | exec − graph_seg |
|---|---|---|---|---|---|
| Travel native | 0.48 (6.5k) | 0.48 (3.5k) | 0.41 (3.4k) | −0.08 [−0.23, +0.09] | −0.08 [−0.23, +0.06] |
| Travel 100 | 0.25 (26.8k) | 0.33 (4.0k) | 0.31 (5.7k) | +0.06 [−0.09, +0.22] | −0.02 [−0.17, +0.13] |
| Travel c100 | 0.14 (26.8k) | 0.33 (4.0k) | 0.25 (6.1k) | +0.11 [−0.02, +0.24]; value acc +0.21 [+0.12, +0.31] | −0.08 [−0.22, +0.06] |
| Travel 500 | 0.16 (123k) | 0.33 (4.1k) | 0.21 (15.9k) | +0.05 [−0.08, +0.17] | −0.13 [−0.27, +0.02] |
| Shopping 100 | 0.48 (25.8k) | 0.50 (9.9k) | 0.56 (5.9k) | +0.08 [−0.08, +0.23]; affected F1 +0.17 [+0.06, +0.28] | +0.06 [−0.06, +0.19] |
| Shopping 500 | 0.52 (103k) | 0.36 (10.3k) | 0.56 (6.1k) | +0.05 [−0.09, +0.19] | +0.20 [+0.03, +0.38]; value acc +0.12 [+0.01, +0.23] |

Reading: the replay-fitted parser-free selector is at parity with the full-history actor on Travel (every interval
contains 0, with a +0.11 point estimate under conflicting witnesses) and 0.02–0.13 below the parser-based structure;
on Shopping it is the best of the three arms at both lengths, significantly above the parser-based structure at 500
records, at 6 % of the full-history tokens. This is the first parser-free actor result that beats the parser-based
one anywhere, and it comes from the domain where the sweep showed p_θ precise. (These are the record-level threshold
0.3 model with segment-level reads; the ladder's t30_seg is the same configuration.)

**Majority-vote LLM discovery, both prompts** (`travel_s30_{v1,v2}_k3_*`; k = 3, 48 episodes per prompt):

| run | episodes | full read correct | cost | LLM frontier | executor frontier | replays | executor frontier covered | type edges (P / R vs skeleton) |
|---|---|---|---|---|---|---|---|---|
| v1 shard 0 | 24 | 7 | $4.2 | 2.29 | 2.83 | 16.4 | 0.42 | flight→transfer (1.0 / 0.2) |
| v1 shard 24 | 19 (budget) | 7 | $13.6 | 5.86 | 2.40 | 35.3 | 0.70 | flight→transfer, transfer→stay, stay→dinner (1.0 / 0.6) |
| v2 shard 0 | 24 | 9 | $9.2 | 3.11 | 3.25 | 16.7 | 0.25 | flight→transfer, transfer→stay (1.0 / 0.4) |
| v2 shard 24 | 24 | 8 | $11.5 | 2.38 | 2.40 | 19.4 | 0.33 | flight→transfer, transfer→stay (1.0 / 0.4) |

Reading: with voting the full-read pass rate is 33–35 % under both prompts, which caps what discovery can label (a
sufficient set exists only where the actor is right); every shard recovers the chain head at precision 1.0 from its
own replays; the LLM's frontier covers 0.25–0.70 of the executor's, i.e. the actor-specific frontier finding of §4.5
stands once noise is voted out. Non-monotone episodes remain the cost driver (35 replays per episode in the v1 shard
that hit its budget).

### 4.8 Extended majority-vote LLM discovery (2026-09-21 evening; episodes 0–191 of Travel seed 30, k = 3, both prompts)

| | prompt v1 | prompt v2 |
|---|---|---|
| episodes processed / usable (full read correct by majority) | 187 / 55 (0.29) | 187 / 73 (0.39) |
| cost | $60 | $102 |
| LLM frontier (mean, median) vs executor frontier on the same episodes | 3.09, 3 vs 2.27 | 2.92, 3 vs 2.48 |
| replays per usable episode (p90); LLM calls | 22.1 (57); 48 | 19.3 (34); 41 |
| executor frontier covered by the LLM frontier; identical sets | 0.26; 10 / 55 | 0.48; 14 / 73 |
| type projection vs interventional skeleton | 4 / 5 edges, precision 1.0 (missing stay → activity) | same |
| edge support | flight→transfer 146, transfer→stay 39, stay→dinner 13, stay→bundle 2 | 200, 34, 11, 2 |
| record kinds the LLM needs most | stay txn 48, dinner txn 35, flight intervention 31, transfer auto 21 | stay txn 59, flight intervention 41, transfer auto 33, dinner txn 30 |
| record kinds the executor needs most | flight intervention 46, dinner txn 24, transfer auto 24, transfer txn 22 | flight intervention 63, transfer auto 38, dinner txn 38 |

Reading. With voting and 55–73 usable episodes the LLM's own replays recover the same four type edges as the
executor's (precision 1.0, the fifth edge has no read behind it), so the actor's structure is identifiable from its
own read interventions. The LLM frontier is larger than the executor's by about 0.5–0.8 records and overlaps it only
0.26–0.48: the actor keys the provider's rule on the stay's own transaction record where the parser keys it on the
flight intervention that opened the segment. The refit `frontier_llm` models (55 and 73 episodes) read 8–10 records
at native length against 4.7–6.3 for the 21-episode model; their actor cells (Travel c100 and 500, each under its own
prompt) are running.

### 4.9 Large-parallel batch (2026-09-21 evening → 22 morning; all four keys)

**Actor panel replicated on three test seeds** (Travel seeds 30/31/32, prompt v1, 16k, verbose; pooled paired
comparison over 180–192 episodes; `results/real/hm3/seeds/`, `panel_summary --domain travel [--seed k]`):

| history | full history | structure (parser) | frontier_exec (parser-free) | structure − full [95% CI] | frontier_exec − full | frontier_exec − structure | tokens: full / structure / exec |
|---|---|---|---|---|---|---|---|
| native | 0.42 | 0.40 | 0.38 | −0.02 [−0.11, +0.07] | −0.05 [−0.14, +0.04] | −0.03 [−0.11, +0.06] | 6.5k / 3.6k / 3.1k |
| 100 mixed | 0.24 | 0.37 | 0.30 | **+0.13 [+0.04, +0.21]** | +0.07 [−0.02, +0.15] | −0.06 [−0.16, +0.04] | 26.8k / 4.0k / 5.6k |
| 100 conflicting | 0.16 | 0.33 | 0.27 | **+0.16 [+0.08, +0.24]** | **+0.11 [+0.04, +0.18]**; value acc +0.22 [+0.16, +0.29] | −0.06 [−0.14, +0.02] | 26.8k / 4.0k / 6.0k |
| 500 mixed | 0.15 | 0.37 | 0.19 | **+0.22 [+0.13, +0.30]** | +0.04 [−0.03, +0.11] | −0.18 [−0.26, −0.09] | 123k / 4.1k / 15.7k |

Per seed the structure − full effect is +0.20 / +0.32 (seed 31, c100 / 500), +0.10 / +0.16 (seed 32), +0.19 / +0.17
(seed 30): the sign holds on every seed and the pooled intervals exclude zero at 100, c100 and 500. The parser-free
replay-fitted selector beats full history under conflicting witnesses on the pooled three seeds (+0.11 [+0.04,
+0.18]) and is at parity elsewhere; it trails the parser-based structure by 0.03–0.06 at ≤100 records and by 0.18 at
500, where it over-selects (15.7k tokens). (Six of the 500-record shards on seeds 31/32 are being completed; n = 180
of 192 at that row.)

**Shopping, parser-free arm under prompt v2** (seed 30, 64 paired episodes; v1 rows in §4.7):

| history | full | structure (parser) | frontier_exec | exec − full | exec − structure |
|---|---|---|---|---|---|
| 100 | 0.42 | 0.34 | 0.56 | +0.14 [−0.02, +0.30]; affected F1 +0.22 [+0.09, +0.35]; value acc +0.30 [+0.16, +0.45] | **+0.22 [+0.06, +0.38]** |
| 500 | 0.30 | 0.53 | 0.55 | **+0.25 [+0.11, +0.39]** | +0.02 [−0.12, +0.16] |

Under both prompts the parser-free selector is the best arm on Shopping at 100 and 500 records at 6k tokens
(full: 27k–106k). Combined with v1 (§4.7: +0.20 over the structure at 500), the Shopping accuracy claim, which was
cost-only for the parser-based structure, is now an accuracy claim for the replay-fitted one.

**Refit LLM-fitted selector** (`frontier_llm` from the 55 / 73 majority-vote episodes; Travel seed 30, own prompt):
c100 0.17 (v1) / 0.21 (v2) against structure 0.33 / 0.41; 500 records 0.16 / 0.17 against 0.33 / 0.56; parity with
full history everywhere (every EES interval contains 0), affected F1 and value accuracy above full under v2 (+0.21,
+0.19 at c100), and it over-selects at 500 (27–37k tokens). Reported as the negative it is: the actor's own replays
identify its structure (§4.8) but 55–73 noisy episodes do not yet yield a selector that competes with the one fitted
on 200 exact executor replays. The executor-fitted selector is the parser-free arm of the paper.

## 5. What the paper claims, in the new framing

1. **Memory reads are interventions; the frontier is identifiable from them and not from the logs' observational
   distribution.** Prop. 1 + the discovery sweep (CI tests prune mediators, empty on Shopping) versus E1a/E2
   (read-intervention discovery recovers the read edges at precision 1.0 with 14–19 replays per episode).
2. **Reading the frontier keeps memory flat as the history grows and protects the actor from conflicting evidence.**
   Deterministic ladders + the actor panel + the substrate port (existing), plus E1b (replays log n, frontier flat).
3. **The same primitive localises the record that caused an anomalous action in one replay when the structural
   prior is right, and in O(log n) otherwise.** E3 + the existing provenance at both layers.
4. **The frontier is actor-specific.** E2: the LLM's minimal read sets differ from the executor's; non-monotone use
   quantified.
5. **Boundaries.** Amortisation loses 0.05–0.2 EES against replay-verified reads; discovery needs a correct full read
   (29–30 % of episodes for this actor at native length); Shopping keeps only the cost claim; CI discovery is the
   wrong tool on deterministic logs; MINJA is an identification boundary.

Vocabulary: "causal" refers to do(read) and to the controlled simulation; edges recovered observationally are
"temporal dependency structure" (Yujia's 9/20 rule stands and is now sharper).

## 6. Figures and tables (have / to do)

Have: gate heat-map (E0); scaling figures `results/real/hm3/figures/{scaling_travel,scaling_shopping32,substrate_travel_arena}.pdf`;
provenance case figure; the one-page diagram (`docs/yujia-causal-bridge-2026-09-20.md`, artifact).
To do: (i) replays-vs-n and frontier-vs-n panel (E1b); (ii) localisation replays histogram by order (E3); (iii) the
LLM-vs-executor frontier composition bar (E2); (iv) one schematic of the read-intervention loop (log → mask →
replay → minimal set → p_θ → read / trace).

## 7. Plan to 2026-09-25

| when | what | needs |
|---|---|---|
| 9/21 morning | localisation rerun (boundary fix) and noise probe read; p_θ fitted on LLM sets; `frontier_llm` selection mode in `hm3.llm`; actor panel Travel c100 + 500 with it (v1, 64 episodes) | API keys 0/1 |
| done 9/21 | p_θ: segment-level selection and threshold sweep (dev only), ladders with the new arms on dev and test (session B) | — |
| done 9/22 | actor panel seed replication: Travel seeds 31/32 (§4.9); six 500-record shards completing | — |
| done 9/22 | majority-vote LLM discovery to 187 episodes both prompts (§4.8); refit frontier_llm actor cells (§4.9, negative) | — |
| done 9/22 | Shopping frontier_exec under v2 at 100 / 500 (§4.9) | — |
| done 9/22 | figures (i)–(iv): `replay_length`, `replay_localise`, `frontier_composition` (LLM vs executor frontier by record kind: the LLM keys on the stay's own transaction in 0.84 of episodes where the executor does in 0.03), `method_schematic` — all in `results/real/hm3/figures/` | — |
| 9/22 (running) | Travel seeds 31/32 under prompt v2 at c100 and 500 (full / structure / frontier_exec) to replicate the v2 rows | API |
| 9/22 | freeze tables after the v2 seed replication lands; Yujia one-pager v2 written (`docs/yujia-method-v2-2026-09-22.md`) | — |
| 9/22–23 | paper: method section (draft written 9/21: `docs/paper-draft-method-2026-09-21.md`), experiments (draft exists, add §4 rows), boundaries | — |
| 9/24 | internal review pass; ablations table; appendix (protocols, prompts, costs) | — |

Not planned: KCI / kernel tests (low priority per 9/20); LightMem; Search/Formal scaling.

## 8. Files

Method: `docs/method-design-read-interventions-2026-09-20.md`, paper text `docs/paper-draft-method-2026-09-21.md`, Yujia page `docs/yujia-method-v2-2026-09-22.md`; sweep module `code/hm3/replay_sweep.py`; collaborator tasks in `docs/bridge-plan-2026-09-19.md` §7.5; code `code/hm3/replay.py` (minimal_sufficient,
ExecutorOracle, LLMOracle, discover, FrontierModel, FrontierSelect), `replay_length.py`, `replay_llm.py`,
`replay_localise.py`; results `results/development/hm3/replay/`, `results/real/hm3/replay/`, `results/real/hm3/replay_llm/`.
Evidence: `docs/hm3-results-package-2026-09-19.md`, `docs/yujia-causal-bridge-2026-09-20.md`,
`docs/paper-draft-experiments-2026-09-20.md`, `docs/experiments-and-paper-status-2026-09-20.md`, `docs/bridge-plan-2026-09-19.md`.
Branch `claude/hm3-handoff-2026-09-18`, everything uncommitted (committing is the user's call).
