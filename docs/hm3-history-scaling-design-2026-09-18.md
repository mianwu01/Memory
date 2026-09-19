# HM3 history-length scaling：冻结设计（2026-09-18）

状态：**在生成任何 test seed 之前冻结。** 本页提交后才允许生成 test seeds 30/31/32；dev seeds 0/1/2
只用于规则校准与本页写明的验收。代码：`code/hm3/scaling.py`（augmentation 与 fixed-K 读取臂）、
`code/hm3/run_det.py --history`。结果目录：`results/development/hm3/scaling/`（dev）、
`results/real/hm3/scaling/`（test 与 API）。

## 1. 问题

历史变长时，学得的结构能否让读取量保持平坦、任务成功率稳定；固定 K 的检索是否丢失必需记录；
读取全部历史的方法读取量是否线性增长。这是论文实际动机（历史越长越不应全读）的直接检验。

## 2. 长度档与领域

- 领域：`travel`、`shopping32`（v3.2）。
- 总记录数档位：**native / 50 / 100 / 500**。native 是未增广的原生 episode（Travel 约 13、Shopping
  约 10 条记录）。其余档位把历史 H 增广到恰好该记录数（最后一个外来 segment 从头截断以对齐）。
- 同一 episode 在四个档位中 **S0 中原链对象、I、A、S1 中原链对象、R、required reads 全部相同**，
  因此 dependency depth 与 relevant-record 数量按构造固定；四档是配对样本。
- 增广后 S0 也包含外来对象（见 §3），因为真实记忆的增长同时增加记录与实体；报告中同时给出
  记录数与对象数。

## 3. 四类干扰，分别冻结

外来对象 id 与 S0 不相交；外来 segment 一律放在真实历史之前。parser 按 segment 顺序取
**最后一个 witness**，且只解析 S0 中存在的对象，因此对被 consult 的 key，est 与 prov 不变。

| 类型 | 构造 | 对 parser 的影响 | 对检索 / LLM 的影响 |
|---|---|---|---|
| A same-world stale versions | 对每个被 consult 的 key，克隆其 witness 记录放到历史开头；delta 重新链接使其 new 值等于真实历史开始时的字段值，old 值按原 delta 差量回推；非 intervention 记录的 kind 在 auto/txn 之间翻转 | 隐含参数值可能不同，但被后面的真实 witness 覆盖 | 同对象、同 key、更早、值不同 |
| B same-type near duplicates | 同一世界的改名副本（对象 id 改名，隐藏参数与 policy key 相同），在其上运行若干随机 prior interventions，合并其对象与记录 | witness 与真实一致；只可能补上未被 consult 的 key | 同 key、同类型、其他链，证据一致 |
| C misleading lexical matches | 同一世界的改名副本，但隐藏参数扰动（二值翻转、连续值重抽）；名字与 key 相同 | 冲突 witness，被后面的真实 witness 覆盖 | 同名同 key 的冲突证据 |
| D cross-world distractors | 无关世界（新 key、新名字、新对象），运行随机 prior interventions | Travel 不解析出共享 key；Shopping 的 category 级 key 天然共享，等价于对未 consult 的 key 起 C 的作用 | 纯体积 |

混合条件（主条件）：A 固定为每个 consulted key 一份克隆；剩余预算在 B、C、D 之间等分。
单类型诊断条件（100 条）：A-only（native + 克隆，不补足到 100）、B-only、C-only、D-only。
A 的"隐含值不同于真值"比例按 episode 度量并报告，不假设。

## 4. 方法臂

现有全部确定性方法（exact_kv、source_union、source_regime、knn、flat、flat_est、gnn、gnn_est、
superset、program、program_reg、graph、graph_pooled、rh_oracle、oracle）不改动。新增固定 K 读取臂：

- `retrieval_k8`、`retrieval_k16`：按 query 文本与 source 对象文本对记录做词元重叠打分，取 top-K
  记录，用 `restricted_est` 只从这些记录恢复参数，再用与 rh_oracle 相同的执行器输出事务。这是
  任何 K 条记录检索器的上界（机制已知，只缺 witness）。
