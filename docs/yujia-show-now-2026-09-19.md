# 现在可以给 Yujia 看的内容（2026-09-19）

全部数字来自仓库分支 `claude/hm3-handoff-2026-09-18` 上的结果文件；每个数字的出处在
`docs/hm3-history-scaling-results-2026-09-18.md`，论文口径的汇总在 `docs/hm3-results-package-2026-09-19.md`。
本页按"主张 → 任务设定 → 之前已有的结果 → 本周新结果 → 边界 → 下一步"组织，可以直接作为会议材料。

## 1. 一句话主张与三件要证明的事

> Access-conditioned temporal dependency structure keeps an agent's memory reads flat as the history grows,
> stays robust when the history accumulates conflicting or stale evidence about the same entities, and traces
> an anomalous action back to the record that caused it; matched retrieval, recency, ledger and full-context
> baselines do not.

对应 8/30 与 9/04 讨论中要分别证明的三件事：

| 要证明的事 | 证据层 | 状态 |
|---|---|---|
| (1) access-regime conditioning 能恢复 pooled / additive 方法漏掉的依赖 | E0 v2（受控仿真） | 完成，PASS |
| (2) 学得的结构相对 ledger / 检索 / 全读有增量，并把读取量压平 | HM3 确定性层 + 真实 actor 层 | 确定性层成立；actor 层：成本 1–3% 任何长度、两个领域成立；准确率优势只在 Travel（同实体冲突 +0.19、500 条 +0.17，会终止的 prompt），100 条纯混合持平，native 全读更好或相同；Shopping 只有成本优势 |
| (3) 同一张图反向遍历能定位驱动错误动作的写入记录，且经干预验证 | HM3 provenance（确定性 + actor 层） | Travel 完成（确定性与 actor 层）；Shopping 为边界 |

## 2. 任务设定：Hidden Mechanism v3（HM3）

HM3 是我们自己构造、按 MemoryArena 四个任务族（Travel、Shopping、Search、Formal）建模的受控 benchmark。
它解决了旧 Travel 版本的两个问题：训练图与运行时遍历的时间语义一致；query 里没有依赖线索，简单 lookup
无法完成任务（零 API gate C1–C8 机器检查）。

**一个 episode** = (H, S0, I, A, S1, R)：历史记录 H（只有结果记录，没有 policy 声明）、干预前状态 S0、
一次干预 I（只说 source 对象和新值）、oracle 修复事务 A、干预后状态 S1、账本 R。方法只看 (H, S0, I)。

**隐藏机制**：每个 episode 抽样一组按实体 key 索引的隐藏参数（Travel：`auto_rebook[provider]`、
`buffer[provider]`、`enforce_late[hotel]`、`late_seating[restaurant]`、`linked[vendor]`；Shopping：
`compat[base|acc]`、`strict_promo[promo]`、`auto_promo`、`enforce_budget`）。每个参数只能从 H 里的一条
结果 witness 恢复（例如 `buffer = pickup_new − arrival_new`）。生成器保证被 consult 的参数都可从 H 恢复。

**输出与评分**：方法提交非幂等的修复事务（revision +1、消耗 token、收费）。主指标 EES = 全部事务合法
且 post-state 与 receipt 都与 oracle 相同；多写一个对象或少写一个都失败。这让"读全部再猜"的 superset
策略真实失败。

**方法臂**（同一执行器、只换读取集合的 selection ladder，与带学得决策模型的完整方法）：
`graph`（学得 typed-path skeleton + 按 access regime 门控的局部决策）、`graph_select`（沿学得 skeleton 读取，
再交给运行时执行器）、`wrong_select_1/2/3`（三个固定重接线的 skeleton）、`bm25_k16`、`recency_k16`、
`program_reg`（关系程序学习器，强对照）、`knn`、`source_regime` / `exact_kv`（查表 / ledger）、`oracle`。

