# 阶段一实验设计：MemoryAgentBench + GRACE-style causal refinement

> 承 `layer1-method-pairing.md` §11 阶段一。
> 代码事实均已对 `HUST-AI-HYZ/MemoryAgentBench` main 分支核实，引用处标了文件与函数名。

---

## 0. 一句话

在 native retriever 已经给出候选集 `S` 的前提下，插入一段 causal refinement 得到 `M ⊆ S`，
用 LongMemEval 的 gold evidence 直接评 mask 的 Precision / Recall / F1 —— **主实验全程不需要 LLM calls**。

---

## 1. 现有数据流（已核对代码）

```
main.py
  create_agent_and_fetch_data()  →  all_context_chunks, all_query_answer_pairs
  │
  ├─ for context_index, (context_chunks, query_answer_pairs) in enumerate(zip(...)):
  │     initialize_and_memorize_agent(..., context_chunks, context_index)
  │       └─ initialization.py::_memorize_context_chunks
  │            for chunk in context_chunks:
  │                agent.send_message(chunk, memorizing=True)        ← 写入阶段 W^N
  │
  │     for query_data in query_answer_pairs:
  │         query, answer, qa_pair_id = unpack_query_data(query_data)
  │         agent.send_message(query, memorizing=False, ...)          ← 读取阶段 R^M
  │           └─ agent.py::_handle_bm25_rag / _handle_embedding_rag / _handle_hippo_rag
  │         save_results_to_file()
```

**chunk 从哪来**（`conversation_creator.py::get_chunks`）：

```python
all_context_chunks = [
    chunk_text_into_sentences(context, chunk_size=self.chunk_size)
    for context in self.contexts
]
# 下游断言：assert isinstance(chunks[0][0], str)   ← chunk 是裸字符串
```

**注入点**（`agent.py::_handle_bm25_rag`，另两个分支同形状）：

```python
bm25_documents      = self.bm25_retriever.get_relevant_documents(retrieval_query)
retrieval_context   = [f"{doc.page_content}\n" for doc in bm25_documents]      # ← S
retrieval_memory_string = "\n".join([f"Memory {i+1}:\n{text}" ...])
ask_llm_message     = retrieval_memory_string + "\n" + message
```

---

## 2. 挂载点：一行

```python
retrieval_context = [f"{doc.page_content}\n" for doc in bm25_documents]        # S
+ retrieval_context = causal_refine(retrieval_context, query=message, ctx=...)  # M ⊆ S
retrieval_memory_string = "\n".join([f"Memory {i+1}:\n{text}" ...])
```

三个 RAG 分支形状一致。**先只改 `_handle_bm25_rag`** —— 它不依赖外部服务（HippoRAG / Zep / Mem0 都要额外 key），最可控。

---

## 3. 三个必须先补的管线缺口

这是本设计最重要的部分：**"LongMemEval 有 gold evidence 所以可以直接评"这条路径，在 MemoryAgentBench 里并不是开箱即用的。**

### 缺口 1 — gold label 根本不在 MemoryAgentBench 里

`utils/eval_data_utils.py` 保留的 metadata key 只有：

```
question_dates, question_types, question_ids, previous_events, qa_pair_ids, demo, source
```

**没有 `answer_session_ids`，没有任何 session id。**

