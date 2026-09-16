# 给 Yujia 的论文 outline：段落目标与句子子目标

本稿只定论证结构，不润色语言。主张：**显式时序结构是否能帮助 agent 更经济地读取记忆，
并追踪可观测的记忆风险来源？** 不以“恢复真实 latent 心理状态”作为已经完成的贡献。
对应英文 outline 已加入原 `causal_memory_formulation.tex`。

2026-09-15 状态：完整实现重评尚未完成。三个 online 机制小例与两个 Travel 开发案例通过；
aiaaa / TokenRhythm 均明确返回余额不足，三套 LoCoMo 完整历史验收仍未通过，正式 100 cases 未启动。
下文 P10–P13 是待完成实验的论证目标，不是已取得的新成绩。

## 1. Introduction

**P1｜目标：从 memory 的实际问题进入。** S1：多轮 agent 依靠先前记录完成当前任务。
S2：保留所有内容增加上下文开销；摘要与检索会丢失依赖或传播错误。
S3：仅看当前回答正确，不能证明所检索的记忆没有潜伏风险。

**P2｜目标：提出具体问题。** S1：把 memory 的写入、读取和目标变量对应起来。
S2：问估计的依赖结构能否筛选有效上下文、定位异常后果的来源。
S3：用同模型、原版 actor 的下游比较验证效用，不假定现实中的图可唯一识别。

**P3｜目标：列出与证据匹配的贡献。** S1：可追踪的结构选择 memory pipeline。
S2：MemoryArena 上的任务—上下文—写入成本比较，包含近期 native baseline。
S3：正常行为下的风险记录实例与受限的来源追踪证据。
S4：单列在线缓解失败及可识别性限制，不把未来工作写成贡献。

## 2. Setting and measurement

**P4｜目标：回答每个 region 的变量口径。** S1：不同环境分别定义变量 schema。
S2：Travel 共享 7 个 slot type；episode 的 traveler/day/record 数可以不同。
S3：regime 变化作用于同一组变量的边/机制；不把 record ID 与变量维数混淆。
S4：明确 region/regime 的转写尚未确认。

**P5｜目标：说明样本和信息流。** S1：t 是 traveler round，episode 是 trial。
S2：当前图用训练 query 的 constraint indicators，lag 窗口不跨 trial。
S3：公开 base + actor 自己的历史写回构成在线记忆。
S4：held-out gold 只供 evaluator，不能作为运行时 oracle。

**P6｜目标：说清 estimand。** S1：P2 问 memory pipeline 的下游效用与计算成本。
S2：P3-A 问可观测异常与历史记录的关联和时序溯源。
S3：P3-B 另问实际阻断后的攻击率和任务效用。
S4：上述问题不等价于识别不可观测的意图。

## 3. Method

**P7｜目标：把已有发现方法当组件。** S1：给出观测矩阵与候选 lag 图接口。
S2：引用已有方法及其识别条件，simulation 只作既有检查。
S3：现实条件无法全部验证，因此输出解释为候选依赖结构。

**P8｜目标：说明图如何实际改变记忆读取。** S1：从当前 query 确定目标 day/slot。
S2：用类型图与显式引用解析找候选祖先单元格。
S3：通过 write provenance 取原值，并展示保留/丢弃的具体条目。
S4：公共 base 完整呈现在 memory context 中；actor 自行生成完整计划，移除本地继承 decoder。

**P9｜目标：说明审计机制与可用标签。** S1：记录 write→read→action 的可观测路径。
S2：分别介绍 MINJA 的 oracle-tagged 演示和 AgentPoison 的 label-free 校准。
S3：按冻结规则选择驱动记录，再做在线 gate。
S4：保持来源追踪、干预有效性与心理推断三者的区别。

## 4. Experiments

**P10｜目标：让 memory 社区认识比较对象。** S1：介绍 MemoryArena 的多轮依赖任务。
S2：覆盖 full context、BM25、CPU dense、滚动 autoregressive summary。
S3：加入完整 Mem0 OSS、作者 AgenticMemory 论文仓库 robust agent、完整核心机制的 LightMem，并标明 commit。
S4：提供原始 LoCoMo 完整历史的机制检查，区分任务接口验证、下游比较与论文分数复现。

