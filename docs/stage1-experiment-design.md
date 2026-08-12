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
- 因此 gate 的参数**不能**按 `(i, j)` 索引（GRACE 原版是这么做的）。必须改成 **content-conditioned gate**：输入 `(query 表示, memory 表示, 位置/时间特征)`，输出一个标量 logit，再走 Hard Concrete。**参数在样本间共享，变量身份不共享。**

> 这是对 GRACE 的**实质改造**，不是直接调用 —— 与 pairing doc §5 的措辞红线一致：
> *Use GRACE's skeleton-and-gating principle to build a causal-inspired refinement module.*

---

## 6. refinement 模块的最小形状

**输入**：query `q`；候选集 `S`（`|S| ≈ 10`）；每条 memory 的 `(text, session_id, 时间戳/位置)`

```
编码：  复用现有 embedding retriever 的 encoder，不另训
gate：  α_i = MLP([e_q ; e_i ; e_q ⊙ e_i ; pos_i])  →  Hard Concrete  →  z_i ∈ [0,1]
损失：  L_task  +  λ · L0
输出：  M = { i : z_i > 0.5 }
```

沿用 GRACE 的解析 L0：`P(z ≠ 0) = sigmoid(log α − τ log(−γ/ζ))`，以及 **0.5 天然阈值**。

> GRACE 原文报告 gate 值呈清晰双峰、无需 post-hoc threshold tuning。
> **这个双峰在 memory 场景是否复现，本身就是一个值得单独报告的结果**（见 §11 第 7 步）。

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
| 主实验 | encoder 前向 + 一个小 MLP，单卡小时级 |
| **LLM calls** | **主实验全程 0**；仅 §7 次指标那一轮需要 |

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

**Q_c**（最需要想清楚）— 损失里的 `L_task` 若用下游 answer 的 NLL，就必须跑 LLM，与"主实验不烧 LLM"冲突。
替代方案是直接用"是否命中 gold session"做监督 —— 但那样 refinement 就退化成一个**有监督的相关性分类器**，
"causal" 的成分基本消失。

> 这不是工程细节，是这条路线**是否名副其实**的问题。建议在动手前先定：
> 是老实承认阶段一只是"causal-inspired 的稀疏选择"，还是要设计一个不依赖 gold 的自监督 `L_task`
> （例如预测被 mask 掉之后对后续 memory 的重建误差）。前者诚实但贡献弱，后者更贴 causal 但要多一轮设计。
