# P3 载体选型 + 记忆平台选型(2026-08-27)

> ⚠️ **2026-08-27 晚间独立复核已推翻本文两处裁定,以
> `p3-minja-causal-audit-results.md` §0 与下方"复核修订"为准。**
> 1. **P3 主次对调:MINJA-QA 升主选,AgentPoison 降第二环境。**
>    决定性事实:**MemAudit(2605.23723)的评测环境是 MINJA,不是 AgentPoison**(本文 §"关键情报"记反了)
>    → 同环境才能与首要 baseline 头对头;且 AgentPoison README **未释放**可直接用的最优触发器
>    (要求自跑梯度式 `trigger_optimization.py`),其 `ReAct/` 有 **15 处 `.to("cuda")`**(已本地核实)。
> 2. **MINJA 的 EHR 路径是合规红线**:MIMIC-III / eICU 凭证数据被直接提交进仓 → **只用 QA 路径**。
> 3. MemAudit **无代码释放**,"首要 baseline"须自行复现(CMIS + DeBERTa 一致性图),算成本不算现成对照。
> 4. 新增必引最近邻:**2608.10502**(依赖图,但基于运行时 provenance 且**假定故障记忆已诊断**为输入
>    → 修复而非发现,不撞我们的"发现"新颖性)。
> 5. 任务乙侧:**MemoryArena 无 LICENSE 文件**(default copyright)→ 插件**不 vendor 其代码**,
>    运行时注册;注册系统数应为 **12**(非 13)。**MemGym 提升为 co-carrier**(Apache-2.0、
>    程序化判分,而非 LLM 相似度奖励)。

> 承 Yujia 指令(2026-08-27,Mian 转达):
> **任务甲**——找一篇已经做过 agent safety / auditing 的近期论文,**直接复用其实验环境或
> 失败场景,只做小改动**,测试我们的因果方法能否恢复导致失败的 hidden driver。
> GPT 建议:HarnessAudit、Auditing LMs for Hidden Objectives(2025)、Auditable Agents。
> **任务乙**——找一个成熟的"Agent Memory PyTorch / benchmark suite"式 GitHub 平台
> (已集成多种记忆方法 + agent 环境 + 评测管线),把我们的方法做成**独立的时序因果记忆
> 插件**接进去,证明能提升现有记忆系统的表现,而非从零重建。
>
> 两条独立搜索(各一 web-agent,file:line / arXiv / repo 均已核验;下方标注核实等级)。
> 结论天然对齐项目的 P2/P3 双分支:**任务乙 = P2 载体(MemoryArena),任务甲 = P3 载体(AgentPoison)**。

---

## 任务甲 — P3:复用哪篇 safety 论文

### GPT 三建议的核验

| 建议 | 真实性 | 是否有可复用环境 | 裁定 |
|---|---|---|---|
| **HarnessAudit**(arXiv 2605.14271,UCSB) | ✅ 真实,代码已放 `github.com/eric-ai-lab/HarnessAudit` + HF 数据 | 210 任务 / 8 域,API-first | **中等契合**:hidden driver 是**轨迹中途的边界违规**,不是"t−k 写入、潜伏、条件触发"的记忆槽;可作**互补审计 baseline**,非主选 |
| **Auditing LMs for Hidden Objectives**(arXiv 2503.10965,Anthropic,2025) | ✅ 真实且著名 | 原模型**未释放**;开源复现基于 **Llama-3.3-70B** | **不契合我们的约束**:隐藏目标**焙进权重**(RM-sycophancy),不是跨轮记忆槽 → 无"门控 read 边"可恢复;且 70B **CPU 跑不动**。仅作 motivation 引用 |
| **Auditable Agents**(arXiv 2604.05485) | ✅ 真实 | **无环境、无代码**(纯问责/日志框架) | **不可用**,跳过 |

**结论**:GPT 三选中,只有 HarnessAudit 有可复用环境,但机制不是记忆型 hidden driver。
真正对口的在**记忆投毒(memory poisoning)**这条线上——它的失败机制**天生就是我们的门控 read 边**。

