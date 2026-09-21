# 两条线之间的桥：缺口定义、今天的新结果、六天计划与双 session 分工（2026-09-19）

本页是本轮工作的权威入口。两个 Fable session 共用同一个 checkout（同一文件系统、不同机器）；§7 规定分工与文件所有权，§8 是待办清单。所有数字均来自本 checkout 的结果文件，路径在表下注明。

> 9/20 晚：总览页 `docs/experiments-and-paper-status-2026-09-20.md`（已完成实验、9/25 前计划、论文结构与证据对应）。

## 0. 一句话

缺口不是"什么都没做"，而是三个具体的子缺口。今天用 HM3 自己的日志把其中两个补上了一半：现成的观测式时序因果发现（E0 的 pooled 估计量）在 HM3 的事件日志上完整恢复了类型级传播骨架并让读取量保持平坦；去掉手写 parser 的选择规则在 500 条历史下仍保持 0.80–0.89。同时发现 actor 层"全读在冲突证据下崩溃"的结果有一个未披露的混淆（4096 输出上限截断后空修复），16k 上限的重跑已启动，结论待定。

## 1. 缺口的精确定义

| 子缺口 | 内容 | 状态（今天之前） |
|---|---|---|
| G1 估计量 | Yujia 7/29 的 TCD 路线在 MemoryArena Travel 上得到 12 条边（10 条自环）、在 MINJA 上 10/10 空图；HM3 的正结果用的是已知干预下的计数 + 决策树 | 两条线用两套方法，没有在同一份数据上对比过 |
| G2 载体 | HM3 是自建生成器 + 自建执行器；MemoryArena 原 actor 上的移植未开始；现代 baseline 只有 A-Mem 中期数 | 正结果不在读者认得的 benchmark 上 |
| G3 外部帮助 | HM3 的 `LearnedGraph` 用了 (a) S0 里给定的 typed links，(b) 训练 episode 的干预标签，(c) 手写 `infer_params`（知道 buffer = pickup_new − arrival_new 这类公式并决定读哪些记录） | reviewer 可以说"智能在 parser 里" |

## 2. 对"MemoryArena-Intervene / Travel-R"方案的核实

那段建议（保留 MemoryArena 的 actor / memory / evaluation / baselines，加受控干预，从轨迹自动学结构，去掉 parser）方向对，但**不能按字面在 MemoryArena Travel 上执行**，原因都在仓库里已核实：

1. **MemoryArena Travel 没有环境动力学。** 每轮一个 traveler 产出一份完整行程（7 个 slot 的场所名），环境只评分，不传播任何变化。没有 flight arrival / pickup / check-in 这类会互相推动的状态字段（`benchmarks/MemoryArena/env/env_systems/travel_env.py`）。"do(flight=20:00) 然后看真实 actor 传播"在这个 benchmark 里没有对应物。
2. **跨 traveler 的唯一依赖是显式文本约束。** T0（`docs/t0-results.md`）：6,826/6,829 条依赖句在当前 query 里点名来源；implicit-v1 把它们搬进历史 notice 后，notice 本身仍写明规则。对这种数据"从干预轨迹学结构"学到的就是约束图，而 parser 已经 100% 读出，`ours ≈ query_only` 是 9/19 停跑决定（`docs/travel-campaign-pause-decision-2026-09-19.md`）已预见的结局。
3. **要让 MemoryArena Travel 有隐藏机制，就必须改写它的数据生成器**，也就是在 MemoryArena 的素材上再造一个 HM3；用 30 步 ReAct actor 生成几百条训练轨迹的成本和噪声（原始 PS 0–16%）六天内做不完。

可执行的版本（本页采用）：**在 HM3 上把 G1 和 G3 关掉，把 G2 缩到"读者认得的 memory 系统作为 selector 同台"**；载体本身仍是自建的，如实写。

## 3. 今天新增的结果

### 3.1 G1：现成的观测式 TCD 在 HM3 日志上恢复了骨架（`code/hm3/tcd_logs.py`）

把 HM3 训练历史 H 当作普通 agent 日志：一条记录一行，变量 = 对象类型（flight / transfer / stay / dinner / activity / bundle），x[t, type] = 该记录是否写了该类型的对象；不用 typed links，不用 parser。日志里标为用户干预（query）的行只做预测变量、不做被预测变量（它们是输入，不是响应）。两种编码：**event**（记录序）和 **segment**（一轮干预一行，即 MemoryArena 当年"该轮是否激活该 slot"的编码）。估计量：**pooled**（E0 的 pooled lagged ridge + BH-FDR，α=0.05，lag ≤ 3，窗口不跨 episode）和 **PCMCI+**（tigramite 5.2，ParCorr，multiple-dataset 模式）。参照 = `LearnedGraph` 的 typed-path skeleton 投影到类型对（Travel 5 条：flight→transfer、transfer→stay、stay→dinner、stay→activity、stay→bundle；Shopping32 3 条）。

| 编码 / 估计量 | Travel（dev 0/1/2 与 test 30/31/32，6 个 seed 一致） | Shopping32（6 个 seed） |
|---|---|---|
| event / pooled | **recall 1.0**，precision 0.21–0.23；强边（系数 ≥ 0.1）= flight→transfer 0.80、transfer→stay 0.80、stay→dinner 0.34–0.43、dinner→bundle 0.70–0.73、bundle→activity 0.75–0.79；其余为 0.02–0.05 的弱正边；自环 11–12 条（均为负或弱） | **recall 1.0**，precision 0.5；强边 cart→line 0.28–0.36、promo→cart 0.29–0.33 |
| event / PCMCI+ | recall 0.4：flight→transfer 0.91–0.97、transfer→stay 1.0，漏 stay→dinner / activity / bundle，多出 flight→dinner@3 | recall 0.33 |
| segment / pooled | recall 0.6–0.8，precision 0.3–0.4，自环 7–9 条 | recall 0.67–1.0 |
| segment / PCMCI+ | 空图或只有自环 | 空图 |

文件：`results/development/hm3/tcd/tcd_graphs_dev.json`、`results/real/hm3/tcd/tcd_graphs_test.json`。

读法：MemoryArena 上 TCD 退化成自环，HM3 上同一估计量恢复整条链。差别不在估计量，在**变量定义与任务有没有传播动力学**：segment 编码（= MemoryArena 的编码）在 HM3 上同样退化。这正是"第一步是重新定义变量"的证据。PCMCI+ 在 one-hot 二值序列上偏保守（漏 stay 的扇出），如实报告。观测图只有类型级骨架，没有门控（哪家 provider 自动改签）；门控仍来自按 regime 估计的局部决策模型。

**观测图能不能驱动选择。** `tcd_select` = 从干预源沿实例 links 只走被恢复的类型对 → 读 parser 归因的记录 → 同一执行器（选择阶梯口径）：

