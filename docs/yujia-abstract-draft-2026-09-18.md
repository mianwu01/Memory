# Abstract 与论证主线草稿（2026-09-18）

> **本轮执行后的更新（优先于下方早期草稿）：** 新版 Travel 已落实为历史notice保留要求、当前query移除依赖线索，1,950-case正式评测已启动；结果待完整核验。MINJA七臂8,400次测试已完成：frequency_regime的trigger攻击为91/360，随机等量删除93/360，差−0.56个百分点，95%区间[−6.11,+5.00]；真实结构臂10/10 runs为空图。不能再用下方旧三seed定位数字支撑“同一张图实现无标签溯源”。
>
> AgentPoison的新模型固定split复跑中，冻结无标签定位直接1/2、cluster扩展后2/2；gated攻击0/72，对照ungated9/72、no-op6/72，沿原判据PASS。该结果不覆盖旧轮FAIL，也不能把cluster扩展贡献全部归因于时序图。完整证据见 [本轮执行记录](autodl-campaign-2026-09-18.md)。
>
> 最终摘要应等待Travel核心完整面板后收口：若学得边相对history lookup无增量，中心句需限定为结构化表示/选择与有条件的来源审计，不能写普遍结构必要性。下方英文保留为执行前的结构草稿，不是可直接提交的最新结果摘要。

用途：给 Yujia 审中心问题、方法与证据的对应关系。本文依据会议纪要、当前 checkout 的代码和结果，以及用户本轮补充“Travel 已设计去掉 query 的版本，MINJA 后续已有无标签版本”。Travel 的具体新版本待对应；不把旧版本的数字移植过来。本文件不替换既有 outline 或历史结果。

## 1. 要交付的论证

9/04 的要求是 paragraph goal / sentence sub-goal 的论文 outline，允许中文，不要求先润色；同时把重心移到真实 memory 对比和具体 demo。Abstract 是这份论证的压缩版。

从 7 月到 9 月保持一致的主线是：**把过去信息对后续任务的时序依赖显式化，用它组织记忆的选择与来源追踪。** 8/21 将效用/效率与可信性列为两条应用分支；9/04 要求通过真实对比说明结构价值，并承认真实轨迹的识别假设。

结合本轮补充，论文应围绕两个实验问题展开：

- Travel：当前请求不直接给出所需历史依赖时，估计的结构能否帮助选择记忆，并改善任务表现与读取开销的取舍？
- MINJA：审计器拿不到记录的投毒标签时，能否利用检索、动作和写入来源定位可疑记忆？

“去掉 query”需要在 setting 里精确定义：可能是移除依赖线索、移除 selector 的 query 输入，或不再用 query 构造发现矩阵；三者不同。任务请求本身是否仍给 actor，不能靠简称推断。下面暂按“当前 query 不再显式暴露所需依赖”组织文字。

## 2. 本轮证据决定的摘要写法

对应的18段paragraph goal / sentence sub-goal已写入[当前P/S结构稿](yujia-paper-outline-2026-09-18.md)，每句附证据或Travel待填范围。

与用户给出的evolution范例一致，最终稿按“现象与缺口→精确问题→决定性方法→带对照的结果→结论”压缩。当前还缺Travel的完整配对结果，不能先把“图优于lookup”“读少40%”写成结论。

- 方法句可以写估计随access regime变化的时序依赖，再分别用于记忆选择与来源追踪；不能把所有应用说成消费同一张学得的图。
- Travel结果句必须对应新版implicit任务，分别交代ours对noGcompact的任务–读取取舍，以及ours对同历史lookup的增量。900-case核心与1,950-case十臂全范围是不同的完整性检查，不能替换。
- AgentPoison可写本轮观察到的攻击成功率9/72→0/72（exact no-op为6/72）；直接无标签定位1/2、冻结cluster扩展后2/2。不能写“阻止了72次原本会成功的攻击”。
- MINJA必须写清本轮结构估计未选出边、频率法与随机等量删除接近（91/360对93/360），因此它提供的是当前结构估计的识别边界，不能作为成功的无标签图溯源数字。
- 结尾的takeaway等待Travel，不预写“the structure that makes reading selective is the one that makes it auditable”。这句话超出了现有两条实现与证据的对应关系。

## 3. 执行前英文草稿存档（不用于当前投稿）

