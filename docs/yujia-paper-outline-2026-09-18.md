# 给 Yujia 的论文结构稿：当前实验版

这是9/04要求的段落goal / 句子sub-goal稿。结果状态以[本轮执行记录](autodl-campaign-2026-09-18.md)为准：MINJA与AgentPoison已完成，Travel正式矩阵仍在运行。保留[9/15历史稿](yujia-paper-outline-2026-09-04.md)，不回填旧数字。

暂定中心句：**我们以可观测的时序依赖描述记忆的使用过程，并通过选择与来源审计两类实验，检验估计的结构相对于完整记忆、历史查找和简单统计的实际价值与边界。**

中心句的结果部分须等Travel收口。当前不声称同一张学得的图完成所有应用，也不预设学得边一定优于历史查找。下列S描述一句话要完成的论证任务，而不是执行日志。

## Introduction

**P1｜goal：指出长期记忆的两项实际需求。**

- S1｜sub-goal：说明agent要从不断积累的历史中选择与当前任务有关的信息。依据：[9/04纪要][meeting]。
- S2｜sub-goal：说明选择的价值必须同时由任务结果和实际读取开销衡量。依据：[Travel协议][travel]。
- S3｜sub-goal：说明当前回答正常仍可能伴随风险记录被读取，因此还需要可追溯的来源信息。依据：[固定MINJA案例][minja-demo]；不将固定案例写成提前检测成功。

**P2｜goal：将选择与审计联系到记忆的使用过程。**

- S1｜sub-goal：将记忆描述为写入、保存、读取再影响动作的时序过程。依据：[formulation][formulation]。
- S2｜sub-goal：解释保存一条记录与在当前动作中读取它是不同事件，依赖可随访问阶段变化。依据：[formulation][formulation]、[E0][e0]。
- S3｜sub-goal：说明需要估计和验证这些依赖，而不能从检索相似度或一个正确答案直接推断影响来源。依据：[审计对照][minja]、[AgentPoison对照][ap]。

**P3｜goal：用陈述句给出共同框架和实验问题。**

- S1｜sub-goal：提出以可观测时序依赖组织记忆选择与来源审计的框架。依据：[formulation][formulation]及下述三个实现分支。
- S2｜sub-goal：把读取问题具体化为学得边是否改善任务–读取取舍，并超出同历史lookup的能力。依据：[Travel核心协议][core]；结果待完整面板。
- S3｜sub-goal：把审计问题具体化为不输入投毒membership时能否定位记录，以及冻结删除规则是否改变后续攻击。依据：[MINJA][minja]、[AgentPoison][ap]。

**P4｜goal：列出与证据一一对应的贡献。**

- S1｜sub-goal：给出write–hold–read的形式化及受控门控依赖检查。依据：[formulation][formulation]、[E0][e0]。
- S2｜sub-goal：给出当前query移除依赖线索后的真实agent比较，分离结构、历史查找与完整记忆。依据：[任务定义][implicit]、[Travel协议][travel]；结果待填。
- S3｜sub-goal：给出无标签来源定位及冻结在线干预的可追溯实验。依据：[MINJA][minja]、[AgentPoison][ap]。
- S4｜sub-goal：将结构估计失败和对照可解释的收益作为实证边界，而非预先承诺结构必要性。依据：[MINJA配对结果][minja]；Travel方向待填。

## Setting

**P5｜goal：明确样本、变量、访问阶段和记忆实例的区别。**

- S1｜sub-goal：定义Travel的episode、traveler round和固定七类slot变量；记录实例可随历史增长。依据：[setting][setting]。
- S2｜sub-goal：定义implicit与explicit的唯一区别：当前请求是否保留依赖句，两者都收到提前的历史notice。依据：[任务定义][implicit]。
- S3｜sub-goal：说明三条结构臂共享notice解析，query_only因此是history lookup对照；closed-loop之后各臂写回历史可以不同。依据：[任务定义][implicit]、[Travel协议][travel]。

**P6｜goal：定义应用分别估计什么、能观察什么。**

- S1｜sub-goal：将Travel的estimand定义为任务表现与读取/写入开销的变化，而非心理意图识别。依据：[Travel协议][travel]。
- S2｜sub-goal：将审计的输入限定为校准阶段可观察的检索、动作及来源通道，投毒membership仅用于后验评价和明确标注的oracle。依据：[MINJA实现][minja-code]、[AgentPoison审计][ap-audit]。
- S3｜sub-goal：区分候选来源定位、可识别的因果效应与实际删除收益，避免用其中一项代替另一项。依据：[MINJA][minja]、[AgentPoison][ap]。

## Method

**P7｜goal：先给出门控依赖的formulation。**