- `recency_k16`：最近 16 条记录，其余同上。

训练与评测在**同一长度条件**下增广（train 200 / dev 60 均增广），每个条件各自拟合。

## 5. 预注册预测（dev 与 test 相同判据；按 episode 配对，报告 95% bootstrap 区间）

- P1 **graph 读取平坦**：graph 的 mean n_reads 在 500 档不超过 native 档的 1.25 倍。
- P2 **graph EES 稳定**：graph 在每个档位的 EES 与 native 的配对差绝对值 ≤ 0.05。
- P3 **固定 K 检索退化**：retrieval_k16 的 required-record recall 在 500 档比 native 低 ≥ 0.20。
- P4 **全历史读取线性增长**：reads 等于全部记录与对象的方法（knn、flat、flat_est、gnn、gnn_est）
  的 n_reads 随总记录数斜率 ≈ 1。

不预注册 program、full 或任何黑盒方法的准确率必须下降；它们的变化如实报告。

## 6. 增广有效性断言（每个 episode，失败则换增广种子重试 3 次，仍失败则丢弃并计数）

1. 对 `relevant_params` 中每个 key，增广后 `infer_params` 的 est 与 prov 与原生完全相同。
2. `required_reads` 完全相同。
3. `rh_oracle` 在增广 episode 上的事务集与 A 相同，EES = 1；`oracle` EES = 1。
4. 总记录数等于目标档位。

丢弃率 > 5% 则该条件作废并回到设计修改，不得只汇报存活子集。

## 7. 进入 API 的条件与 API 设计

dev 上 P1、P2 在两个领域全部档位成立，且断言丢弃率 ≤ 5%，才生成 test seeds 30/31/32
（train 130/131/132）并运行 test 确定性面板；同时启动 API。

API（与 round 3/4 可比）：
- 端点 AutoDL OpenAI-compatible，请求模型 `deepseek-v4-flash`（探针返回 `DeepSeek-V4-Flash-0731`），
  temperature 0，prompt v2，retry policy 不变；4 个 key 按 shard 并行。
- 领域 Travel（主，与 round 3/4 可比）；Shopping32 为次要，需要新增 OP card，首次进入 LLM 臂，
  单独报告。
- test seed 30，episode 0–63；档位 native / 100 / 500；cells：`graph_closed/compact`、
  `graph_closed/verbose`（同一选择、冗余序列化的诊断臂）、`full/verbose`（配对锚）。
- 判据：graph_closed/compact 相对 full/verbose 的配对 EES 差与 input tokens 差按档位报告；
  预注册预测为 graph 的 input tokens 随档位近似平坦、full 线性增长；不预注册 full 的 EES 必须下降。
- 费用按 `llm.py` 的 DeepSeek 费率估计；AutoDL 实际计费另记。预算上限：Travel $40，Shopping $30。

## 8. 与其他实验的关系

- 与 round 3/4 相比只改历史长度；selector、prompt、模型家族相同。
- 反向 provenance 在独立设计页（`docs/hm3-provenance-design-2026-09-18.md`）。

## 9. dev 校准修订（2026-09-18，test seeds 生成之前；理由如实记录）

1. **外来 segment 的位置。** 初版把全部外来 segment 放在真实历史之前，导致 recency-K 在 500 条时
   仍以 1.0 recall 命中全部必需记录（真实 witness 永远在末尾），失去作为 fixed-K 对照的意义。
   修订：对每个外来 segment 单独用 parser 判断它是否为任何被 consult 的 key 产生 witness；
   产生者放在真实历史之前，不产生者在真实 segment 之间随机位置插入（不插在最后一个真实 segment
   之后）。A 克隆一律最前。§6 的断言不变，仍由它保证 est / prov / required reads 不变。
   dev seeds 0 的 20 个 episode 上：Travel 四档丢弃率 0；Shopping 500 档 5%（其余 0）。
2. **每个外来世界最多 8 个 segment。** 否则 500 条记录只来自 3 个外来世界，对象数不随长度增长。
   修订后 Travel 500 档约 620 个对象、100 档约 145 个；Shopping 500 档约 265 个。