| 臂 | native | 50 | 100 | 500 | 500 档 reads |
|---|---:|---:|---:|---:|---:|
| graph_select（干预式骨架，原臂） | 1.000 | 1.000 | 1.000 | 1.000 | 12.4 |
| **tcd_select（观测式 pooled 图）** | **1.000** | **1.000** | **1.000** | **1.000** | **12.4** |
| tcd_select（PCMCI+ 图） | 0.59 | 0.59 | 0.59 | 0.59 | 6.8 |
| bm25_k16 | 0.90 | 0.32 | 0.04 | 0.04 | 21.2 |
| recency_k16 | 0.94 | 0.71 | 0.47 | 0.32 | 21.3 |
| wrong_select_1（重接线） | 0.43 | 0.43 | 0.43 | 0.43 | 5.9 |

Travel dev seeds 0/1/2，60 episode/seed；test seeds 30/31/32 数字相同到小数点后两位（tcd_select 1.000 / reads 11.2→12.1）。Shopping32 test seeds 30/31/32：tcd_select 0.972–0.978 = graph_select，reads 19→22 平坦；bm25_k16 0.98→0.05；recency_k16 1.00→0.66；wrong_select_1 与 graph_select 相同（cart 两跳内全连通，该对照在 Shopping 无区分力，与 9/18 结论一致）。文件：`results/development/hm3/tcd/ladder_dev_travel.json`、`results/real/hm3/tcd/ladder_test_travel.json`、`results/real/hm3/tcd/ladder_test_shopping32.json`。

### 3.2 G3：去掉手写 parser 的选择（`code/hm3/keysel.py`）

规则"最近的同 key 先例"：沿骨架到达的每个对象，取其类型声明的 key 字段（provider / hotel / restaurant / vendor，这是元数据，不是 policy 知识），找同类型同 key 值的对象最近被写入的 n 个 segment，读这些 segment 里的干预记录和先例对象及其 1-hop 邻居的记录；没有先例就读邻居最近被写入的 segment。不知道 buffer 是什么，也不知道怎么算。

| 臂 | native | 50 | 100 | 500 | 500 档 reads |
|---|---:|---:|---:|---:|---:|
| graph_select（parser 选记录） | 1.000 | 1.000 | 1.000 | 1.000 | 12.4 |
| key_select（n=1） | 0.97 / 0.98 | 0.90 / 0.93 | 0.81 / 0.83 | 0.65 / 0.57 | 16 |
| key_select2（n=2） | 1.00 / 0.99 | 0.97 / 0.99 | 0.92 / 0.94 | 0.82 / 0.80 | 26 |
| key_select3（n=3） | 1.00 / 1.00 | 0.97 / 0.99 | 0.95 / 0.98 | 0.89 / 0.88 | 35 |
| tcd_key_select（观测图 + 无 parser） | = key_select2 | | | | |
| bm25_k16 | 0.90 / 0.92 | 0.32 / 0.41 | 0.04 / 0.03 | 0.04 / 0.04 | 21 |

每格 dev / test 三 seed 均值。Shopping32（dev / test）：key_select 0.99 / 0.96 → 0.91 / 0.93（500 条，reads 31），key_select3 1.00 / 1.00 → 0.97 / 0.96（reads 69）。读法：**parser 不是选择阶段的必需品**，代价是读取量从 12 涨到 26–35（仍与 500 无关）和 500 档 0.1–0.2 的损失（损失来自同 key 的无信息先例，如 transfer 自己被移动过但没有航班变化）。执行器里的领域规则对所有阶梯臂相同。

### 3.3 actor 层：输出截断与 prompt 版本的混淆，16k 重跑的结果

**发现。** 审计 `results/real/hm3/scaling_v2` 的账本：`finish_reason` 和 `raw_reply` 记录的是格式修复那次调用，第一次尝试是否被 4096 输出上限截断在账本里看不见；按 `output_tokens ≥ 4096` 反推，100/500 档的 full/verbose 有 56/64、58/63 格被截断，修复调用返回 `[]`，判 0。把上限提到 16,384 后（`results/real/hm3/long_out/travel_{100,500,c100}`，同一批 64 个 episode，prompt v2，臂 = full/verbose、graph_closed/compact、bm25_k16/compact、graph_key2/compact）：

| 条件（prompt v2，16k） | full/verbose EES（打满 16k 的格） | full 未打满的格 EES | graph_closed EES（打满） | graph_key2 EES（打满） | graph_closed − full | graph_key2 − full |
|---|---:|---:|---:|---:|---|---|
| 100 | 0.20（45/64） | 0.53 | 0.25（6/64） | 0.36（16/64） | +0.05 [−0.09, +0.19] | +0.16 [+0.02, +0.30] |
| 500 | 0.11（50/63） | 0.38 | 0.29（4/63） | 0.24（22/63） | +0.17 [+0.05, +0.30] | +0.13 [−0.02, +0.25] |
| c100（同实体冲突 witness） | 0.19（38/63） | 0.44 | 0.32（7/63） | 0.33（18/63） | +0.13 [−0.02, +0.27] | +0.14 [+0.02, +0.27] |

输入 tokens 中位数：full 70k / 261k / 69k，graph_closed 1.7k，graph_key2 2.6–2.9k；输出：full 16.4k（打满），graph 1.2–1.5k。bm25_k16 在 100/500 档为 0.06 / 0.03（34–36 格打满），对 full −0.14 / −0.08。

**机制。** 对 episode test-016（100 档）做的重复探针：prompt v2 三次全部打满 16k，文本进入循环（"Actually h0 is auto … " 反复）；prompt v1（没有"先列 policy ledger"的方法段）四次都在 600 tokens 内终止，T91/S75 的取值全对（从 100 条记录里恢复了 buffer 45），但对 dinner 和 bundle 多写了两笔（collateral），EES 0。所以旧表里"全读在冲突证据下崩溃"的直接原因是 **v2 prompt 的"逐实体 policy ledger"步骤在 100+ 条记录上不终止**，不是 actor 解析错了冲突。

**判定（对照原判据）。** full 在 16k 下没有回到 ≥ 0.3（0.20 / 0.11 / 0.19），多数格仍打满，所以"稳健性"的弱形式保留：在这个 prompt 下，全读 actor 在长历史上不能完成分析；但效应量减半（+0.05 / +0.17 / +0.13，只有 500 档显著），而且 full 一旦终止就与 graph 相当或更好（0.38–0.53）。论文 §4.4 改写为两条：**成本**（输入 1–3%，输出 1/10）是主主张；**稳健性**只能写成"在要求先建 policy ledger 的 prompt 下，全读 actor 在 100+ 条记录上不终止"，并附打满比例与 prompt v1 的对照。旧的 4096 表不再作为主表。

**parser-free 的 actor 层结果（G3）。** graph_key2（选择阶段不用 parser）对 graph_closed：16k 下 +0.11 / −0.05 / +0.02（100 / 500 / c100），区间都含 0；4096 下 +0.14 / +0.02 / −0.13。即 actor 层与 parser 版持平，代价是输入 tokens 多 50–70%。native 档 graph_key3 对 graph_closed +0.19 [+0.05, +0.33]（读的记录更完整），仍输 full −0.19。

