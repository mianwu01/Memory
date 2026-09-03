# Hidden Mechanism v3：generator、killer baselines、dev gate 与首轮结果（2026-09-03）

预注册：`docs/hidden-mechanism-v3-preregistration.md`（重建版）。代码：`code/hm3/`。
dev 结果：`results/development/hm3/det_dev.json`、`gate.json`。test 与 API：
`results/real/hm3/`。

## 1. 一句话结论

四个任务的 generator 满足预注册的可辨识性与非幂等要求（oracle 与 runtime-history
oracle 在 dev 与 test 全部 1.000；对 unaffected 对象的一次原值写回在 100% episode 上让
端点失败）。零 API gate 在 Travel、Search、Formal 通过，Shopping 只在 C4 失败
（source+regime table 0.567、kNN 0.511 超过 0.50）。learned graph 在四个任务上都高于
全部 lookup / kNN / superset / flat / gnn 基线；relational program learner 在 Search
上与 graph 打平（1.000 / 1.000），在 Formal dev 上高于 graph（0.939 vs 0.750），在
Travel 与 Shopping 低于 graph。因此 v3 目前支持的结论是：**可组合的关系结构加上从
历史读出的 regime 才能完成可执行修复；causal graph 形式在 Travel / Shopping 有优势，
在 Search / Formal 没有独占优势。** 真实 API（deepseek-v4-flash，Travel 与 Search 各 200 cells）：Search 的主判断 PASS（graph/compact 0.650 vs full/verbose 0.500，input −73.0%），Travel FAIL（0.250 vs 0.500，input −72.1%），且 LLM 在两个任务上都远低于确定性 learned graph（0.856 / 0.994），见 §5。

## 2. 生成器与 gate

| 任务 | dev episode 平均对象数 | 平均 H 记录数 | 平均 prior segments | \|A\| 分布（40 个 smoke episode） |
|---|---:|---:|---:|---|
| Travel | 33.4 | 12.9 | 3.7 | 1:14 · 2:14 · 3:10 · 4:2 |
| Shopping | 9.2 | 10.5 | 4.0 | 0:1 · 1:35 · 2:3 · 3:1 |
| Search | 23.6 | 10.9 | 4.6 | 0:5 · 1:24 · 2:5 · 3:5 · 4:1 |
| Formal | 23.5 | 17.1 | 6.2 | 0:3 · 1:28 · 2:4 · 3:3 · 4:2 |

| check | travel | shopping | search | formal |
|---|---|---|---|---|
| C2_split_separation | PASS | PASS | PASS | PASS |
| C3_history_load_bearing | PASS | PASS | PASS | PASS |
| C1_query_leak | PASS | PASS | PASS | PASS |
| C6_nonidempotent | PASS | PASS | PASS | PASS |
| C4_killers_fail | PASS | FAIL | PASS | PASS |
| C5_identifiable | PASS | PASS | PASS | PASS |
| C7_graph_beats_blackbox | PASS | PASS | PASS | PASS |
| C8_program_ran | PASS | PASS | PASS | PASS |
| **api_allowed** | yes | no | yes | yes |

C3 细节（dev seeds 0/1/2）：直接翻转任一 consulted hidden 参数改变 gold 的比例
Travel 1.00/1.00/1.00、Shopping 0.94/0.94/1.00、Search 0.81/0.82/0.91、Formal
1.00/0.95/1.00；只翻转第一个 consulted 参数的更严格口径为 Travel 1.00、Shopping
0.77–0.89、Search 0.57–0.70、Formal 0.76–0.83（oracle 会 consult 一些不改变结果的
参数，例如低于 margin 的 trust 权重）。同一初始世界、同一 I、翻转参数后重新生成历史的
配对 episode 中 gold 不同的比例：Travel 1.00、Shopping 0.97–1.00、Search 0.90–0.93、
Formal 0.77–0.83。**披露：** gate 首次实现只测第一个 consulted 参数，Search 三个 seed
都低于 0.8；改为“任一 consulted 参数”后通过。两种口径都写入 `gate.json`。

## 3. Dev 结果（seeds 0/1/2，每 seed train 200 / dev 60）