- S1｜sub-goal：用示意式 `Y(t+1)=b(H(t))+1[U(t)=read]·f(M(t))+ε(t)` 表达记录效应仅在相应访问条件下出现；说明这是机制形式而非所有环境的已识别真模型。依据：[formulation][formulation]。
- S2｜sub-goal：指出纯加性 `g(M)+h(U)` 一般不能表达上述交互，但允许非线性交互的模型可以；不将“加入regime节点”一概等同于加性模型。依据：[写作核对][abstract]。
- S3｜sub-goal：由此引出按regime估计与检验依赖的动机，不声称pooled依赖必然为零。依据：[E0][e0]及其限定的测试设置。

**P8｜goal：交代实际估计路径及共享框架的范围。**

- S1｜sub-goal：介绍Travel的类型图由训练集历史要求构造的变量，经既有PCMCI skeleton与GRACE refinement估计；不写成从当前测试actor的自生成轨迹学习。依据：[训练清单][train]。
- S2｜sub-goal：介绍E0和MINJA结构臂的regime-conditioned估计；MINJA使用可观察record检索通道与动作异常，区别于频率法。依据：[E0][e0]、[MINJA结构实现][minja-code]。
- S3｜sub-goal：说明AgentPoison冻结driver及cluster扩展的独立实现，使每项结果对应其真正消费的结构或分数。依据：[AgentPoison审计][ap-audit]。
- S4｜sub-goal：明确共享的是时序依赖与provenance视角，各分支并非同一估计器或同一张训练好的图。依据：以上三条实现路径。

**P9｜goal：解释估计结构如何改变实际读取。**

- S1｜sub-goal：由当前目标和历史notice解析实例引用，再利用类型依赖寻找需要读取的祖先单元格。依据：[任务与selector定义][implicit]。
- S2｜sub-goal：将被选内容紧凑序列化，与可见base一起交给原版actor生成完整计划。依据：[Travel协议][travel]、[固定demo][travel-demo]。
- S3｜sub-goal：用noGcompact关闭选择、用query_only移除学得类型边，分别检验裁剪效用与学得边增量。依据：[核心协议][core]。

**P10｜goal：解释来源审计如何连接冻结干预。**

- S1｜sub-goal：沿write→retrieve→action记录追溯可疑来源，明确时间顺序提供的方向信息。依据：[MINJA固定案例][minja-demo]、[AgentPoison审计][ap-audit]。
- S2｜sub-goal：只用校准信息冻结候选记录及删除规则，再在测试请求上比较ungated、no-op和其他删除对照。依据：[MINJA][minja]、[AgentPoison][ap]。
- S3｜sub-goal：将来源命中与攻击变化分别计量，避免把关联定位直接写成单记录致因证明。依据：[MINJA配对结果][minja]、[AgentPoison][ap]。

## Experiments

**P11｜goal：给出门控估计的受控机制证据。**

- S1｜sub-goal：交代已有E0中两条gated read边及所测试的blind、regime-augmented与conditioned估计器。依据：[E0][e0]。
- S2｜sub-goal：报告三个既有噪声设置下conditioned各恢复2/2，所测blind和augmented各0/2。依据：[E0][e0]。
- S3｜sub-goal：将结论限定在这些估计器与受控设置，不把它升级为所有pooled或非线性模型的不可能性定理。依据：[写作核对][abstract]；不新增simulation。

**P12｜goal：让读者理解真实memory比较及公平性。**

- S1｜sub-goal：介绍implicit十臂：ours、noGcompact、history lookup、BM25、full、dense、summary、Mem0、A-Mem、LightMem，并说明explicit条件有三条结构臂。依据：[Travel协议][travel]。
- S2｜sub-goal：说明各臂使用同一backbone和原版actor，方法自身的额外写入调用计入开销；原生接口验证与论文分数复现分开。依据：[执行记录][campaign]、[native适配][native]。
- S3｜sub-goal：说明50个episode各3次生成，先在episode内平均再配对；API重复不能替代独立任务。依据：[Travel协议][travel]。

**P13｜goal：用主结果判定结构究竟增加了什么。**

- S1｜sub-goal：报告ours相对noGcompact的任务分数差、实际memory context与总actor输入变化。依据：**待Travel完整评分**，不填旧39.55%或−1.43点。
- S2｜sub-goal：报告ours相对history lookup的增量，并比较该增量在implicit/explicit条件下是否改变。依据：**待900-case核心面板完整核验**。
- S3｜sub-goal：报告近期native方法在任务表现、读写成本及执行完成率上的位置；执行失败完整保留。依据：**待1,950-case全范围收尾**；严格完整主表与执行覆盖报告分别交付。
- S4｜sub-goal：依结果将贡献限定为学得边增益、选择效率或尚未显示增量，不以baseline对比代替未运行的pooled/wrong-graph拓扑消融。依据：[实际执行范围][campaign]。

**P14｜goal：用一个固定episode解释保留、舍弃与最终动作。**

