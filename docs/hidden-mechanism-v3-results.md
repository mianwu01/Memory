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
在 Search / Formal 没有独占优势（fresh seeds 20–22 上 graph 0.883 / 0.800 / 1.000 / 0.717，program_reg 0.667 / 0.828 / 0.994 / 0.889，§7.2）。** Shopping v3.2 通过全部 gate（§7.3）。真实 API 四轮（§5、§7.1、§7.5、§7.6）：n=20/cell 的两轮点估计判断互相矛盾；n≈64/cell 的 round 3/4 给出稳定结论——graph selection（含 witness 闭包）把 input 减少 70–74%，EES 低 0.10–0.19（Travel −0.190 [−0.333, −0.048]，Search −0.104 [−0.254, +0.045]），非劣性（−0.10）未达到；LLM 最好的 cell 远低于确定性 learned graph。round 1 细节：Search 的主判断 PASS（graph/compact 0.650 vs full/verbose 0.500，input −73.0%），Travel FAIL（0.250 vs 0.500，input −72.1%），且 LLM 在两个任务上都远低于确定性 learned graph（0.856 / 0.994），见 §5。

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

## 5.1 Follow-up（2026-09-03，test 与 API 之后，全部为 post-hoc）

**Formal 上 program learner 的 seed 不稳定性是拟合失败。** test 三个 train seed 的
program EES 为 0.150 / 0.283 / 0.917（seed 110 / 111 / 112），dev 三个 seed 为 0.983 /
0.917 / 0.917。用 train seed 110 拟合的默认 HistGradientBoosting（max_iter 200、
lr 0.08、min_samples_leaf 4）在**自己的训练 episode** 上只有 9/40 全对，训练集里出现了
两个各只有 2 个样本的稀有标签；换成更强正则的配置（max_iter 150、lr 0.05、
min_samples_leaf 10、L2 1.0、max_leaf_nodes 15）后训练 40/40、test 52/60。这个配置作为
`program_reg` 加入并在 dev 与 test 全部重跑（数字见下表）；`program` 的原始数字保留为
confirmatory 结果，`program_reg` 是 post-hoc 变体。

| method（dev / test EES） | travel | shopping | search | formal |
|---|---:|---:|---:|---:|
| program | 0.689 / 0.667 | 0.406 / 0.494 | 1.000 / 0.989 | 0.939 / 0.450 |
| program_reg | 0.678 / 0.656 | 0.867 / 0.828 | 1.000 / 0.989 | 0.894 / 0.933 |
| graph | 0.872 / 0.856 | 0.794 / 0.828 | 1.000 / 0.994 | 0.750 / 0.789 |

**Travel 的 thinking-enabled 重跑不可行（2 cells，$0.334 后中止）。** 在
`deepseek-v4-flash` 上启用 `thinking` 后，graph/compact 的前两个 cell 都在 8192 completion
tokens 内没有产出任何可见答案（finish=length，reasoning 占满预算），format repair 再耗
8192 tokens 仍为空；每 cell $0.167。按此推算 40 cells 约 $6.7 且大概率全部无效，因此
没有继续。Travel 交互项损失的解释仍停留在 §5 的推理瓶颈；是否用更大的 completion 预算或
另一个模型重跑，留给 Yujia 决定。ledger 在 `results/real/hm3/exploratory_thinking/`。

**Shopping v3.1（`shopping31`，dev only）。** 让每个 base 携带全部 accessory 类别、2–3 个
promotion（brand 取自它要求的某条 line，使 strict 规则当前可满足）、预算 slack 收紧到
0–60、干预采样只取“扰动最多”的变体。dev 上 |A| 分布从 v3 的 1:51/60 变为 1:41 · 2:18 ·
3:1。gate（dev seeds 0/1/2）：C1/C2/C3/C5/C6/C7 通过，C4 仍失败：kNN 从 0.511 降到
0.383，但 source+regime table 仍为 0.533。
剩下的泄露来自可见状态自身的一致性：S0 里 promo 的 active 状态与 hidden strictness 一致、
accessory 与 base 在初始状态下已按 hidden compat 匹配，所以按 (category, role, priority,
status) 做的细 key 表能复制一半 episode。v3.1 的 dev EES：graph 0.800、
program 0.806、gnn_est 0.706、rh_oracle 1.000。
要通过 C4 需要 v3.2：初始状态不再与 hidden policy 一致（例如 promo 初始状态随机、accessory
初始不一定兼容），这改变了“状态总是合法”的假设，留待下一轮决定；v3.1 没有跑 test split。
结果：`results/development/hm3/det_dev_shopping31.json`、`gate_shopping31.json`。

