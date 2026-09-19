# Agentic 实验计划:三部分,LLM-agent 系统,CPU-only(2026-08-27)

> 承 `meeting-minutes-2026-08-21.md`。定调:论文主干 = 用时序因果结构做记忆;
> 两分支 = 效果/效率、可信性;实验三部分 = 仿真 / 效率 / 可信性;
> **后两部分各 1–2 个代表性设置,baseline 极简,coverage > depth**。
> 会后两条硬约束:**(H1) 载体必须是 LLM-agentic 系统**(非游戏/网格);
> **(H2) CPU-only**——本机无本地推理,一切 agent 运行走 LLM API(env 目前**无任何 key**,
> 见 §四,是唯一硬阻塞)。

---

## 0. 方法主干(三部分共用,不随载体变)

固定 schema 记忆 `X_t ∈ R^d`(Form A:槽位值 + 持续规则 + provenance);
从轨迹抽取变量表 → 时序因果发现 → 学得依赖图 `G` → **图反过来作用于记忆**
(`wrap_user_prompt` 内按 `An_G(query)` 施加保留/掩码)。三部分只换**载体与评价目标**:

| 部分 | 载体 | 主评价 | 状态 |
|---|---|---|---|
| P1 仿真 | E0 (自造 SCM) + RoomEnv(受控) | 结构恢复 F1、regime 必要性 | ✅ 完成并**冻结**;E0 v2（无 oracle 泄漏）2026-09-18 跑完并通过 C1–C3;C4 触发:per-regime 回归同样达标,Regime-GRACE **不再作为方法贡献**(见 §1 修订) |
| P2 效率/效果 | **MemoryArena**(真实 LLM-agent,**12** 记忆系统同台) | 任务成功率 / 压缩比 / 延迟 | 🔨 插件已对齐真实 7 槽 travel schema 并离线通过(压缩比 0.011);阻塞在 endpoint |
| P3 可信性 | **MINJA-QA**(记忆投毒,复用其攻击与数据) | 隐藏驱动检出率、行为/相似度审计漏检对照 | ✅ **v0 已跑**(离线 answerer),见 `p3-minja-causal-audit-results.md` |

> **2026-08-27 晚间修订(独立复核 + 首轮实验后)**
> - P3 载体由 MemoryArena 自造场景改为**复用 MINJA-QA**——符合 Yujia"改造 recent work"的原话,
>   且异常动作判据(答案 ASCII+4 → {E,F,G,H})是**数据自带**的,无需自定义标注。
> - **MemoryArena 无 LICENSE** → 插件独立成文件、运行时注册,不 vendor/不分发其代码。
> - **MemGym 提升为 co-carrier**(Apache-2.0 + 程序化判分),用于 P2 的"效用层"复核。
> - P3 首轮的**诚实负结果**:E0 的"池化致盲"不会自动转移;转移的是**估计量衰减**(见结果文档 §3 R1)。

---

## 1. P1 — 仿真(冻结,循例)

**归位**:E0 + RoomEnv 的全部已有结果落此格。**不再投入扩展**
(RoomEnv v2 coupling / 更多 scaling / kg-memory-transfer 复现 / Craftax 门 / SW·TW —— 全停)。

> **2026-09-18 修订(E0 v2 跑完后,用户拍板)。** E0 v2(`docs/e0-v2-design-2026-09-03.md`,
> `results/e0v2/summary.md`)去掉了 v0/v1 的三处 oracle 泄漏后:池化臂(pooled ridge、additive-u、
> PCMCI、GRACE 官方实现、池化 gate)在任何样本量都恢复不了 gate 表(C2 PASS);打乱 u 的对照全部坍塌
> (C3 PASS);Regime-GRACE 达标(C1 PASS)。但 **C4 触发**:看到 u 的 per-regime 回归(v0 估计量去掉
> oracle)与 interaction-HC 同样达标,E0b 里 per-regime 回归到达 memory-cell F1 ≥ 0.9 所需的 T 比
> Regime-GRACE 小 2–4 倍,Regime-GRACE 在 λ=0.5 下对 distractor cell 还有约 9% 假阳性;E0c 的 MLP 机制
> 也分不开两者;唯一领先处是 d=1000(per-regime 需 SIS 筛选,0.969 vs 1.000)。
> 结论:E0 支持的是"**regime 条件化是必要的**"(池化 vs 条件化),不支持"Regime-GRACE 是更好的估计量"。
> 论文第一部分按设计页 C4 的措辞写:regime 索引的 gate 表是正确的估计对象,若干估计量都能拟合,我们
> 用最简单的 per-regime 回归 + FDR(P2/P3 已经在用);Regime-GRACE 降为附录行(d=1000 一行如实报告)。
> **"regime-conditioned GRACE v1 作为方法贡献"一项撤销**;不再改造 E0(潜变量 regime 等版本)——
> 那是加深第一部分,与 Yujia"可循既有论文、篇幅从简"的定调相悖。P3 的机制故事(隐藏触发 = 门控 read
> 边,池化/行为审计看不见、regime 条件化看得见)不受影响,因为它是池化 vs 条件化的对比。