**prompt v1 的 16k 面板（完成，n=53–64）。** full/verbose 终止（打满 16k 的格 3–5 个），EES 100 档 0.25、500 档 0.16、c100 0.12；graph_closed/compact 0.25 / 0.29 / 0.16。配对差 graph − full：**+0.00 [−0.14, +0.14]（100）、+0.13 [+0.00, +0.25]（500）、+0.00 [−0.10, +0.10]（c100）**。两臂在 v1 下的失败模式都是多写（collateral 0.7–1.2 笔/episode，legal 0.65–0.81）。同一臂跨 prompt：graph_closed 在 c100 上 v2 − v1 = +0.23 [+0.05, +0.39]（v2 的 ledger 方法对短上下文有效），full 在 100 档 v2 − v1 = −0.05（区间含 0，v2 不终止与 v1 多写抵消）。

**最终判定。** actor 层能写的只有两条：(1) **成本**：任何长度下输入 1–3%、输出约 1/10，与 prompt 和上限无关；(2) **500 条记录下的适度优势**：两种 prompt 下是 +0.13 到 +0.17（v1 区间下端触 0）。"在冲突证据下更稳健"**撤回**：换成会终止的 prompt 后，100 档与 c100 两臂持平（0.25 对 0.25，0.12 对 0.16）；v2 下 full 的崩溃是不终止。旧的单类型分解表与 prompt v3 结果都是 4096 上限的运行，移到附录并标注。汇总命令：`python3 -m hm3.panel_summary --domain travel`（`results/real/hm3/long_out/panel_summary_travel.json`）。

平行的 4096 口径 parser-free 臂已完成（`results/real/hm3/keysel/travel_{native,100,500}`），数字见上。

### 3.4 同一张观测图反向追责（`hm3.provenance --graph tcd`）

正向 = `tcd_select`（观测式 pooled 图上的实例遍历 + parser 归因记录 + 运行时执行器），反向 = 从异常对象沿同一张图的类型对回溯到路径上各对象的 policy witness，再 leave-one-out 重排；协议、污染方式、对照与 `docs/hm3-provenance-design-2026-09-18.md` 完全相同，图的 SHA 记录在结果里。Travel test seeds 30/31/32，每 seed 60 episode：

| 指标 | native（观测图） | 500 条（观测图） | 参照：干预式 LearnedGraph，native |
|---|---:|---:|---:|
| 事件数 / episode | 52–56 / 60 | 54–57 / 59–60 | 42–52 / 60 |
| top-1 命中 | 0.52–0.61 | 0.46–0.65 | 0.55–0.65 |
| top-3 命中 | 0.96–0.98 | 0.91–1.00 | 0.98–1.00 |
| 替换 top-3 为干净版本后恢复 | 0.96–0.98 | 0.91–1.00 | 0.98–1.00 |
| 替换 matched random-3 | 0.00 | 0.00 | 0.00 |
| 替换最相似非祖先 / 最近记录 | 0.00–0.02 / 0.00–0.04 | 0.00 / 0.00–0.05 | 0.00 / 0.00–0.02 |
| BM25（异常对象为 query）top-3 | 0.26–0.52 | 0.16–0.31 | 0.29–0.60 |

文件：`results/real/hm3/tcd/provenance/test_tcd_{native,500}.json`。读法：Yujia 8/21 的"同一张图正向选择、反向追责"在观测式 TCD 图上成立，与干预式骨架的数字相同；事件数更多是因为观测图的正向臂用的是运行时执行器（没有学得的门控模型），污染更容易改变它的输出。

### 3.5 审计：今天的结果是不是代码错了或方法不对（回答 9/19 深夜的追问）

逐项核对，结论在前。

**观测式 TCD 的选择结果是真的。** `tcd_select` 与干预式骨架在 30/30 个 dev episode 上读到完全相同的对象集合；把恢复的边只留强链（flight→transfer→stay→{dinner, activity, bundle}）读取集合不变，只留弱的多余边读取集合塌到 1 个对象。所以 EES 1.0 来自恢复的链，不是来自代码把两者接到了同一处。事件编码里"用户干预行只做预测变量"用的是运行时可见的记录 kind 字段，没有偷看 gold。

**parser-free 选择是真的。** `key_select` 只用类型声明的 key 字段与 segment 边界；它读的记录里包含 segment 的干预记录（航班新到达时间），这是恢复 buffer 所必需且运行时可见的。执行器里的领域规则对阶梯上所有臂相同，这是阶梯的定义（"机制已知、只缺 witness"的选择上界），文档里已写明。

**actor 层旧数字是假的，新数字是真的，但 actor 实验本身的设计有两处不该沿用。** 先看 16k、会终止的 prompt v1 下 graph_closed 的失败分解（100 条，64 格）：EES 16、非法（对已被环境自动改签的 transfer 再写一笔，revision 过期）21、对未变对象多写 16、取值错 9。具体例子：provider 自动改签的 T67 被 actor 手动写入；把 provider 的 buffer（pickup_new − arrival_new = 50）算成两次 pickup 的差（+15）；把 buffer 与 transfer 的 ride 时长混为一谈。这些错误发生在**正确的最小记录集已经在上下文里**的情况下。全读臂的失败模式相同，外加漏对象。也就是说，actor 层在测 DeepSeek-Flash（关闭 thinking）做领域算术与 auto/txn 协议的能力，选择的信号被压在 0.1–0.4 的窄带里；EES 是全对全错的度量，把这种差别抹平。