**历史长度设定**（本周新增，`docs/hm3-history-scaling-design-2026-09-18.md`）：把每个 episode 的历史增广到
native（约 13 条）/ 50 / 100 / 500 条记录，四类干扰分别冻结——A 同对象旧版本、B 同 key 的一致重复 witness、
C 同 key 的冲突 witness（改名的同世界副本，隐藏参数扰动）、D 无关世界。增广后 S0 的原链、I、A、required reads
全部不变，因此四档是配对样本；断言逐 episode 验证，Travel 丢弃率 0–2%。

**真实 actor 设定**：DeepSeek-V4-Flash（AutoDL 端点，thinking 关闭，temperature 0，prompt v2 = policy ledger
→ propagate → check），test seed 30（64 个 episode）与 seed 31 复现；cells = selection × serialization：
`graph_closed`（图的读取 + witness referent 的 1-hop 闭包）、`full`（全部历史与状态）、`bm25_k16`、
`recency_k16`、`program`，每种 compact / verbose 两种序列化。全部配对到同一批 episode 报告 bootstrap 95% 区间。

## 3. 之前已有的结果（本周之前）

**HM3 v3 确定性层，fresh test seeds 20/21/22（EES）**

| 方法 | Travel | Shopping v3.2 | Search | Formal |
|---|---:|---:|---:|---:|
| 最好的 lookup / kNN | 0.30 | 0.46 | 0.41 | 0.14 |
| gnn_est（黑盒表示学习） | 0.74 | 0.71 | 0.46 | 0.26 |
| program_reg（关系程序） | 0.67 | 0.78 | 0.99 | 0.89 |
| learned graph | 0.88 | 0.76 | 1.00 | 0.72 |
| oracle | 1.00 | 1.00 | 1.00 | 1.00 |

读法：显式结构远高于 lookup / kNN / 黑盒；与关系程序相比，图在 Travel 胜，Shopping、Search 持平，Formal 输。

**HM3 API round 3/4（native 长度，n≈64/cell）**：graph_closed/compact 比 full/verbose 低 0.19 [0.05, 0.33]
（Travel）、0.10 [−0.05, 0.25]（Search），输入减少 70–74%；非劣性未达到。这是本周要回答的核心缺口。

**E0（原版）**：regime-conditioned 方法在三档噪声下恢复 2/2 gated read edges，blind / additive 为 0/2。

**MINJA（AutoDL，8,400 tests）**：真实结构臂 10/10 runs 未选出边；frequency-regime 与 matched random 无差别
（91/360 对 93/360）。作为识别边界报告。**AgentPoison**：无标签定位直接 1/2、冻结 cluster expansion 后 2/2。
**Travel implicit-v1**：暂停，图与运行时时间语义不一致、lookup 可直接解题。

## 4. 本周新结果

### 4.1 E0 v2：access-regime conditioning 可识别（5 seeds × 3 噪声，n=32，T=10,000）

冻结判据 E0a：**PASS**。C1（regime-conditioned 方法 cell-memory F1 ≥ 0.90，≥ 4/5 seeds，每档噪声）5/5、5/5、5/5；
C2（没有 pooled / additive 臂达到该线）PASS；C3（全部 shuffle-regime 对照 < 0.70）PASS。也达到 C1 线的诚实基线
是 per-regime 拟合与 HC0 interaction 模型：关键是按 access regime 条件化，不是某个特定估计器。
σ=0 的代表数：regime_grace cell-memory F1 1.000，pooled_ridge 0.428，additive_u 0.428，PCMCI 0.409，
shuffle 对照 0.54–0.63。

### 4.1b 结构能否由成熟的 causal discovery 算法得到（9/20 会后补）

同一批事件日志（每条记录一行、每个对象类型一个二值变量、用户干预为外生），跑 PCMCI+（ParCorr、G²）与 GRACE 参考实现（PCMCI+ 骨架 / 开放骨架 ×1、×3、×10），六 seed。

