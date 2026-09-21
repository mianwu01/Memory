# Method design: identifying the memory frontier by read interventions (2026-09-20)

给 Yujia 的六行摘要：现在的 pipeline（观测日志 → GRACE/回归 → 骨架 → 前向选择 / 后向追责）是工程，审稿人会说"就是沿外键做闭包"。
本设计把它变成一个有形式对象、有识别定理、有算法与复杂度界的方法：记忆系统对自己的**读取**做干预（重放时屏蔽记录），
由此识别出决策的 causal frontier（formulation 中的 F_t），不依赖 faithfulness，因此在观测式 TCD 被确定性写入击败的地方仍然成立
（这正是 9/20 扫描的现象）。前向选择 = 读预测出的 frontier；后向追责 = 同一个屏蔽-重放原语反向使用；两者用同一个 O(k log n) 的
自适应搜索，并由类型级结构先验摊销。现有全部结果保留为证据，新增三组实验（确定性重放识别、LLM 自身重放识别、预算下的定位），
四天内可完成。"causal" 一词落在干预上，站得住。

## 1. What is wrong with the current method as a contribution

The current pipeline learns a type-level skeleton from training episodes with observed outcomes (supervised on which
objects changed), attaches decision-tree gates, and reads the closure at test time; provenance walks the same graph.
The 9/20 sweep showed that off-the-shelf discovery reproduces the skeleton's *reach* but prunes its mediators, and the
pipeline tolerates that. Three objections a strong reviewer will make:

1. The learned object is a five-edge type graph over foreign keys. Following it is a join, and the gains against
   retrieval baselines follow from the benchmark's construction.
2. "Causal" is carried by a word: the structure is either supervised from outcomes or recovered by observational tests
   whose assumptions (faithfulness) fail on exactly these logs, as we ourselves show.
3. The selector depends on a hand-written parser (`infer_params`) that recovers the hidden policies; the parser-free
   variant is weaker, so the method as stated is domain-engineered.

## 2. The proposal in one paragraph

An agent's memory reads are interventions it performs on itself. In the formulation's gated SCM, a carrier m_s reaches
the decision Y only through its read gate g_s ∈ {0,1} (α_e(u) with u the access regime), and g is set by the memory
system. Setting g is free and safe at replay time: re-run the decision policy π on a logged episode with a subset of
records visible, and observe whether the decision changes. This is do(g = 1_S), an intervention on the access regime
with exogenous assignment, so it identifies which records the decision depends on without any assumption on the
write process. Deterministic writes, which break every conditional-independence test on the logs (Proposition 1),
are irrelevant, because we intervene on reads, not on writes. The method: (i) per episode, find a minimal sufficient
read set by adaptive elimination with the replay oracle, O(k log n) replays for a k-record frontier among n records
(Proposition 2); (ii) learn a type-level *conditional frontier model* from those sets, which predicts for a new
episode which records along which typed paths under which regime features are necessary, and select them (forward);
(iii) for an anomalous decision, run the same elimination on the read set with clean-replacement replays, ordered by
the structural model, to localise the causing record in O(log n) replays (backward). The forward and backward
functions are one primitive. The actor can be the deterministic executor or the LLM itself; in the latter case the
identified frontier is *actor-specific* (what this model's decisions depend on), needs no parser, and is what
trustworthy memory (D trust) requires for specific edits and auditable recall.

## 3. Formal objects

Notation follows `causal_memory_formulation.tex`. Episode e: history H = (m_1, …, m_n) of carriers (records), state
S_0, cue I, decision Y = π(S_0, I, {m_s : g_s = 1}) with π fixed (deterministic executor, or an LLM at temperature 0
treated as a fixed measurable map with bounded noise, §6). Correctness c(Y) ∈ {0,1} against the oracle.

**Definition (read-sufficient set, frontier of π).** S ⊆ [n] is *sufficient* for e if c(π_S) = c(π_[n]) = 1. It is
*minimal* if no proper subset is sufficient. The π-frontier F^π_e is a minimal sufficient set; under uniqueness it is
the causal frontier F_t restricted to carriers (Lemma frontier); under redundancy (two witnesses of the same key) it
is one of the minimal hitting sets and any of them is a lossless memory for e.

**Assumption (monotone use).** If S is sufficient and S ⊆ T then T is sufficient. Exact for the executor (more
witnesses never remove a key). For the LLM it is the "distractor-free" case; its violation under conflicting witnesses
is precisely the long-history failure the actor panel measures, and §6 treats it.

**Proposition 1 (observational tests cannot recover mediated read structure on agent logs).** Let writes be
deterministic in their parents (w_c = f(w_b), w_b = g(w_a)) as they are in HM3 and in any agent whose actions are
functions of its context. Then the observational distribution over write indicators is not faithful to the
mechanism graph: w_c ⟂ w_b | w_a and w_c ⟂ w_a | w_b both hold, so any constraint-based method removes at least one
of a→b→c's edges and may keep a→c at lag 2. (Standard determinism failure; the 9/20 sweep is its instance: PCMCI+ and
GRACE-on-PCMCI keep flight→transfer→stay and route the tail to flight at lag 2–3; on Shopping they return the empty
graph.)

