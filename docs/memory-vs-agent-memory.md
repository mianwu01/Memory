# 因果记忆 vs. Agent Memory：一份对照笔记

> 用途：厘清本项目所说的 "memory" 与 agent-memory 文献所说的 "memory" 的差别，
> 以及"只懂 agent memory"时的知识缺口。
> 依据：`causal_memory_formulation.tex` (v0.1) 的 §Problem statement、§Definitions、
> §Selection、§Positioning 各节。

---

## 一、结论

两者不是同一个对象。

- **agent memory 文献**里，memory 是一个**被工程化的模块**：存储 + 检索 + 反思策略。
- **本项目**里，memory 是一个**被定义的对象**：时序因果模型中的时延因果依赖结构。

差别落在三层：本体、判据、手段。而本项目的贡献恰好住在第二、三层。

---

## 二、逐层对照

### 1. 本体 —— memory 是什么

| 维度 | agent memory 文献 | 本项目 |
|---|---|---|
| memory 是 | 模块：向量库 / 图 / 文件 + write–retrieve–reflect 策略 | 时序 SCM 中变量（观测或潜在）之间的**时延因果依赖** |
| 最小单位 | 一条记录 / 一个 chunk | **write–hold–read 模体** |
| 内部 vs 外部 | 两类东西（上下文窗口 ≠ 外部数据库） | 二分消解：外部存储 = 带恒等动力学与门控写/读边的一个变量 |
| 图的性质 | 常为知识图谱（断言关系） | **生成机制**图，支持 `do(·)` 陈述；非知识图谱 |

原文（§thesis）：

> memory is time-delayed dependency among the variables (observed or latent) of a
> temporal causal model, not a separate external module; an external store is formally
> just a variable with identity dynamics and gated write/read edges, so the
> internal/external dichotomy dissolves at the level of the graph.

### 2. 判据 —— 怎么算"记住了"

- **agent memory**：下游任务分数（检索命中率、QA 准确率、任务成功率）。
  这正是 MemoryAgentBench、MemoryArena 这类基准所测量的东西。
- **本项目**：**D3 可信记忆（trustworthy memory）**，三张证书：
  1. **值对应** —— `ẑ_{ρ(i)} = h_i(z_i)`，容许置换与分量可逆变换；
     可证不可能处（同时冻结的多项允许 hold 中任意可逆混合）放宽到 block 级；
  2. **结构对应** —— `Ĝ` 上的 write/hold/read 边与真图在记忆相关索引集 `M` 上一致；
  3. **选择稳健** —— 若长滞后依赖纯由 selection 造成，系统必须报告 **no carrier**。

这是**可辨识性判据**，不是准确率判据。§related 一节把分界线写死了：

> the memory-agent literature engineers storage, retrieval, and reflection
> **heuristically**; the shared gap is the absence of a **correctness criterion**
> grounding memory in the truthful process, and D3 is that criterion.

### 3. 手段 —— 关联 vs 介入

D1（记忆载体）是**刻意介入式**的定义：不仅要求 `c_{t0} ⊥̸ y_{t1}`，还要求对任意
`s ∈ (t0, t1]` 与常数 `m̃`，在 `do(m_s := m̃)` 之下 `c_{t0} ⊥ y_{t1}`。

> The definition is deliberately interventional: **association at a lag is exactly
> what selection can fake.**

§selection 进一步指出：agent 语料**天然是目标筛选过的**（模仿成功轨迹、RLHF 式过滤、
子目标条件化行为；且 demonstration 数据中的子目标可证是对 `(s_t, a_t)` 的 selection）。
于是 agent memory 赖以训练与评测的数据，恰恰是最容易伪造出"假记忆"的那类数据 ——
一个必须用生成式解释掉全部依赖的流水线，会在这种数据上**幻觉出一条记忆边或一个幽灵持久潜变量**。

---

## 三、只懂 agent memory 够不够

**不够，但它是必需的一半。**

### 够用且不可替代的部分

- **问题直觉**：为什么要记、记什么、何时忘。本项目的因果前沿 `F_t` 本质上就是
  "memorize only what matters" 的形式化 —— Direction 1 被 subsume 而非并列。
- **定位与对照组**：写 §related、设计 E0/E1，都需要知道 mem0 / Letta / HippoRAG /
  Cognee / ReasoningBank 具体在做什么。
- **现成弹药**：MemoryArena 的核心发现（在 LoCoMo 等长上下文基准上接近饱和的 agent，
  在 agentic 设定下表现很差）本身就是"关联式记忆判据不足"的经验证据，可用于支撑
  D3 的必要性。

### 必须补齐的缺口

| 缺口 | 卡住的具体条目 |
|---|---|
| 时序 SCM、d-分离、Markov + faithfulness | 前沿引理（`F_t` 是唯一最小充分记忆）的陈述与证明 |
| 可辨识性：置换 + 分量可逆不确定性；非平稳 / 多域辨识 | Conjecture 1（regime change + set identifiability + gluing）整条线 |
| 因果发现算法：PC-stable、PCMCI⁺、DYNOTEARS、CD-NOD | Layer 1 的 procedure 与 `Ĝ_W → F̂_t` 构造 |
| selection / collider 偏倚；selection-structure identification | D3 的证书 (iii) 与 confabulation control |
| POMDP belief state、PSR、computational mechanics causal states | **最危险的一处**：定义性主张本身是旧的（"the definitional claim alone is old"），不了解会把旧结论误当新贡献 |

### 一句话

> **agent memory 给你问题与对照组；因果那套给你判据与证明。**

本项目的新意住在后者。原文（§how to read）：

> the identifiability framing is what makes this direction different from the
> memory-agent literature.

---

## 四、最短补课路径

1. d-分离 + Markov / faithfulness
2. 时序因果发现（PCMCI⁺ 一篇足够入门）
3. 可辨识性的不可能性 / 层级 / 两条路线 + 非平稳辨识
4. selection bias 与 collider
5. POMDP belief state、PSR、causal states（读到摘要级，知道边界即可）

第 1–4 步在本仓库已有材料覆盖：`artifacts/02-theory-primer.html`、`artifacts/course-zh.html`。

---

## 五、两个基准在本项目中的位置

| 基准 | 性质 | 在本项目中的用途 |
|---|---|---|
| [MemoryAgentBench](https://github.com/HUST-AI-HYZ/MemoryAgentBench)（ICLR 2026, arXiv 2507.05257） | 离线数据集，四能力切分（AR / TTL / LRU / CR），增量注入多轮 | E0 的轻量对照；§related 中"能力分解式评测"的代表 |
| [MemoryArena](https://github.com/ZexueHe/MemoryArena)（ICML 2026, arXiv 2602.16313） | 多 session Memory–Agent–Environment 闭环，子任务显式互依 | 与 write–hold–read 模体同构；其"agent 自选记什么"本身即一个选择机制 → 天然 collider，与 §selection 直接呼应 |

两者均属"以下游分数为判据"的一类，因此它们是**对照组**，不是判据来源。
