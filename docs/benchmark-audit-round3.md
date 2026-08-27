# 基准审计第三轮:C5(观测→变量映射须未解)下的语言/事件流候选(2026-08-21)

> 背景:用户裁定 RoomEnv 的 KG 原生观测(RDF 三元组)是**实质性领域限制**——
> 观测→记忆变量的映射被 schema 直给,而该映射正是 Yujia"变量定义最重要"的核心难题。
> 新判据 **C5:映射必须是未解问题**。RoomEnv/E0 降为受控诊断层。
> 本轮对 TextWorld、ALFWorld、ScienceWorld、MemGym 做了全源码审计(四份独立报告,
> 均有 file:line 证据),并对每个候选**显式裁定**:它服务的是
> MemoryArena/MemoryAgentBench 式的总体目标(一般 agent 记忆),还是只是好做因果发现的基底。

## 0. 总裁定表

| 候选 | (1) NL/事件流观测 | (2) 因子化隐状态+干预→独立金图 | (3)=C5 映射未解 | (4) 一般长程记忆 | 显式裁定 |
|---|---|---|---|---|---|
| **ScienceWorld** | ✅ 纯 NL,真局部可观测 | ✅ `getObjectTree()` 逐对象属性块;tick 循环即因果图(数值系数可读);变体种子/每-tick 简化开关/py4j 反射;无快照分叉 | ✅ 指称多对多、无对齐表、~5 个潜计数器根本未序列化 | ✅ 程序性/空间/测量记忆;**独有:无动作外生过程** | **结构层主基准(found)**。服务原目标的"单集内记忆"半边;多会话交错流需自行组合任务 |
| **TextWorld** | ✅ 纯 NL(结构信息严格 opt-in) | ✅ 全量事实逐步可读;`.twl` 声明式规则集=金边+金**非**边;生成期全干预+快照回滚 | ✅ 释义语法+噪声闲文;若干谓词(match/ingredient_k)**无文本实现** | ⚠️ 原生任务弱(一次写入、可重观测、50 步帽) | **设计路径**:机械最干净,但记忆难度须用 GameMaker **自造**(信息一次性、异地消费、后续矛盾更新、干扰写入)。原样不服务目标;自造后可以,但须声明为我们构造的基准 |
| **ALFWorld** | ✅ 纯 NL | ✅ 33 谓词 + PDDL 动作模式;`apply()` 免费返回逐步 Δs;干预=改 `:init` 字符串/注入 do() 动作 | ❌ **C5 不成立**:~20 条模板语法随基准发货,仓库自带 expert 用 `str.split` 15 行反解 | ❌ 50 步、无外生动态、可重观测、无多试次 | **只作管线验证脚手架**。不服务目标。AMA 桥(同轨迹跨层)真实但廉价:judge 噪声 0.33–0.49 + 轨迹不受记忆压力,承载不了主张 |
| **MemGym** | ⚠️ τ² 对话/DR 文档流/SWE 终端输出 | ❌ 五赛道全无:τ² 循环归 tau2 所有、WebArena 只在 done 时探状态、无 reset/hook | ❌ 双向失败:agentic 赛道无记忆变量;DR/CodeQA 把映射**预先解掉**(fact→hop 表直给) | ✅ SWE 50 步/τ² 100/WebArena 30–50 | **纯下游效用 harness**——但它的 SWE/WebArena 评分是**程序化**的(swebench harness / REST verify),比 AMA 的 LLM judge 干净得多 → 效用层升格首选。DR 的 per_turn_retention 表可作弱结构探针 |

RMBench(机器人,重)与 "DynamicMem"(不可核实)维持第二轮结论。

## 1. 决定性发现:ScienceWorld 的无动作外生过程

这是整个搜索中唯一"天生满足 C1+C5 的时序结构"来源:

- **热弛豫**:每 tick 每对象与容器及同容器邻居换热(`EnvObject.scala:521-533`,
  系数 0.10 写死在源码);冰箱里的水自行趋向 2°C,观测只写 "a substance called water",
  取值须显式用温度计——**k 步前拨的开关驱动一个从不被言语化的连续隐状态**;