**Proposition 2 (identification and cost by read interventions).** With π fixed and monotone use, F^π_e is identified
from replays {c(π_S)} and adaptive elimination (ddmin-style halving) returns a minimal sufficient set with at most
O(|F| log n) oracle calls; without monotonicity it returns a 1-minimal set (no single removal keeps sufficiency) with
the same bound. Proof: exogenous g removes confounding by construction; halving with a monotone oracle is standard
group testing (Hwang's generalised binary splitting bound). No faithfulness, no assumption on the write process.

**Definition (type-level conditional frontier model).** Let τ(s) be the record's object type, ρ(s) the typed path from
the cue's object to that object in S_0 (the template), and z(s) the regime features readable from the record and its
segment (kind, position in segment, same-key precedent count). The model is p_θ(s ∈ F | ρ(s), z(s)), fitted on the
per-episode minimal sets from training replays. Forward selection reads {s : p_θ > ½} plus the referents' one-hop
closure (as graph_closed does now). The projection of {ρ : p_θ high} to type pairs is the type-level structure
reported against the interventional skeleton.

**Backward (abduction with the same primitive).** For an anomalous decision on objects O, candidates are the read
records on typed paths into O, ordered by p_θ and path length; test = replace a candidate block by its clean version
and replay; eliminate by halving. Returns the causing block in O(log n) replays; the ordering makes the first test
succeed in most incidents (current path ranking already puts the record in the top-3 in 0.91–1.00 of incidents).

## 4. Why this is a method and not a pipeline

- The learned object is F^π, defined by interventions the memory system performs itself. "Causal" refers to do(g).
- A negative result is part of the method: Proposition 1 says why observational discovery is the wrong tool here,
  and the sweep of 9/20 becomes its evidence rather than a bridge to defend.
- An algorithm with a bound (Proposition 2) and an amortising learned model (p_θ) that makes test-time selection
  replay-free. Cost is explicit: replays at training time, k-sized reads at test time.
- Forward and backward are the same primitive; provenance stops being a separate heuristic.
- The parser is gone from the main claim: with the LLM as π, p_θ is fitted on the LLM's own replays and selects
  records by their typed path and regime features. The executor version is the controlled instance.
- It connects to the formulation's Lemma (F_t is the unique minimum memory) and to D trust (edits through identified
  carriers are specific), which is what Yujia asked the theory to buy.

## 5. Experiments (new rows; everything existing stays as evidence)

E1 *Interventional discovery, executor as π.* 200 training episodes × 3 seeds × 2 domains; replays per episode; the
recovered type structure vs the interventional skeleton (P/R = 1/1 expected on Travel, including the mediators the CI
tests drop); downstream selection with p_θ vs graph_select. Also on 100- and 500-record histories: replays per
episode grow as log n (the bound), the frontier size does not.
E2 *Interventional discovery, LLM as π.* 32–64 training episodes where the full-context actor is correct; ddmin with
DeepSeek-V4-Flash at temperature 0; report the LLM-frontier size, its overlap with the executor frontier, the type
structure it implies, and the actor panel with p_θ fitted on LLM replays (parser-free selection) vs graph_seg.
E3 *Localisation under a budget.* The 52 incidents: replays to localise with (a) halving only, (b) halving ordered
by p_θ / path, (c) BM25 order; report the median and the 90th percentile.
E4 *Obs vs interventional on the same logs* (have: the 9/20 sweep). Table: PCMCI+, GRACE, regression, read-intervention.
E5 *Robustness of Proposition 2's assumption.* Monotonicity violations for the LLM: fraction of episodes where adding
records flips a correct decision (this is the conflicting-witness effect); the 1-minimal set still selected.

Schedule: E1 today (deterministic, minutes). E2 tomorrow morning (≈500 calls). E3 tomorrow (≈300 calls). Tables
frozen 9/22; text 9/22–23.

## 6. Risks and how they are handled

