# Yujia 会议纪要：memory 实验收口与论文 outline（2026-09-04）

来源：用户于 2026-09-14 提供的 9-04.zip 转录整理，原材料为 13 张截图，时间戳
2026-09-04 14:53。本仓未收到截图或 zip；本页依据用户提供的文字。YZ 为 Yujia Zheng，
MW 为我方。材料为不连续片段，不能推断片段间缺失的问答。截图 3/4 重复，5/6 合并，
9/10 的接续已经由用户整理。

## 本次要求及其优先级

| 要求 | 转录依据 | 执行口径 |
|---|---|---|
| 明确变量集合 | “for each region ... number of variables or set of variables, same ... or different?” | 先将 region 暂解为 regime，明确这不是已确认的转写；区分固定变量 schema、regime-specific edges 和变长记忆记录集合 |
| 加入近期、代表性 memory baseline | “more recent baselines ... most popular baseline ... right now ... 3” | 覆盖通用检索、递归摘要、现有主流 memory 系统；使用真实实现，明确托管版/OSS/适配版区别 |
| 冻结仿真扩展 | “existing results already cover the simulation ... focus ... memory stuff” | 保留已有仿真结果；不再扩展 simulation 或将四个 synthetic v3 环境作为当前主线 |
| 用真实对比说明结构价值 | “in real world ... show that we need structure ... by comparison” | 下游任务、成本与同输入消融为主；不把强领域程序持平当成禁止一切真实 memory 实验的条件 |
| 具体 demo / slide | “one example ... identified causal structure ... why it really matters” | 展示原始记忆、query、选择结果、write/read/action 路径和对照，并附可追溯 ID |
| 风险记忆审计 | “behave ... normally ... see ... what ... drives” | 展示正常表面输出下仍存在的风险记忆，以及后续触发；不把文字 thought 当成潜在心理状态的直接测量 |
| 承认识别假设边界 | “might not ... satisfy ... identifiability ... causal graph” | 真实数据称作估计的时序依赖/候选驱动结构；无 oracle 标签输入；受控数据的 oracle 只作上界 |
| 同步写 outline | “goal ... a specific paragraph ... sub-goal ... sentence ... even ... Chinese” | 在原 LaTeX 内增加可读的段落/句子目标 outline，另给中文版本；无需先润色 |

用户附注“加一张非常具体的 slide，甚至比再加 aggregate plot 更重要”来自截图中的中文
批注，非 Yujia 的逐字语音。本次按用户明确提出的交付要求执行。

## 对旧计划的更新

1. 本次要求取代 2026-08-21 的“baseline 极简”安排：需要增加被 memory 社区识别的
   代表方法，但不以数量堆砌替代公平对比。
2. Hidden Mechanism v3 预注册保留为备选设计，不继续将其开发/准入作为所有工作的
   关键路径。这次会议并未为 v3 的细节签字，也没有抹掉 v1/v2 的负面审计。
3. “需要结构”操作化为在既定任务、相同模型/输入/decoder 下，结构选择相对比较方法
   的任务与效率收益；不声称因果表示在所有算法中不可替代。
4. P3-A 事后溯源与 P3-B 在线缓解分开报告。已有两个在线协议 FAIL 保留；展示潜伏
   风险或一个成功干预例子不能覆盖整体负结果。
5. CPU-only 和新 DeepSeek 中转继续生效。现有历史结果不回填；新增实验使用新目录，
   方法筛选/适配测试与冻结评估分开。

## 本轮交付清单

- [ ] 代表性 baseline 来源、版本、适配边界与可执行比较结果：三套 native 实现已接入、开发已运行；relay 401 Invalid token 打断，正式配对结果仍未完成。
- [x] setting / variable / sample / regime 的明确说明与机器可读审计。
- [x] 三页具体 slide / PDF / 可展开证据的可视化（read-only Travel 对比 + MINJA 风险案例）。
- [x] 中文段落/句子目标 outline，并接入现有 LaTeX。
- [x] 更新 README/HANDOFF，让读者先看到本次任务与最新结果。

转写处理：code/color/caudal structure 按 causal structure 理解；“Oracle 3”含义仍不
确定，可能为 oracle graph/DAG；“all posse generated”疑为 all outputs generated。
不会据这些不确定短语补写新的技术假设。

详细交付、实际数字与恢复步骤见 [9/04 执行报告](yujia-meeting-delivery-2026-09-14.md)。
