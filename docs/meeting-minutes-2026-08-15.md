# 会议纪要 — Benchmark 落地讨论会（2026-08-15,与 Yujia）

> 记录人:Mian (Nothern) Wu。本纪要依据会后回忆与整理稿写成,**转述为主、非逐字引语**;
> 结构沿用 7 月走读会纪要(verdict → 新输入 → 方向调整 → 行动项),供 changelog 与 v0.2 使用。
> 会前状态 = 仓库截至 2026-08-12(commit `47a7355`)的五份文档:
> `form-a-representation.md`、`task1-candidate-methods.md`、`layer1-method-pairing.md`、
> `stage1-experiment-design.md`、`memory-vs-agent-memory.md`。
> 注意:会上向 Yujia 汇报的口径是 8/11 的工作笔记,**晚于它的 8/12 实验结果(§四)会上未过目**。

---

## 一、总体 verdict

一句话:**不要卡在"GRACE 能否扩展到 5000 维"这类实现细节上;先在一个具体的 agent-memory
benchmark 里把 Layer-1 因果记忆完整地形式化**——变量是什么、样本是什么、时序如何构成、
因果发现的输入输出是什么、图如何反过来作用于记忆、最终目标是记忆可信性还是下游收益。
可扩展性若真成为瓶颈,用变量分组 / 更粗的变量粒度解决。表述扎实之后,才加深实验。

## 二、逐条 verdict(对照会上汇报的条目)

| 汇报条目 | 他的意见(转述) | 结论 |
|---|---|---|
| GRACE 可扩展性(原生 ~100 变量) | 可扩展性确实是问题,且此前已讨论过;不是新障碍 | **已知风险**,不作为当前主线 |
| 变量 = LM 的原始隐维度? | 不必逐维当变量:可先把维度**分组为 chunk/group**,控制变量总数。变量粒度本身是**设计选择** | **接受分组方案**;仓库 Form A 的 `d = 语义槽位 ≈ 20–100` 已在此精神之内 |
| 分组方案怎么选 | 分组只是实用策略,**可以以后再定**;项目内核是"把时序结构引入记忆" | 不在当前关键路径上 |
| 两层框架 | 再次确认:Layer 1 = observed,Layer 2 = latent;当前围绕这一高层原则推进 | **不变**(与 7 月会一致) |
| 是否继续加深实验 | **最强的一条**:现在最重要的是把 problem formulation 精确写下来——样本是什么?setting 是什么?具体场景是什么?写下来并持续挑战,直到表述真正扎实,再深入实验 | **v0.2 的核心任务**;8/12 那批无-LLM 小实验属于"挑战表述",不属于被叫停的"加深实验"(见 §四) |
| MemoryArena / MemoryAgentBench | 立场不是"别用 benchmark",而是:先给选定 benchmark 做**完整实现方案**(定义变量 / 样本 / 轨迹 / 实验)→ double-check → 表述合理后再放大实验 | 与 8/12 的落点一致:LongMemEval 降级为诊断/压缩,MemoryArena 承载正面验证 |
| benchmark 中一轮对话对应什么 | 需要具体定义:一次 conversation / round 对应什么;变量到底是什么;样本到底是什么。**变量的定义尤其重要** | LongMemEval 侧 Form A 已答;**MemoryArena 侧完全未答 → v0.2 必答** |
| 变量必须是标量吗 | **不必**。他明确列了三种:一个标量维度可以是一个变量;多个量聚合成一个变量;**一整个向量本身也可以定义为一个变量** | 直接背书 Form A §2 的选项 (iii)(槽位值 embedding);且 GRACE encoder 标量→k 维只需换一层线性投影 |
| 每个变量的样本从哪来 | 每个变量需要**多个样本**。早先 communication 论文里"每个 question/query 是一个样本"可作参照,但他未细看本 benchmark,**不能直接搬用**,要先想清楚这里怎么形式化 | 对应 task1 表 §2 的 (A) 逐 episode 重拟合 vs (B) 摊销之争;v0.2 须写明每变量的有效样本数 |
| repository 与 benchmark 从哪边入手 | 明确回答:**both**。方法最终要落进一个具体 repository,同时要与做实验的 benchmark 兼容 | 两侧并行考虑 |
| 评价目标 | 提前定好两类目标:(a) **记忆本身的可信性**;(b) 记忆对**下游任务**(inference / reasoning)的效果。实验不能只测因果图恢复得多好 | 与 8/12 结论二严丝合缝:knowledge-update 的 gold 含被覆盖旧值,mask F1 会惩罚正确的遗忘 → 下游为主指标 |
| 发表目标 | 从简单版本起步,进展顺利再瞄准更有野心的目标。转写把 venue 名转成了"Acquia"之类,**不可靠,不猜** | 待下次确认 |

## 三、悬而未决问题的解答:X_t^i 是什么

8/11 笔记遗留问题:"X_t^i 是什么?是否意味着先得到几十到几百个稳定的 observed memory
units / state groups,再在这些单元上做因果发现?"

**答:是,且仓库里已有精确定义**——`form-a-representation.md` §1 的 Form A:

- `X_t ∈ R^d`:固定 schema 的记忆状态,`X_t^j` = 槽位 `j` 在时间步 `t` 的取值;
- **状态持续规则** `X_t^j = v_t^j`(若更新)否则 `= X_{t-1}^j` —— 这正是 formulation.tex
  里 write–hold–read 模体 hold 段的 `σ = 0` 离散版,保证每个时间步拥有同一套固定变量;