- **植物生命阶段**:种子→苗需连续 10 tick 有水有土(计数器不序列化、不显示);
  缺水 10 tick 病、20 tick 死;
- **燃烧倒计时**:100-tick 潜伏计时器,归零删除对象生成灰;
- 斜面滑动、水槽注水、秒表等设备自动机。

即观测流真非马尔可夫:agent 必须记住"**什么时候**开的火/种的种子/按的表"。
这正是 LongMemEval/travel 里我们证明不存在、travel-R 里要人工搬运的东西——此处由物理给出。

定位语(采纳审计原话):**"easy-mechanism / hard-instantiation"**——机制词汇小
(~8 个过程复用于 30 任务),不能吹成"困难因果发现";卖点是**可审计的金标 + 未解的
NL→变量抽取 + 真外生时序**三者同时成立。

## 2. 修订后的三层证据架构

| 层 | 载体 | 交付物 | 状态 |
|---|---|---|---|
| **受控诊断** | E0 + RoomEnv-v3 | regime 必要性(三方法汇合)、oracle-C4、规模曲线 | ✅ 已完成(`e0-v0-results.md`、`roomenv-pipeline-results.md`) |
| **语言上的结构** | **ScienceWorld(主)** + TextWorld 自造记忆游戏(辅)+ ALFWorld(管线验证) | NL→变量抽取作为**被测量的显式阶段**(终于把 Yujia 的"变量定义"变成实验对象);抽取质量 × 图恢复 × 记忆收益的三段归因 | 待启动(先装 JRE) |
| **下游效用** | **MemGym(SWE/τ²/WebArena,程序化评分)** + MemoryArena + AMA/MAB-压缩 | 同一 memory 接口(MemGym 只需 `manage_context`+`reset` 两方法)的任务成功率/压缩/延迟 | 排队;MemGym 升为效用层首选(评分最干净) |

对总体目标的诚实定位:ScienceWorld 覆盖"单集内程序性记忆"半边;
MemoryArena/MemGym 式"多会话交错流"半边要么用 ScienceWorld 任务链/变体串接,
要么用 TextWorld 自造——两条都属"构造",在论文里须与 found-benchmark 结果分开陈述。

## 3. 行动项(优先级序)

1. **[环境] ScienceWorld 落地**:`pip install scienceworld py4j` + 用户态 JRE
   (`pip install install-jdk; python -c "import jdk; jdk.install('11')"`——沙盒无 java,已核实);
   **版本钉死**(1.3.0 改过物理),记录 JAR hash;
2. **[T0-SW] ScienceWorld 手上检验**(全 CPU、无 LLM):load task-1-boil,
   逐步 dump `getObjectTree()`,(a) 复现热传导数值(源码系数 vs 实测 Δ温度,
   类比 RoomEnv 的 0 失配复现);(b) 量化"未言语化率"——隐状态变量中有多少
   从不出现在 look/action 反馈里(C1 的量化版);(c) 从 tick 源码手工导出
   boil 任务的金边表,与 (a) 对拍;
3. **[补丁面] 评估 JAR 小补丁**(~5 个潜变量入 JSON;或先用 SCIENCEWORLD_DEBUG
   stdout 抓取顶事);
4. **[设计] TextWorld 记忆游戏设计备忘**(信息一次性+异地消费+矛盾更新+干扰写入,
   用 GameMaker/quest API;金图免费),与 Yujia 对齐后再造;
5. **[效用接口] MemGym `BaseMemoryManager` 两方法适配器**骨架(与 MemoryArena 的
   两方法适配器同构,复用 Form B 的掩码链设计);
6. **[汇报] 向 Yujia 摆出三层架构 + 本轮四份审计 + "ScienceWorld 的外生过程恰是
   formulation 里 write–hold–read 的物理实现"这一对应(stove=write 事件,
   弛豫=hold 动态,测温=read)。**