### 真正对口的候选(记忆投毒线,按契合度排序)

| # | 论文 | arXiv / 场所 | 代码 | 机制 = hidden driver | CPU 可行 |
|---|---|---|---|---|---|
| **主选** | **AgentPoison** | 2407.12784,**NeurIPS 2024** | ✅ **`github.com/AI-secure/AgentPoison`(官方)** / `BillChan226/AgentPoison`(作者镜像),~240★,含**释放的触发器 + 投毒数据** | 优化触发词进入长期记忆/RAG-KB,查询含触发词→检索投毒示例→驱动异常动作(如自动驾驶急停);≥80% ASR,<0.1% 投毒率 | ✅ **复用**即可:**不重跑触发器优化**(那步需 GPU),用已释放触发器;检索 embedder 走 CPU,agent 走 API;文本域 **ReAct-StrategyQA** 最省 |
| 契合最纯 | **MINJA** | 2503.03704,**NeurIPS 2025** | ⚠️ `github.com/dsh3n77/MINJA` 存在,但检索显示"作者表示**将**释放代码"——**代码完整性存疑,须先核**;三管线 RAP/EHRAgent/QA | **query-only** 投毒:普通查询即把恶意推理记录写入 agent 自己的长期记忆,潜伏,后续 benign 查询检索到→被引偏;98.2% 注入 / 76.8% ASR;**恶意记录刻意与受害查询低相似** → 相似度审计天然失效 | ✅ agent 走 API,检索走 CPU |
| 最省集成 | **AgentDojo** | 2406.13352,**NeurIPS 2024 D&B** | ✅ `github.com/ethz-spylab/agentdojo`,**~773★,活跃**,`pip install agentdojo` | 间接 prompt injection 藏在环境数据项(邮件/文档),t0 写入、k 步后读入上下文→触发恶意副作用 | ✅ 全 API,pip 装 |

### 关键情报:已有"因果审计投毒记忆"的竞品 → 反而磨利我们的 novelty

搜索顺带命中三篇**同方向**近作,必须知道(避免撞车 + 提供 baseline):

- **MemAudit**(arXiv **2605.23723**,2026-05):"Post-hoc Auditing of Poisoned Agent Memory via
  **Causal Attribution** and Structural Anomaly Detection"。**已核**(WebFetch 全文):
  用的是**逐记录影响力归因(per-record / influence-based)+ 结构异常检测,仅检测,
  NOT 时序因果结构学习,不恢复依赖图**;benchmark 用 **AgentPoison**。
  → **最近竞品,但不重叠**:我们做的是**时序因果发现**、恢复**依赖图**、把 hidden driver
  标为异常动作的**时序因果祖先(门控 read 边)**,且同一张图**反过来做记忆选择/掩码**
  (审计 + 记忆双用)。MemAudit 是"给某条记录打分",我们是"恢复结构 + 门控语义"。
  **MemAudit = 首选对比 baseline**,且它选 AgentPoison 恰好印证 AgentPoison 是公认的投毒审计测试床。
- **Memory Poisoning Attack and Defense on Memory Based LLM-Agents**(arXiv 2601.05504)——防御/检测 baseline。
- **MEMSAD**(arXiv 2605.03482):"Gradient-Coupled Anomaly Detection for Memory Poisoning in RAG Agents"——同上。

### P3 裁定(2026-08-27 recon 后更新 — 两 repo 已 clone 逐文件核实)

**MINJA 代码核实 = GO**(非 stub):三管线 QA/EHR/RAP 均有完整可跑 `.py` + 投毒模板在仓。
`dsh3n77/MINJA` MIT / 35★ / 4 commits / 2026-08-11。→ 早先"次选待核"疑虑消除,**首选顺序调整**:

- **首个 instrumentation 目标 = MINJA-QA**(`QA/main.py`)—— **两仓中最省的 CPU 路径**:
  纯 OpenAI API、**Levenshtein 字符串检索(无 embedder、无 GPU、无外部 server)**、
  MMLU 数据 + 投毒 payload(`QA/victim.json`)全部在仓。记忆 = `memory.json` 的 dict 列表,
  投毒记录的 `thought` 携带 hijack,检索→few-shot→答案翻转是干净因果链,直接映射 X_t/动作。
  须踩坑:文档薄(用法读 argparse)、`gpt-4o` 写死(参数化)、`QA/main.py:326-327` 疑似缩进 bug。
- **头对头测试床 = AgentPoison-ReAct-StrategyQA**(`AI-secure/AgentPoison`,MIT/240★/2026-08-15 活跃):
  KB 自带(`ReAct/database/strategyqa_train_paragraphs.json`,9251 段);**投毒在运行时由任意 trigger
  字符串生成**(`local_wikienv.py:142-204`)→ **可跳过 GPU 触发器优化**;检索 = DPR cosine
  (`local_wikienv.py:290-361`,已带 poison-hit 标记 `:353`,便于金标)。须踩坑:多处 `.to("cuda")`
  逐行改 cpu(`local_wikienv.py:60,63,66,…`)、需 `openai<1.0`、首跑一次性 CPU 嵌入 9251 段。
  **为何仍要跑它:MemAudit 正是用 AgentPoison 做审计 → 同测试床才能与首要 baseline 头对头。**
- **不用于首轮**:AgentPoison-Agent-Driver / EHRAgent、MINJA-RAP(WebShop server)/EHR
  (bundled MIMIC-III via LFS,凭证数据,合规勿再分发)—— 环境重,首轮不值当。
- **补充审计 baseline:HarnessAudit**(轨迹级边界违规,另一类 driver,覆盖面用)。
- clone 位置:`…/scratchpad/AgentPoison_AIsecure/`、`…/scratchpad/MINJA/`。
- **小改动方案(AgentPoison,CPU-only)**:载入投毒记忆 DB + 已释放触发器;两组查询
  (含/不含触发词);开启轨迹 write-back 使投毒 trace 在 t−k 写入、T 步检索;
  固定 schema `X_t` 槽位 = {top-K 检索记录、投毒项被检索指示、触发词出现指示、动作};
  时序因果发现 → 证明投毒槽是异常动作的**门控祖先**;对照 (a) 仅看动作成功的行为审计、
  (b) 相似度检索审计、(c) **MemAudit 的逐记录归因** —— 三者要么漏检要么无结构,唯我方给出图。

---

## 任务乙 — P2:插进哪个记忆平台

### 生态硬事实

**成熟高星的 repo 全是"单一记忆产品",不是"多方法插件宿主"**:
mem0(~64k★)、Letta(~24k★)、MemOS(~11k★)、cognee(~6–14k★)、A-Mem(~1.1k★)——
各自一套记忆、一个 API,**不集成多方法、无 agent 环境、无对照评测** → 它们是**要打败的 baseline,
不是宿主**(且多数已被 MemoryArena 包进去了)。

**真正符合"多方法 + agent 环境 + 评测管线 + 插件注册"的,全是小型近期研究套件**
(MemoryArena 58★ / MemGym 21★ / AMA-Bench 75★ / MemoryAgentBench 440★)。
"成熟多贡献者高星"与"是可插件 benchmark 套件"在 2026-08 **基本互斥**。

### 对照(已在手的四个 + 最强外部替代)

