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