沿用自前几轮、今天不该照搬的两处设计：(a) 比较的是 graph_closed/**compact** 对 full/**verbose**，序列化与选择混在一起（前几轮自己的消融显示 verbose 对 graph 有 +0.14）；(b) graph_closed 只给 witness 记录不给产生它的干预记录，前几轮的 graph_seg（整段）在 native 把差距从 −0.33 缩到 −0.11。今天的重跑照抄了 graph_closed/compact，这是我的疏漏。

**重做（已启动）。** 同一序列化两侧对齐：graph_seg/verbose 与 graph_closed/verbose 对 full/verbose，16k，prompt v2（`long_out/travel_{100,500,c100}/shards_v`），随后 v1。汇总工具 `hm3.panel_summary` 已加 affected F1 与 value accuracy 的配对差：EES 之外，这两个部分得分度量才能显示选择的作用（v1 下 500 档 graph_closed 的 value accuracy 0.58 对 full 0.41，affected F1 0.80 对 0.72；100 档两臂持平）。

**重做的结果（prompt v2，16k，同一 verbose 序列化，n=54–63；v1 进行中）。**

| 条件 | full/verbose EES（打满 16k） | graph_closed/verbose | graph_seg/verbose | graph_seg/verbose − full | graph_seg/verbose − graph_closed/compact（旧臂） |
|---|---:|---:|---:|---|---|
| native | 0.66（6/62） | 0.29 | 0.44 | −0.23 [−0.39, −0.06] | — |
| 100 | 0.20（45/64） | 0.38 | 0.37 | +0.18 [+0.04, +0.32] | +0.11 [−0.05, +0.26] |
| c100 | 0.19（38/63） | 0.48 | 0.44 | +0.22 [+0.07, +0.39] | +0.13 [−0.04, +0.30] |
| 500 | 0.11（50/63） | 0.40 | 0.56 | +0.44 [+0.30, +0.57] | +0.27 [+0.08, +0.44] |

部分得分同向：affected F1 +0.31 / +0.43 / +0.51，value accuracy +0.32 / +0.44 / +0.46。graph_seg/verbose 输入 3.6–4.4k tokens（full 69k–261k），输出 1.1–1.5k（full 打满 16k）。所以旧臂 graph_closed/compact 低估了结构的作用 0.1–0.3：compact 序列化与只给 witness 不给产生它的干预记录，两者一起压低了 actor 对同一份记录的利用。v2 下 full 的失败仍是不终止，最终判定等 v1 verbose 面板（`long_out/travel_*_v1/shards_v`）。

**重做后的最终判定（prompt v1，会终止，16k，同一 verbose 序列化，n=52–63）。**

| 条件 | full/verbose | graph_seg/verbose | graph_seg − full（EES） | value accuracy 差 |
|---|---:|---:|---|---|
| native（v1 / v2） | 0.48 / 0.66 | 0.48 / 0.44 | +0.00 [−0.16, +0.14] / −0.23 [−0.39, −0.06] | −0.04 / −0.09 |
| 100 条混合 | 0.25 | 0.33 | +0.08 [−0.06, +0.22] | +0.01 [−0.12, +0.15] |
| 100 条同实体冲突 | 0.14 | 0.33 | **+0.19 [+0.06, +0.32]** | +0.18 [+0.04, +0.31] |
| 500 条混合 | 0.16 | 0.33 | **+0.17 [+0.03, +0.32]** | +0.24 [+0.13, +0.36] |

两种 prompt 下方向一致（v2：+0.18 / +0.22 / +0.44）。所以 §3.3 里"冲突证据下更稳健撤回"的判断是用旧臂（compact、只给 witness）得出的，现在改为：**给 actor 完整的 witness 段（verbose）时，同实体冲突证据让会终止的全读 actor 从 0.25 掉到 0.14，结构化读取保持 0.29–0.33；100 条纯混合时两臂持平（+0.08，区间含 0）；500 条时结构领先 0.17；native 时 v2 下全读最好（0.66 对 0.44，−0.23），v1 下两臂相同（0.48 对 0.48）。** 成本主张不变：graph_seg/verbose 输入 3.8–4.1k tokens 对 full 27k–123k（v1）或 69k–261k（v2）。旧的 4096、compact 表移到附录。

**结论。** 桥的三块结果（观测式 TCD 恢复骨架、同图正反两用、parser-free 选择）没有代码错误，也符合 7/29 与 8/21 的方法要求。actor 层不是"没做出来"，是前几轮的头条数字来自截断与不终止，今天如实修正；它剩下的差距一部分是 actor 执行能力，一部分是比较设计，后者正在重做。

### 3.6 G2：MemoryArena substrate port（9/20 启动）

用户 9/20 决定尝试。范围（五天内可完成的版本）：

1. **真实实体**（`code/hm3/dgp_travel_arena.py`，领域名 `travel_arena`）：每个世界设在 MemoryArena travel 数据库的一个真实目的地城市；航班是真实航班号、真实到达时间、真实出发城市（`clean_Flights_2022.csv`），住宿是该城市的真实 accommodation 名，晚餐是该城市的真实餐厅名；隐藏策略按这些真实名字索引（`enforce_late[<hotel name>]`、`late_seating[<restaurant name>]`）。机制、可见规则、parser、执行器与 HM3 Travel 完全相同。接送 provider 与 bundle vendor 在数据库里没有对应物，保留生成 id，论文如实说明。词表缓存 `results/real/hm3/arena_vocab.json`（312 个城市；名字含 `[ ] |` 的排除，因为策略 key 写作 `name[key]`）。
2. **MemoryArena 的 memory 接口**（`code/hm3/arena_run.py`）：每条历史记录经 `add_chunk` 写入，查询经 `wrap_user_prompt` 读出，返回的 `<memory_context>` 里出现的记录 id 即 actor 收到的记录；所有系统用同一 verbose 序列化和同一 HM3 actor prompt。系统 = MemoryArena 自己的实现，按文件加载、一行不改（其 git 树保持干净）：`bm25`（`RAGMemorySystem`，其默认 top_k = 3）、`bm25_k16`（同类，top_k = 16，与我们的固定 K 臂对齐）、`long_context`（全部）、`amem`（`AMemMemorySystem`，其默认 k = 5，LLM 换成 actor 同一端点，写入 tokens 记录）；`causal` = 我们的 graph_seg 选择放在同一个两方法接口后面（selector 需要的状态与干预在构造时给，类比 ReasoningBank 的 user_id）。记忆构建按 (system, episode, condition) 缓存，两种 prompt 复用。
3. **确定性门**（`results/development/hm3/arena/ladder_dev_travel_arena.json`，dev seed 0）：真实实体上 graph_select / tcd_select 在 100 条为 1.000（reads 11.7），bm25_k16 0.07，recency_k16 0.44，key_select2 0.97，wrong_select_1 0.56，program_reg 0.58；与合成 id 的 Travel 一致，说明机制不依赖 id 的形态。
4. **actor 面板**（`results/real/hm3/arena/travel_arena_{native,100,c100,500}/shard_*/{v1,v2}`）：seed 30，64 episode，16k，两种 prompt；`amem` 只在 native 与 100 档。启动脚本 `code/hm3/arena_shards.sh`（每个 shard 一个进程，v1 → v2 → amem v1 → amem v2 顺序执行，选择缓存不会被两个进程同时写）。9/20 下午三次启动失败后（内联引号把 `&&` 链拆成并行、`kill` 匹配到自己的 shell、相对路径），17:55 干净启动：16 个进程，全部在 v1 阶段，无重复。第一版 runner 的 `causal` 臂 state block 从记录反推（required-read recall 0.75），已改为 selector 自己的对象读取并加断言（接口返回的记录 == selector 的记录）；受影响的 160 格已删除重跑。汇总：`hm3.panel_summary --domain travel_arena`（`arena/` 已加进 SOURCES）。

5. **结果（9/20 晚，四个便宜系统 64 episode × 4 条件 × 2 prompt 全部完成；A-Mem 100 档运行中）。** ours − long_context：native +0.05 / +0.03（v1 / v2，区间含 0），100 条 +0.31 / +0.30，冲突 +0.12 / +0.27，500 条 +0.20 / +0.48；ours − BM25 top-16：+0.14 到 +0.55，全部显著。ours 输入 3.8–4.8k tokens，long_context 7k–269k。MemoryArena 默认 BM25（top-3）在所有长度 0.02–0.08；A-Mem（默认 k=5）native 0.11–0.14。合成 id 上 native 档全读更好的 crossover 在真实实体上没有出现（持平）。完整表在结果包 "Substrate" 节。

论文口径：载体仍是我们构造的机制，实体、记忆接口与 baseline 实现来自 MemoryArena。它回答的是"结果是否是合成 id 或我们自己写的 baseline 的产物"，不回答"公开 benchmark 原任务上是否成立"。

### 3.7 9/20 会后：causal 这个词的合法性（最高优先级）

Yujia 的判断：pipeline 已完整；"causal" 只有在结构由成熟的 causal discovery 算法得到时才能讲，否则叫 temporal dependency structure，causal 主张留给受控仿真。做法：在同一批事件日志上跑 PCMCI+（ParCorr、G²）与 GRACE（PCMCI+ 骨架 / 开放骨架 ×1、×3、×10），与干预式骨架和我们的回归估计量比边的 P/R 与 seed 稳定性，再把每张图插进现有的正向选择与反向 provenance。代码 `code/hm3/grace_logs.py`（环境：`PYTHONPATH=pylib_tcd:pylib2:旧 pylib`，见 memory）。Travel seed 0 的初步结果：所有成熟方法都恢复链头 flight→transfer→stay；CI 检验把链尾归到 flight 的 lag 3 并剪掉中介（中间写入是确定性的，即 E0 记录的 hold regime 下 faithfulness 失效）；GRACE 开放骨架把五条真边排在最前但阈值不够稀疏（×3：R 0.8 / P 0.27；×10：P 0.5 / R 0.6）。`tcd_logs.adjacency_reads` 已支持按 lag 展开，剪过的图仍能到达全部受影响对象（29/30）。六 seed 双领域扫描已完成且跨 seed 稳定。下游：Travel 上除 ×10 过度惩罚外，每张恢复的图都把选择做到参照水平（EES 1.000，reads 10–12），GRACE ×3、G²、回归三张图的 provenance 与参照相同（top-3 0.91–1.00，替换恢复同率，对照 0）；Shopping 上 CI 骨架太稀疏（0.10–0.44），GRACE 开放骨架与回归达到参照。结论：pipeline 消费的结构可由 GRACE 参考实现从日志得到；中介边被 CI 剪掉的 caveat 如实写。不为让 GRACE "赢"调参；所有估计量并列报告。表在结果包 "Structure from established causal discovery methods" 节。

## 4. 给 Yujia 的四个事实与一个问题（修订版）

事实一（不变）：TCD 按原方案跑在 MemoryArena Travel 和 MINJA 上得到 10 自环 + 2 跨 slot 边，以及空图。

事实二（新）：同一个 pooled 时序估计量在 HM3 的事件日志上恢复了完整的传播骨架（Travel 6/6 seed recall 1.0；Shopping32 6/6 recall 1.0），用它选记忆与干预式骨架完全一致（Travel EES 1.0 / reads 12；Shopping32 0.99 / reads 21），用它反向追责与干预式骨架相同（top-3 0.91–1.00，干净替换恢复同率，对照 0）；用 MemoryArena 式的"每轮激活"编码，它在 HM3 上同样退化成自环。所以 7/29 的路线没有错，错的是当时 benchmark 的变量没有传播动力学。

事实三（新）：把手写 parser 从选择里拿掉，500 条历史下确定性层 Travel 0.80–0.89、Shopping32 0.96–0.97（reads 26–69，与历史长度无关）；actor 层与 parser 版持平（§3.3）。

事实四（新，必须先说）：旧的 actor 层"全读在冲突证据下崩溃"（+0.28 / +0.24）混有两件事：4096 输出截断后的空修复，和 v2 prompt 的 policy-ledger 步骤在 100+ 条记录上不终止。用会终止的 prompt、同一 verbose 序列化、完整 witness 段重跑后：100 条混合两臂持平（+0.08，区间含 0），同实体冲突 +0.19 [+0.06, +0.32]，500 条 +0.17 [+0.03, +0.32]，native 全读更好或相同（v2 −0.23，v1 0.00）；成本优势不变（输入 1–3%）。效应量约为旧表的一半到三分之二，方向在两种 prompt 下一致。

问题：论文是哪一种？
(A) 以 TCD 为方法：可以写"观测式时序发现在有传播动力学的 memory 任务上恢复骨架，在静态规划 benchmark 上退化"，门控由 regime 条件化的局部模型补；载体仍是 HM3（自建），补现代 memory 系统同台。
(B) 以干预式结构学习为方法，如实命名，其余同 (A)。
两者都要问：HM3 在她的三块里算 memory task 还是 simulation；以及是否接受"载体自建、baseline 认得"的折中，因为读者认得的载体六天内做不出隐藏机制版本。

### 4.1 对现有 abstract 的四处措辞（供讨论，不替她改）

1. "this structure can be recovered and that it makes memory both selective and auditable"：把 **recovery** 与 **utility** 拆开写。recovery 的证据是 E0（受控 SCM）和本页 §3.1（HM3 日志上的观测式 TCD），都在生成数据上；utility 的证据是 HM3 的选择与 provenance。MemoryArena/MINJA 上没有 recovery。
2. "the latent temporal process"：现有实验都在观测变量上（Layer 1）；"latent" 会让读者期待 Layer 2 的表示学习。建议 "the temporal process underlying the trajectory"。
3. "we write things down mainly when that recall cannot be trusted"：实验只回答 what to read 与 what caused the error，没有 write policy 的实验；引言里可保留作动机，方法/实验不要承诺。
4. write/hold/read 门控：E0 的 regime 是访问阶段，HM3 的 regime 是隐藏策略；正文必须分开命名（`docs/causal-vocabulary-and-estimators-2026-09-19.md` §2）。

## 5. 六天计划（9/19–9/25）

| 日期 | 内容 | 负责 |
|---|---|---|
| 9/19 | TCD-on-logs、parser-free 阶梯（Travel dev/test 完成）、截断审计、16k 重跑与 keysel 臂启动、本页 | A |
| 9/20 | 16k 重跑收口与判定（§3.3）；Shopping32 阶梯 test 面板；Shopping32 16k 重跑；native 16k 复核 | A / B |
| 9/21 | Mem0 selector 臂（Travel/Shopping native+100）、A-Mem 100 档补齐；graph_key 的 actor 配对表 | B / A |
| 9/22 | provenance 用观测图反向遍历（可选，B）；结果包与 show-Yujia 文档改写（A） | A / B |
| 9/23 | 论文 outline §2–§4 按新事实改；case figure 数据 | A |
| 9/24 | 冻结主表；补跑缺格 | A / B |
| 9/25 | 交稿材料 | A |

## 6. 不做的事（六天内）

- 不在 MemoryArena Travel 上造受控干预面板（§2）。
- 不再改 E0。
- 不为 PCMCI+ 调参：它作为现成方法如实报告。
- 不把 4096 口径的旧 actor 表继续当主表，直到 §3.3 判定。

## 7. 双 session 分工与规则（2026-09-20 重写；以本节为准，B 从这里开始读）

### 7.1 现状（9/20）

已完成并写进 `docs/hm3-results-package-2026-09-19.md`、`docs/yujia-show-now-2026-09-19.md`、`docs/paper-outline-detailed-2026-09-19.md`：
- 桥的三块（§3.1 观测式 TCD 恢复骨架、§3.2 parser-free 选择、§3.4 同一观测图反向追责），Travel 与 Shopping32 的 dev/test 阶梯全部完成。
- actor 层的审计与重做（§3.3、§3.5）：Travel 与 Shopping32 在 16k、两种 prompt、同一 verbose 序列化下的全部面板完成。最终口径：成本主张两个领域成立；准确率优势只在 Travel（同实体冲突 +0.19、500 条 +0.17，会终止的 prompt），Shopping 500 条全读反而更好（−0.19）。
- 旧的 4096 上限 / compact 表全部标为附录。汇总命令 `python3 -m hm3.panel_summary --domain {travel,shopping32}`。

仍在运行（nohup，跨 session 存活；**不要重复启动**）：
- ~~mem0_raw~~ **已完成**（四条件各 64/64，0 失败）：Travel native 0.27、100 条 0.05（required-read recall 0.79 → 0.39，44/64 打满 16k）；Shopping32 native 0.53、100 条 0.30。对 graph_seg/verbose：Travel −0.16 / −0.31，Shopping 100 条 −0.05。已写进结果包 Boundaries。
- `results/real/hm3/memsys/amem16k/{travel,shopping32}_100`：A-Mem 100 档 16k 重跑，8 个进程，每条件 11–14/64（A-Mem 写入侧每 episode 约 99 次 LLM 调用，预计还要数小时）。两个领域各有 3 格 `infrastructure_failure: Connection error.`（端点瞬断）。**B1 补充：** 全部 shard 结束后，用与启动时完全相同的命令再启动一次同一 out_dir（runner 只跳过已成功的 cell，会重试失败格），把这 6 格补上。
- 判断"完成"的方法：`ps -o args -C python3 | grep -c memsys_llm` 为 0，或每个 shard 目录的 `llm_ledger.jsonl` 里 `"event": "cell"` 行数达到 16。

### 7.2 规则（不变）

- **Session A**（本页作者）拥有 `code/`；**只有 A 运行 git**。工作树目前有未提交的改动（`code/hm3/{keysel,tcd_logs,panel_summary}.py` 新增，`llm.py`、`provenance.py`、`memsys_llm.py`、`memsys_summary.py`、`autodl_shards.sh` 修改，五份 docs 修改），提交与否由用户决定。
- **Session B** 只跑实验、只写自己名下的结果目录和 `docs/bridge-session-b-notes-2026-09-19.md`。**不改 `code/` 下任何文件**（要改就写进 notes），**不运行任何 git 命令**，不删除、不重命名已有目录，不重启已在运行的 shard。
- API key：B 用 `KEYIDX="2 3"`（或 `sed -n 3p / 4p` 取第 3、4 行），A 用 0、1。
- 并发：同一时刻不超过 16 个 actor/memsys 进程。这台机器与其他用户共享，负载常在 130–160；每个 episode 的生成与增广是 CPU 密集的，超过 16 个进程会把所有 shard 拖到每格几分钟。
- 环境：

```bash
ROOT=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/Memory
PYLIB=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/claude-20043/-mnt-cpfs-epic-user-yangboxue-20260612-opsd-Memory/aa111f6d-b918-45ce-bc18-326170fa9a1b/scratchpad/pylib2
TCD=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/claude-20043/-mnt-cpfs-epic-user-yangboxue-20260612-opsd-Memory/217e732a-15fb-4e94-a23f-a5fefafa4d2b/scratchpad/pylib_tcd   # tigramite
export PYTHONPATH=$TCD:$PYLIB:$ROOT/benchmarks/A-mem:$ROOT/code
cd $ROOT/code
```

### 7.3 踩过的坑（B 必读）

1. **actor 输出上限**：所有 actor / memsys 调用必须 `--max_tokens 16384`；4096 会把长历史的全读臂截断成空修复判 0（§3.3）。
2. **prompt 版本**：`hm3.llm` 默认 `--prompt v1`，shard 脚本默认 `PROMPT=v2`；两者都要报。v2 的 policy-ledger 步骤在 100 条以上历史不终止。
3. **序列化**：只把 graph_seg/verbose 或 graph_closed/verbose 与 full/verbose 比；compact 对 verbose 的比较低估结构 0.1–0.3。
4. **Mem0**：默认抽取模式（infer=True）对本任务几乎不存记忆，作为负结果报告；可比臂是 `--system mem0_raw`。`memsys_llm` 已把 Qdrant 路径、history.db、`MEM0_DIR` 都隔离到每个进程/episode 的临时目录，否则并行 shard 会互相锁死（`Storage folder ... already accessed`）。
5. **A-Mem**：每次构造 reset Chroma，逐 episode 无污染；100 档必须 16k。
6. **shell**：把带花括号展开的路径放进带引号的变量里不会展开（`"a_{100,500}/*"`），计数会得到 0；用显式路径。`grep -c` 在文件不存在时输出空字符串，算术前要 `${c:-0}`。
7. **shard 启动脚本**：`code/hm3/autodl_shards.sh` 的 `echo` 不要接管道，否则前台会挂住；用 `> /dev/null 2>&1`。

### 7.5 B 的新任务（2026-09-21 中午起；优先级高于 7.4 里未完成的项）

背景：9/20 夜方法重做——记忆系统对自己的**读取**做干预（重放时屏蔽记录，ddmin 找最小充分读集），parser-free 的 frontier 模型把重放摊销到测试时；设计 `docs/method-design-read-interventions-2026-09-20.md`，全貌 `docs/full-status-method-experiments-paper-2026-09-21.md`。代码在 `code/hm3/replay*.py`（A 已写好，B 只运行）。B 的机器是 Python 3.12，**不要**用 A 的 PYLIB；先检查 `python3 -c "import sklearn, numpy"`：能 import 就全部可跑，不能就只跑 B4、B6（它们不用 sklearn）。环境：`cd $ROOT/code; export PYTHONPATH=$ROOT/code; export OMP_NUM_THREADS=2`。每个任务一个 nohup 进程，总数 ≤ 8（这些是 CPU 密集的）。结果目录都是新的，不会与 A 冲突；跑完把每条打印的汇总行贴进 notes。

**B4 重放次数 vs 历史长度，test seeds（CPU，不需要 sklearn，约 30 分钟）。** dev seeds 已有（`results/development/hm3/replay/length_*.json`），要 test seeds 的同一张表：

```bash
nohup python3 -m hm3.replay_length --domains travel shopping32 --seeds 30 31 32 --n_train 60 --out ../results/real/hm3/replay > ../results/real/hm3/replay/length_test.log 2>&1 &
```

**B5 p_θ 折中扫描，其余 seed 与长度（CPU，需要 sklearn；每个约 30–60 分钟）。** 已有 travel/shopping32 seed 0 在 500 条。要：

```bash
for dom in travel shopping32; do for seed in 1 2; do for L in 500 100; do
  nohup python3 -m hm3.replay_sweep --domain $dom --seed $seed --length $L --out ../results/development/hm3/replay > ../results/development/hm3/replay/sweep_${dom}_s${seed}_${L}.log 2>&1 &