## 6. 现在能写与不能写的结论

能写：
1. v3 的四个 DGP 让 lookup、kNN、conservative superset 在可执行端点上失败，同时
   oracle 与只看历史的 oracle 都能完成，即任务可辨识且 history 是 load-bearing。
2. 学到的关系结构（graph 或 program）加上从历史解析的 regime 在 dev 与 test 上都远高于
   黑盒与 lookup 基线。
3. 逐对象的 relational program learner 与 graph 的关系：confirmatory 的 `program` 在 Search 打平、
   Formal dev 更高、Travel 与 Shopping 更低；post-hoc 正则化后的 `program_reg` 在 test 上 Shopping 打平
   （0.828 / 0.828）、Search 打平、Formal 更高（0.933 vs 0.789），只有 Travel 仍低于 graph
   （0.656 vs 0.856）。causal graph 的传播形式只在 Travel 这种多跳数值链上有独占优势。

4. 真实 API 上 graph selection 相对 full/verbose 稳定减少 70–80% input tokens；n≈64 时 EES 低
   0.10–0.19（Travel [−0.333, −0.048]，Search [−0.254, +0.045]），witness 闭包修复了 Travel 一半的差距。
5. Shopping v3.2（初始状态与 hidden policy 解耦）通过全部 gate；fresh seeds 上 killers
   ≤ 0.456，graph 0.756，program_reg 0.778。

不能写：
1. “learned causal structure 对四任务正确性必不可少”：Search 与 Formal 的反例已经在
   dev 与 test 出现。
4. “LLM runtime 已经能利用学到的结构”：两轮 LLM 最好的 cell 是 0.650 / 0.700，同一 seed 上
   learned graph 是 0.856 / 0.994；prompt 版本造成的移动与 selection 造成的移动同量级。
5. “graph selection 在 EES 上非劣于 full/verbose”：n≈64 的 round 3/4 明确否定了 −0.10 边界下的
   非劣性；能写的是 input 减少与可量化的 EES 代价。
2. Shopping 的 gate 未通过 C4，其 test 数字只作 deterministic replication 报告。
3. 关系型学习器的特征在 dev 上修订过四轮（预注册 §3 已披露）；test 与 API 在修订之后
   才运行，但 dev 数字不是 pristine。

## 7. Round 2（2026-09-03，预注册 §9；prompt v2、fresh test seeds、Shopping v3.2）

### 7.1 API round 2：prompt v2（policy ledger → propagate → check），同一 episode 与 cells

#### travel

| selection / serialization | n | ees | exact_action_set | affected_f1 | collateral_txns | value_accuracy | input_tokens | output_tokens | cost | parse_ok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| exact / compact | 20 | 0.000 | 0.000 | 0.050 | 0.000 | 0.050 | 26440 | 9642 | 0.111 | 1.000 |
| exact / verbose | 20 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 23996 | 8867 | 0.108 | 1.000 |
| full / compact | 20 | 0.650 | 0.600 | 0.873 | 0.300 | 0.833 | 66471 | 42177 | 0.517 | 1.000 |
| full / verbose | 20 | 0.600 | 0.550 | 0.690 | 0.150 | 0.700 | 216541 | 52493 | 0.850 | 1.000 |
| graph / compact | 20 | 0.600 | 0.600 | 0.883 | 0.300 | 0.700 | 43592 | 27993 | 0.308 | 1.000 |
| graph / verbose | 20 | 0.350 | 0.300 | 0.705 | 0.150 | 0.508 | 63509 | 27184 | 0.345 | 1.000 |
| program / compact | 20 | 0.250 | 0.250 | 0.507 | 0.150 | 0.300 | 25448 | 14600 | 0.157 | 1.000 |
| program / verbose | 20 | 0.250 | 0.200 | 0.552 | 0.250 | 0.300 | 39185 | 12451 | 0.146 | 1.000 |
| source / compact | 20 | 0.250 | 0.250 | 0.425 | 0.200 | 0.350 | 25215 | 15346 | 0.175 | 1.000 |
| source / verbose | 20 | 0.100 | 0.100 | 0.333 | 0.150 | 0.175 | 44691 | 14943 | 0.207 | 1.000 |

