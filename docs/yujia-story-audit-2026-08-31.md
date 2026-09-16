# Yujia 故事线与四任务修复总审计（2026-08-31）

## 1. 最终裁决

本轮已经把四个 task 从 T0 admissibility prototype 修到可运行的 T1：只有训练集暴露
历史干预 outcome，dev/test outcome 隔离；测试含新实体、新值、新模板或 held-out regime；
每个任务均有六臂和 selection × serialization 正交评价。统一结果保存在
[`suite_t1.json`](../results/development/causal_benchmarks/suite_t1.json)。

但这次修复没有把负结果改写成正结果：四个 learned selector 都优于同预算 generic
retrieval，却没有一个优于最强 domain solver。因此当前项目只完成了 Yujia 故事线的
一部分，不能宣称两个卖点已经同时成立。

| 故事线部分 | 状态 | 可以写的结论 | 不能写的结论 |
|---|---|---|---|
| Simulation，known DGP | **PASS（observed）** | regime-conditioned 方法在 linear 和 observed MLP 上五个 seed 的 overall/read F1 都为 1.0 | 识别了未观测 latent variable |
| 四个 dynamic/formal T1 | **PARTIAL PASS** | train-only impact selection 在 novel split 上优于 generic retrieval，并压缩 context | learned causal graph 对任一 task 是必需的；0/4 通过强 domain 判据 |
| Four-task real API v1 | **EXECUTED / NOT CONFIRMATORY** | 288 request rows、309 ledger events；learned valid-only endpoint 4/4 为 1.0，compact context 明显低于 full-state | 一次调用 reliability；causal necessity；v1 `experiment_complete=false` |
| Anti-shortcut / hidden-routing v2 | **STOP / PARTIAL** | v1 四任务 lookup shortcut 与 v2 codebook/sparse-mask microbenchmark 的边界已量化 | correctness necessity；四个独立 domain replication；授权新 API |
| MemoryArena effectiveness/efficiency | **PARTIAL PASS** | compact-v3 通过冻结的 PS non-inferiority + input reduction 合取判据 | 原 Travel 证明 causal discovery necessity；所有 latency 维度都更快 |
| Hidden-driver auditing | **SUPPORTED WITH BOUNDARIES** | MINJA/AgentPoison 支持 temporal dependency、gated read 与 write ancestry 的审计价值 | 新预注册的 confirmatory detection PASS，或击败 MemAudit |
| Actionable online safety | **FAIL** | 当前 gate 是一个已执行但失败的安全实验 | 已能保证 agentic system 安全 |
| 完整两卖点故事 | **NOT ESTABLISHED** | 可报告上述分项证据 | effectiveness/efficiency 与 actionable safety 都已闭环 |

可执行裁决器是 [`yujia_story_audit.py`](../code/yujia_story_audit.py)，生成
[`yujia_story_audit.json`](../results/development/yujia_story_audit.json)。它直接读取冻结
artifact 并重新计算 verdict，不依赖本页人工口径。

## 2. 四个 task 修复了什么

四个任务共同遵循以下隔离契约：

1. 一个训练 sample 是一次已经完成的
   `(pre_state, intervention, post_state)` transition；learner 不读 gold graph、active
   edges、affected labels 或 evaluator post-state。
2. 一个测试 sample 只暴露 history、pre-state、query 与结构化 intervention source；
   dev/test 不含 `observed_transition`。
3. 一个 variable 是一个有名字的单维 scalar/categorical state cell；整张 state 才是由
   这些 cell 组成的向量。当前实验不是把一整段 LM embedding 当成一个 variable。
4. 测试先评价 impact selection，再由所有 selector 共用 deterministic value decoder。
   因而 endpoint success 隔离了 selection sufficiency，但不是 learned equations 或
   LLM end-to-end execution 证据。
5. 六臂分别是 Exact-KV、最强 domain solver、同预算 generic retrieval、learned graph/
   impact selector、oracle graph、full history/state；compact 与 verbose serialization
   对同一 selection 交叉评价。

