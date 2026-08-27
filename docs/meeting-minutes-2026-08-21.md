# 会议纪要 — 论文框架与实验三部分(2026-08-21,与 Yujia)

> 记录人:Mian (Nothern) Wu。本纪要以 **ASR 逐字转写为底**(与 8/15 纪要的"转述为主"不同;
> 转写噪声按 `[likely: …]` 标注,如 "temporal code structure" → temporal causal structure、
> "interoperability" → interpretability、"color structure" → causal structure)。
> **关键前提:会前 Yujia 已过目 8/20–21 的全部结果**(E0 三方法汇合、oracle-C4、
> scaling 表、三轮基准审计)。故本 transcript 应读作**他对这批结果的回应与定调**,
> 而非不知情下的事前指导。§五 收录 2026-08-27 会后裁定(Mian),一并计入 changelog。

---

## 一、总体 verdict

论文故事定形为:**在"利用因果结构(observed 或 latent)做记忆"这一主干之上,开两条分支**:

1. **效果/效率(effectiveness / efficiency)**:借助时序因果结构,记得更好、更省、更快;
2. **可信性(trustworthiness)**:现有 agent 审计手段有根本局限——只能观察 agent 的
   行为/输出,"不知道它在想什么";恢复时序结构(latent 或 observed)之后,
   可以看清**某个时点真正驱动 agent 决策的因素**(当前或未来时点),
   检测到 malicious / suspicious 的驱动源后,可对后续动作进行管控。

实验的组织原则:**coverage 优先于 depth**——"不要在单一方向上做一堆实验",
后两部分各只需 **1–2 个代表性实验/设置**,**不必与十来个 baseline 比**;
理论/仿真部分可以"follow or even refer to existing papers"。

## 二、逐条(对照转写)

| 转写要点(逐字为底) | 整理 | 对项目的含义 |
|---|---|---|
| "temporal causal structure … memorize stuff better … more efficient way" | 分支一:效率/效果 | 需要真实系统上的 1–2 个代表性设置 |
| "auditing … can only observe what this agent … generate. We don't know what they are thinking … recover those temporal structure … see what really drives the agent decision" | 分支二:可信性/审计 | **仓库现状:零覆盖**;是最大的新增设计项 |
| "both points … are natural result of our method. If we can have our measure pretty good and recover reliable structure, we can easily show both" | 两分支都是方法的自然产物 | 方法核心不变(结构恢复 + 图作用于记忆),变的是叙事与验证场 |
| (对方提出)"a suitable environment for experiments" → "we modify some existing or recent work … recover something that's being hidden … or construct those scenarios by ourselves" | **合适的实验环境是未决问题**;两条出路:改造 existing/recent work,或自造场景 | 读作对现有基准群的隐性回应(travel NO-GO、AMA NO-GO、RoomEnv C5 + 外部效度≈0):**没有现成的合格环境** |
| "the first part is about simulation … we construct the structural causal model, all the data generation process by ourselves … MLP … latent variable … we know the [ground-truth] structure … it is something we must do" | 第一部分:仿真,金结构已知 | **E0 + RoomEnv 全部归入此格**——必做,但只是 table stakes |
| "the second part … better efficiency on the memorization or effectiveness … improving the speed, or minimizing the size … better memorization performance" | 第二部分:记忆效率/效果 | 需真实 agentic 系统承载(见 §五 裁定) |
| "the third part … not only interpretability, but as an actionable way … make sure our multi-agent system, or any type of agentic system … safe … we exactly know what our agent have been thinking and also memory in mind, and what really drives or governs their future behavior" | 第三部分:可解释 → 可操作的安全 | "agentic system" 措辞 → LLM-agent 系统,非游戏/网格环境(§五 已确认) |
| "for the last two parts, we don't need to do a very comprehensive one … one or two representative experiments and setups" | 后两部分各 1–2 个设置 | 直接约束实验预算与选型 |
| "we don't have to compare with … all those existing models. We just need to support our story" | baseline 极简 | kg-memory-transfer 的 5-seed 复现协议等重对比**不再必要** |
| "the theory part, or the simulation part, we can just follow or even refer to existing papers" | 仿真部分循例即可 | 受控层不再加深(冻结,见计划文档) |

## 三、衔接:与 8/20–21 结果的关系

1. **受控层被归位为"第一部分:仿真"**。E0 的三方法汇合(PCMCI+ / 池化回归 /
   GRACE 盲跑与 u-增广**全部**漏掉门控 read 边;唯 regime 条件化恢复)、
   oracle-C4(祖先掩码以 8–21% 记录达到回答器信息上限)、scaling 表,
   在新框架下作为仿真证据 + 方法动机保留——但按 Yujia 定调,这部分"可循既有论文",
   **不是论文卖点,不再投入**。
2. **三方法汇合结果获得新叙事位**:hidden trigger / sleeper 行为**就是**一条门控 read 边
   (t−k 写入、潜伏 hold、条件触发 read)。E0 已证明"只看行为/池化的方法"(≈行为审计)
   对这条边致盲、regime 条件化可恢复——这正是分支二(可信性)的机制预演。
   分支二不需要新机器,需要的是**真实 agent 框架里的实例化**。
3. **"suitable environment" 未决 = 三轮审计负结果的另一面**:审计已证明没有现成基准合格;
   Yujia 给出的两条路(改造 recent work / 自造场景)与审计结论互相印证,
   基准适格性审计阶段就此**正式关闭**。

## 四、行动项

全部展开见同日撰写的 `agentic-experiment-plan.md`,此处列纲:

1. **[冻结] 受控层扩展**:RoomEnv v2 coupling、更多 scaling 配置、kg-memory-transfer
   复现、Craftax G1 门、TextWorld 自造备忘、ScienceWorld T0(JRE 安装搁置)——全部停止;
   唯一保留的活跃项 = **regime-conditioned GRACE v1**(方法贡献,E0 上开发,纯 CPU)。
2. **[Part 2] MemoryArena 落地**:`CausalMemorySystem` 适配器骨架已建
   (`code/arena_causal_memory.py`,接口按源码核实)。
3. **[Part 3] hidden-driver 构造设计**(改造记忆投毒线 recent work,或启用 travel 的
   hint 反馈环)。
4. **[依赖] 补齐 LLM API key**(env 已查无任何 key,是 agent 实验的唯一硬阻塞)。

## 五、会后裁定(2026-08-27,Mian,计入 changelog)

- **"suitable environment" 必须是 LLM-agentic**(agent / LLM-agent 系统);
  与 Yujia "agentic system" 口径确认一致。游戏/网格环境(RoomEnv、ScienceWorld、
  TextWorld)不满足此门槛。
- **RoomEnv / E0 判定为"太小、非真实 benchmark/codebase"**,不满足要求 → 按 §四-1 冻结。
- **全部实验 CPU-only,禁用 GPU**(节点虽有卡,一律不用;`causalts` 须显式
  `device="cpu"` + `CUDA_VISIBLE_DEVICES=""`,此坑已踩过)。

## 六、待确认(下次会议或邮件)

- Yujia 说"modify some existing or recent work"时,心中是哪篇/哪类工作
  (记忆投毒?agent 审计?某个具体 memory 系统)?
- venue(8/15 §六 遗留,仍未确认);
- "每变量多个样本"在逐 episode 重拟合 vs 跨 episode 摊销下的形式化(8/15 §六 遗留);
- ScienceWorld / TextWorld 在 agentic 裁定下是否保留任何角色(默认:降为附录或取消)。
