# Hidden Mechanism v3 预注册（重建版，2026-09-03，正式输出前冻结）

## 0. 来源与状态

本文件在 2026-09-03 的仓库中并不存在；`docs/`、另一分支
`claude/memoryagentbench-memoryarena-5415kl`、git reflog 与备份目录都没有它，也没有
dynamic/formal v1、dev killer audit、real-API v1（288 requests / $6.607622）和
hidden-routing v2 的代码或结果。本文件根据 2026-09-03 用户给出的 P2 问题清单与
v3 方案逐条重建，并记录 double-check 时发现的问题和处理方式。凡是方案原文没有、
由本轮补充的设计，用 **[补充]** 标出。

冻结顺序：本文件 → generator / killer baselines / dev gate 实现 → dev seeds 上跑
gate → gate 通过的 setup 才进入 test split 与真实 API。dev 结果只用于 gate 判断与
方法选择；test seeds 与 API 输出在 gate 之后才产生。

## 1. 问题定义

P2 要证明的是：学到 hidden temporal causal structure 之后，memory 维护更准、更省。
v1/v2 只证明了 structured memory / compression 有用，四个 lookup baseline 的
propagation sufficient-mask rate 都是 1.0，而且 selection 与 serialization 混在一起。

v3 把任务改成

> learned hidden mechanism → causal memory maintenance → executable downstream repair

一个 episode 是 `(H, S0, I, A, S1, R)`：

| 符号 | 含义 |
|---|---|
| H | 干预前历史：更早的干预以及环境自动效果、修复事务各自的结果记录 |
| S0 | pre-state：对象、字段、link、revision、status |
| I | 干预：只暴露 source 对象和它的新值 |
| A | oracle 修复事务 |
| S1 | 执行 I 与 A 之后的 post-state |
| R | receipt：intervention / auto / txn 条目的账本 |

Test 方法只看 `(H, S0, I)`。graph、affected nodes、required reads、oracle actions、
post-state 对方法不可见。

### 1.1 Query 只暴露 source

Query 形如 “Flight F68 (Lena, day 2) now arrives at 18:15.” 或
“Document D77 is now published.”，只含 source id 与新值。gate C1 机器检查 query 与
I 的 JSON 里不出现任何下游 id，也不出现 gate 词汇。

### 1.2 输出是非幂等 transaction

```
{"op": "shift_reservation", "object_id": "S12", "expected_revision": 1, "payload": {"checkin": 1205}}
```

每个手动事务都会：revision +1、消耗一个 change token、按 op 收费、丢失 price lock、
写入 receipt。即使把原值写回也一样。`expected_revision` 与当前 revision 不符即为
非法。环境自动效果（auto）同样使 revision +1，但不收费、不消耗 token。因此对一个
已被环境自动更新的对象再写一次，会因为 revision 过期而非法；对 unaffected 对象写回
原值，会让 post-state 与 receipt 都偏离 oracle。conservative superset 在这里真实失败。

**[补充]** receipt 以多重集比较（kind, op, object, rev, fee, token）；每个 plan 对同一
对象只允许一个手动事务，同一对象需要改多个字段时合并进一个 payload。

### 1.3 Primary metric

```
Executable Exact Success (EES) = 全部事务合法 AND post_state == oracle post_state AND receipt == oracle receipt
```

同时报告：exact action set、affected P/R/F1、collateral transactions、required-read
recall、value accuracy、utility/regret（fee + 5 × token 相对 oracle）、input/output
tokens、cost、latency。Mask F1 只作诊断。

## 2. 四个 DGP

四个任务共用 `code/hm3/core.py` 的对象 / 事务 / receipt 引擎，机制各不相同：

| 任务 | 结构 | hidden 参数（按 episode 抽样，按可见 key 索引） | 自动效果 |
|---|---|---|---|
| Travel | flight → transfer → stay → {dinner, activity}，dinner → bundle | `auto_rebook[provider]`、`buffer[provider]`（连续）、`enforce_late[hotel]`、`late_seating[restaurant]`、`linked[vendor]` | transfer 自动跟随航班（若 auto_rebook） |
| Shopping | base line → accessories（compatibility factor graph）、promo（hypergraph）、cart budget（全局重优化） | `compat[base|acc]`、`strict_promo[promo]`、`auto_promo`、`enforce_budget` | promo 自动开关（若 auto_promo）、cart total 重算 |
| Search | doc → base claim → composite claim（AND/OR，两层） | `trust[class] ∈ {0,1,2}`、`dedup`、`policy ∈ {propagate, ignore}`、`auto_base` | evidence_effect 记录、base verdict 自动更新（若 auto_base） |
| Formal | def → scope → lemma，lemma → dependents（proof DAG），section/local shadowing | `section_shadows`、`sensitive[lemma|name]`、`stmt_sensitive[lemma]`、`auto_local` | rebind（总是 auto）、local 块 recheck（若 auto_local） |