| 方法 | Travel 边 P / R（5 条真边） | Shopping32（3 条） | 用它选择（Travel EES，各长度） | 用它追责（top-3 / 替换恢复） |
|---|---|---|---|---|
| GRACE 开放骨架，×1 或 ×3 | 0.19–0.29 / 0.80–1.00 | 0.50–0.60 / 1.00 | 1.000 | 0.91–1.00 / 同率 |
| GRACE + PCMCI+ G² 骨架 | 0.25–0.40 / 0.40 | 0 / 0 | 1.000（按 lag 展开） | 0.91–1.00 / 同率 |
| PCMCI+ ParCorr | 0.20 / 0.40 | 0 / 0 | 0.989–1.000 | — |
| GRACE ×10 | 0.40–0.75 / 0.40–0.80 | 1.00 / 0.33–0.67 | 0.81–0.87 | — |
| 我们的 pooled 回归 + FDR | 0.21–0.23 / 1.00 | 0.50 / 1.00 | 1.000 | 0.91–1.00 / 同率 |
| 干预式骨架（参照） | — | — | 1.000 | 0.91–1.00 / 同率 |

读法：所有方法都恢复链头 flight→transfer→stay；CI 检验把链尾归到 flight 的 lag 2–3 并剪掉中介（中间写入是确定性的，即 E0 记录的 faithfulness 失效），但按 lag 展开后到达的对象相同，所以选择与追责的数字与参照一致。开放骨架的 GRACE 把链头两条边排在门值第 1、2 位，stay → {dinner, activity, bundle} 排在第 5–21 位（30 条中），被 flight → stay / activity / bundle 这些 lag 2–3 捷径压在后面；真边在门值排序下的 average precision：Travel 0.47–0.77，Shopping 0.70–1.00。Shopping 上 CI 骨架为空，GRACE 开放骨架与回归恢复全部三条边。因此 pipeline 消费的结构可以由 GRACE 参考实现从日志得到；论文把这些边称为从观测日志识别的 dependency structure，因果解释由受控实验、重接线对照和干净替换检验承担。

### 4.2 确定性层：结构让读取平坦、检索随长度失效（Travel，dev seeds 0/1/2，每 seed 60 episode）

| 方法臂 | native | 50 | 100 | 500 | 500 档 reads |
|---|---:|---:|---:|---:|---:|
| graph_select（沿学得 skeleton 读取） | 1.000 | 1.000 | 1.000 | 1.000 | 12.4 |
| wrong_select 1 / 2 / 3（重接线 skeleton） | 0.43 / 0.04 / 0.04 | 同 | 同 | 同 | 5.9 / 2.2 / 2.8 |
| bm25_k16 | 0.90 | 0.32 | 0.04 | 0.04 | 21.2 |
| recency_k16 | 0.94 | 0.71 | 0.47 | 0.32 | 21.3 |
| learned graph，gate 在 native 训练集上拟合（正式臂 graph_nf） | 0.87 | 0.86 | 0.84 | 0.83 | 12.4 |
| learned graph，gate 按档位重拟合（消融） | 0.87 | 0.84 | 0.84 | 0.85 | 12.3 |
| program_reg（读取全部） | 0.68 | 0.66 | 0.68 | 0.68 | 1125 |
| knn（读取全部） | 0.32 | 0.39 | 0.33 | 0.32 | 1125 |

正式 graph 臂的 gate 在该 seed 的 native 训练集上拟合一次、只增广评测历史（设计修订 §9.6，2026-09-19 拍板）：
历史变长改变的是证据，机制不变；按档位重拟合会让 gate 在被外来 witness 污染的 regime 估计上训练，保留为消融
（Shopping 的重拟合在 100 档坍塌到 0.175 而 native-fit gate 在同一评测集上保持 0.77–0.81）。reserved test seeds
30/31/32 上 graph_nf 为 0.88 / 0.86 / 0.85 / 0.80（native / 50 / 100 / 500），reads 11.2 → 12.1。
预注册的四条预测对正式臂全部成立：P1 graph reads 平坦（11.4 → 12.4）；P2 graph EES 稳定（配对差 −0.01 / −0.03 /
−0.04，只有冲突 witness 单类型条件 c100 越界到 −0.07）；
P3 固定 K 检索丢失必需记录（recall 0.97 → 0.64）；P4 读全部历史的方法 reads 线性增长（53 → 1125）。
重接线的图对照说明收益来自正确的依赖拓扑；bm25 / recency 说明词法检索与最近记录在长历史下失效。

