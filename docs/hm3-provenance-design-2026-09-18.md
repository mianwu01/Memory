# HM3 backward provenance：冻结设计（2026-09-18）

状态：设计在实现前冻结；dev seeds 0/1/2 校准注入规则，test seeds 30/31/32 报告。代码：
`code/hm3/provenance.py`。结果：`results/development/hm3/provenance/`、`results/real/hm3/provenance/`。

## 1. 问题

一次错误的修复来自一条被污染的历史记录时，**正向选择所用的同一张学得图** 能否反向定位到这条写入，
并且这一定位能通过干预验证（把它替换为干净版本后错误消失，而替换匹配对照记录不会）。

## 2. 事件与污染注入

- 领域 Travel、Shopping32；episode 来自与 scaling 相同的生成器（native 长度；500 档作为附加条件）。
- 对每个 episode，从 `required_reads.records` 中取一条 witness 记录 r*，施加**最小污染**：按固定顺序尝试
  候选改写（auto↔txn 的 kind 翻转；数值 delta 平移 ±15/±30；shift↔cancel 的 op 互换；attrs/sku 改为
  目录中另一变体），保留第一个使 `infer_params` 对某个被 consult 的 key 给出不同值的改写。找不到则该
  episode 不构成事件（计数报告）。
- 事件 = 污染后 forward `graph` 的计划与干净计划不同，且在污染 episode 上 EES 失败。
- 审计器得到的异常信号：计划与环境结果不一致的对象集合（错写、漏写或非法事务的 object_id），
  不得到 r*，不得到 gold。

## 3. 反向 trace（同一 graph artifact）

`LearnedGraph` 拟合后序列化 skeleton、majority 与各 template 模型参数并取 sha256；forward 选择与
backward trace 都只通过这一个对象调用，结果文件记录同一 SHA。

trace(anomalous objects) → 沿 skeleton 模板从 source 到异常对象的路径上的每个对象，取其
`param_keys_for` 对应的 prov 记录，按"路径上距异常对象的跳数升序、记录时间降序"排序，输出前 k 条。

## 4. 对照与干预验证

对每个事件比较四种"替换为干净版本"的干预：

1. predicted：trace 的 top-1 记录；
2. matched random：从 graph 读取集合中随机取一条（同数量）；
3. similar non-ancestor：与 top-1 词元最相似、但其对象不在路径上的记录；
4. recency：最近一条记录。

干预后重新运行同一 forward `graph`（确定性），记录 EES 是否恢复、计划是否回到干净计划。

## 5. 指标与判据（按 episode 配对，报告 bootstrap 95% 区间）

- 定位：precision@1、precision@3、MRR（r* 在 trace 列表中的名次）。
- 干预：predicted 替换后 EES 恢复率 − matched random 恢复率；predicted − similar non-ancestor。
- 预注册预测：precision@1 ≥ 0.5；predicted 恢复率高于两种对照各 ≥ 0.3；两领域各 ≥ 40 个事件/seed。
- 不预注册 LLM 版本的数字；LLM 版本（graph_closed 选择下，污染 vs 替换后各一次调用，20–30 个事件）
  在确定性结果通过后再做，单独报告。

## 6. 边界

- 这是对已知机制生成器上的定位与干预实验；不声称在无 ground truth 的真实日志上成立。
- 若 trace 只在 top-1 处退化到"最近记录"同等水平，则同图反向审计的增量未被证实，如实报告。