原版 LongMemEval（[xiaowu0162/LongMemEval](https://github.com/xiaowu0162/LongMemEval)，ICLR 2025）的 schema 是有的：

| 字段 | 含义 |
|---|---|
| `question_id` | 问题唯一 id |
| `haystack_session_ids` | 历史 session 的 id 列表 |
| `haystack_sessions` | 历史 session 的实际内容 |
| **`answer_session_ids`** | **evidence session 的 id 列表 ← gold** |
| turn 内 `has_answer: true` | **turn 级 gold，比 session 级更细** |

**补法**：用被保留下来的 `question_ids` join 回原版 LongMemEval。
**风险**：必须先确认两边 id 是同一套命名 —— 见 §8 的 S1。

### 缺口 2 — `haystack_sessions` 在数据里，但 loader 没读

HF dataset card 显示 `metadata` 字典含 `demo / haystack_sessions / keypoints / previous_events / qa_pair_ids`，
但 `eval_data_utils.py` 的保留清单里没有它。**加一个 key 即可，改动最小。**

### 缺口 3 — chunk 的 provenance 全部丢失（最要紧）

`chunk_text_into_sentences()` 返回 `List[List[str]]`，**纯字符串**：无 offset、无 session 归属、无任何位置元信息。
下游还有 `assert isinstance(chunks[0][0], str)` 把这个形状钉死了。

**后果**：即便拿到了 gold session id，也无法回答"哪些 chunk 属于 gold session" —— mask 的正例标签算不出来。

两条补法：

- **(A) 保守**：改 chunk 函数返回 `(text, source_session_id, char_span)`，下游取 `.text`，保持断言兼容。改动局部，与原 benchmark 的 chunk 划分完全一致、可比。
- **(B) 干净**：绕过 sentence chunking，**直接按 session 边界切 —— 一个 session = 一个 chunk**。于是 `chunk id ≡ session id`，gold 直接可用。

**建议先做 (B)**，理由见 §4。(A) 作为可比性对照保留，见附录 Q_b。

---

## 4. 变量定义：先做 session 级

理由三条：

1. **gold 本来就是 session 级**（`answer_session_ids`）→ 粒度天然对齐，省掉一整层易错映射。
2. 直接回避 §5 里"变量身份跨样本不一致"问题的一半。
3. LongMemEval_S 每条约 40–50 个 session → `N ≈ 50`。而候选集 `|S| = top-k ≈ 10`。
   对比 GRACE ablation 里 `d = 50` 时的 ~15,000 候选边 —— **我们这个尺度对 gating 极其友好**，
   这也正是"retriever 充当 skeleton"这个 hypothesis 想要的效果。

turn 级 `has_answer` 留作后续更细粒度的 ablation。

---

## 5. 变量集不标准，怎么处理

`layer1-method-pairing.md` §5 已指出：这里是 `short T + growing variable set + sample-specific variables`，不是标准 TCD。具体处理：

- **不跨样本共享变量身份。** 每个 question 的 haystack 独立成图 —— "每个样本一张图"，而不是"所有样本共用一张图"。
- 因此 gate 的参数**不能**按边索引。必须改成 **content-conditioned gate**：输入 `(query 表示, memory 表示, 位置/时间特征)`，输出一个标量 logit，再走 Hard Concrete。**参数在样本间共享，变量身份不共享。**

**这一点已在参考实现层面确认**（`causalts/grace/gated_discovery.py`）：

```python
self.log_alpha = nn.Parameter(torch.zeros(num_vars, Lp1, num_vars))   # [cause, lag, effect]
nn.init.constant_(self.log_alpha, -0.5)                               # 初始偏关
```

gate 是**每条边一个自由标量参数**，形状直接由变量数决定。所以在"变量身份跨样本不一致"的设定里，这套参数化**根本无法迁移** —— 不是不优雅，是维度对不上。

> 因此这是对 GRACE 的**实质改造**，不是直接调用 —— 与 pairing doc §5 的措辞红线一致：
> *Use GRACE's skeleton-and-gating principle to build a causal-inspired refinement module.*

**一个现成的接入点**：参考实现的 `_NonlinearEncoder` 是"共享 MLP + 每个 `(cause, lag)` 一个可学 embedding（dim 8）"。
我们要做的替换很自然 —— **把那个按身份索引的可学 embedding，换成该条 memory 的内容 embedding**。
结构不动，只是 embedding 的来源从"查表"变成"编码内容"。这比"另起炉灶"好讲得多。

---

## 6. refinement 模块的最小形状

**输入**：query `q`；候选集 `S`（`|S| ≈ 10`）；每条 memory 的 `(text, session_id, 时间戳/位置)`

```
编码：  复用现有 embedding retriever 的 encoder，不另训
gate：  log α_i = MLP([e_q ; e_i ; e_q ⊙ e_i ; pos_i])  →  Hard Concrete  →  z_i ∈ [0,1]
聚合：  ŷ = Σ_i z_i · h_i                       ← 对应 GRACE 的 per-effect gated aggregation
解码：  (μ, log σ) = MLPDecoder(ŷ)
损失：  NLL  +  λ · Σ_i P(z_i ≠ 0)
输出：  M = { i : z_i > threshold }
```

### 6.1 参考实现的具体形状（`causalts/grace/gated_discovery.py`，已核对）

可直接照搬的部分：

| 组件 | 参考实现 | 我们 |
|---|---|---|
| Hard Concrete 采样 | `u ~ U(ε, 1−ε)`；`s = sigmoid((log u − log(1−u) + log α)/τ)`；`z̄ = s(ζ−γ)+γ`；`z = clamp(z̄, 0, 1)` | 照搬 |
| 超参 | `τ` = temperature，`γ = −0.1`，`ζ = 1.1`（Louizos et al. 2018 原值） | 照搬 |
| L0 惩罚 | `P(z≠0) = sigmoid(log_alpha − temperature · log(−γ/ζ))`，求和后乘 `lambda_l0 * _l0_scale` | 照搬 |
| Decoder | `_MLPDecoder`：每个 effect 一个独立 MLP，输出 `(μ, σ)`，默认 2 层 × 64，SiLU | 我们只有一个 effect（answer），退化成单个 decoder |
| Encoder | 线性 + 基展开 `[x, x², |x|]`，或 `_NonlinearEncoder`（共享 MLP + per-(cause,lag) embedding，dim 8，hidden 32） | **替换 embedding 来源**，见 §5 |

**不适用于我们的部分**：损失里还有第三项 `lambda_lag_group · Σ max(0, lags_per_pair − max_lags_per_pair)` ——
这是约束"同一对变量占用的 lag 数"的，session 级设定里没有 lag 维度，**直接去掉**。

### 6.2 ⚠️ 修正："0.5 天然阈值"要打折扣

论文报告 gate 值双峰、0.5 可直接切。但**参考实现的主入口不是单次训练**：

```
run_stability_selection(df, max_lag, lambda_grid, n_subsamples, stability_threshold, use_ci_skeleton)
    → GraceResult（binary graph + stability scores）
run_cdnots_gated(df, max_lag, skeleton, gate_threshold, lambda_cv)
    → 单次 gated refinement
StabilitySelector.run() / .get_graph(threshold)
```

也就是说，实际推荐用法是 **λ 网格 × 子采样的 stability selection**，最终靠 stability score 过阈值 —— 不是一次训练后切 0.5。

对我们的影响两条：
1. **成本要重估**（见 §10 修正）。
2. 设计上二选一：**要么照做 stability selection**（更贴原方法、更稳），**要么明确声明我们简化为单次训练 + 0.5**，并把"双峰是否复现"作为这个简化是否成立的检验（§11 第 7 步）。
   建议先做后者（便宜），若双峰不干净再上 stability selection。

---

## 7. 评测

### 主指标（不烧 LLM）

- **Mask Precision / Recall / F1**，正例 = `answer_session_ids`
- **压缩率** `|M| / |S|`

### 基线

| # | 基线 | 作用 |
|---|---|---|
| 1 | similarity top-k（即 `S` 本身） | native 现状；也是 Recall 上界 |
| 2 | recency top-k | 最常见的廉价启发式 |
| 3 | **random top-`|M|`** | **控制 `|M|` 相同**，隔离"是不是只是变少了" |
| 4 | oracle（只给 gold session） | 下游性能上界 |

> **关键**：必须在**相同 `|M|`** 下比 causal refinement 与 random / similarity。
> 否则分数差可能纯粹来自候选数变化，而不是选得更准。

### 次指标（要烧 LLM，放第二轮）

下游 QA accuracy，验证 mask 变好确实转化成答案变好。这一步才需要 `llm_based_eval/longmem_qa_evaluate.py`。

---

## 8. 两个 sanity check —— 先跑，很便宜

### S1：join 命中率

`question_ids`（MemoryAgentBench）↔ `question_id`（原版 LongMemEval）的匹配率。
**低于约 95% 就先别往下做**，先搞清楚 MemoryAgentBench 重构时改了什么。

### S2：native retriever 的 Recall 上界 ← 最重要

native top-k 的 `S` 对 gold session 的 recall 是多少？

这一条**直接决定整个 hypothesis 成不成立**：GRACE 要求 skeleton 是 **high-recall** 的。
如果 top-10 的 recall 只有 0.6，那 refinement 最多提 precision，recall 只会更低 ——
"retriever ≈ skeleton" 这个类比在这里就不成立，必须先把 k 调大。

> **S2 应当第一个跑。** 它比任何模型实现都更早地决定这条路走不走得通。

---

## 9. 通过 / 失败判据

| 结果 | 判定 | 下一步 |
|---|---|---|
| 相同 `|M|` 下 mask F1 显著优于 similarity 与 random，且 Recall 掉幅可接受 | **通过** | 进第二轮下游 QA |
| precision 明显提升但 recall 掉太多 | **有条件通过** | 调 λ，报完整 precision–recall 曲线 |
| gate 不呈双峰，或 F1 不优于 random | **失败** | 先上调 top-k（让 `S` 更大、更像 skeleton）再试一次；仍失败则这条 pairing 不成立，如实记录 |

---

## 10. 成本

| 步骤 | 成本 |
|---|---|
| S1 / S2 | 分钟级，纯数据处理 |
| 缺口 2 / 3 的代码改动 | 小时级 |
| 主实验（单次训练版） | encoder 前向 + 一个小 MLP，单卡小时级 |
| 主实验（stability selection 版） | **× `|λ grid|` × `n_subsamples`** —— 见 §6.2，先别默认走这条 |
| **LLM calls** | **主实验全程 0**；仅 §7 次指标那一轮需要 |

**许可提醒**：参考实现 `bloomberg/causal-ts` 是 **GPL-3.0-or-later**。照抄或改写其代码会带上 copyleft。
若只按论文与本文的公式自行实现，则不受影响 —— 鉴于我们本来就要改 gate 参数化（§5），**建议自行实现，只把它当对照读**。

---

## 11. 分步 checklist

1. [ ] **S2**：native retriever 对 gold session 的 recall@k（k 扫 5 / 10 / 20 / 50）← 先跑这个
2. [ ] **S1**：`question_ids` join 命中率
3. [ ] 缺口 2：loader 保留 `haystack_sessions` / `haystack_session_ids`
4. [ ] 缺口 3(B)：按 session 边界切 chunk，令 `chunk id ≡ session id`
5. [ ] 落地 gold mask，跑通基线 1–4 的 mask P/R/F1（此时尚无 refinement，先出纯基线表）
6. [ ] 实现 content-conditioned Hard Concrete gate
7. [ ] 训练；**报 gate 值分布，看是否复现双峰**
8. [ ] 主结果表 + 相同 `|M|` 对照
9. [ ] （第二轮）下游 QA accuracy

---

## 附：未决问题

**Q_a** — MemoryAgentBench 重构 longmemeval 时是否改动过 session 内容？若改过，join 回原版拿到的 gold 可能对不上。→ S1 顺带验。

**Q_b** — 若走 (B) 按 session 切 chunk，`chunk_size` 这个超参就失效，与原 benchmark 的 RAG 基线不再严格可比。要不要同时保留 (A) 跑一组可比实验？

**Q_c —— 已解决（查阅参考实现后）。**

原先的顾虑是：`L_task` 用下游 answer 的 NLL 就得烧 LLM，用"是否命中 gold session"做监督又会退化成有监督分类器，
"causal" 的成分消失；当时以为需要另行设计一个自监督目标。

**其实 GRACE 自己的 `L_task` 就是自监督的**，不需要任何外部标签：

```
Loss = NLL + λ_L0 · Σ P(z ≠ 0) + λ_lag_group · (…)
NLL  = sq_err / (2σ²) + log σ + 0.5·log(2π)
target = obs[..., -1]                    ← 当前时刻的 effect 变量值
```

即：**用 gated 聚合后的 causes 去预测 effect，预测误差就是任务损失。** 没有标签，纯 self-supervised。

搬到 memory 场景的对应写法：

```
causes  = 候选集 S 里各条 memory 的编码 h_i
gate    = z_i
effect  = 该 query 的 answer 表示（或 answer span 的编码）
L_task  = NLL of  decode( Σ_i z_i · h_i )  →  answer 表示
```

**既不需要 LLM calls，也不需要 gold session 标签** —— gold 只用在**评测**，不进训练。
这样"稀疏选择由预测目标驱动"这层与 GRACE 完全同构，路线名副其实的问题随之消失。

> 剩下的唯一设计选择：effect 用 answer 的 embedding，还是用 answer token 的 NLL（后者要跑 LLM）。
> 建议先用 embedding，把 LLM 完全留到 §7 的次指标那一轮。