**P11｜目标：交代公平性、选择与成本。** S1：当前开发共享 aiaaa `deepseek-v4-flash-0731`、原版 actor 提示、全部工具、完整计划输出与 30 steps；不与旧 TokenRhythm 结果拼表。
S2：开发 ID 101；新评估拟覆盖 111–120，须待验收后冻结，属于已看过历史 holdout 的描述性复验。
S3：PS/SPS/SR、episode 等权均值与原始逐例结果一起报告。
S4：写入/更新 LLM tokens、actor tokens 和时延都记账；报价估算不等于中转账单。
S5：Mem0 / LightMem / A-Mem 的检索规模分别为作者任务配置的 200 / 60 / 10；A-Mem 保留作者 1000-token 上限，memory 使用验证过的 `reasoning_effort=none`。

**P12｜目标：解释 P2 实际结果。** S1：修复后的十臂表完成并核验前保持待填，旧 v5 不作为完整实现主比较。
S2：判断性能、输入开销、写入开销间的取舍，允许 baseline 更强。
S3：旧 10-episode compact-v3 结果只作为单独历史证据。
S4：noGcompact 固定格式并关闭选择规则；query_only 保留引用解析但移除学得的类型边，分离图的增益。
S5：复用 episode、一次 API 实现与同一中转 backbone 不能确立稳定 SOTA；原生 actor 长度上限输出保留评分。

P12 历史探索性证据（不满足此次完整实现要求）：v5 Ours 与 noGcompact 的逐 episode PS/SPS/SR 持平，person-PS 都为 90.91%（20/22），输入少 49.63%，费用高 4.59%。不得用这组数据填充修复后的表，也不据此承诺新结果。

**P13｜目标：给一张读者能看懂的具体 slide。** S1：给出真实 query 与需要的历史单元格。
S2：画实际类型图、解析出的实例引用以及选取的记录；图例区分来源。
S3：并排展示 ours、autoregressive summary 和 native baseline 的实际 context 与答案。
S4：如果都回答对，就解释压缩与信息组织；如果答错，就展示错误，不编造结构修复。

**P14｜目标：展示潜伏风险而非“读心”。** S1：MINJA t=15 写入 `fixed_1_3` 的答案偏移规则。
S2：t=16 检索它但仍给正确 C，说明表面正常和风险内容可共存。
S3：t=19 新 query 无攻击 note，检索含同一记录及其他污染记录，输出 H 而 gold 为 D。
S4：同一来源在不同情境出现不构成单记录反事实证明；展示已估计的 gated read→action 边及标签边界。

**P15｜目标：完整呈现审计与缓解结果。** S1：P3-A 汇报跨 seed 来源追踪证据。
S2：AgentPoison record 9251 用 label-free 输入被选中，9252 通过 cluster 扩展。
S3：给出一个 gate 移除污染但任务仍答不出的实例。
S4：两个 P3-B 冻结协议 FAIL，说明仅定位来源不足以保证效用恢复。

## 5. Related work, limitations, conclusion

**P16｜目标：定位关系。** S1：与记忆抽取/更新系统比较结构对读写的约束。
S2：与普通 RAG / autoregressive summary 比较依赖表达。
S3：与现有 causal discovery 区分贡献：使用已有结果，不重做 simulation。
S4：与攻击检测区分：溯源和有效在线缓解需要不同证据。

**P17｜目标：让限制可检查。** S1：披露 query 显式引用与可见公共 base，避免把解析先验归于图。
S2：变量选择、测量误差、混杂、有限 trial 数限制因果解释。
S3：当前只有 Travel 的近期 native baseline 比较，跨 memory task 的外推有限。
S4：历史 holdout 重用、单次模型采样与中转模型差异限制统计主张。
S5：总结已支持的效用/审计结论，并将跨任务扩大与在线缓解作为下一阶段。

## 图表位置与取舍

1. Figure 1：具体 Travel memory 选择与风险记忆的两页 demo，优先于新增 aggregate plot。
2. Table 1：变量、trial、可见输入与 oracle 口径。
3. Table 2：近期 baseline 的同路由配对任务/成本结果及配置。
4. Table 3：P3-A 与 P3-B 分列，失败不隐藏。
5. Appendix：现有 simulation、上游 commit/config、逐 episode 结果、完整 trace 与失败案例。

需要 Yujia 判断的研究取舍：论文主贡献以 memory 效用 + 审计为中心是否合适；是否保留较长
latent-identifiability 理论讨论。两点不会阻塞本轮已授权的实验、demo 与 outline 完成。

执行注记（2026-09-15）：旧 v5 已降为历史探索性比较；完整实现重评因中转余额不足中断，P12 尚不能填新排名。
已交付的 P13 slide 是相同历史的 read-only ours/noGcompact 与实际开发 AR summary 比较，
未重跑各 arm 的 actor；P14 风险 slide 有原始轨迹支持。不要将本 outline 的待填实验目标当作完成结果。