| 套件 | repo | 集成记忆方法 | 插件接口 | agent 环境 | 固定 schema(我方发现所需) | CPU-only |
|---|---|---|---|---|---|---|
| **MemoryArena(incumbent)** | `ZexueHe/MemoryArena` 2602.16313 | **13**(mirix/mem0/mem0-g/letta/rag/memorag/graphrag/amem/lightmem/reasoningbank/zep/long_context) | **2 方法鸭子接口** `add_chunk`+`wrap_user_prompt`,注册进 `MEMORY_FACTORIES`(源码 `server.py:49`) | travel/shopping/search/math,真 write-hold-read | ✅ travel 专为此 | ✅ 已验证 |
| MemGym(最强外部) | `WujiangXu/MemGym` 2605.20833 | ~10(A-MEM/HippoRAG/Mem0/MemoryBank/LightMem/SimpleMem+…) | **显式 `register_memory_model()`**,Memory-Reasoning 分离 | SWE/τ²/WebArena/DR/CodeQA | ❌ 非固定 schema | ⚠️ MemRM-1.7B + Docker/WebArena 摩擦 |
| AMA-Bench | `AMA-Bench/AMA-Bench` | ~5 | `BaseMethod`+`method_register.py` | BabyAI/TextWorld/Crafter | 部分 | ⚠️ 文档建议 CUDA/vLLM |
| MemoryAgentBench | `HUST-AI-HYZ/MemoryAgentBench`(ICLR 2026,440★) | cognee/letta/mem0 | config 选择 | **inject-once/query-many 检索式,无交互 write-hold-read** | ❌ | 不明 |

### P2 裁定

- **#1:留在 MemoryArena** —— (a) 已集成 13 系统给出正面对照;(b) `add_chunk`/`wrap_user_prompt`
  是全场最低摩擦插件面,**我方插件已写好并离线通过**(`code/arena_causal_memory.py`);
  (c) travel 提供固定 schema、跨 episode 共享、记忆是唯一跨轮通道 —— 时序因果发现**只有这里**具备;
  (d) 干净 CPU-only;(e) 已是 2026 公认 benchmark。**唯一风险 = 单作者"preview"**,
  缓解:**vendored 钉住已审计 commit**,防上游 churn。
- **#2 fallback:MemGym** —— 若审稿要"code/web 环境广度"或更强 baseline 名册(HippoRAG/MemoryBank)
  再上;接受 CPU 摩擦(跳 SWE/WebArena、MemRM 换 API-judge)。
- **不采纳为宿主**:mem0/Letta/MemOS/cognee(单产品,当 baseline);MemoryAgentBench 作**补充检索式评测面**。

---

## 汇总裁定 + 下一步

1. **P2 载体 = MemoryArena**(插件已写,`code/arena_causal_memory.py`);**不重建**。契合 Yujia"做成插件接进去"。
2. **P3 载体 = AgentPoison**(主),**MINJA**(若代码完整则升主),**HarnessAudit** 补充;
   **MemAudit(2605.23723)= 首要对比 baseline,且共用 AgentPoison 测试床**。
3. **novelty 边界已明**:MemAudit 做逐记录**归因/检测**;我们做时序**因果发现 + 依赖图**,
   hidden driver = **门控 read 边(时序祖先)**,同图**双用**于记忆选择。E0 三方法汇合是其受控预演。
4. **阻塞不变**:LLM API key(P2/P3 全依赖)+ CPU-only。
5. **待核**:`dsh3n77/MINJA` 代码完整度(决定 MINJA 能否升主选)。
6. **待与 Yujia 确认**:他说"modify recent work"是否就指记忆投毒线;P3 首个 setup 用
   AgentPoison-StrategyQA(文本、最省)是否 OK;是否要在同一篇里同时展示 P2(MemoryArena 提升)
   与 P3(AgentPoison 审计)以覆盖两分支。

### 已核验的关键链接
- 论文:arXiv 2407.12784(AgentPoison)、2503.03704(MINJA)、2406.13352(AgentDojo)、
  2605.14271(HarnessAudit)、2503.10965(Hidden Objectives)、2604.05485(Auditable Agents)、
  **2605.23723(MemAudit,竞品)**、2601.05504、2605.03482(投毒检测 baseline)。
- Repos:`github.com/AI-secure/AgentPoison`、`github.com/BillChan226/AgentPoison`、
  `github.com/dsh3n77/MINJA`(⚠️代码完整度待核)、`github.com/ethz-spylab/agentdojo`、
  `github.com/eric-ai-lab/HarnessAudit`、`github.com/ZexueHe/MemoryArena`、`github.com/WujiangXu/MemGym`。