3. **断言失败重试 5 次**（原 3 次）。
4. A 的"隐含值不同于真值"比例：Travel 约 55%（37/67 keys），Shopping 约 5%（3/62）。Shopping 的
   compat witness 需要替换后的 accessory 属性与 base 匹配，重新链接后的克隆很少满足，因此
   A 在 Shopping 中主要是同对象的冗余旧记录而不是冲突记录。如实报告，不改构造。

5. **selection ladder 与 wrong-graph 对照（2026-09-18 晚，test 生成前）。** 首版 wrong graph 用 superset 规则沿
   重接线拓扑传播，EES 恒为 0，与 superset 本身相同，说明它测的是缺失的 gate 模型而不是拓扑；作废，移入附录
   （`wrong_graph_k`）。正式对照改为 selection ladder：`graph_select`（沿学得 skeleton 读取对象与其 policy
   记录）与 `wrong_select_1/2/3`（沿三个固定重接线 skeleton 读取），全部经 `restricted_est` 与运行时执行器，
   与 `bm25_k16` / `recency_k16` / `retrieval_k` 同一执行器、同一口径；报告 reads 数。这样对照隔离的是拓扑对
   **选择** 的价值，正是 LLM 臂所测的量。Shopping 的 cart 在两跳内全连通，重接线后读取集合常与原图相同，
   该对照在 Shopping 预期无区分力。

6. **graph 的 gate 在 native 训练集上拟合（2026-09-19 凌晨，dev 面板判定之后、test seeds 运行之前；由第二个
   session 记录，用户拍板）。** dev 面板与逐 episode 追踪（结果页 §2.4）表明：按"每档各自拟合"的口径，graph 的
   EES 偏移全部来自 gate 模型的**训练**证据被同 key 的外来 witness 污染（B/C 副本与 D 世界的 category 级 key
   把真实链未见证的 key 定义为外来值、或覆盖未 consult 的 key），以及断言丢弃使训练集在档位之间不再配对；
   Shopping32 在 100/500 档因此从 0.78 跌到 0.57（seed 平均），而同一评测集用 native 训练集的 gate 为
   0.77–0.81，用"只看真实记录"的 oracle 估计恰为 native。结构性 provenance 无法替代：Travel 的 policy 由同一
   世界其它链的记录见证，C 副本与真实的另一条链只差取值，按链或按连通分量限定证据会丢掉必需 witness
   （原型在 native 上跌到 0.37）。因此把 gate 视为**机制模型**：历史变长改变的是证据，不是机制；正式 graph 臂
   改为 `graph_nf` / `graph_pooled_nf`（gate 在该 seed 的 native train 200 上拟合一次，评测历史按档增广；
   `run_scaling` 对 `fit_native` 学习器传 native 训练集），P1/P2 对这两臂判定；原"每档各自拟合"的 `graph` /
   `graph_pooled` 行保留为消融（量化在污染证据上重拟合 gate 的代价）。其它臂口径不变。
   预期：两领域主档位 |ΔEES| ≤ 0.05；Travel c100 仍可能超界（评测侧 C 冲突 witness 经 enforce_late 状态推断
   进入 gate 特征，见结果页 §2.4 通道 3），如实报告。
   dev 结果（Travel，`det_dev_nf_travel.json`）：`graph_nf` P1 1.087 PASS；P2 50/100/500 = −0.011/−0.033/−0.044
   通过，a100/d100 恰为 0，c100 = −0.072 [−0.117, −0.033] 越界（翻转几乎全是"先 cancel 再 shift 同一 dinner"
   的非法计划，gate 被未 consult 的 key 的冲突估计带偏）。
   **冲突感知的两个探索臂（同日 smoke，Travel seed 0 / Shopping seed 0）：** `graph_cf`（native-fit，gate 特征里
   把"不同对象见证出不同取值"的 key 记为未知）**负结果**：c100 从 0.733 跌到 0.467、illegal 0.27——遮蔽同时丢掉
   了 consult key 上正确的最后 witness，而 native 训练历史里没有冲突，gate 学不到"冲突意味着什么"。`graph_cfa`
   （每档拟合，估计保留，按参数族追加冲突指示特征）：Travel c100 0.733 → 0.817（回到 native 0.817 的水平），
   Shopping 100 档 0.183 → 0.200（无效，且拟合 81 s）。因此正式臂只有 `graph_nf` / `graph_pooled_nf`；
   `graph_cfa` 作为探索臂在 Travel dev 全档与 test 上并列报告，Shopping 不跑。