| Task | Intervention 后隐藏的传播 | Novel test | 最强 domain baseline | 120-episode learned / generic recall | learned / domain success | learned/full compact chars | Causal necessity |
|---|---|---|---|---:|---:|---:|---|
| Dynamic Travel | flight/venue/hotel change → transfer/attraction/dinner/check-in | entity、arrival/deadline value、paraphrase、全 fixed/no-late gate | itinerary rule solver | 1.000 / 0.686 | 1.000 / 1.000 | 87.55 / 489.25 | **FAIL** |
| Dynamic Shopping | availability/price/policy → compatibility/budget/cart | template、CPU entity、price value、CPU-cancel × hard-cap | catalog + compatibility/budget solver | 1.000 / 0.219 | 1.000 / 1.000 | 336.28 / 1494.92 | **FAIL** |
| Dynamic Search | revision/retraction/trust/version → evidence/claim descendants | node/entity/template、trust transition、version 3 | provenance parser/solver | 1.000 / 0.500 | 1.000 / 1.000 | 1262.33 / 6517.33 | **FAIL** |
| Causal Formal | definition/parameter/axiom correction → lemma/theorem recomputation | primitive value、template、task family/regime combinations | executable program/dataflow | 1.000 / 0.485 | 1.000 / 1.000 | 291.54 / 398.50 | **FAIL** |

各任务权威说明与实现：

- Travel：[`causal-benchmark-dynamic-travel.md`](causal-benchmark-dynamic-travel.md) / [`dynamic_travel.py`](../code/causal_benchmarks/dynamic_travel.py)
- Shopping：[`causal-benchmark-shopping.md`](causal-benchmark-shopping.md) / [`dynamic_shopping.py`](../code/causal_benchmarks/dynamic_shopping.py)
- Search：[`causal-benchmark-search.md`](causal-benchmark-search.md) / [`dynamic_search.py`](../code/causal_benchmarks/dynamic_search.py)
- Formal：[`causal-benchmark-formal.md`](causal-benchmark-formal.md) / [`causal_formal.py`](../code/causal_benchmarks/causal_formal.py)

这些修复解决了“Exact-KV 是否足够”“query 是否泄漏 descendants”“train/test 是否隔离”
和“graph/serialization 是否 bundle”四个设计缺陷。它们没有自动解决更强的问题：在已知
schema 且领域规则可执行时，一个 causal learner 为什么必须优于规则程序。这个失败应当
成为论文的 stop rule，而不是继续换名字规避 baseline。

后续静态复核又把 task-validity 进一步收窄：Dynamic Search 的 episode-specific opaque
provenance 使 query 无法命名 descendants，可作为 hidden-dependency PASS，但其 learned arm
仍是 learned gate + deterministic provenance parser 的 hybrid；Shopping 与 Travel 分别可由
observable-regime impact table、source-to-impact-union lookup 复制，均为 PARTIAL；Formal 的
`intervention.kind` 暴露 active/inactive gate，在固定拓扑下为 NO-GO。因此“四项都有真实
propagation”不等于“四项都要求 learned hidden structure”。

## 3. Yujia 三部分实验审计

### 3.1 Simulation：must do

[`yujia_simulation_v2.py`](../code/yujia_simulation_v2.py) 定义 project-owned
write-hold-read DGP。一个 episode 是独立 trajectory；discovery 的一个回归 sample 是
`(X[t-1], U[t], X[t])`。变量为 `c,m,y,d1,d2,p1,p2` 的标量坐标；`h` 是 generator-only
latent variable。

五 seed、每 seed 240 episodes 的结果：

| Family | Pooled overall/read F1 | Regime-conditioned overall/read F1 | Grouped fallback |
|---|---:|---:|---:|
| linear observed | 0.580 / 0.647 | **1.000 / 1.000** | — |
| MLP observed | 0.516 / 0.533 | **1.000 / 1.000** | — |
| MLP latent | 0.447 / 0.409 | 0.800 / 0.667 | **1.000 / 1.000** |

latent 的 grouped arm 把两个有噪 measurement `p1,p2` 聚合为受控的 `h_group`。它是
Yujia 所说“先分组控制变量数”的一个 simulation fallback，不是从语言 embedding 恢复
latent dimension，也不是完整 LM scalability 方案。故本项结论是：observed nonlinear
simulation 已完成；latent identification 未完成；LM 维度 grouping 仍待真正实现。

### 3.2 Memory effectiveness / efficiency

#### 3.2.1 Four-task SelectionPlan + real API

DeepSeek dev v9 的 96-call decoder gate 完整通过；随后冻结的 4 task × 12 test episodes ×
6 arms 已执行 288/288 request rows。usage ledger 为 309 events、`$6.607622`；protocol/
result/ledger hash 审计完整。284 rows 可评分，4 个 full-state rows 在三次尝试后仍未满足
输出合同，作为 missing 保留，不记语义零分，所以 `full_scope_complete=true` 而
`experiment_complete=false`。