done; done; done   # 8 个进程；若机器负载高就分两批
```

**B6 用同一原语定位肇事记录，其余条件（CPU，不需要 sklearn）。** Travel native 与 500 已有（`results/real/hm3/replay/localise_travel_*.json`）。要 Travel 100 条与 c100，以及 Shopping32 native / 500（Shopping 预期是边界：多数腐蚀不产生事故，照实报）：

```bash
nohup python3 -m hm3.replay_localise --domains travel --history 100:abcd --out ../results/real/hm3/replay > ../results/real/hm3/replay/localise_travel_100.log 2>&1 &
nohup python3 -m hm3.replay_localise --domains travel --history 100:c    --out ../results/real/hm3/replay > ../results/real/hm3/replay/localise_travel_c100.log 2>&1 &
nohup python3 -m hm3.replay_localise --domains shopping32 --history native   --out ../results/real/hm3/replay > ../results/real/hm3/replay/localise_shopping_native.log 2>&1 &
nohup python3 -m hm3.replay_localise --domains shopping32 --history 500:abcd --out ../results/real/hm3/replay > ../results/real/hm3/replay/localise_shopping_500.log 2>&1 &
```

**B7 frontier 阶梯的新臂（CPU，需要 sklearn；每个阶梯 1–3 小时）。** A 刚注册了 `frontier_select_o1_t30_seg`（整段选择）、`frontier_select_o1_t70`、`frontier_select_o1_t50_seg`。dev 与 test 各一个进程、两个领域：

```bash
L="frontier_select_o1_t30_seg frontier_select_o1_t70 frontier_select_o1_t50_seg graph_select"
for dom in travel shopping32; do conds="native 100 c100 500"; [ $dom = shopping32 ] && conds="native 100 500"
  nohup python3 -m hm3.run_scaling --domains $dom --seeds 0 1 2 --conditions $conds --split dev --train_seed_offset 100 --learners $L --out ../results/development/hm3/replay/ladder_frontier2_dev_$dom.json > ../results/development/hm3/replay/ladder_frontier2_dev_$dom.log 2>&1 &
  nohup python3 -m hm3.run_scaling --domains $dom --seeds 30 31 32 --conditions $conds --split test --train_seed_offset 100 --learners $L --out ../results/real/hm3/replay/ladder_frontier2_test_$dom.json > ../results/real/hm3/replay/ladder_frontier2_test_$dom.log 2>&1 &