7. **Shopping 增广的 no-interleave fallback（`ec0662f`）之后，Shopping 的 50/100/500/b100/c100/d100 六个档
   全部重跑**（dev 与 ladder 文件的旧 entry 已删除，旧结果备份在第二个 session 的 scratchpad）；Travel 的
   评测集丢弃率为 0，不重跑；Travel 训练集原先每档丢 0–3 个 episode，在 `graph_nf` 口径下训练集为 native，
   不受影响。

8. **bagged gate 与最终口径（2026-09-19 早，dev 判定后、test 落盘后；用户"fix all"授权下的全部尝试如实记录）。**
   §9.6 的 native-fit 口径在 Shopping dev 全部通过，但在 Travel test 500 档越界（−0.079 [−0.124, −0.039]）；
   按档拟合的 `graph` 在 Travel dev/test 全部通过、在 Shopping dev/test 坍塌——两种口径各失一个领域。追踪 Shopping
   的坍塌（seed 0，100 档）：按档拟合的 gate 在留出的训练 episode 上 EES 0.85、在 dev 上 0.18；前 195 个训练
   episode 拟合得 dev 0.75，前 199 个得 0.18；去掉不同的 40-episode 块分别得 0.17 / 0.73 / 0.15 / 0.18 / 0.78。
   这是深度 5、叶最小 2 的单棵决策树在受污染训练行上的刀锋式方差。于是试了 gate 装袋（25 棵同规格树，80% 行，
   多数票）与训练行并集（native ∪ 该档增广）：
   - `graph_bag`（按档拟合 + 装袋）：Travel dev/test 全部通过（|Δ| ≤ 0.022）；Shopping 仍各有一个 seed 坍塌
     （dev seed 2 的 100 档 0.133，test seed 31 的 500 档 0.233），P2 在 Shopping dev 100 档（−0.217）与 test
     500 档（−0.167）越界。
   - `graph_nf_bag`（native-fit + 装袋）：与 `graph_nf` 几乎相同——Shopping dev/test 全部通过（|Δ| ≤ 0.022），
     Travel test 500 档 −0.073、dev c100 −0.067 越界；装袋不改变评测侧的污染效应。
   - `graph_un_bag`（native ∪ 增广训练行 + 装袋，只跑了失败的 cell）：Travel test 500 档三个 seed 0.915/0.883/0.847
     （native 0.950/0.900/0.833）、dev c100 与 native 相同；Shopping dev seed 2 的 100 档回到 0.733（native 0.783），
     但 Shopping test seed 31 的 500 档仍坍塌（0.250）。凡让 gate 在受污染的训练行上拟合的口径，在 Shopping 都
     至少有一个 (seed, 档) 坍塌；该 cell 的训练集（train seed 131，500 档）有 17 个 episode 走了 no-interleave
     fallback，是否由此导致尚未查明，记为未决。
   - `graph_sel`（按留出训练集选口径）作废：留出训练集看不到这种方差（0.85 vs 0.18），会选错。`graph_un` /
     `graph_un_cfa`（不装袋）smoke 无效（Shopping 100 档 0.167），作废。
   **最终口径：正式 graph 臂 = `graph_nf` / `graph_pooled_nf`（§9.6），P1/P2 对其判定。** 理由：唯一在训练侧
   与污染证据完全隔离的口径，8 个 (领域 × split) 判定中通过 7 个；唯一越界是 Travel test 500 档（−0.073 ~ −0.079），
   机制为评测侧 C 类冲突 witness 经未 consult 的 key 进入 gate 特征（结果页 §2.4），如实报告。`graph`（按档单树）、
   `graph_bag`、`graph_nf_bag`、`graph_cfa`、`graph_un_bag` 作为消融/探索行并列报告。