learned arm 在四个 task 上的 selection F1 和 valid-only endpoint 都是 1.0；总 input 为
71,381，full-state 为 175,735，费用分别 `$0.533` 与 `$2.957`。但这只是条件性执行/
efficiency 证据，原因有三：

1. v1 `domain_solver` 是 conservative potential reachability，不是仓库已有的 strongest
   executable rule/provenance/dataflow solver；
2. Travel/Shopping/Formal 有上述 structured shortcut；
3. ledger 的 25 个错误尝试中，24 个是 node-set semantic contract mismatch。旧策略把它们
   与工程格式失败一起重试，其中 11 个 request 被重试到可评分，故 valid-only 1.0 不是无偏
   的一次调用 endpoint reliability。

v1 原 artifacts 不覆盖、不 repair。完整矩阵、missing IDs、hash 与后续失败分类要求见
[`causal-api-six-arm-v1-results.md`](causal-api-six-arm-v1-results.md)。

#### 3.2.2 Anti-shortcut stop 与 v3 预注册

更强的 dev-only audit 不再只比较 Exact-KV。`source_union` 与 `query_signature` 在四项现有
task 上的 propagation sufficient-mask rate 都是 1.0，因此四项全部触发 necessity stop。
Search 仍可保留精确 routing/efficiency 问题，但不能用 endpoint sufficiency 证明 hidden
structure 必需。

独立 hidden-routing v2 也被 fail-closed：公平 train-enabled consistent-codebook program 与
learner exact tie；runtime history 暴露 100% potential-edge endpoint skeleton；多个
conservative superset 已 100% sufficient；四个“领域”的 normalized structural fingerprint
完全相同。故 artifact 为 `PARTIAL`、`all_domains_pass=false`。它只支持 latent-codebook
decoding / exact sparse-mask microbenchmark，没有调用第二轮 API。

下一版已先按 8-15 要求写清 sample、variable、trajectory、四个不同 DGP、non-idempotent
RepairPlan、strongest relational/black-box baselines 与 endpoint admission，见
[`hidden-mechanism-v3-preregistration.md`](hidden-mechanism-v3-preregistration.md)。该文档等待
Yujia double-check；在此之前不把 design 当结果，也不冻结 test/API。

#### 3.2.3 MemoryArena

真实 MemoryArena 的最强冻结证据是 IDs 111–120 的 compact-v3：query-ancestry 相对
noG 的 episode-mean PS 为 `−1.43` 点，在允许的 `−5` 点内；API input 从 718,215 降到
434,162，减少 **39.55%**，超过预注册的 30%，因此合取协议通过。

边界必须同时保留：

- query-ancestry 相对 long context 少 79.0% input、低 47.6% cost，但 wall duration
  **慢 8.9%**；“更快”不是普遍成立。
- compact-v3 同时改变 selection 与 serialization，39.55% 不能全部识别为 graph
  adjacency 的单独作用。
- 原 Travel 的 query surface 可由 `(person, day, slot)` parser 恢复；它对 causal
  discovery necessity 是 **NO-GO**，只对 structured-memory compression 是 PASS。
- 四个 T1 的 selection × serialization 已正交，但零 LLM 且共用 oracle value decoder；
  它们补的是 mechanism test，不替代真实 agent endpoint。

因此 Yujia 的 “记得更好、更快、更省”目前应拆成：更省有冻结正证据；效果有
PS non-inferiority 和相对 BM25 的正证据；速度是多轴 trade-off；learned causal
necessity 没有成立。

### 3.3 Trustworthiness / auditing / executable safety

P3-A 与 P3-B 必须分开：

- P3-A auditing：MINJA decisive path 为 22/76，ordered edge 3/3 seeds 找到、2/3 gated；
  AgentPoison label-free temporal ancestry 直接找到 1/2 poison records，冻结的 cluster
  expansion 覆盖 2/2。综合状态为 `SUPPORTED_WITH_IDENTIFICATION_BOUNDARIES`，不是新
  confirmatory binary PASS。
- P3-B mitigation：MINJA 与 AgentPoison 都只有 1/3 seed blocks 改善，两个冻结协议均
  `pass=false`。所以“根据结构介入并保证安全”的卖点当前实验上 **FAIL**。