每个 hidden 参数都能由 H 中的一个 outcome witness 精确恢复：例如
`buffer = pickup_new − arrival_new`，`late_seating` 由过去的 dinner shift/cancel 决定，
`trust[class]` 由 evidence_effect 的 weight/reason 决定，`sensitive[l|n]` 由上一次
bump 后 l 是否 recheck 决定。witness 全部是结果记录，没有任何 policy 声明记录。

**[补充] 可辨识性由构造保证。** generator 先随机生成若干 prior segments，再选 test
intervention，然后用 runtime-history parser 检查 oracle 实际 consult 的每个参数是否能从
H 恢复；缺的参数通过定向 prior intervention（在副本上模拟并验证）补齐，补不齐就重采样
world。每个 consult 的参数家族还会再补一个其他 key 的 distractor witness，防止
episode 级聚合统计（自动事件数量、取消数量）泄露 query 触及实体的 regime。

**[补充] 可见状态泄露检查。** Travel 初始 pickup 原来等于 arrival + buffer，直接泄露
buffer，已改为独立的手动预订时间。可见的 late_arrival=1 蕴含 enforce_late=1、S0 中
composite verdict 与 promo 状态与 hidden policy 一致，这三处保留，属于 visible regime
cue，`source + visible-regime table` 能利用其中一部分。

## 3. 方法

所有非 oracle 方法共用同一份训练数据 `(H, S0, I, A, S1, R)`。

**[补充] 结构与取值分离。** 确定性方法输出 structural plan：对哪些对象、什么 op、
auto 还是 txn、写哪些字段。取值由共享 executor（`core.plan_to_txns`）按领域的局部规则
在 scratch state 上顺序计算，scratch 反映干预与此前已计划的效果，因此上游漏判或误判
会污染下游取值。executor 能用的 regime 参数只来自该方法**实际读取**的历史记录
（`restricted_est`），不读历史的方法拿不到 hidden 参数。LLM full runtime 自己给出取值。

| 方法 | 看到什么 | 结构决策 |
|---|---|---|
| exact_kv | source | 空 plan |
| source_union | 训练集里同 source 类型出现过的 impact template 的并集 | 只要出现过就写 |
| source_regime | 同上 + 候选对象的可见类别字段与 status 做细 key | 多数票，退化到粗 key |
| knn | episode 级特征（source、对象计数、H 聚合计数）；k=5 | 邻居 template 投票 |
| flat / flat_est | 对象 slot-position、类型、数值字段、自身历史计数；`_est` 加 history parser 的估计 | HistGradientBoosting 逐对象 |
| gnn / gnn_est | 同上但 permutation-equivariant，3 层 relation-typed message passing | 逐节点分类 |
| superset | 学到的 typed-path skeleton，所有边强制激活 | 全部可达对象都写 |
| program | typed path、witness 统计、regime 估计、1-hop 邻居上下文、parent-relative 差分；两遍 iterative closure | HistGradientBoosting 逐对象 |
| graph | typed-path skeleton + 每条边一个 gated 局部机制（决策树：parent 新值与 child 字段差分、regime 估计） | 从 source 沿 skeleton 传播，值实时进入 scratch |
| rh_oracle | 真实机制，参数由 H 解析 | — |
| oracle | 真实机制与参数 | — |

history parser（`infer_params`）是共享基础设施：graph、program、flat_est、gnn_est 都拿
它的输出当特征；差别在于是否用关系结构与传播来组合这些估计。**预先声明：** program
与 graph 打平是可能的诚实结果，届时结论写成“可组合关系结构有用，causal graph 不具备
独占优势”。

**[补充] 类型一致解码。** 分类型基线只在训练中见过该对象类型的标签里取 argmax。

**[补充] dev 阶段对关系型学习器的特征修订（在 gate 与 test 之前，全部披露）。**
在 dev seed 0 上观察到 program 与 graph 的失败集中在三类局部特征无法表达的判断：
超边条件（promo 是否仍满足全部 required categories 与 brand）、同类兄弟排序（预算
超支时移除“最可选、最贵”的一行）、以及“聚合后取值是否真的改变”（Search 的
verdict、Formal 的 cert）。为此给 program 与 graph 同时加入四类通用特征：
(a) 候选对象与 parent 的 dict 字段逐 key 相等指示；(b) 1-hop / 2-hop 邻域 token 重叠
计数；(c) 同类兄弟的数值字段排名；(d) 与 parent token 关联的 regime 估计
（`sensitive[lemma|name]` 里 name 是刚被 bump 的定义）；以及 (e) would-change：在
当前 scratch 上模拟该模板多数 op 的局部取值规则，看值是否变化。(e) 把领域声明的
局部取值规则当作特征暴露给关系型学习器；这与 executor 用同一规则计算取值是一致的，
黑盒基线（flat / gnn）不使用它。graph 的传播引擎同时允许已判定对象被新的 parent
再次触发（预算级联需要 cart → line → cart 的第二轮）。program 改为只在闭包上下文
（S1 邻居取值）上训练，测试时迭代三遍。dev seed 0 单次试验的 graph EES：Travel
0.83、Shopping 0.73、Search 1.00、Formal 0.80；这些数字是开发观察，正式 dev 表以
`results/development/hm3/det_dev.json` 为准。