主判断 (graph, compact) 相对 (full, verbose)：EES 差 +0.000，input tokens 减少 79.9% → **PASS**。

selection 隔离：EES -0.250，input 减少 70.7%。
serialization 隔离：EES +0.050，input 减少 69.3%。

| cell | round 1 EES | round 2 EES |
|---|---:|---:|
| exact/compact | 0.050 | 0.000 |
| exact/verbose | 0.000 | 0.000 |
| full/compact | 0.500 | 0.650 |
| full/verbose | 0.500 | 0.600 |
| graph/compact | 0.250 | 0.600 |
| graph/verbose | 0.450 | 0.350 |
| program/compact | 0.200 | 0.250 |
| program/verbose | 0.300 | 0.250 |
| source/compact | 0.250 | 0.250 |
| source/verbose | 0.450 | 0.100 |

#### search

| selection / serialization | n | ees | exact_action_set | affected_f1 | collateral_txns | value_accuracy | input_tokens | output_tokens | cost | parse_ok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| exact / compact | 20 | 0.200 | 0.200 | 0.417 | 0.050 | 0.400 | 24873 | 21586 | 0.230 | 1.000 |
| exact / verbose | 20 | 0.250 | 0.250 | 0.283 | 0.000 | 0.300 | 22325 | 6912 | 0.089 | 1.000 |
| full / compact | 20 | 0.700 | 0.700 | 0.823 | 0.450 | 0.875 | 40099 | 29625 | 0.362 | 1.000 |
| full / verbose | 20 | 0.650 | 0.650 | 0.743 | 0.300 | 0.775 | 118956 | 39658 | 0.602 | 1.000 |
| graph / compact | 20 | 0.450 | 0.450 | 0.500 | 0.000 | 0.450 | 47410 | 35484 | 0.390 | 1.000 |
| graph / verbose | 20 | 0.550 | 0.550 | 0.600 | 0.000 | 0.550 | 52162 | 21109 | 0.288 | 1.000 |
| program / compact | 20 | 0.450 | 0.450 | 0.500 | 0.000 | 0.450 | 50807 | 33990 | 0.369 | 1.000 |
| program / verbose | 20 | 0.500 | 0.500 | 0.600 | 0.000 | 0.500 | 51980 | 25243 | 0.314 | 1.000 |
| source / compact | 20 | 0.350 | 0.350 | 0.350 | 0.000 | 0.350 | 53041 | 45251 | 0.479 | 1.000 |
| source / verbose | 20 | 0.400 | 0.400 | 0.467 | 0.000 | 0.500 | 36501 | 21964 | 0.261 | 1.000 |

主判断 (graph, compact) 相对 (full, verbose)：EES 差 -0.200，input tokens 减少 60.1% → **FAIL**。

selection 隔离：EES -0.100，input 减少 56.2%。
serialization 隔离：EES +0.050，input 减少 66.3%。

| cell | round 1 EES | round 2 EES |
|---|---:|---:|
| exact/compact | 0.200 | 0.200 |
| exact/verbose | 0.250 | 0.250 |
| full/compact | 0.500 | 0.700 |
| full/verbose | 0.500 | 0.650 |
| graph/compact | 0.650 | 0.450 |
| graph/verbose | 0.500 | 0.550 |
| program/compact | 0.500 | 0.450 |
| program/verbose | 0.400 | 0.500 |
| source/compact | 0.450 | 0.350 |
| source/verbose | 0.250 | 0.400 |

Round 2 合计 400 cells，input 1,073,242 / output 506,518 tokens，估计费用 $6.309。

### 7.2 Deterministic replication，fresh test seeds 20/21/22（train 120/121/122），全部方法

`graph_pooled`（所有 template 共享一个正则化 gradient-boosted gate，template 身份作 one-hot，传播不变）与 `program_reg` 在这一轮是预先加入的方法，其余与 round 1 相同。