这不抹掉 auditing 的支持性证据，但阻止把“能追溯可疑驱动”直接升级为“干预一定安全
有效”。权威源是 [`p3_hidden_driver_recovery_summary.json`](../results/real/p3_hidden_driver_recovery_summary.json)
与 [`p3-minja-causal-audit-results.md`](p3-minja-causal-audit-results.md)。

## 4. 指标与 literature review 决策

完整综述见 [`memory-evaluation-literature-review.md`](memory-evaluation-literature-review.md)。
项目以后固定按四层报告，禁止用上游 proxy 替代最终 endpoint：

| Setting | Primary | Secondary / diagnostic |
|---|---|---|
| Known-DGP simulation | edge/parent precision、recall、F1，按 lag/regime 分层 | pooled vs conditioned、seed variance、SID 类干预诊断 |
| Dynamic propagation | whole-episode state success、affected-result/state P/R/F1、negative controls | required-read recall、chain length/regime slices |
| Agent memory | 官方最终任务 success（Travel 用 PS）与 token/cost/latency Pareto | SPS、answerability、context recall、SR |
| Safety audit | label-free driver/record P/R/F1/AUPRC、held-out temporal ancestry | edge recovery 与 provenance diagnostics |
| Online mitigation | held-out ASR 与 benign utility 共主，跨 seed consistency | exposure、records removed、no-op、parse/API failures |

所有 retrieval arm 应匹配 context budget；所有系统比较应配对到共同 episode ID；selection
和 serialization 必须做二维消融；空 affected set 需要显式定义 precision/recall；不得只报
稀疏 full-state cell accuracy。

## 5. 8-15 遗留要求

| 要求 | 当前状态 | 处理 |
|---|---|---|
| 先写清 sample / variable / trajectory | **已完成** | 本文第 2、3 节及 machine-readable audit 的 `formulations` |
| 绑定具体 repo / benchmark | **已完成** | 每个 setting 均列本仓模块与外部 benchmark 边界 |
| plan 与 Yujia double-check | **外部待确认** | 仓库内部无法替 Yujia 签字；必须把本审计交她确认后再冻结论文 claim |
| memory 指标 literature review | **已完成** | 独立综述按 intrinsic/downstream/efficiency/safety 分层 |
| scalability 的变量分组退路 | **部分完成** | simulation 的 measured-proxy group 已实现；LM representation 分组尚未实现 |

## 6. 允许与禁止的论文表述

允许：

- regime conditioning 在 known observed SCM/MLP 上恢复真实结构；
- 四个 task 证明只改 query key 不够，并证明 train-only learned impact selector 能在
  novel split 胜过 generic matched retrieval、减少 context；
- four-task v1 证明 value-free SelectionPlan 能接入真实 API decoder，但只在合同有效响应
  条件下支持执行/效率；
- MemoryArena compact-v3 通过自己的冻结 effectiveness/input-efficiency 判据；
- recovered temporal structure 对 hidden-driver audit 有支持性价值，但有识别边界。

禁止：

- 四个 task 中任何一个证明 learned causal graph 相对领域程序不可替代；
- 原 Travel 是 causal-memory 主结果；
- T1 已学习结构方程或完成自然语言到 intervention 的端到端识别；
- grouped proxy 等于 latent causal discovery 或 LM scalability 已解决；
- 当前 mitigation 能保证安全；
- 方法在所有 latency/cost 维度都更快。
- v1 valid-only endpoint 代表一次调用可靠性，或其 learned arm 已胜 strongest domain solver。

## 7. 下一冻结点

当前不应继续通过调 selector 在这四个 task 上追逐一个已经被 domain program 饱和的
accuracy 数字。下一主实验只有两条科学上诚实的选择：

1. 把主张收窄为 dependency-aware memory maintenance/compactness，并把强 domain solver
   作为竞争方法而非需要击败的“非因果”稻草人；或
2. 设计 domain mechanism 对 agent 不可用、只能从多环境 observational/interventional
   trajectory 估计，且 test intervention 需要组合泛化的环境；预注册 learner 相对 oracle
   source + strongest non-causal/domain baseline 的最小优势。

无论选哪条，P3-B 都需要新冻结干预策略、held-out seeds、ASR 与 benign utility 共主指标，
才能再次尝试 actionable-safety claim。最终选项与 claim wording 必须由 Yujia 外部确认。

当前仓库已把第二条具体化为 Hidden Mechanism v3 预注册，但尚未获得 Yujia external
double-check，故不能把“文档完成”写成“实验完成”。