### 4.3 真实 actor 层：成本，以及 500 条记录下的适度优势（Travel，DeepSeek-V4-Flash；9/19 晚修订）

本节首版的表来自 4096 输出上限的运行，审计发现两件事：被截断的第一次回复没有 JSON，修复调用返回空数组判 0（full/verbose 在 100/500 档有 56/64、58/63 格被截断）；prompt v2 的"先为每个实体建 policy ledger"步骤在 100 条以上的历史上不终止（同一 episode 重复三次都循环到 16k 上限）。全部臂已在 16,384 上限下按两种 prompt 重跑。汇总命令 `python3 -m hm3.panel_summary --domain travel`。

| 历史 | prompt，上限 | full/verbose EES（打满上限的格） | graph_closed EES | graph − full | graph_key2（不用 parser） |
|---|---|---:|---:|---|---:|
| native（约 13 条） | v2，4096 | 0.55（11/64） | 0.22 | −0.33 [−0.47, −0.19] | 0.36 |
| 100 条混合 | v2，16k | 0.20（45/64） | 0.25 | +0.05 [−0.09, +0.19] | 0.36 |
| 100 条混合 | v1，16k | 0.25（5/64） | 0.25 | +0.00 [−0.14, +0.14] | — |
| 500 条混合 | v2，16k | 0.11（50/63） | 0.29 | +0.17 [+0.05, +0.30] | 0.24 |
| 500 条混合 | v1，16k | 0.16（5/63） | 0.29 | +0.13 [+0.00, +0.25] | — |
| 100 条同实体冲突 | v2，16k | 0.19（38/63） | 0.32 | +0.13 [−0.02, +0.27] | 0.33 |
| 100 条同实体冲突 | v1，16k | 0.12（3/58） | 0.16 | +0.00 [−0.10, +0.10] | — |

同一序列化两侧对齐后（verbose 两侧，witness 所在整段保留；prompt v2，16k；9/20 补）：

| 历史 | full/verbose EES（打满 16k） | graph_seg/verbose EES | graph_seg − full | 比旧臂 graph_closed/compact 高 |
|---|---:|---:|---|---|
| native（约 13 条） | 0.66（6/62） | 0.44 | −0.23 [−0.39, −0.06] | — |
| 100 条混合 | 0.20（45/64） | 0.37 | +0.18 [+0.04, +0.32] | +0.11 |
| 100 条同实体冲突 | 0.19（38/63） | 0.44 | +0.22 [+0.07, +0.39] | +0.13 |
| 500 条混合 | 0.11（50/63） | 0.56 | +0.44 [+0.30, +0.57] | +0.27 |

会终止的 prompt v1 下同一面板（同 verbose 序列化，n=52–63）：100 条混合 graph_seg 0.33 对 full 0.25（+0.08 [−0.06, +0.22]）；native 0.48 对 0.48（+0.00）；同实体冲突 0.33 对 0.14（**+0.19 [+0.06, +0.32]**）；500 条 0.33 对 0.16（**+0.17 [+0.03, +0.32]**）。上表旧臂用 compact 序列化且只给 witness 记录，低估了结构的作用 0.1–0.3。

tokens：graph_seg/verbose 输入 3.6–4.4k、输出 1.1–1.5k；graph_closed/compact 输入 1.5–1.8k、输出 0.6–1.3k；full 在 100 档 27k（v1）或 70k（v2，打满），500 档 123k–261k。bm25_k16 与 recency_k16 在长历史下 0.02–0.09。

