# Layer 1 方法选型：两条 pairing 的理由、边界与风险

> **状态：working hypothesis，不是已确定的最终方案。**
> 本文记录的是"为什么现在会出现这两套 pairing"的推理过程，不是选型结论。
> 姊妹文档 `memory-vs-agent-memory.md` 讲的是 Layer 2 的判据问题，见文末"两份文档的关系"。

---

## 0. 先明确 Layer 1 到底要什么

Yujia 给 Layer 1 的最简目标，本质上是：

```
past memory  →  discover temporal dependency  →  only keep what matters
```

**最终产物不是一张漂亮的 causal graph，而是一个 memory mask**

```
M_t ∈ {0,1}^N
```

所以选算法时真正要问的只有两个问题：

1. **这个平台上的"时间"到底长什么样？**
2. **这个方法输出的结构，能不能自然地变成 memory mask？**

这两个问题决定了下面两套 pairing 的分工。**不是**"GRACE 天生属于 MemoryAgentBench、UnCLe 天生属于 MemoryArena"，而是先看平台产生什么形态的数据，再看哪种方法的 inductive bias 与之最接近。

---

## 1. MemoryAgentBench 的实际数据形态（已核对代码）

它**不是**一个持续在线运行的 `W → R → W → R → ⋯` memory process。

实际是：先把所有 context 灌进去，再集中回答问题，即

```
W^N R^M
```

**代码依据**（`agent.py`）：所有 chunk 走 `send_message(message, memorizing=True)`，之后 query 走 `send_message(message, memorizing=False)`；README 自述的设计哲学也是 "inject once, query multiple times"。

**推论**：整个 benchmark 只有**一次** write→read transition，没有丰富的 write/hold/read regime alternation。

因此在这里问"第 17 个 timestep 和第 22 个 timestep 的 causal graph 是否动态变化"并不自然。它真正自然的问题是：

> **Query 来的时候，已有的几十条 memory 中，哪些应该被保留下来交给 LLM？**

### 1.1 它本来就有一个两阶段 retrieval，且注入点干净

现状是：

```
All memory  →  similarity / BM25 top-k  →  LLM
```

**代码依据**（`agent.py::_handle_bm25_rag`，`_handle_hippo_rag`、`_handle_embedding_rag` 同形状）：

```python
bm25_documents = self.bm25_retriever.get_relevant_documents(retrieval_query)
retrieval_context = [f"{doc.page_content}\n" for doc in bm25_documents]
retrieval_memory_string = "\n".join([f"Memory {i+1}:\n{text}" ...])
ask_llm_message = retrieval_memory_string + "\n" + message
```

检索器实现在 `methods/`：`embedding_retriever.py`、`graph_rag.py`、`raptor.py`、`self_rag.py`、`zep.py`，以及 `hipporag/`、`memorag/`。

**注入点就在 retrieval 之后、拼进 prompt 之前**，非常干净。

假设有 32 条 memory `{m_1, …, m_32}`，native retriever 先给出候选

```
S = {m_2, m_5, m_8, m_10, m_14, …}      (10 条)
```

真正的问题随之变成：**similarity 认为这 10 条相关，但它们真的全都应该进入 context 吗？**

于是可以插入第二段：

```
S  →  causal refinement  →  M ⊆ S
```

---

## 2. GRACE 实际做的是什么