| method | formal | search | shopping | shopping32 | travel |
|---|---:|---:|---:|---:|---:|
| exact_kv | 0.033 ± 0.024 | 0.106 ± 0.048 | 0.039 ± 0.021 | 0.028 ± 0.021 | 0.000 ± 0.000 |
| source_union | 0.000 ± 0.000 | 0.117 ± 0.014 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| source_regime | 0.017 ± 0.024 | 0.172 ± 0.034 | 0.583 ± 0.059 | 0.456 ± 0.016 | 0.061 ± 0.034 |
| knn | 0.072 ± 0.048 | 0.411 ± 0.031 | 0.461 ± 0.044 | 0.261 ± 0.034 | 0.300 ± 0.027 |
| flat | 0.094 ± 0.021 | 0.067 ± 0.014 | 0.189 ± 0.097 | 0.339 ± 0.044 | 0.006 ± 0.008 |
| flat_est | 0.144 ± 0.064 | 0.072 ± 0.008 | 0.211 ± 0.149 | 0.233 ± 0.138 | 0.006 ± 0.008 |
| gnn | 0.222 ± 0.061 | 0.367 ± 0.036 | 0.717 ± 0.049 | 0.700 ± 0.068 | 0.406 ± 0.031 |
| gnn_est | 0.256 ± 0.031 | 0.461 ± 0.083 | 0.750 ± 0.036 | 0.711 ± 0.055 | 0.744 ± 0.068 |
| superset | 0.067 ± 0.014 | 0.278 ± 0.021 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.011 ± 0.008 |
| program | 0.939 ± 0.042 | 0.994 ± 0.008 | 0.322 ± 0.227 | 0.750 ± 0.047 | 0.744 ± 0.042 |
| program_reg | 0.889 ± 0.057 | 0.994 ± 0.008 | 0.828 ± 0.031 | 0.778 ± 0.070 | 0.667 ± 0.059 |
| graph | 0.717 ± 0.082 | 1.000 ± 0.000 | 0.800 ± 0.049 | 0.756 ± 0.048 | 0.883 ± 0.024 |
| graph_pooled | 0.733 ± 0.059 | 0.989 ± 0.016 | 0.839 ± 0.016 | 0.728 ± 0.070 | 0.867 ± 0.047 |
| rh_oracle | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| oracle | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |

### 7.3 Shopping v3.2：初始状态与 hidden policy 解耦

| check | shopping32 |
|---|---|
| C2_split_separation | PASS |
| C3_history_load_bearing | PASS |
| C1_query_leak | PASS |
| C6_nonidempotent | PASS |
| C4_killers_fail | PASS |
| C5_identifiable | PASS |
| C7_graph_beats_blackbox | PASS |
| C8_program_ran | PASS |
| **api_allowed** | yes |

C4：{'exact_kv': 0.017, 'source_union': 0.0, 'source_regime': 0.461, 'knn': 0.239, 'superset': 0.0}；C7：graph 0.806，black boxes {'flat': 0.25, 'flat_est': 0.239, 'gnn': 0.744, 'gnn_est': 0.689}；C8：program 0.789。

Shopping v3.2 test（seeds 20/21/22）：

| method | shopping32 |
|---|---:|
| exact_kv | 0.028 ± 0.021 |
| source_union | 0.000 ± 0.000 |
| source_regime | 0.456 ± 0.016 |
| knn | 0.261 ± 0.034 |
| flat | 0.339 ± 0.044 |
| flat_est | 0.233 ± 0.138 |
| gnn | 0.700 ± 0.068 |
| gnn_est | 0.711 ± 0.055 |
| superset | 0.000 ± 0.000 |
| program | 0.750 ± 0.047 |
| program_reg | 0.778 ± 0.070 |
| graph | 0.756 ± 0.048 |
| graph_pooled | 0.728 ± 0.070 |
| rh_oracle | 1.000 ± 0.000 |
| oracle | 1.000 ± 0.000 |

### 7.4 读法：两轮 API 合起来说明了什么

配对 bootstrap（每 episode 的 EES 差，4000 次重抽，`results/real/hm3/round2/paired_bootstrap.json`）：