## 4. Selection × Serialization

LLM 臂固定二维消融：selection ∈ {exact, source, graph, program, full} ×
serialization ∈ {verbose JSON, compact 行}。selection 决定哪些对象与历史记录进入
prompt；serialization 决定同一集合怎么写。主判断固定为 (graph, compact) 相对
(full, verbose)：**EES 差 ≥ −0.10 且 input tokens 减少 ≥ 30%**。次级：
(graph, verbose) − (full, verbose) 隔离 selection；(full, compact) − (full, verbose)
隔离 serialization；(program, ·) 与 (graph, ·) 并列报告。

## 5. 零 API gate（dev seeds 0/1/2）

| 检查 | 阈值（本文件写下后不再改） |
|---|---|
| C1 query leak | query 与 I 不含任何下游 id，不含 gate 词汇：0 处泄露 |
| C2 split separation | train/dev/test episode id 两两不交；topology hash 重叠 = 0 |
| C3 history load-bearing | 直接翻转 relevant hidden 参数改变 gold 的比例 ≥ 0.8；同一初始世界、同一 I、翻转参数后重新生成 H 的配对 episode 中 gold 不同的比例 ≥ 0.5，配对数 ≥ 10；另报告可见摘要完全相同的配对里 gold 不同的比例 |
| C4 killers fail | exact_kv、source_union、source_regime、knn、superset 的 dev EES 各 ≤ 0.50 |
| C5 identifiable | oracle 与 rh_oracle 的 dev EES = 1.0 |
| C6 non-idempotent | oracle plan 加一次对 unaffected 对象的原值写回：100% episode 端点失败 |
| C7 graph > black box | graph 的 EES 在 ≥ 2/3 dev seeds 上高于 flat、flat_est、gnn、gnn_est，且均值更高 |
| C8 program ran | program 有结果；`tie` = \|graph − program\| ≤ 0.05；`program_better` = program > graph + 0.05 |

`api_allowed[domain]` = C1–C7 全部通过。C8 只报告。真实 API 只为 Travel 与 Search；
Shopping 与 Formal 做 deterministic replication。

**[披露]** 在写下 C4 阈值之前，Travel 已经做过 80/120 个训练 episode 的 smoke run；
那次 kNN 为 0.50–0.58，原因是许多 episode 只有一个 hidden 二元决策，模板复制有一半
机会碰对。随后把 Travel 的干预采样改为更常触发 late-cutoff / dinner-conflict，并把
bundle 概率提高到 0.75，使每个 episode 平均含多个 hidden 决策；改动在 gate 与全量
dev run 之前完成。

## 6. 数据边界

- dev：seeds 0/1/2，每 seed train 200 / dev 60；gate、方法选择、prompt 检查只用 dev。
- test：seeds 10/11/12，train seeds 110/111/112（offset 100）；每 seed test 60。
- API：Travel 与 Search，test seed 10 的前 20 个 episode，5 × 2 cells，共 400 requests；
  model `deepseek-chat`（记录 returned model）、temperature 0、max_tokens 2048；预算上限
  $15；retry 只允许一次 format-only repair，node set / identity / value / revision 错误
  为 terminal semantic failure，不重试；append-only ledger，resume 只跳过已完成 cell。
- 凭证只经 `code/run_with_local_deepseek.py` 进入子进程环境，不进入任何结果文件。

## 7. 现在能写与不能写的结论

gate 与 test 之前，P2 的可写结论仍然是：structured / dependency-aware memory 在
MemoryArena 上保持效果并减少输入；compact SelectionPlan 能驱动 value update。
“learned causal structure 对四任务正确性必不可少”要等 v3 的 test 与 API 结果。


## 8. Test 之后的追加（2026-09-03，全部 post-hoc，不改变 §5 的判断）

- `program_reg`：program learner 的正则化配置（max_iter 150、lr 0.05、min_samples_leaf 10、
  L2 1.0、max_leaf_nodes 15），因为默认配置在 Formal 的 train seed 110 上连自己的训练
  episode 都只拟合 9/40。在 test 已经评分之后加入并在 dev/test 全部重跑；`program` 的
  原始数字保持为 confirmatory。
- `shopping31`：Shopping 的加密隐藏决策变体，只跑了 dev 与 gate（C4 仍失败：source+regime
  0.533），没有 test split。
- Travel thinking-enabled 重跑：2 cells 后中止（reasoning 占满 8192 completion tokens，
  无可见答案），$0.334，不计入 §5。