done
```

**B8（可选，需要 B 的机器能 `import openai`；key 2/3）。** 两件 API 活，A 的 key 0/1 正被 k=3 的 LLM 发现占用：
1. v2 prompt 下的多数票 LLM 发现（A 在 v1 上跑着）：
```bash
mapfile -t KEYS < <(grep -v '^\s*$' $ROOT/api/api.txt)
for sh in 0 24; do idx=$([ $sh = 0 ] && echo 2 || echo 3)
  OPENAI_API_KEY="${KEYS[$idx]}" OPENAI_BASE_URL=https://www.autodl.art/api/v1 nohup python3 -m hm3.replay_llm --domain travel --seed 30 --ep_start $sh --n_train 24 --prompt v2 --repeats 3 --out_dir $ROOT/results/real/hm3/replay_llm/travel_s30_v2_k3_$sh --budget_usd 12 > $ROOT/results/real/hm3/replay_llm/v2_k3_$sh.log 2>&1 &
done
```
2. parser-free `frontier_exec` 臂补齐面板（Travel native、100；Shopping32 100、500；v1、verbose、16k）：
```bash
cd $ROOT
for spec in "travel native" "travel 100:abcd" "shopping32 100:abcd" "shopping32 500:abcd"; do set -- $spec; dom=$1; H=$2; tag=${H%%:*}
  KEYIDX="2 3" PROMPT=v1 SERS=verbose MAXTOK=16384 PYLIB= bash code/hm3/autodl_shards.sh results/real/hm3/frontier_llm/${dom}_${tag}_exec $dom $H 64 16 3.0 frontier_exec > /dev/null 2>&1