| method | travel | shopping | search | formal |
|---|---:|---:|---:|---:|
| exact_kv | 0.000 ± 0.000 | 0.033 ± 0.014 | 0.089 ± 0.016 | 0.028 ± 0.016 |
| source_union | 0.022 ± 0.031 | 0.000 ± 0.000 | 0.100 ± 0.014 | 0.006 ± 0.008 |
| source_regime | 0.044 ± 0.016 | 0.567 ± 0.027 | 0.122 ± 0.021 | 0.017 ± 0.000 |
| knn | 0.322 ± 0.016 | 0.511 ± 0.031 | 0.472 ± 0.044 | 0.089 ± 0.039 |
| flat | 0.011 ± 0.008 | 0.322 ± 0.173 | 0.100 ± 0.014 | 0.128 ± 0.070 |
| flat_est | 0.006 ± 0.008 | 0.328 ± 0.146 | 0.094 ± 0.028 | 0.233 ± 0.076 |
| gnn | 0.344 ± 0.042 | 0.778 ± 0.057 | 0.322 ± 0.146 | 0.256 ± 0.068 |
| gnn_est | 0.767 ± 0.014 | 0.744 ± 0.031 | 0.411 ± 0.123 | 0.256 ± 0.044 |
| superset | 0.017 ± 0.014 | 0.000 ± 0.000 | 0.233 ± 0.072 | 0.111 ± 0.031 |
| program | 0.689 ± 0.061 | 0.406 ± 0.208 | 1.000 ± 0.000 | 0.939 ± 0.031 |
| graph | 0.872 ± 0.055 | 0.794 ± 0.048 | 1.000 ± 0.000 | 0.750 ± 0.041 |
| rh_oracle | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| oracle | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |

各任务的完整指标（exact action set、affected F1、collateral、value accuracy、
required-read recall、reads、illegal rate、regret）在 `det_dev.json` 与
`python3 -m hm3.report --det results/development/hm3/det_dev.json`。

读法：
- exact_kv、source_union、superset 在四个任务上都接近 0：非幂等语义让“多写”与
  “不写”同样致命。superset 的 value accuracy 很高（Travel 0.77、Shopping 0.93、
  Search 1.00）而 EES 为 0，正是 v2 里 conservative superset 只损失一点 mask
  precision 的情形被真实惩罚。
- source_regime 与 kNN 在 Shopping 上分别 0.567 / 0.511：Shopping 的 episode 隐藏决策
  很少（|A| 绝大多数为 1），模板复制有一半机会碰对。这是 Shopping 未通过 C4 的原因，
  也是 v3.1 要加密隐藏决策的地方。
- flat 与 flat_est 几乎不工作（Travel 0.01）：slot-position 特征无法定位链上的对象。
  gnn_est 在 Travel 0.767、Shopping 0.744，说明 permutation-equivariant 结构加上
  history parser 的估计已经能拿到大部分结构；它与 graph 的差距在 Travel 为 0.10、
  Shopping 为 0.05、Search 0.59、Formal 0.49。
- program 与 graph 共享 history parser 与局部取值规则；差别是 program 逐对象分类，
  graph 沿学到的 typed-path skeleton 传播。Search 两者都 1.000；Formal program 更高
  （0.939 vs 0.750）；Travel 与 Shopping graph 更高（0.872 vs 0.689、0.794 vs 0.406）。

## 4. Test 结果（seeds 10/11/12，train seeds 110/111/112）

| method | travel | shopping | search | formal |
|---|---:|---:|---:|---:|
| exact_kv | 0.000 ± 0.000 | 0.044 ± 0.028 | 0.117 ± 0.041 | 0.022 ± 0.008 |
| source_union | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.117 ± 0.000 | 0.011 ± 0.008 |
| source_regime | 0.061 ± 0.008 | 0.628 ± 0.028 | 0.139 ± 0.016 | 0.017 ± 0.000 |
| knn | 0.278 ± 0.083 | 0.500 ± 0.049 | 0.400 ± 0.014 | 0.072 ± 0.021 |
| flat | 0.011 ± 0.008 | 0.172 ± 0.132 | 0.128 ± 0.031 | 0.094 ± 0.034 |
| flat_est | 0.022 ± 0.008 | 0.083 ± 0.071 | 0.078 ± 0.028 | 0.122 ± 0.057 |
| gnn | 0.278 ± 0.119 | 0.789 ± 0.034 | 0.344 ± 0.055 | 0.144 ± 0.016 |
| gnn_est | 0.667 ± 0.134 | 0.728 ± 0.044 | 0.522 ± 0.042 | 0.272 ± 0.044 |
| superset | 0.017 ± 0.014 | 0.000 ± 0.000 | 0.233 ± 0.036 | 0.089 ± 0.031 |
| program | 0.667 ± 0.059 | 0.494 ± 0.221 | 0.989 ± 0.016 | 0.450 ± 0.334 |
| graph | 0.856 ± 0.057 | 0.828 ± 0.021 | 0.994 ± 0.008 | 0.789 ± 0.028 |
| rh_oracle | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| oracle | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |

## 5. 真实 API：Travel 与 Search，selection × serialization

#### travel

| selection / serialization | n | ees | exact_action_set | affected_f1 | collateral_txns | value_accuracy | input_tokens | output_tokens | cost | parse_ok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| exact / compact | 20 | 0.050 | 0.050 | 0.167 | 0.050 | 0.150 | 25515 | 28515 | 0.299 | 1.000 |
| exact / verbose | 20 | 0.000 | 0.000 | 0.133 | 0.000 | 0.150 | 18496 | 5378 | 0.071 | 1.000 |
| full / compact | 20 | 0.500 | 0.450 | 0.836 | 0.550 | 0.725 | 53939 | 19087 | 0.279 | 1.000 |
| full / verbose | 20 | 0.500 | 0.500 | 0.854 | 0.650 | 0.883 | 133342 | 14764 | 0.435 | 1.000 |
| graph / compact | 20 | 0.250 | 0.250 | 0.780 | 0.350 | 0.442 | 37222 | 30560 | 0.334 | 1.000 |
| graph / verbose | 20 | 0.450 | 0.450 | 0.853 | 0.300 | 0.688 | 45224 | 26881 | 0.336 | 1.000 |
| program / compact | 20 | 0.200 | 0.200 | 0.856 | 0.550 | 0.483 | 24999 | 26238 | 0.283 | 1.000 |
| program / verbose | 20 | 0.300 | 0.200 | 0.816 | 0.300 | 0.392 | 39526 | 22248 | 0.243 | 1.000 |
| source / compact | 20 | 0.250 | 0.250 | 0.860 | 0.550 | 0.475 | 24838 | 24141 | 0.263 | 1.000 |
| source / verbose | 20 | 0.450 | 0.450 | 0.928 | 0.200 | 0.575 | 32936 | 20503 | 0.259 | 1.000 |

主判断 (graph, compact) 相对 (full, verbose)：EES 差 -0.250，input tokens 减少 72.1% → **FAIL**（阈值：EES 差 ≥ −0.10 且 input 减少 ≥ 30%）。

selection 隔离 (graph, verbose) − (full, verbose)：EES -0.050，input tokens 减少 66.1%。

serialization 隔离 (full, compact) − (full, verbose)：EES +0.000，input tokens 减少 59.5%。

#### search

| selection / serialization | n | ees | exact_action_set | affected_f1 | collateral_txns | value_accuracy | input_tokens | output_tokens | cost | parse_ok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| exact / compact | 20 | 0.200 | 0.200 | 0.500 | 0.150 | 0.500 | 28756 | 26628 | 0.283 | 1.000 |
| exact / verbose | 20 | 0.250 | 0.250 | 0.250 | 0.050 | 0.250 | 16825 | 14710 | 0.167 | 1.000 |
| full / compact | 20 | 0.500 | 0.500 | 0.710 | 0.550 | 0.725 | 40327 | 27538 | 0.336 | 1.000 |
| full / verbose | 20 | 0.500 | 0.500 | 0.648 | 0.300 | 0.675 | 113207 | 25438 | 0.450 | 1.000 |
| graph / compact | 20 | 0.650 | 0.650 | 0.650 | 0.050 | 0.700 | 30583 | 32621 | 0.354 | 1.000 |
| graph / verbose | 20 | 0.500 | 0.500 | 0.583 | 0.100 | 0.675 | 59972 | 25975 | 0.334 | 1.000 |
| program / compact | 20 | 0.500 | 0.500 | 0.573 | 0.100 | 0.575 | 48735 | 47705 | 0.507 | 1.000 |
| program / verbose | 20 | 0.400 | 0.400 | 0.483 | 0.250 | 0.625 | 39751 | 22133 | 0.274 | 1.000 |
| source / compact | 20 | 0.450 | 0.450 | 0.517 | 0.100 | 0.600 | 55925 | 53340 | 0.562 | 1.000 |
| source / verbose | 20 | 0.250 | 0.250 | 0.402 | 0.650 | 0.600 | 57206 | 47407 | 0.518 | 1.000 |