E0 已证明 write–hold–read 门控边对 PCMCI+、池化回归、GRACE(盲+u 增广)**全部致盲**,
唯显式 regime 条件化恢复;E0 v2 在去掉 oracle 泄漏后复现了这一点。

产出即用于论文的"第一部分",按 Yujia"可循既有论文"处理:篇幅从简,重点让读者信服
金结构可恢复、门控需要 regime 条件;估计量用 per-regime 回归。

---

## 2. P2 — 效率/效果,MemoryArena(首选真实载体)

**为什么是 MemoryArena**:唯一在手的**真实 LLM-agent codebase**——13 个真实记忆系统
(mirix / mem0 / mem0-g / letta / rag / memorag / graphrag / amem / lightmem /
reasoningbank / zep / long_context / memorag)已注册在 `memory/server.py:49`
`MEMORY_FACTORIES`,天然同台对比;接入我们的方法只需**注册一个新记忆系统**
(源码核实的**两方法鸭子接口**:`add_chunk(chunk:str)` 写入、
`wrap_user_prompt(prompt:str)->str` 用 `<memory_context>…</memory_context>` 包裹后返回,
`run_travel.py:262` 以 `</memory_context>` sentinel 切分——**该 sentinel 载荷关键**)。

**变量/样本(承 Form B,MemoryArena 侧)**:
- t = 一个对话 round;变量 i = 7 槽位 travel schema(源 T0 已核实)+ 可选 agent 记忆槽;
- 取值先用更新指示 (i),有信号再上值 embedding (iii)(GRACE encoder 换线性投影即可);
- 每变量样本:跨 episode 摊销池化(单 episode T=5–8 太短,8/15 §六 遗留问题,此处正面回答)。

**评价(Yujia 的双目标,P2 主推下游)**:
1. **主**:任务成功率 @ 匹配 token 预算(压缩轴)——我方 `CausalMemorySystem`
   vs `long_context`(全上下文上界)、`rag`(BM25/embedding 检索,最强非因果基线)。
   **按 Yujia:只留 1–2 个 baseline**,建议 long_context + rag 两条即可。
2. **诊断**:压缩比(保留 token / 全历史 token)、端到端延迟。

**T0-Arena(第一个可跑实验,CPU-only)**:
`CausalMemorySystem` 先以"结构化槽位 + 祖先掩码"实现(离线图或规则图,**先不跑发现**),
在 travel 上对 long_context / rag 比成功率-压缩 Pareto。**目的是复刻 oracle-C4 的
压缩优势能否在真实 LLM agent 上兑现**,而非证明发现必要(travel T0 已知 discovery 非必需——
故 travel 在 P2 只承载**结构化记忆的压缩/效率**主张,这点须在论文里诚实分离)。

**诚实风险**:travel 的依赖在 query 文本里显式,P2 的胜点是压缩/效率,不是"因果发现带来收益"。
若要让"发现带来收益"在真实系统上成立,需 travel 之外的环境(math/webshop/search),
或启用被关掉的反馈环(见 P3)——留作 P2 v1 的延伸。

---

## 3. P3 — 可信性/审计(核心新增,改造 recent work)