done
```
（`PYLIB=` 置空是给 3.12 机器用的。启动脚本的 echo 不要接 `head`——会 SIGPIPE 杀掉后续 shard，A 今天踩过。）

汇总：B4/B6 各自打印一行 JSON；B5 打印每个设置一行；B7 用 `python3 - <<EOF` 读 json 里 `runs[*].learners[*].summary.ees`；B8 的面板用 `python3 -m hm3.panel_summary --domain travel`（`frontier_exec` 已在 ARMS 里）。

**9/21 17:00 A 的回复：** §7.5 全部收到并并入 `docs/full-status-method-experiments-paper-2026-09-21.md` §4.7。两处代码已改：`replay_localise` 的 bm25 键改为 `bm25_anomaly`（六个定位文件正在 A 这边重跑，之前的 bm25 列一律读作 history 列）；`panel_summary.SOURCES` 加了 `{d}_native_exec` 与 `{d}_100_exec`。口径确认：阶梯的 `n_reads` 是 **对象数 + 记录数**（`core.score_plan`），扫描的 `records` 只数记录；Travel 500 的 125–133 = 49 条记录 + 它们的 referent 与一跳闭包对象。B 暂无新任务；下一批（若有）写在 §7.6。

**9/21 17:40 A：** 用户批准大并行；B 空闲期间 A 占用全部四个 key（0–3）跑三批：Travel seeds 31/32 的 actor 面板（full / graph_seg / frontier_exec × 四条件，v1）、多数票 LLM 发现扩到 episode 48–191（两种 prompt，12 个进程）、Shopping frontier_exec v2。B 若要再启 API 任务，先在 notes 里说一声，改用 KEYIDX="2 3" 时 A 不再往 2/3 上加进程。

### 7.6 9/22 早：B 暂无新任务

A 的机器重启后也是 Python 3.12（`PYTHONPATH=$ROOT/code` 即可）。A 正在跑：Travel seeds 31/32 的 v1 500 条补完与 v2 c100/500 复制（key 0–3）。§7.5 的全部结果已并入状态页 §4.7–4.9；B 的两处代码问题已修。若 B 想做点什么：把 `docs/full-status-method-experiments-paper-2026-09-21.md` §4 从头读一遍，把数字与 `results/` 里的 json 逐条核对，不一致的写进 notes §7（这是冻结表前最有价值的事）。

### 7.4 B 的任务（按顺序）

**B1 收 memsys 结果。** 等 §7.1 的两组进程结束后：

```bash
python3 -m hm3.memsys_summary --system mem0_raw --ref 16k --domains travel shopping32
python3 -m hm3.memsys_summary --system amem --dir amem16k --ref 16k --domains travel shopping32
python3 -m hm3.memsys_summary --system amem --ref 4096 --domains travel shopping32   # native 档仍是 4096 口径
```
把三张表贴进 notes，并标出每个条件的 cap hits（表里有列）。若 mem0_raw 某个条件的 `infrastructure_failure` 行数不为 0，把首条错误贴进 notes，不要重跑。

**B2 parser-free 的同序列化 actor 臂（唯一缺的格）。** 结果包里 parser-free（graph_key2）只有 compact 口径。跑 verbose + 整段的版本，两种 prompt，Travel 三个条件：

```bash
cd $ROOT
for P in v2 v1; do suf=""; [ $P = v1 ] && suf="_v1"
  for H in 100:abcd 500:abcd 100:c; do tag=${H%%:*}; [ "$H" = "100:c" ] && tag=c100
    KEYIDX="2 3" PROMPT=$P SERS=verbose MAXTOK=16384 SHARDSUB=shards_key bash code/hm3/autodl_shards.sh results/real/hm3/long_out/travel_${tag}${suf} travel $H 64 16 30.0 graph_key2 > /dev/null 2>&1
  done