- LLM nondeterminism: temperature 0 plus a repeat on disagreement; report the disagreement rate. Episodes where the
  full-context actor is wrong are excluded from discovery (no sufficient set exists).
- Non-monotone LLM use: ddmin returns a 1-minimal set; we report how often removal of a block *improved* correctness
  (conflicting witnesses) as a finding, not a failure.
- Redundant witnesses: minimal sets are not unique; the type-level model pools over episodes so redundancy averages
  out; selection reads all high-probability records.
- Cost: replays happen at training time only; test-time reads are the same 4k tokens as now.
- Scope: HM3 and the MemoryArena substrate; MINJA is out of scope for this method.

## 7. Code plan

`code/hm3/replay.py`: `minimal_sufficient(candidates, ok)` (ddmin), `ExecutorOracle(domain, ep)`, `LLMOracle(client,
domain, ep, prompt)`, `discover(domain, episodes, oracle) -> per-episode minimal sets + replay counts`,
`FrontierModel.fit/select` (typed path × regime features → probability; sklearn tree/GBM), `type_edges(model)`,
`localise(ep, incident, oracle, order)`. Registration in `scaling.py` as `frontier_select` (executor-fitted) and in
`llm.py` as selection mode `frontier` (LLM-fitted, parser-free).

## 8. Results so far (2026-09-20 night; deterministic executor as π; `code/hm3/replay*.py`)

**E1a Discovery on native training logs** (200 episodes × 3 dev seeds per domain, replays = executor calls):

| domain | records per episode | π-frontier size | replays per episode (ddmin) | type projection vs interventional skeleton |
|---|---|---|---|---|
| Travel | 18.5 | 2.6–2.7 | 14.0–14.1 | 4/5 edges, precision 1.0 on every seed; missing stay → activity |
| Shopping32 | 13.8–14.5 | 2.1–2.2 | 13.4–13.9 | 2/3 edges, precision 1.0; missing cart → promo |

The missing edges are exactly the edges whose child has no hidden policy behind it (activity is repaired from visible
rules; the promo's state is in S_0): nothing has to be *read* for them, so they are not in the read frontier although
they are in the affected set. This is the frontier / affected-set distinction of the formulation, observed.
The π-frontier is a strict subset of the generator's required records in 165/200 episodes (equal in 58/200): the
executor's parser does not need the segment's intervention record that the generator lists. What the actor needs is
what is identified.

**E1b Replays vs history length** (60 training episodes × 3 seeds; `results/development/hm3/replay/length_*.json`):

| domain | native (≈18 records) | 100 records | 500 records |
|---|---|---|---|
| Travel, frontier size | 2.7–2.9 | 2.9–3.1 | 2.9–3.1 |
| Travel, replays (mean / p90) | 14.7–15.4 / 24–26 | 21.6–21.7 / 33–39 | 27.2–28.5 / 43–52 |
| Shopping32, frontier size | 1.9 | 1.9 | (running) |
| Shopping32, replays | 13.4 / 20 | 17.2 / 27 | (running) |

Replays grow with log n (18 → 100 → 500 records: ×1.5 then ×1.3) while the frontier is flat, as Proposition 2 says.
Every augmented episode still has a sufficient full read (full_ok 58–60/60).

**E1c Amortised selection (parser-free)** — the conditional frontier model (gradient boosting on categorical
segment / key / recency / changed-field features; numeric state features overfit and were dropped; threshold 0.3)
on dev seeds at native length: Travel EES 1.00 / 0.97 / 0.92 with 4.3–5.2 records, Shopping 0.93 / 0.90 / 0.87 with
3.5–4.1 records; required-record recall 0.76–0.82 against the generator's list (which over-counts, see above). The
ladder across lengths with the model fitted on the condition's own logs is running (`ladder_frontier_*`).

**E3 Localisation by the same primitive** (Travel test seeds, native, incidents built as in hm3.provenance;
test = replace a candidate prefix by its clean version and replay; `results/real/hm3/replay/localise_travel_native.json`):

| candidate order | hit (seed 30 / 31 / 32) | replays to localise, median / p90 |
|---|---|---|
| structural trace (the graph's path ranking) | 0.98 / 0.94 / 0.92 | 1 / 4–6 |
| read set, then history order | 0.98 / 0.94 / 0.92 | 4 / 6 |
| BM25 against the anomaly | 0.68 / 0.48 / 0.72 | 5–6 / 8 |
| history order | 0.68 / 0.48 / 0.72 | 5–6 / 8 |

The structural prior puts the causing record first in most incidents (median one replay); without it the same
search needs five to six. The 500-record condition and the LLM-as-π discovery (E2, seed 30, both prompts) are running.