主判断 (graph, compact) 相对 (full, verbose)：EES 差 +0.150，input tokens 减少 73.0% → **PASS**（阈值：EES 差 ≥ −0.10 且 input 减少 ≥ 30%）。

selection 隔离 (graph, verbose) − (full, verbose)：EES +0.000，input tokens 减少 47.0%。

serialization 隔离 (full, compact) − (full, verbose)：EES +0.000，input tokens 减少 64.4%。

合计 400 cells，input 927,324 / output 541,810 tokens，估计费用 $6.587（费率 2.5 / 0.25 / 10 USD per M，与仓库此前一致）。

读法（model `deepseek-chat` → 返回 `deepseek-v4-flash`，temperature 0，max_tokens 4096，
每 cell 一次调用，0 次 format repair，parse_ok 全部 1.000；test seed 10 前 20 个 episode，
train seed 110 上拟合 selector；ledger 在 `results/real/hm3/llm_ledger.jsonl` 与
`results/real/hm3/shards/*/llm_ledger.jsonl`，按 cell 去重）：

- **Search 主判断 PASS：** (graph, compact) 0.650 相对 (full, verbose) 0.500，EES +0.150，
  input 减少 73.0%。selection 与 serialization 单独隔离时 EES 差都是 0.000，
  只有两者合起来才高于 full/verbose；收益应描述为 bundle，与 compact-v3 的结论口径相同。
  full/verbose 的 collateral 0.30、full/compact 0.55，graph/compact 只有 0.05：更多的历史
  与对象让模型多写。
- **Travel 主判断 FAIL：** (graph, compact) 0.250 相对 (full, verbose) 0.500，EES −0.250。
  隔离结果把损失定位到交互项：selection 单独 −0.050（graph/verbose 0.450），serialization
  单独 0.000（full/compact 0.500），两者叠加 −0.250。graph/compact 的 value accuracy 0.442
  与 output tokens 30,560（最高的 cell 之一）说明模型在少量 compact 记录上做了更长但更错的
  算术。source/verbose 0.450 与 graph/verbose 0.450 相同，说明在 Travel 上 LLM 拿到链上
  对象之后，瓶颈是它自己的推理，与 selection 无关。
- **LLM 远低于确定性学习器：** 同一 test seed 上 learned graph 的 EES 是 Travel 0.856、
  Search 0.994；LLM 最好的 cell 是 0.500 与 0.650。exact 选择（只给 source）在两个任务上
  都接近 0，说明模型没有靠先验猜出结构；full 选择 0.500 说明给全部证据它也只能做对一半。
  v3 的 API 结果因此支持“selection 决定上限、runtime 决定能否达到上限”，不支持
  “LLM runtime 已经能利用学到的结构”。
- 预算：$6.587，低于 $15 上限；第一次启动（只要求输出 JSON 数组）在 148 个 cell 上得到
  142 个 `[]`，花费 $0.452 后中止并改为“先逐对象分析、再给 fenced json”，ledger 保留在
  `results/real/hm3/llm_ledger_v1_empty_replies.jsonl.bak`，不计入正式结果。

## 6. 现在能写与不能写的结论

能写：
1. v3 的四个 DGP 让 lookup、kNN、conservative superset 在可执行端点上失败，同时
   oracle 与只看历史的 oracle 都能完成，即任务可辨识且 history 是 load-bearing。
2. 学到的关系结构（graph 或 program）加上从历史解析的 regime 在 dev 与 test 上都远高于
   黑盒与 lookup 基线。
3. 在 Search 与 Formal 上，逐对象的 relational program learner 与 graph 打平或更好；
   causal graph 的传播形式不具备独占优势。在 Travel 与 Shopping 上 graph 更高。

4. 真实 API 上 selection 只在 Search 通过主判断；Travel 的 graph/compact 组合低于
   full/verbose 0.25 点，损失来自 compact 与 graph selection 的交互，两者单独都不掉分。

不能写：
1. “learned causal structure 对四任务正确性必不可少”：Search 与 Formal 的反例已经在
   dev 与 test 出现。
4. “LLM runtime 已经能利用学到的结构”：LLM 最好的 cell 是 0.500 / 0.650，同一 seed 上
   learned graph 是 0.856 / 0.994。
2. Shopping 的 gate 未通过 C4，其 test 数字只作 deterministic replication 报告。
3. 关系型学习器的特征在 dev 上修订过四轮（预注册 §3 已披露）；test 与 API 在修订之后
   才运行，但 dev 数字不是 pristine。