done
```
一次只启动一个 prompt 的 12 个 shard；完成后 `python3 -m hm3.panel_summary --domain travel` 会自动把 `graph_key2/verbose` 配对进表（脚本已含该臂）。这回答"去掉 parser 后 actor 层是否仍与 parser 版持平"的 verbose 版本。

**B3 A-Mem native 档 16k 复核（可选，B1 完成后）。** A-Mem native 的四个条件仍是 4096 口径（Travel 7/64、Shopping 10/64 被截断）。若有余力：

```bash
for D in travel shopping32; do for s in 0 16 32 48; do e=$((s+16))
  OPENAI_API_KEY="$KEY" OPENAI_BASE_URL=https://www.autodl.art/api/v1 nohup python3 -m hm3.memsys_llm --system amem --domains $D --seed 30 --n_eval 64 --ep_start $s --ep_end $e --history native --k 16 --max_tokens 16384 --budget_usd 20 --out_dir $ROOT/results/real/hm3/memsys/amem16k/${D}_native/shards/${D}_${s}_${e} > $ROOT/results/real/hm3/memsys/amem16k/${D}_native_${s}.log 2>&1 &
done; done
```

**B4 notes。** `docs/bridge-session-b-notes-2026-09-19.md`：每张表、每个异常、每条想改代码的建议。A 会把表合并进结果包。

### 7.5 对 B 9/19 notes §2 的处理（9/20）

1–3 已改：`memsys_summary` 的 cap-hit 阈值改为读各 shard `llm_protocol.json` 的 `max_tokens`；参照目录缺账本时跳过；`autodl_shards.sh` 的 `PYLIB` 可用环境变量覆盖或置空。4–5 记入 §7.2（B 的机器是 Python 3.12，memsys 臂只能在 A 的机器跑，B3 由 A 负责）。B 收 A-Mem 16k 表时请重跑 `memsys_summary`，cap hits 列现在正确。

### A 的清单

- 收 B1/B2 的表进结果包 §Layer 2 与 §Boundaries；outline §4.7 的"现代 memory 系统"段按 mem0_raw / A-Mem 16k 改写。
- 论文 §4.4 的成本图与 EES–历史长度图的数据文件。
- 与用户确认是否提交当前工作树。

## 8. 待办清单

- [x] `code/hm3/tcd_logs.py`、`keysel.py`：观测式 TCD 图、parser-free 选择；`llm.py` 的 `graph_key{n}` 模式；`provenance.py --graph tcd`
- [x] TCD 图与选择阶梯：Travel / Shopping32，dev + test，六 seed
- [x] 观测图 provenance：Travel test seeds，native / 500
- [x] actor 层审计与 16k 双 prompt 同序列化重跑：Travel（native/100/c100/500）与 Shopping32（100/500）
- [x] `hm3.panel_summary`、`hm3.memsys_summary --ref 16k`
- [x] 结果包 / show-Yujia / outline / vocabulary 按最终口径改写；4096 表标附录
- [x] mem0_raw 四条件（已收表，写进结果包）
- [x] A-Mem 100 档 16k：64/64（6 格连接失败已补），表已更新进结果包
- [x] graph_key2/verbose 同序列化臂（B2，B 完成）：≤100 条与 parser 版持平，500 条落后 0.14–0.27，对 full 仍 +0.03 到 +0.17
- [x] A-Mem native 16k（Travel 由 B 的 venv312 跑完 0.34；Shopping 由 A 跑完 0.61）。A 在 17:05 改计划并向同一 out_dir 启动，与 B 撞车，20 行重复 cell 由汇总去重，Shopping 日志被截断但账本无损：A 的责任，规则改为"改 §7 前先在 notes 留言，启动前 stat 目标账本"
- [x] formulation ↔ HM3 映射：`docs/hm3-formulation-mapping-2026-09-20.md`（sample / variable / time step / regime / carrier / frontier，变量集合跨 episode、条件、regime、领域的一致性）
- [x] provenance case figure：`results/real/hm3/provenance/figures/case_travel_s30_test000.{pdf,svg,png}`（`code/hm3/case_figure.py`，数字对照 episode 核过：buffer[P51]=20、late_cutoff 1290）
- [ ] 结果包合并 memsys 表；成本图数据（A）
- [x] substrate port（§3.6）：门已过，actor 面板四系统完成，结果包 "Substrate" 节已写；A-Mem 100 档收尾中
- [ ] A-Mem native 16k：A 已在本机启动（travel 60/64 续跑，shopping32 7/64）
- [ ] 提交工作树（用户决定）

- 9/20 深夜：Yujia 交付页 `docs/yujia-causal-bridge-2026-09-20.md`（一张图 + 三组数）已写；actor 层 provenance 16k 重跑完成（v1 net +0.13 / +0.17，v2 +0.35 / +0.29），替换 4,096 上限旧行；GRACE 图选出的记录集与参照相同（63–64/64），不重跑 actor 面板。
- 9/20 更晚：图（`results/real/hm3/figures/`）、实验节草稿（`docs/paper-draft-experiments-2026-09-20.md`）、GRACE 门值排序 AP 已加；"GRACE 把 5 条真边排在最前"一句是错的，已在结果包与交付页改正。