| 域 | 比较 | round 1 | round 2 | 两轮合并（n=40） |
|---|---|---:|---:|---:|
| Travel | graph/compact − full/verbose | −0.250 [−0.500, 0.000] | 0.000 [−0.300, +0.300] | −0.125 [−0.325, +0.075] |
| Travel | graph/verbose − full/verbose | −0.050 [−0.300, +0.200] | −0.250 [−0.500, 0.000] | −0.150 [−0.325, +0.025] |
| Travel | full/compact − full/verbose | 0.000 [−0.200, +0.200] | +0.050 [−0.200, +0.300] | +0.025 [−0.150, +0.175] |
| Search | graph/compact − full/verbose | +0.150 [−0.150, +0.450] | −0.200 [−0.400, 0.000] | −0.025 [−0.200, +0.175] |
| Search | graph/verbose − full/verbose | 0.000 [−0.350, +0.350] | −0.100 [−0.350, +0.150] | −0.050 [−0.250, +0.150] |
| Search | full/compact − full/verbose | 0.000 [−0.250, +0.250] | +0.050 [−0.250, +0.350] | +0.025 [−0.175, +0.225] |

- 预注册的点估计规则在两轮里给出相反的判断：round 1 Search PASS / Travel FAIL，round 2
  Travel PASS（0.000，input −79.9%）/ Search FAIL（−0.200）。每 cell 20 个 episode 时，
  一个 episode 就是 0.05，任何 cell 间的差在 ±0.25 以内都落在噪声里；两轮合并后所有六个
  区间都跨 0。诚实的结论是：**在这个样本量下，selection 与 serialization 对 EES 的影响
  都没有被分辨出来，非劣性没有被建立，损害也没有被建立。** 可以稳定写的是 input tokens：
  graph/compact 相对 full/verbose 在四个 (域, 轮) 组合里都减少 68–80%。
- prompt v2 把 full/verbose 从 0.500 提到 0.600（Travel）与 0.650（Search），把 Travel
  graph/compact 从 0.250 提到 0.600；也把 Search graph/compact 从 0.650 拉回 0.450，Travel
  graph/verbose 从 0.450 拉到 0.350。改 prompt 造成的 cell 间移动与 selection 造成的移动
  是同一量级，这本身就是“runtime 是瓶颈”的又一个证据。
- LLM 两轮最好的 cell 是 0.650 / 0.700（Travel full/compact、Search full/compact），同一
  test seed 上确定性 learned graph 为 0.856 / 0.994。四个 exact 选择的 cell 在两轮里都
  ≤ 0.25，说明模型没有靠先验猜出结构。
- 要把 selection 效应做成 confirmatory，需要每 cell ≥ 80 个 episode（把 ±0.25 收到
  ±0.12）或换更强的 runtime；两者都是下一轮的决定。两轮合计 800 cells，$12.90。

### 7.5 API round 3：主判断的功效补样（预注册 §11；每 cell 80 episodes，prompt v2）

| 域 | cell | n | EES | input tokens |
|---|---|---:|---:|---:|
| travel | graph/compact | 64 | 0.219 | 125,735 |
| travel | full/verbose | 63 | 0.635 | 627,177 |
| travel | graph/verbose | 63 | 0.238 | 180,892 |
| travel | full/compact | 63 | 0.492 | 259,518 |
| search | graph/compact | 69 | 0.493 | 172,230 |
| search | full/verbose | 67 | 0.597 | 423,982 |
| search | graph/verbose | 69 | 0.522 | 199,869 |
| search | full/compact | 69 | 0.493 | 202,900 |

| 域 | 比较 | mean | 95% CI | W/T/L | n |
|---|---|---:|---:|---|---:|
| travel | graph/compact − full/verbose | -0.413 | [-0.540, -0.286] | 1/35/27 | 63 |
| travel | graph/verbose − full/verbose | -0.397 | [-0.540, -0.254] | 3/32/28 | 63 |
| travel | full/compact − full/verbose | -0.143 | [-0.302, +0.016] | 9/36/18 | 63 |
| search | graph/compact − full/verbose | -0.104 | [-0.254, +0.045] | 10/40/17 | 67 |
| search | graph/verbose − full/verbose | -0.075 | [-0.239, +0.090] | 13/36/18 | 67 |
| search | full/compact − full/verbose | -0.104 | [-0.269, +0.045] | 10/40/17 | 67 |

Travel 主判断（点估计规则）：EES 差 -0.416，input 减少 80.0% → **FAIL**；配对 95% 区间 [-0.540, -0.286]（n = 63）。

Search 主判断（点估计规则）：EES 差 -0.104，input 减少 59.4% → **FAIL**；配对 95% 区间 [-0.254, +0.045]（n = 67）。