> GRACE: *Gated Refinement for Accurate Causal Edge Discovery in High-Dimensional Time Series*，
> [arXiv 2606.23880](https://arxiv.org/abs/2606.23880)（2026-06）。以下数字已对原文核实。

GRACE **不是**"给它一大堆变量就端到端发现所有 causal edges"。它是 two-stage：

```
skeleton  →  neural refinement
```

1. 第一阶段：用 high-recall 的 constraint-based 方法产生 candidate skeleton —— 宁可把真 edge 基本都留下，同时夹杂大量 false positives。
   **原文用的是 CDNOTS 与 PCMCI（partial correlation）为主，DYNOTEARS（score-based）与 RCoT（nonlinear CI test）为辅。**
2. 第二阶段：给每条候选 edge 一个独立的 **Hard Concrete gate**（reparameterization trick 采样，在 0 与 1 上有正概率质量），配 **解析形式的 L0 正则**（无需 Monte Carlo）：
   `P(z ≠ 0) = sigmoid(log α − τ log(−γ/ζ))`。
   gate 值呈清晰双峰，真 edge 集中在 0.5 以上、假 edge 集中在 0.5 以下，**不需要 post-hoc threshold tuning**。

即

```
candidate edges  →  sparse binary edges
```

**关键 ablation（Table 9, Appendix G）**：去掉 skeleton 后，全部 `d²(L+1) − d` 条候选边直接交给 gates ——
在 `d = 50` 时约 **15,000 条候选** vs 约 **100 条真实边**。原文原话：

> "no λ setting can recover signal at this ratio (F1 ≪ 0.02)"

> **skeleton 对 GRACE 不是锦上添花，是核心。**

---

## 3. 与 MemoryAgentBench 的对应 —— 这是我们的 hypothesis

| | 候选生成 | 精炼 |
|---|---|---|
| GRACE 原论文 | all possible causal edges → CI / PCMCI skeleton | Hard Concrete gating |
| 我们在 Agent Memory 中 | all memories → dense / BM25 retriever | Hard Concrete gating |

对应关系是：

```
retriever  ≈  candidate generator / skeleton
```

> ### ⚠️ 措辞红线
>
> **不要写**：`GRACE naturally uses retrieval as skeleton.` —— 它没有。
>
> **应写**：`We hypothesize that the native high-recall retriever can play the role of GRACE's candidate skeleton.`

这条 hypothesis 本身才是 potentially novel 的地方，写成既有结论反而把新意抹掉了。

---

## 4. GRACE 的输出形式也对得上

我们最终要的是

```
m_i = 1  (keep memory i)   /   m_i = 0  (drop memory i)
```

即一个**稳定的离散决策**。Hard Concrete gate 天生趋向 0/1，与 memory mask 高度一致。

反过来，CUTS+ 的问题是：continuous graph scores 的 ranking 可能不错，但 threshold 之后不一定形成干净的 binary graph。GRACE 的 pair-level evaluation 下（**Table 6, Appendix E**）：

| `d = 100` | CUTS+ | GRACE |
|---|---|---|
| `T = 1000` | **0.055** | 0.834 |
| `T = 2000` | **0.117** | 0.859 |

对一个最终必须做 keep/drop 的 memory system 来说，GRACE-style gating 比单纯的 continuous score 更有吸引力。

---

## 5. 但有一处重要的"不自然"，必须写进 doc

**MemoryAgentBench 并不真的符合标准 GRACE / TCD 的 setting。**

标准 temporal causal discovery 想要的是：一套**固定**变量 `X^1, …, X^d`，观测很多 timestep `t = 1,…,T`。例如温度、气压、风速、湿度 —— 四个变量一直存在，只是值随时间变化。

但 MemoryAgentBench 的 memory 是 chunk：

- chunk 17 在前 16 步**根本不存在**（growing variable set）；
- conversation A 的 chunk 17 与 conversation B 的 chunk 17 **不是同一个变量**（sample-specific variables）；
- 一条 trajectory 可能只有 `T ≈ 32`（short T）。

所以真实 setting 是

```
short T  +  growing variable set  +  sample-specific variables
```

这不是标准 TCD。

> ### 因此 claim 要这样写
>
> **不是**：`Run GRACE on MemoryAgentBench.`
>
> **而是**：`Use GRACE's skeleton-and-gating principle to build a causal-inspired refinement module for MemoryAgentBench.`
>
> 这两个 claim 的差别很大，审稿人会直接盯这一处。

---

## 6. MemoryArena 为什么不一样

MemoryArena 的数据生成过程更接近 Yujia 最初想象的 Agent Memory：

```
Agent acts → gets observation → writes memory → later retrieves memory → acts again → ⋯
```

write / read **真正 interleave**。在目前 survey 过的几个平台里，它是唯一具备这种 multi-session Memory–Agent–Environment loop 的。

所以在这里，`u_t` 才真正有意义 —— 而不是简单的 `W W W W R R R R`。

### 6.1 `u_t` 到底能不能读出来（已核对代码，仅 `run_travel.py`）

这是阶段二的前置问题，结论比预想的好，但有两处要修正。

**架构上，write / read 是显式的。** 记忆系统是一个 HTTP 服务，端点就三个：

```
POST /memory/initialize
POST /memory/add                 ← 写
POST /memory/wrap_user_prompt    ← 读
```

`memory/client.py` 的 `MemoryClient` 只有对应的三个方法。**写和读不在 agent 的思维链里，而在 API 边界上** —— 这比"要从自然语言 trace 里猜"好太多。

**修正一：`u_t` 的时机不是 agent 决定的。** `run_travel.py` 每一轮的顺序由 harness 写死：

```
wrap_user_prompt(query)  →  agent 行动  →  add(action + observation + judgement)
```

即 `R → A → W` 周期重复。我先前说"写入时刻由 agent 自己决定、`u_t` 内生、只能靠 change-point 估" —— **这是错的**。
准确的说法是：**时机是外生且规则的，内生的是内容**（agent 决定往 `add` 里塞什么）。

两个后果，方向相反：

- ✅ **A5（regime 可观测）基本免费** —— 只要在 client 上打点即可，不需要 change-point detection。
- ⚠️ **但 regime 的"丰富度"要打折。** `R A W R A W …` 是周期的，不是我在 §6 开头写的那种自由交错的
  `{observe, write, plan, read, act}`。**动态性不来自 regime 交错，而来自跨 round / 跨 person 的任务语境变化。**
  也就是说 `A_t` 依然是个正当问题（"随任务推进，哪些记忆变得重要"），但论据要换成这一条，不能再拿"regime 丰富交错"当理由。

**修正二：这个 trace 目前没有落盘。** `MemoryClient` 的 payload 只有 `user_id`、`memory_system_name`、`question`/`chunk` ——
**无时间戳、无 session id、无 turn index**。`run_travel.py` 存的是 `generated_plan_{data_idx}.json`
（`metadata` / `all_results` / `scratchpads`）与 `stats_results/usage_stats.json`；
**记忆操作只打到 stdout，不持久化**。

→ 阶段二的第一件事是**给 client 加一层记录**（写/读、轮次、时间、内容哈希）。改动很小，但**必须先做**，否则没有可分析的对象。

**A8（无选择）依然全破**：agent 决定往 `add` 里写什么，这本身就是对内容的选择。§7.3 已说明 UnCLe 的 `Δε` 会在这种数据上误报，所以 selection gate 强制前置。

**成本提示**：代码里有 `time.sleep(60)` 用于等 Mem0 建索引 —— 按轮计的 60 秒惩罚，阶段二排期要算进去。

### 6.2 四个入口全部核对后的 regime 结构

| 入口 | 内层多步循环 | read（`wrap_user_prompt`） | write（`add`） |
|---|---|---|---|
| `run_travel.py` | 无 | 轮首，每轮一次 | 轮尾，每轮一次 |
| `run_math.py` | 无（per subtask） | 轮首 | 轮尾 |
| `run_shopping.py` | **有**，`for turn_idx in range(1, max_rounds+1)` | **整个 episode 只在首轮一次**（`memory_injected` 标志位守住） | `use_step_memory=True` → **内循环每步写**；否则 episode 结束批量写 |
| `run_search.py` | 逻辑在 env server 内，脚本层不可见 | 脚本层无 | 脚本层无（`memory_url` / `memory_system` 作为配置传给 env server） |

### 6.3 ❗ 修正三：「write / read 真正 interleave」这个说法要收窄

`run_shopping.py` 确实有内层多步循环，写入也确实能进内循环：

```python
for turn_idx in range(1, args.max_rounds + 1):
    if memory is not None and not memory_injected:
        prompt = memory.wrap_user_prompt(prompt_source)   # ← 只此一次
        memory_injected = True
    action = agent.act_with_messages(input_messages)
    result = env_client.step(action, ...)
    if use_step_memory and memory is not None:
        for entry in build_memory_entries(...):
            memory.add(entry)                             # ← 每步可写
```

但**读只发生一次**，被 `memory_injected` 守住。所以 shopping 的 episode 内 regime 是 `R W W W W …`，
不是读写交替 —— **在读这一侧，反而比 travel 更不交错**。

**四个入口没有任何一个在 episode 内交替读写。** 准确的表述应当是：

```
MemoryAgentBench:  W^N R^M               —— 全局只有一次 write→read 转换
MemoryArena:       (R … W)(R … W)(R … W)  —— 在 round / episode 粒度上反复交替
```

pairing 的逻辑**依然成立**（反复交替 vs 单次转换，确实是不同的问题形态），
但"真正 interleave"这个说法太强，应改为**"在 round 粒度上反复交替"**。
`A_t` 的论据仍按 §6.1 的修正走：**来自跨 round / 跨 person 的任务语境变化，而非 regime 交错**。

### 6.4 另外三条工程事实

- **`run_search.py` 的记忆操作不在脚本层。** 全部逻辑委托给 env server（脚本只发一次 `run_sequential`），
  所以 §6.1 说的"给 client 打点"对 search **不适用**，得改到 env server 侧。阶段二要按入口分别处理。
- **shopping 有 `backfill_memory_from_artifacts()`**，resume 时会把过去的步骤补写进记忆。
  这会让朴素按调用序还原的 trace 出现**重放写入**，做时序分析前必须先剔除。
- **shopping 的落盘比 travel 好**：`eval_{stem}_step_{N}_{timestamp}.json` 逐 episode 存交互记录，
  另有 `summary.json` / `summary_all.json`。**若阶段二要选一个入口先做，shopping 的可观测性最好，且是唯一有内层多步结构的。**

---

## 7. UnCLe 为什么在这里变得有意思

多数 temporal causal discovery 方法默认

```
G_t = G          (causal graph 永远不变)
```

即：若 `X^1_{t-3} → X^5_t` 存在，就假设整个数据生成过程中都存在。

但 Agent Memory 很可能不是这样。设有一条过去 memory：

> "User's hotel is in Shinjuku."

- 当 `u_t = plan Tokyo transportation` 时，`m_hotel → a_t` 可能非常重要；
- 当 `u_t = solve coding problem` 时，这条 edge **根本不应该 active**。

所以更自然的对象不是 `G` 而是

```
G_t        甚至        G_t = G(u_t, state_t)
```

**GRACE 与 UnCLe 最大的概念差别：**

| | 关心的问题 | 对象 |
|---|---|---|
| GRACE | Which edges **exist**? | `A` |
| UnCLe | Which edges are **active at this time**? | `A_t` |

### 7.1 UnCLe 的机制（已核对论文 + 实现 `etigerstudio/uncle-causal-discovery`）

- **Uncoupler / Recoupler**：参数共享的 TCN autoencoder，把每条单变量序列 `x_i` 映到隐序列 `z_i ∈ ℝ^{T×C}` 再重建。
- **Dependency Matrices**：`Ψ = {Ψ¹,…,Ψ^C}`，每个 `Ψ^c ∈ ℝ^{N×N}`，在各 semantic channel 内做自回归 `ẑ^c_{:,t+1} = σ(Ψ^c ẑ^c_{:,t})`。
  实现里是 `self.var_mat = nn.Parameter(torch.zeros(c_in, c_in, channels, lag).normal_(0, 0.01))`。
- **静态图**：对 channel 做 L2 pooling，`Â_Agg = √( (1/C) Σ_c (Ψ^c)² )`；实现即 `var_mat.squeeze(3).norm(dim=2)`。
- **动态影响**：对变量 `j` 的时间轴做**随机置换**，比较置换前后的预测误差增益
  `Δε^{i,j}_t = max(0, ε'^{i,j}_t − ε_{i,t})`。
  实现即 `X_[i,i,:] = X_[i,i, torch.randperm(X_.shape[2])]`，随后 `error_difference = red_error − full_error`，负值截零。

### 7.2 ⚠️ 一处重要修正：`Ψ` 本身是静态的

前文（及 §8、§9 的表述）把 UnCLe 说成"学习一个随时间变化的图 `G_t`"，**这是过度表述**。

准确的说法是：**UnCLe 学的是一个静态的 `Ψ`（按变量身份索引，训练一次），"动态"完全来自推理期的逐点扰动归因。**
它给出的是每个时刻的 `Δε` 分数矩阵，**不是**一个学到的、由状态生成图的映射。

所以 `G_t = G(u_t, state_t)` 这个写法**不能算作 UnCLe 已经提供的东西** —— 它是我们想要的对象，而 UnCLe 只提供了一个 post-hoc 的时间分辨归因。§9 对照表里"目标结构 = dynamic `G_t`"应读作**我们的目标**，不是 UnCLe 的既有能力。

### 7.3 ❌ 已证伪：扰动 ≠ `do(·)`

先前猜测"UnCLe 的扰动路子形式上接近 D1 的 `do(m_s := m̃)`，可能成为 Layer 1 与 Layer 2 的接口"（当时标注为待验证）。
核对实现后，**这个类比不成立**，三条理由：

1. **扰动的对象不同。** UnCLe 是对某变量**自身时间轴做随机置换**（保边际分布、毁时序结构）；
   D1 是把载体在特定时刻 `s` **赋为常数** `m̃`（切断全部入边、固定取值）。两者语义不同。
2. **作用的层次不同。** UnCLe 扰动的是**已拟合预测器的输入**，量的是那个模型误差的变化 ——
   这是 model-sensitivity / feature-ablation，回答"我的模型有多依赖 `x_j`"。
   D1 量的是**真实过程的介入分布** `P^{do(·)}`，回答"世界里这条通路存不存在"。
3. **最致命的一条：它过不了 confabulation control。**
   在 §selection 的构造里，`y` 只由 `d` 生成、与 `c` 无任何通路，但经 `S=1` 筛选后 `c ⊥̸ y`。
   在被选择的population上拟合的模型**必然会用 `c` 去预测 `y`**，于是置换 `c` 会抬高误差 → `Δε > 0` → **UnCLe 断言一条虚假的边**。
   这正是 Prediction P2 描述的失败模式，而 D1(ii) 就是为拒斥这种情形设计的。

**结论**：UnCLe 的 `Δε` 是关联性的模型归因，不是介入。它不能替代 D1 的介入判据。

**但这个否定结论有用**：它把阶段二的一件事从"可选"变成"必须" ——
若采用 UnCLe，**selection gate 是强制前置的，不是加分项**，否则在 goal-filtered 的 MemoryArena 语料上必然产生幻觉边。

于是：MemoryArena 的优势是**动态交互**，UnCLe 的优势是**动态因果图** —— 在科学问题上对得比较准。

---

## 8. 为什么不交叉配

### MemoryArena + GRACE —— 其实可以，而且应该做 static baseline

这点很重要：**不是** "MemoryArena 只能用 UnCLe"。

但若对整个 trajectory 只学一个 `G`，你实际在问的是"**平均而言**这些 memory dependency 有没有"。而 MemoryArena 更有价值的问题是"**此时此刻**哪些 dependency active"。

极端例子：若 `m_1 → a_t` 只在 10% 的 timestep 里非常重要、其余 90% 完全没用，static graph 要么把它平均掉、要么一直保留，两者都不理想。dynamic graph 才允许它在某些 context 取 1、另一些取 0。

→ 只用 static GRACE，MemoryArena 的额外信息没被充分利用。

### MemoryAgentBench + UnCLe —— 能跑，但卖点浪费

`W^N R^M` 没有丰富的 repeated regime switching。即使让 `G_t` 一直变化，也很难说清这些变化对应什么 meaningful process；最后很可能只得到 `G_write` 和 `G_read` 两块。那就没必要动用一个专门的 dynamic graph method。第一阶段不划算。

---

## 9. 两套 pairing 回答的是两个不同的研究问题

| | MemoryAgentBench + GRACE-style | MemoryArena + UnCLe-style |
|---|---|---|
| 最核心的问题 | Which memories should survive retrieval? | Which memory dependencies are active now? |
| memory 状态 | 基本静态库 + query | 在线不断演化 |
| write / read | phase-separated | interleaved |
| 目标结构 | sparse selection | dynamic `G_t` |
| 方法优势 | clean discrete gating | time-varying edges |
| 最自然输出 | binary memory mask | state-dependent / dynamic mask |
| 工程难度 | 低 | 高 |
| 科学风险 | TCD formulation 不完全匹配 | UnCLe 的 dynamic evidence 还较弱 |

即两个不同难度的 Layer 1：

```
简单版：   retrieved candidates  →  causal refinement  →  mask
完整版：   agent trajectory      →  G_t              →  dynamic causal memory mask
```

---

## 10. 风险是不对称的 —— 但不对称在哪里，需要修正

> UnCLe: *Towards Scalable Dynamic Causal Discovery in Non-linear Temporal Systems*，
> NeurIPS 2025，[arXiv 2511.03168](https://arxiv.org/abs/2511.03168)。以下已对原文核实。

不能因为"理论上漂亮"就把 MemoryArena + UnCLe 当最终答案。UnCLe 的实证覆盖是这样的：

| | 数据集 | 变量数 | 有 causal ground truth？ |
|---|---|---|---|
| **static** 因果发现 | Lorenz96 | `p = {20, 20, 100}` | ✅ |
| | NC8 | 8 | ✅ |
| | FINANCE | 20, 40 | ✅ |
| | fMRI | 15 | ✅ |
| **dynamic** 因果图恢复 | TVSEM（系数每 400 步切换一次） | **2（bivariate）** | ✅ |
| | ND8 | **8** | ✅ |
| 真实交通数据 | METR-LA | 207 sensors | ❌ 仅与真实路网地理比对 |
| | PEMS-BAY | 325 sensors | ❌ 同上 |

即：**static 验到 `d = 100`，但真正 dynamic 的验证只到 `d ≤ 8`。** 唯二的 dynamic ground-truth 数据是一个二元 SEM 和一个 8 变量系统。

限制声明是原文明写的：

> "The primary limitation of our work … is the lack of formal identifiability guarantees. While UnCLe demonstrates strong empirical performance, we do not provide a theoretical proof under which conditions it is guaranteed to recover the true dynamic causal graph."

所以：

```
MemoryArena + UnCLe  =  概念上匹配最好
                     ≠  工程上风险最低
```

反而 MemoryAgentBench + GRACE-style 更容易先拿到结果。

### 10.1 ⚠️ 一处修正：identifiability 缺口不是 UnCLe 独有的

先前的说法是"UnCLe 无 identifiability guarantee，而 GRACE 更稳"，这在 identifiability 这一维上**不成立**。
核对 GRACE 原文 Appendix B，它同样明确排除了这一点：

> "The results provide *qualitative intuition* … but do not constitute identifiability guarantees for the full nonlinear model."

即 **两个候选 estimator 都没有 identifiability 保证**。风险的不对称在别处：

| 维度 | GRACE | UnCLe |
|---|---|---|
| identifiability guarantee | ❌ 无（Appendix B 明确排除） | ❌ 无（Limitations 明确排除） |
| selection soundness（D3 iii） | ❌ 不提供 | ❌ 不提供，且 `Δε` **必然在 selection 上误报**（§7.3） |
| 实证成熟度 | static，验到 `d = 100` | **dynamic 只验到 `d ≤ 8`** |
| 输出可直接当 mask | ✅ Hard Concrete 双峰；但主入口是 stability selection，非单次切 0.5 | ⚠️ `Δε` 是连续分数，需自行离散化 |
| 参数索引方式 | 按边身份 `[N, L+1, N]` | 按变量身份 `[N, N, C, lag]` |
| 公开实现 | `bloomberg/causal-ts`，**GPL-3.0-or-later** | `etigerstudio/uncle-causal-discovery`，**无 license 文件** |
| 代码可复用性 | 库形态，有 docs / tests / CI | 研究代码：模型即 `bin/experimental_utils.py` 里的 `VARP` 类，Python 3.8.10，无包结构 |

**真正的不对称是"实证成熟度"和"输出形式"，不是 identifiability。**

### 10.1.1 一个共同的结构性障碍（两阶段都要处理）

核对两边实现后发现**同一个问题**：

```python
# GRACE
self.log_alpha = nn.Parameter(torch.zeros(num_vars, Lp1, num_vars))          # [cause, lag, effect]
# UnCLe
self.var_mat   = nn.Parameter(torch.zeros(c_in, c_in, channels, lag)...)     # [var, var, channel, lag]
```

**两者的核心参数都按变量身份索引，形状由变量数写死。** 而我们的设定里变量身份跨样本不一致
（conversation A 的 session 17 ≠ B 的 session 17），所以**两个方法都不能直接迁移** —— 不是不优雅，是维度对不上。

两阶段都要做同一件事：**把身份索引的参数摊销成内容条件化的网络**。
这既是必要改造，也说明"principle 而非 run"的措辞在两个阶段**同样适用**，不只是阶段一。

### 10.2 由此产生的、必须主动交代的张力

`causal_memory_formulation.tex` §Positioning 明说，本项目与 memory-agent 文献的区别就在于 **identifiability framing**。而上表显示：**Layer 1 的两个候选 estimator 都不提供 identifiability。**

这不是选型失误，但必须先手说清楚，否则 Yujia 会直接问穿：

> **Layer 1 的 estimator 是工程选择，不承担 identifiability 论证；identifiability 由项目自身的 Layer 2 结果（D3、Conjecture 1）承担。**
> 二者是分工，不是同一个主张被稀释。

反过来说，这也提示了一个**正面的机会**：如果 Layer 2 的可辨识性结论能反过来给"什么条件下 mask 可信"提供保证，那就正好补上 GRACE / UnCLe 都缺的那一块 —— 这可能比单纯"把某个 TCD 方法接到 memory 上"更像一个贡献。

---

## 11. 推荐顺序：两个阶段，不是两个平行项目

### 阶段一 —— MemoryAgentBench + GRACE-style refinement

先回答最基本的问题：

> 在 native similarity retrieval 已经产生候选的情况下，加入 temporal / causal structure，能不能进一步产生更好的 memory mask？

**评测路径**：LongMemEval 带 gold evidence 字段 `answer_session_ids`（甚至有 turn 级 `has_answer`），因此原则上可以直接测

```
Mask Precision / Recall / F1
```

而不必一开始就烧大量 LLM calls。

> ⚠️ **但这条路径不是免费的。** 核对代码后发现：MemoryAgentBench 的 loader
> （`utils/eval_data_utils.py`）**没有保留任何 session id**，且 `chunk_text_into_sentences()`
> 返回的是裸字符串、**provenance 全部丢失**。所以 gold session → gold chunk 的对齐要自己补。
> 三处具体缺口与补法见 **`stage1-experiment-design.md`**。

**正信号**：`causal mask  >  similarity / recency`。

### 阶段二 —— MemoryArena + dynamic causal structure

若阶段一有正信号，再升级去回答更深的问题：

> 当 Agent 自身的 state / action / regime 不断变化时，memory dependency 是否也应该动态变化？

这时 UnCLe 才真正发挥价值。

---

## 12. 给 Yujia 的 doc 里该怎么写

**不要写死成：**

```
Task1 method: GRACE
Task1 method: UnCLe
```

**更准确的表述：**

```
MemoryAgentBench:  GRACE-style sparse causal refinement  as the first practical route
MemoryArena:       UnCLe-style time-resolved causal discovery  as the dynamic extension
```

这样既说清了为什么选，又不会被误读成"这两个现成方法拿来直接跑就已经适配 Agent Memory"。

---

## 附：两份文档的关系

| | `memory-vs-agent-memory.md` | 本文 |
|---|---|---|
| 层次 | Layer 2 判据 | Layer 1 方法选型 |
| 结论 | 两个基准**不能**进 E1 的判据链 —— 真实数据没有 ground-truth latent，值对应（MCC）无从计算 | 两个基准**可以**做 Layer 1，且各配一种方法 |

两者不冲突，差别恰在**有没有可评的真值**：

- Layer 1 的产物是 mask，而 mask **有** gold evidence 可评（LongMemEval 的 `answer_session_ids`）→ 所以 Layer 1 能先在真实数据上跑出结果。
- Layer 2 的产物是 latent 的值对应，真实数据**没有**真值 → 所以 Layer 2 必须留在合成数据（E1）。

这也解释了为什么推荐顺序是"先 Layer 1 真实数据、后 Layer 2 合成数据"，而不是反过来。