- S1｜sub-goal：展示episode101 round2的当前请求和历史要求，让读者看到依赖来自哪里。依据：[固定Travel demo][travel-demo]。
- S2｜sub-goal：并列ours选5/42、history lookup选4/42、noGcompact保留42/42单元格，标出学得边实际改变的内容。依据：[demo原始证据][travel-demo-json]。
- S3｜sub-goal：展示三臂原始计划与对应评价，解释差异；少读一个单元格、完整执行和答对分别是不同事实。依据：[demo原始证据][travel-demo-json]。

**P15｜goal：报告AgentPoison的来源定位与干预结果。**

- S1｜sub-goal：报告冻结无标签driver直接命中1/2投毒记录，cluster扩展后2/2，区分两阶段贡献。依据：[AgentPoison][ap]。
- S2｜sub-goal：报告gated攻击0/72，对照ungated9/72、exact no-op6/72，3/3 blocks改善，满足沿用的判据。依据：[AgentPoison][ap]。
- S3｜sub-goal：说明这是原固定split在新接口/模型上的复跑；正常检索0/24被改变，因此正常回答变化不能归因于删除。依据：[AgentPoison][ap]、[来源核验][ap-audit]。

**P16｜goal：用MINJA说明当前无标签结构估计的边界。**

- S1｜sub-goal：报告10次独立写入下，冻结结构臂10/10未选出边，保持这项失败及暴露/共检索诊断。依据：[MINJA][minja]。
- S2｜sub-goal：报告trigger攻击ungated158/360、regime frequency91/360、pooled frequency91/360、随机等量删除93/360；frequency对随机差−0.56个百分点，95%区间[−6.11,+5.00]。依据：[MINJA][minja]。
- S3｜sub-goal：说明oracle删除为0/360，表明该载体的攻击可以受记忆删除影响，但当前结构估计与频率排序未提供超出相应对照的支持。依据：[MINJA][minja]。
- S4｜sub-goal：给出固定run0的写入、检索、动作和七臂结果，展示整体结果的机制语境；不挑成功案例替代汇总。依据：[固定MINJA demo][minja-demo]。

## Related work and limitations

**P17｜goal：把贡献放到三类已有工作之间。**

- S1｜sub-goal：对照检索、递归摘要和带链接/图的memory系统，不声称既有方法都没有结构。依据：[baseline适配][native]、[已核对相关文献][abstract]。
- S2｜sub-goal：对照时序依赖与异质机制发现，说明本文复用已有估计工具、检验memory用途的部分。依据：[formulation][formulation]、[已核对相关文献][abstract]。
- S3｜sub-goal：对照记忆投毒和provenance研究，说明无标签定位、来源回溯与在线防御的不同评估目标。依据：[MINJA][minja]、[AgentPoison][ap]。

**P18｜goal：界定证据能支持的外推范围。**

- S1｜sub-goal：说明真实轨迹的识别假设、观测变量选择及运行时顺序会限制图的因果解释。依据：[setting][setting]、[MINJA实现][minja-code]。
- S2｜sub-goal：说明同一backbone、Travel基准历史接触、AgentPoison固定split复用及MINJA有限question bank限制泛化。依据：[执行记录][campaign]、[训练清单][train]。
- S3｜sub-goal：说明当前对照尚未覆盖所有拓扑与预算控制，随机删除仅匹配记录数，不能据此声称结构普遍必要或安全得到保证。依据：[实际执行范围][campaign]、[MINJA][minja]。
- S4｜sub-goal：以完整Travel结果和已完成审计结果共同收束论文主张，不将旧tagged恢复或旧压缩数字混入本轮结论。依据：**待Travel收尾**及[当前写作边界][abstract]。

附录集中容纳API路由与预算、native配置差异、训练/测试哈希、重试与失败分类、未知用量、全部逐例输出；这些内容支撑可复核性，不替代主文的发现。

[meeting]: meeting-minutes-2026-09-04.md
[formulation]: ../causal_memory_formulation.tex
[setting]: yujia-setting-2026-09-04.md
[implicit]: travel-implicit-v1-2026-09-18.md
[campaign]: autodl-campaign-2026-09-18.md
[abstract]: yujia-abstract-draft-2026-09-18.md
[native]: autodl-native-conformance-2026-09-18.md
[e0]: ../results/regime_grace_e0.json
[train]: ../results/development/autodl_20260918/graph/training_manifest.json
[travel]: ../results/real/autodl_travel_20260918/protocol.json
[core]: ../results/real/autodl_travel_20260918/registered_core/protocol.json
[travel-demo]: ../results/development/autodl_travel_dev_v2/demo/comparison.html
[travel-demo-json]: ../results/development/autodl_travel_dev_v2/demo/evidence.json
[minja]: ../results/real/minja_autodl_2026_09_18/evidence_report.md
[minja-demo]: ../results/real/minja_autodl_2026_09_18/fixed_demo/index.html
[minja-code]: ../code/minja_autodl_campaign.py
[ap]: ../results/real/autodl_agentpoison_20260918/results.md
[ap-audit]: ../results/real/autodl_agentpoison_20260918/provenance_audit.json