Round 3 合计 527 cells，input 2,192,303 / output 969,038 tokens，估计费用 $12.024。 不完整的 cell（基础设施失败）见各 shard ledger 的 `infrastructure_failure` 记录。

读法（round 3）：预算上限 $12 在 527/640 cells 时到达，每 cell 63–69 个 episode，配对分析只用
两个 cell 都有输出的 episode。与 round 2 共享的前 20 个 episode 上，Travel graph/compact 的
逐 episode 结果只有 10/20 一致（temperature 0 下 deepseek-v4-flash 仍不确定），所以 20 个
episode 的 cell 均值本身就在 ±0.2 内漂移。n≈64 时结论稳定：Travel graph/compact 明显低于
full/verbose（−0.413 [−0.540, −0.286]），selection 单独隔离 −0.397，serialization 单独隔离
−0.143 [−0.302, +0.016]；Search −0.104 [−0.254, +0.045]。

失败审计定位了原因：Travel 38 个失败的 late episode 中 33 个的 witness 记录指向未被选入
state 的对象（其他链的 flight / transfer / dinner / bundle）。graph 的 required-read recall
是 1.00，即 witness 记录本身都在；缺的是记录 referent 的对象字段（例如 “T58 pickup
860→1045” 旁边没有 T58 的 provider），模型无法把 witness 落到 policy 的 key 上。这是 LLM 侧
selection 的闭包缺陷：确定性 executor 总能看到完整 S0，所以 graph 在同一 episode 上仍是
0.856。Round 4（预注册 §12）把 selection 改为 graph reads ∪ 记录 referent ∪ 其 1-hop 邻居
（Travel compact prompt 从 2.5k 字符升到 3.4k，full/compact 为 6.1k），结果见 §7.6。

### 7.6 API round 4：graph selection 加 witness 闭包（预注册 §12；配对对象为 round 3 的 full/verbose）

| 域 | cell | EES | full/verbose | 配对差 [95% CI] | W/T/L | n | input 减少 | 点估计规则 |
|---|---|---:|---:|---:|---|---:|---:|---|
| travel | graph_closed/compact | 0.444 | 0.635 | -0.190 [-0.333, -0.048] | 6/39/18 | 63 | 73.8% | FAIL |
| travel | graph_closed/verbose | 0.317 | 0.635 | -0.317 [-0.461, -0.159] | 5/33/25 | 63 | 53.4% | FAIL |
| travel | closure effect: graph_closed/compact − graph/compact | — | — | +0.234 [+0.094, +0.359] | 19/41/4 | 64 | — | — |
| search | graph_closed/compact | 0.493 | 0.597 | -0.104 [-0.254, +0.045] | 10/40/17 | 67 | 69.5% | FAIL |
| search | graph_closed/verbose | 0.448 | 0.597 | -0.149 [-0.284, -0.015] | 7/43/17 | 67 | 31.6% | FAIL |
| search | closure effect: graph_closed/compact − graph/compact | — | — | +0.000 [-0.145, +0.145] | 13/43/13 | 69 | — | — |

Round 4 合计 320 cells，input 1,043,767 / output 511,613 tokens，估计费用 $6.413，0 次基础设施失败。

读法：闭包修复了 Travel 上一半的差距（graph_closed/compact 相对 graph/compact +0.234
[+0.094, +0.359]），但 graph_closed/compact 仍低于 full/verbose 0.190 [0.048, 0.333]；Search 的闭包
没有作用（0.000），graph_closed/compact 低 0.104 [−0.045, +0.254]，点估计恰好越过 −0.10 的边界。
graph_closed/verbose 在两个域都比 compact 差（Travel 0.317、Search 0.448），这一轮 serialization
的方向与 round 2 的 Travel 观察一致：给这个 runtime 更长的 JSON 反而更差。

在 n≈64、prompt v2、deepseek-v4-flash 上可以稳定写的结论：graph selection 把 input 减少 70–74%，
代价是 EES 低 0.10–0.19；非劣性（−0.10）没有达到。差距的一半来自 selection 闭包（可修），剩下的
一半是 runtime 对最小证据集的利用能力。四轮 P2 API 合计 $32.1；更强的 runtime 或“graph 选择 +
同 key 全部 witness segment”的 selection 是下一轮的候选，本轮不再追加。