**主张**:行为审计有根本局限(只见输出);记忆里被隐蔽写入、潜伏、条件触发的驱动源
(= 一条**门控 read 边**)对行为/相似度审计**不可见**,但对**恢复出的时序结构可见**——
它会被标为异常动作的**因果祖先**。E0 三方法汇合已是该现象的受控预演,P3 = 真实 agent 上的实例化。

**载体选定 = 复用 AgentPoison(见 `p3-safety-benchmark-selection.md`)**,不自造环境。
Yujia"modify recent work / recover something hidden"落到**记忆投毒线**——其失败机制天生就是门控 read 边。

- **主选 AgentPoison**(NeurIPS'24,`github.com/AI-secure/AgentPoison`,240★,**触发器+投毒数据已释放**,
  故省掉 GPU 触发器优化;文本域 ReAct-StrategyQA 最省,CPU-only):
  载入投毒记忆 DB + 已释放触发器;两组查询(含/不含触发词);开轨迹 write-back 使投毒 trace
  t−k 写入、T 步检索;`X_t` 槽位 = {top-K 检索记录、投毒项被检索指示、触发词指示、动作};
  时序因果发现 → 投毒槽 = 异常动作的**门控祖先**;对照 (a) 行为审计、(b) 相似度检索审计、
  (c) **MemAudit(2605.23723)逐记录归因** —— 唯我方给出结构/图。
- **次选 MINJA**(NeurIPS'25,`dsh3n77/MINJA`):query-only、低相似度、跨轮持久 = **最纯门控 read 边**;
  **代码完整度待核**,完整则升主选。
- **novelty 边界**:MemAudit 做逐记录**归因/检测**(无图);我们做**因果发现+依赖图**,同图**双用**于
  记忆选择 → 首要 baseline 且共用 AgentPoison 测试床。备选审计对照 HarnessAudit(轨迹级违规,另类 driver)。

**评价**:检出率(隐藏驱动是否进入 `An_G(异常动作)`)、行为审计漏检率对照、
可选的"检出→gate 后续动作"闭环成功率(Yujia 的 "allow the system to gate the following actions")。

**代表性**:按 Yujia"1–2 个设置",P3 先做 **AgentPoison-StrategyQA(文本、最省、CPU)**,
MINJA 或驾驶域作为更强主张的第二设置。

---

## 4. 阻塞与依赖(务必先解)

| 阻塞 | 现状 | 解 |
|---|---|---|
| **LLM API key** | env 无任何 key(仅 `CLAUDE_CODE_EXECPATH`);MemoryArena 支持 ANTHROPIC / OpenAI / Gemini / OpenRouter | **必须先配一个**——P2/P3 全部依赖;建议 ANTHROPIC 或 OpenRouter(源码路径最全) |
| GPU 禁用 (H2) | 本机有卡但一律不用 | `causalts` 强制 `device="cpu"` + `CUDA_VISIBLE_DEVICES=""`(已知坑);记忆系统里若有本地 embedding,改走 API embedding 或 BM25 |
| 部分记忆系统需外部服务 | letta/zep/mem0 可能起服务或额外 key | 首轮 baseline 只用 `long_context` + `rag`,避开重依赖 |

## 5. 里程碑(依赖 key 到位)

1. **M0(可离线做)**:`CausalMemorySystem` 骨架(✅ `code/arena_causal_memory.py`)+
   regime-conditioned GRACE v1 in E0(纯 CPU,不依赖 key)。→ 2026-09-18:E0 v2 已跑完,该项按 §1 修订撤销。
2. **M1(需 key)**:T0-Arena — 我方(规则/离线图 + 祖先掩码)vs long_context vs rag,
   travel 成功率-压缩 Pareto。
3. **M2(需 key)**:P3 路线 B — 开 hint 环,验证图抓 hint→动作边 + 行为审计漏检对照。
4. **M3**:P3 路线 A — 注入 covert chunk,三审计对照 + gate 闭环。
5. **M4**:把 GRACE 发现的图接进 `CausalMemorySystem`(替换规则图),完成"发现→记忆→收益"整链。

## 6. 待与 Yujia 确认

- "recent work" 具体所指(记忆投毒?agent 审计?)——决定 P3 路线 A 的改造对象;
- P2 是否接受"travel 上胜点是压缩/效率、非发现必要"的诚实分离,还是要求换环境证明发现收益;
- venue;向量值变量是否 v1 就上。
