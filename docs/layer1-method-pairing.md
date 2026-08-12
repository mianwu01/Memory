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

GRACE **不是**"给它一大堆变量就端到端发现所有 causal edges"。它是 two-stage：

```
skeleton  →  neural refinement
```

1. 第一阶段：找一个 **high-recall candidate skeleton** —— 宁可把真 edge 基本都留下，同时夹杂大量 false positives。
2. 第二阶段：给每条候选 edge 一个 **Hard Concrete gate**（`z_ij^(k) ≈ 0 or 1`），再用 **L0 sparsity** 把错误候选删掉。

即

```
candidate edges  →  sparse binary edges
```

**关键 ablation**：去掉 skeleton 后，在 `d = 50` 时直接把约 **15,000 条**候选边交给 gates，而真实边只有约 **100 条**，结果 `F1 < 0.02`。

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

反过来，CUTS+ 的问题是：continuous graph scores 的 ranking 可能不错，但 threshold 之后不一定形成干净的 binary graph —— GRACE 的 pair-level evaluation 下，CUTS+ 到 `d = 100` 的 thresholded F1 非常低。

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

所以在这里，`u_t` 才真正有意义：

```
u_t ∈ { observe, write, plan, read, act }
```

而不是简单的 `W W W W R R R R`。

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

## 10. 风险是不对称的

不能因为"理论上漂亮"就把 MemoryArena + UnCLe 当最终答案。读完 UnCLe 后的实际情况：

- static graph 有 ground truth 到 `d = 100`；
- 但**真正 dynamic graph 的验证只有 `d ≤ 8`**；
- 207 / 325 变量的交通数据**没有 causal ground truth**；
- 作者自己明确承认**没有 identifiability guarantee**。

所以：

```
MemoryArena + UnCLe  =  概念上匹配最好
                     ≠  工程上风险最低
```

反而 MemoryAgentBench + GRACE-style 更容易先拿到结果。

### 10.1 一处需要主动交代的张力（本文补充）

UnCLe "no identifiability guarantee" 这一条，和本项目的立身之本正面相撞：`causal_memory_formulation.tex` 的 §Positioning 明说，与 memory-agent 文献的区别就在于 **identifiability framing**。把一个自称无 identifiability 保证的方法放在 dynamic 主线上，Yujia 大概率会直接问穿。

建议在 doc 里先手说明：**UnCLe 是 estimator 的选择，identifiability 的论证由项目自身的 Layer 2 结果承担，不由 UnCLe 提供。** 两者是分工，不是同一件事被稀释。

---

## 11. 推荐顺序：两个阶段，不是两个平行项目

### 阶段一 —— MemoryAgentBench + GRACE-style refinement

先回答最基本的问题：

> 在 native similarity retrieval 已经产生候选的情况下，加入 temporal / causal structure，能不能进一步产生更好的 memory mask？

**评测路径（关键优势）**：LongMemEval 带 gold evidence 字段 `answer_session_ids`（`longmemeval` 已在 MemoryAgentBench 的数据集清单内），因此可以直接测

```
Mask Precision / Recall / F1
```

而不必一开始就烧大量 LLM calls。

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