读法：actor 层能站住的是四条。**成本**：输入 1–3%、输出约 1/10，与 prompt 和上限无关。**冲突证据**：给 actor 完整的 witness 段时，同实体冲突让会终止的全读 actor 从 0.25 掉到 0.14，结构化读取保持 0.29–0.33，两种 prompt 下都成立；效应量约为旧表的三分之二。**长历史**：500 条时结构领先 0.17（v1）到 0.44（v2）。**短历史**：ledger 式 prompt 下全读最好（0.66 对 0.44），普通 prompt 下两臂相同（0.48 对 0.48）。100 条纯混合时两臂持平。**Shopping32 是准确率主张的边界**：会终止的 prompt 下，100 条两臂持平（0.48 对 0.48–0.50），500 条全读 0.53、graph_closed/verbose 0.48（−0.05）、graph_seg/verbose 0.34（−0.19 [−0.34, −0.03]）；ledger 式 prompt 下 500 条 +0.17 / +0.23 只是全读不终止。Shopping 里成立的只有成本（7–11k 对 26k–103k tokens）。上下文形式决定效应大小：witness 必须连同产生它的干预记录、以与全读相同的 verbose 形式给出；compact 只给 witness 的旧臂损失 0.1–0.3。不用手写 parser 的选择（graph_key2）与 parser 版 compact 臂持平。

### 4.3b 在 MemoryArena 的真实实体与记忆接口上（9/20）

把 Travel 机制放到 MemoryArena 的真实航班、住宿、餐厅上，记忆走 MemoryArena 自己的 `add_chunk` / `wrap_user_prompt`，baseline 用它的实现原样加载（BM25 默认 top-3 与 top-16、long_context、A-Mem 默认 k=5），我们的图放在同一接口后面。64 episode，16k，两种 prompt。

| 历史 | ours（v1 / v2） | long_context | BM25 top-16 | ours − long_context（v1） |
|---|---:|---:|---:|---|
| native | 0.42 / 0.62 | 0.38 / 0.59 | 0.28 / 0.30 | +0.05 [−0.09, +0.17] |
| 100 条混合 | 0.50 / 0.52 | 0.19 / 0.22 | 0.02 / 0.06（A-Mem 0.02 / 0.06） | +0.31 [+0.17, +0.44] |
| 100 条同实体冲突 | 0.34 / 0.42 | 0.22 / 0.16 | 0.02 / 0.03 | +0.12 [−0.02, +0.27] |
| 500 条混合 | 0.34 / 0.56 | 0.14 / 0.08 | 0.05 / 0.02 | +0.20 [+0.08, +0.33] |

读法：合成 id 上的结论在真实实体、benchmark 自己的接口和 baseline 实现上成立，且 native 档不再出现全读更好的 crossover（持平）。边界：任务机制是我们的，实体、接口、baseline 是 MemoryArena 的；这不是 MemoryArena 原来的规划任务。

### 4.4 同一张图的反向 provenance，经干预验证（Travel，reserved test seeds 30/31/32）

正向选择与反向追踪使用同一个拟合好的图（SHA 记录）。每个 episode 把一条必需 witness 最小污染，审计器只拿到
异常对象，沿 skeleton 回溯到路径上各对象的 policy witness，再用 leave-one-out 重排。

| 指标 | seed 30 | seed 31 | seed 32 | 500 条记录 |
|---|---:|---:|---:|---:|
| 事件数 / episode | 52/60 | 48/60 | 42/60 | 45–51 |
| top-1 命中被污染记录 | 0.62 | 0.65 | 0.55 | 0.53–0.64 |
| top-3 命中 | 1.00 | 0.98 | 0.98 | 0.94–0.98 |
| 替换 top-3 为干净版本后 EES 恢复 | 1.00 | 0.98 | 0.98 | 0.94–0.98 |
| 替换 3 条 matched random 记录 | 0.00 | 0.00 | 0.00 | 0.00 |
| 替换最相似的非祖先记录 | 0.00 | 0.00 | 0.00 | 0.00 |
| BM25（以异常对象为 query）top-3 命中 | 0.46 | 0.29 | 0.60 | 0.14–0.36 |