以下保留一个 Travel 结果槽。MINJA 数字仅对应当前可复核的三 seed 无标签校准实验；若用户指的是更晚版本，应整体替换这一句。该摘要可用于审结构，尚不是填完结果的投稿版本。

> Long-lived LLM agents must reuse past information selectively while retaining a way to trace the sources of memory-induced errors. We introduce a temporal dependency framework that connects selective memory use with source-level auditing. We formulate memory as a write–hold–read process over observable state variables, allowing dependencies to vary across access regimes. This formulation supports two operations: selecting historical information through estimated dependencies and tracing anomalous actions through retrieval and write provenance. Controlled simulations recover gated read edges missed by the tested pooled and additive baselines. On a redesigned Travel task whose queries do not explicitly reveal the required historical dependencies, [insert the verified task-performance and input-token comparison against the matched baseline, including evaluation size]. In MINJA, an auditor calibrated without poison labels identifies poisoned records with 73.7% precision and 28.0% recall across three seeds. This framework connects memory efficiency and source-level auditing through an explicit account of how stored information is used over time.

S6 在结果核验后按实际方向写，不预设结构一定获胜。若用新实验数字，必须同时更新任务版本、对照和评估规模。

## 4. 存档草稿的句子目标

| 句子 | Sub-goal | 支撑材料 / 待补内容 |
|---|---|---|
| S1 | 提出长期记忆的两项实际需求：选择与来源追踪 | [8/21 纪要](meeting-minutes-2026-08-21.md)、[9/04 纪要](meeting-minutes-2026-09-04.md) |
| S2 | 用陈述句明确共同框架 | [7 月 formulation 纪要](meeting-minutes-formulation-walkthrough.md)、[8/15 纪要](meeting-minutes-2026-08-15.md)；下文限制“同一张图”的含义 |
| S3 | 交代 formulation 的决定性特点：write–hold–read 与 regime 变化 | `causal_memory_formulation.tex`；`code/regime_grace.py`；应用实例不一定都使用同一个估计器 |
| S4 | 把结构变成两项可检验操作 | Travel selector 与 MINJA retrieval/action/write 记录；不声称 MINJA 无标签分数来自同一 GRACE 图 |
| S5 | 一句受控机制证据，不让仿真占据摘要主位 | [E0 结果](../results/regime_grace_e0.json)：三个噪声水平下各 2/2，所测 blind/additive 各 0/2 |
| S6 | 说明新版 Travel 如何检验依赖未在当前请求中暴露时的效用 | 用户确认存在新设计；具体版本与对应结果待对齐，不能填旧 compact-v3 数字 |
| S7 | 用无投毒标签的结果直接回答来源审计问题 | [MINJA 汇总](../results/real/minja_online_gate_summary.json)及 seed0/1/2 原始 JSON |
| S8 | 收束共同方法视角 | 结论限定为选择和来源审计，不扩展为安全保证或普遍因果可识别性 |

## 5. 历史版本与数字核对

| 实验 | 当前 checkout 中核实的内容 | 摘要中如何使用 |
|---|---|---|
| 历史 compact-v3 Travel | 10 episodes；输入 718,215 → 434,162，少 39.55%；episode-mean PS 差 −1.43 点。使用共同本地 v3 decoder；graph selection 与 compact serialization 捆绑变化 | 可在正文独立报告；不能写成新版无 query 结果、原版 actor 结果或同格式的纯图增益 |
| Travel-R v0 | 将依赖句移到历史；当前 query 可解析依赖降到 1/6,829。小候选池下随机 @3 已为 0.711 | 证明已有移除当前 query 依赖线索的设计，不能据此声称已获得 LLM 端到端收益 |
| Dynamic Travel T1 | query 不枚举 downstream cells；100 test episodes 中 learned 与 matched lexical 同为平均 3.20 cells，affected recall 1.000 对 0.691；domain solver 同样达到 task success 1.0 | 是 selection 实验，共享 SCM decoder；若写入摘要必须明确该性质，不冒充原生 MemoryArena agent 结果 |
| MINJA 旧 tagged 恢复 | retrieve→action edge found 3/3，gated 2/3；blind PCMCI 0/3；`poison_retr` 来自标签 | 机制验证；不能用 3/3 充当后续无标签定位成绩 |
| MINJA 后续无标签校准 | 不读 `is_poison`、poison source 或 test outcome；38 条被标出记录中 28 条为 poison，总 poison 100 条；precision 73.7%，recall 28.0% | 可以写进来源定位结果；无标签指无 poison membership 标签，仍使用可观测 trigger、note presence 和可机械判定的异常动作 |
| MINJA 后续在线删除 | held-out ASR 6/36 → 5/36，只有 1/3 seed 改善，冻结协议 `pass=false` | 不写成已证实有效防御。若摘要只主张来源定位，可在正文完整报告这项干预检验 |
| AgentPoison 无标签定位 | 直接命中 1/2 poison records，冻结 embedding-cluster expansion 后 2/2 | 可补充正文的第二载体，不能把 expansion 的贡献全部归给图 |