- 配套 `U_t`(本步更新集)与 `P_t`(provenance 指针,knowledge-update 类问题必需)。

本次会议补上的增量是:**取值不必是标量**(整向量可为一个变量),这为 Form A §2 的三个
取值选项——(i) 更新指示、(ii) 标量编码、(iii) 值 embedding——中的 (iii) 提供了直接许可;
且 §2 已核实 GRACE encoder 只需把标量→64 的线性投影换成 k→64,其余组件不动。
建议顺序不变:先 (i) 探事件结构信号,有信号再上 (iii)。

## 四、关键衔接:8/12 实验结果与本次会议的关系(会上未过目,需下次同步)

会上汇报口径停在 8/11("方法/仓库选型"阶段)。但 8/12 的五份文档已把局面推进了一大步,
其结论与 Yujia 的指示**互相印证**,应在下次会议正面同步:

1. **LongMemEval 召回轴:`G` 没有可证明的空间(负结果)。** 手工构造三例中 `An*(Y_q) = Y_q`,
   图不提供额外信息;30 例盲写语义扩展实验给出 `E(q) ≈ An_G(Y_q)`,残差全是时间算术
   (用现成日期索引解决,与因果结构无关);BM25@10 召回已达 0.947。
2. **LongMemEval 压缩轴:有大空间(正信号)。** oracle-turn 只需 0.2% token 即 100% 可答,
   BM25-turn@10 花 2.3% 只到 70.4%;turn 级粒度是最大杠杆;recency 几乎无信号。
   → 主指标改为 **accuracy–compression Pareto**;"什么东西能填这个空间"尚未证明是因果结构。
3. **MemoryArena 判断反转。** 四个环境全部具备 `s_{t-k} → s_t → a_t`;此前"接口表达不出
   mask"的否定被修正——正确做法是自己注册成一个记忆系统(`MEMORY_FACTORIES`,三个方法,
   约一天工程量),天然与其余 13 套记忆系统同台对比。
4. **方法定局(按"能跑>能扩展>易接入>效果好"核实实现后):** 主方法 GRACE(`causal-ts`,
   逐 episode 重拟合,v1 保留 CI skeleton);baseline CDNOTS+(同库零成本);备选 JRNGC;
   第二版摊销方向 ACD。**UnCLe(dynamic 仅 d≤8、无 license)、CUTS+(无 lag 维)、AVICI(无时序)已排除**;
   cMLP 在"未读实现"名单里,不再是默认 baseline。8/11 笔记里的 UnCLe / cMLP 表述已过时。
5. **三处已作废说法不再复述**(3000 chunks ≠ 3000 变量;相似度预筛 ≠ skeleton;
   MemoryAgentBench 并非零环境搭建),v0.2 沿用勘误后的表述。

与 7 月会的连线:7 月的变量例子是 KV cache / 激活维度,本次会放宽为"粒度是设计选择";
Form A 的语义槽位粒度与之相容。7 月点名的 VARLiNGAM 入口已被"按实现核实"的
GRACE/CDNOTS+ 选型实质取代,归档为方法史。

## 五、行动项

1. **[文档] v0.2 增写"benchmark 实例化"一节,重心在 MemoryArena**(LongMemEval 侧 Form A
   已基本答完)。对四个环境(webshop / travel / search / math)逐项回答,写到可被挑战的精度:
   - t 是什么:一个 turn / subtask / 环境步?
   - 变量 i 是什么:环境状态槽位、agent 记忆槽位、动作,各占几维?粒度为何?
   - X_t^i 的取值类型(标量 / 向量)及从原始轨迹的抽取方式;
   - 一个样本、一条轨迹是什么;**每个变量有多少有效样本**((A) 逐 episode vs (B) 摊销);
   - 因果发现的输入表与输出图;图如何作用于记忆(`wrap_user_prompt` 内施加 mask);
   - 双评价目标:下游任务成绩为主;可信性/mask 指标为诊断(knowledge-update 单列)。
2. **[检验] "G 挣不挣得到位置"前移到 MemoryArena**:travel 的逐步纠错反馈闭环最像
   write–hold–read,先在它上面找"query 未直接点名、却由时序依赖系统预测"的槽位间依赖;
   LongMemEval 只保留压缩轴诊断,**不下载 longmemeval_m**。
3. **[搁置] 可扩展性**:维持 Form A §4 的拆分——agent 实验 d≈20–100,合成实验单独证明
   发现模块可扩展(这正是 Yujia 建议过的做法);分组三档(标量维 / chunk / 整向量)记为设计轴。
4. **[同步] 下次会议先补交 8/12 结果**(§四的 1–4),再走读 MemoryArena 实例化草稿;
   确认 venue。本纪要计入 changelog。

## 六、待确认(下次会议或邮件)

- 发表目标 venue(转写不可靠,需口头确认);
- 向量值变量(选项 iii)是否作为 v1 就上,还是按 Form A 建议先跑更新指示 (i);
- "每个变量需要多个样本"在逐 episode 重拟合 (A) 下如何量化(`T≈48` 是否够 GRACE 收敛,
  还是必须靠跨 episode 摊销 (B) 才算满足他的样本要求);
- LongMemEval 压缩轴的空间由什么填:因果结构、类型化抽取、还是日期索引——需要一个可判别的实验设计。
