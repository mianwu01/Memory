# P2 PS confirmatory rerun protocol — fixed before run B (2026-08-28)

触发原因：run A 的 `causal-learned-pure` 与 `causal-learned` 官方 PS 均为 0%，用户要求复核并重新运行。

执行前审计确认：

- 两臂 submission 都覆盖固定 IDs 1–5 和 37 persons。
- learned 的 37 份计划均可解析；34/37 persons 只在非 query-constraint slots 上失败。
- pure 有 1 份不可解析计划，其余 coverage 完整。
- 官方 PS 要求一个人的三天全槽位全部通过；SPS 只平均 query-derived constraint slots，因此高 SPS 与低 PS 可以同时出现。

Run B 固定如下：

- 只重跑被质疑的两臂：`causal-learned-pure`、`causal-learned`。
- episode IDs 仍为 `1 2 3 4 5`，模型仍为 `deepseek-v4-flash`，其余 agent/env/memory 参数不变。
- 使用全新输出目录 `causal-learned-pure-rerun`、`causal-learned-rerun`，不删除或覆盖 run A。
- 无论 PS 是否改善，run A 与 run B 都并列报告；不得用更有利的一次替代原结果。
- scorer、逐 person failure decomposition 与 usage 都按相同代码重新计算。

Run B 不是新的 baseline comparison，也不改变原四臂预注册 run A；它回答的是方法臂 PS=0 是否能在一次独立 API generation 中复现。