来源：[Travel setting](yujia-setting-2026-09-04.md)、[compact-v3 汇总](../results/real/p2_compact_v3/round_summary.json)、[Travel-R](travel-r-v0.md)、[Dynamic Travel](causal-benchmark-dynamic-travel.md)、[Dynamic Travel T1 JSON](../results/development/causal_benchmarks/dynamic_travel_t1.json)、[MINJA 结果 §6.1](p3-minja-causal-audit-results.md)、[P3 汇总](../results/real/p3_hidden_driver_recovery_summary.json)。

注意：当前 checkout 未找到用户粘贴对话中的 `c6948c2` 对象，也没有该对话中的 `claude/fast-campaign-2026-09-17` 分支。这只说明本地版本未对齐，不能据此否认其他版本的设计或结果。

## 6. 旧草稿需要改掉的论断

1. **不把所有 memory 方法描述成没有结构。** [A-MEM](https://arxiv.org/abs/2502.12110)明确使用动态链接和记忆演化；[Zep](https://arxiv.org/abs/2501.13956)明确使用 temporal knowledge graph。创新定位应具体到“估计记忆使用中的时序依赖，并用于选择与来源审计”。两篇摘要于 2026-09-18 在线核对。
2. **`cannot recover` 不是 E0 2/2 对 0/2 能证明的定理。** 只能说所测方法在这些设置中漏掉边。严格加性模型 `f(X)+h(U)` 无法一般地表达 `U·X`，但把 U 当输入的非线性模型可以表达交互；且若 U 与 X 独立，`Y=U·X+ε` 仍可有 `E[Y|X]=P(U=1)X`，pooled 依赖不必消失。[CD-NOD](https://jmlr.org/papers/v21/19-232.html)也已研究异质/非平稳机制，regime conditioning 本身不宜被包装成首次提出。
3. **“同一框架”与“同一张学得的图”分开。** 当前可核实的 Travel selector、MINJA tagged edge recovery、MINJA label-free driver 不是同一条实现路径。`code/minja_online_gate.py::learn_driver_scores` 是在指定校准条件下对 record 的异常检索比例打分，没有调用 `regime_grace`。可以主张统一的 temporal-dependency/provenance 视角；严格的“同一张图正向读取、反向审计”需要相应实现与实验支持。
4. **不再把旧 query-explicit 边界当作新版任务的结论。** 原任务、移除依赖线索的变体、去 query 输入的 selector 消融分别标识；旧 0/4 不自动否定后续设计，也不自动被后续设计推翻。
5. **学习范例的论证压缩，而非只删限制。** 把决定结论含义的条件留在结果句里，例如 `without poison labels`、matched baseline、任务版本。费用日志、路由、配置细节放实验与附录。若主张范围是 provenance，结尾不必堆砌所有 mitigation 失败；若主张 safe memory 或有效防御，这些失败就不能省略。

## 7. 对原 outline 的最小调整建议

- Introduction：由“哪些过去信息影响当前决策”串起选择与来源审计；陈述共同框架，再介绍两项具体检验。
- Setting：分别定义 Travel 的 query 信息边界与 MINJA 审计器可见通道，写清新旧版本；变量、样本、regime 的定义保留。
- Method：先给 formulation，再写依赖估计、读取选择和 provenance；逐个对应实际实现，避免方法名替代方法定义。
- Experiments：先给新版 Travel 主对比与同输入消融，再给 MINJA 无标签定位；tagged MINJA 和 E0 作为机制证据。在线干预结果独立、完整报告。
- Demo：用一个新版 Travel 例子展示当前 query 没给出的依赖如何来自历史；用一个 MINJA 例子展示标签未知时如何选出记录、对应哪些动作。
- Conclusion：只收束已验证的效用与来源审计贡献。更强的 causal identification、图不可替代性及安全保证需要各自证据。