actor 层（全部 52 个事件，graph_seg/verbose）：干净历史 0.42，污染历史 0.17，替换审计器 top-3 后 0.48，替换
random-3 后 0.27；top-3 − random-3 = +0.21 [+0.04, +0.37]，top-3 − 污染 +0.31 [+0.15, +0.46]，替换后不低于干净历史。random-3 臂的 prompt 与污染
prompt 逐字相同（图只读约 6 条记录，top-3 被排除），所以它度量的是 actor 的逐次调用方差，+0.21 已扣除。

## 5. 边界与需要如实说的地方

1. **Shopping32**：修正增广丢弃率后重跑（64 个 episode，无丢弃），actor 层 native 无差别（−0.07 [−0.21, +0.08]），
   100 档 graph 0.50 对 full 0.25（+0.25 [+0.11, +0.39]），500 档 0.55 对 0.30（+0.25 [+0.14, +0.38]）；BM25 在 500 档
   回到 full 的水平（−0.03）。因此长历史下的选择优势在 Shopping 也成立。provenance 仍是边界（24 个污染里 19 个让
   parser 失去该 key 的 witness，witness-based 追踪按构造找不到；BM25 能按词元找到但替换后恢复 ≤ 0.08）；重接线
   对照在 Shopping 无区分力（cart 两跳内全连通，三个重接线里两个读到与学得 skeleton 相同的集合）。
2. **native 档全读更好**（flash −0.33，Pro −0.10）。论文按 crossover 写。
3. **假设**：当前世界自己的 witness 是任务会 consult 的 key 的最新记录（增广按此构造，parser 取最后一个 witness）；
   对任务不 consult 的 key，外来 witness 可能更晚。第二个 session 的逐 episode 审计确认增广本身干净（oracle 与
   rh_oracle 在所有档位无一翻转），确定性 graph 的偏移只来自 regime 估计特征块的三条通道（外来 witness 定义了
   真实历史未见证的 key；对未 consult 的 key 覆盖真实 witness；Travel 的 late 标志状态推断读到同名 hotel 的外来
   stay），因此正式臂改为 native-fit gate。
4. **复核过并已修正 / 解释的地方**：首轮 prompt 用不同前缀标出了外来记录（已统一重编号并重跑，结论不变）；
   graph 臂在长历史下自身分数上升，来自同实体额外 witness 被图选中（逐 episode 核实）；首版 wrong graph
   继承 superset 规则的失败、测的是缺失的门控模型，已换成 selection ladder；Shopping 增广曾丢弃 27% episode，
   已用 fallback 修到 0 并重跑。
5. **现代 memory 系统对照**：A-Mem 正在以"读取预算匹配的选择臂"运行（Travel 与 Shopping，native 与 100 条：每条
   历史记录按 A-Mem 自己的 LLM note 构造与 evolution 写入，query 用其 embedding 检索 top-16，交给同一 actor prompt，
   写入侧 LLM token 单独报告）。LightMem 暂缓：它把记录改写成抽取事实，检索结果无法映射回记录 id。Mem0 / dense
   未跑（端点无 embedding；本地 embedder 现已可用）。MemoryArena 原 actor 上的移植（第三层）尚未开始。

## 6. 会议上建议展示的顺序

1. §1 的表：三件事与证据层的对应。
2. §2 的一个 Travel episode 示意：query 只说航班新到达时间；历史里 provider 的 buffer 只能从一条 witness 相减得到；
   修复事务非幂等。
3. §4.2 表 + §4.3 第一张表：reads 平坦、检索失效、actor 层 crossover。
4. §4.3 分解表：崩溃来自冲突证据，prompt 规则救不回。
5. §4.4 表：同图反向定位与干预验证。
6. §5：Shopping 边界与假设。

## 7. 正在补齐的

Shopping 三 seed 主面板的重跑（ladder 已完成：graph_select 0.99，BM25 0.99 → 0.07）、test seeds 30–32 的确定性
面板（Travel 已完成 11/12 个条件，与 dev 一致：graph 0.88 → 0.89，BM25 0.92 → 0.03，recency 0.93 → 0.30）。
之后是把 Travel / Shopping 机制移植到 MemoryArena 原 actor 并接入 A-Mem / LightMem（第三层），以及论文的
主表与 case figure。
