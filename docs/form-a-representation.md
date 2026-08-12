# Form A：representation 与 graph-to-mask mapping

> 承 `task1-candidate-methods.md`。本页补的是那份文档缺掉的一座桥：
> `text session → X_t` 与 `G → C_t` 到底怎么定义。
> 所有代码事实已核对 `HUST-AI-HYZ/MemoryAgentBench` 与 `bloomberg/causal-ts`。

---

## 0. 先记两处已作废的说法

| 作废的说法 | 为什么错 |
|---|---|
| "3000 chunks 正是 500–5000 variables 区间" | **类型错误。** chunk 是按顺序 `send_message(chunk, memorizing=True)` 喂进去的，是**时间步**不是变量。3000 chunk 是 `T≈3000`，不是 `d≈3000`。而且 chunk 当变量填不出 `X` —— chunk 17 在前 16 步不存在。 |
| "用 similarity prefilter 顶替 GRACE 的 skeleton" | **类型不匹配。** GRACE 的 skeleton 是 `S ∈ {0,1}^{d×d×(L+1)}`，是**候选边**；top-200 是**候选记忆项**。真要换，替代物必须也产出 candidate-edge tensor。 |
| "MemoryAgentBench 零环境搭建" | README 要求 conda Python 3.10.16 + requirements，且 HippoRAG / Cognee / Letta 有依赖冲突。正确说法是"比 MemoryArena 轻得多"（一套环境 vs 四套环境 + 记忆服务 + 多个外部 key）。 |

---

## 1. 完整的链

```
Session_t  --[state extraction]-->  (X_t, U_t, P_t)
X_{1:T}    --[GRACE]------------->  G[c, ℓ, e]
q          --[target parser]----->  Y_q ⊆ {1..d}
(G, Y_q, t_q) -------------------->  A_q   (time-indexed causal ancestors)
A_q        --[provenance P]------>  S_q   (source sessions)
C_q(s) = 1[s ∈ S_q]              -->  M_q^causal = C_q ⊙ M
```

三个抽取产物：

- **`X_t ∈ R^d`** —— 固定 schema 的记忆状态
- **`U_t ⊆ {1..d}`** —— 本 session 更新了哪些槽位
- **`P_t^j`** —— 槽位 `j` 的当前值**由哪个 session 写入**（provenance 指针）

### 1.1 状态持续（关键）

```
X_t^j = v_t^j          若槽位 j 在 t 被更新
      = X_{t-1}^j      否则
```

只有加了这条，每个时间步才真的拥有**同一套固定变量**，`X ∈ R^{T×d}` 才成立。

> **这不是新机制。** 它就是 `causal_memory_formulation.tex` 里 write–hold–read 模体的 **hold 段**：
> `m_t = m_{t-1} + σ ε_t`。Form A 的持续规则是它 `σ = 0` 的离散版本。
> 也就是说 Layer 1 的这个 representation 和 Layer 2 的模体是**同一个对象**，不是两套东西。

### 1.2 为什么必须要 provenance

反例：`hotel_city` 在 session 3 写成 Boston，session 20 写成 Tokyo，query 在 session 50。

若只按"祖先槽位被更新过的 session 全保留"，session 3 和 20 都会留下。但当前有效状态是 Tokyo，
session 3 是**被覆盖掉的旧值**。所以必须经 `P_t^j` 回溯到**真正供给了当前值的那个 session**。

### 1.3 `Y_q` 是集合，不是单个 `e*`

LongMemEval 的问题类型有六种（已核对）：
`single-session-user`、`single-session-assistant`、`single-session-preference`、
`temporal-reasoning`、`knowledge-update`、`multi-session`，外加 abstention（`question_id` 带 `_abs` 后缀）。

像"我搬到 Tokyo 之后换的第一份工作是什么"同时依赖 location / employment / 时序，
所以目标是 `Y_q ⊆ {1..d}`，取 `An*(Y_q)`。

> 这与 `causal_memory_formulation.tex` 的 `F_t(Y)` 定义一致 —— 那里 `Y` 本来就是**一组**任务变量。

---

## 2. 尚欠的定义：`x_t^j` 到底存什么

GRACE 的 decoder 是**高斯**的（已核对源码）：

```python
# _MLPDecoder: 每个 effect 一个独立 MLP，输出 (mu, sigma)
NLL = sq_err / (2*sigma**2) + log(sigma) + 0.5*log(2*pi)
```

所以 `hotel_city = "Tokyo"` 这类 categorical 值**不能原样塞进去**。三个选项，学到的东西不同：

| 选项 | 定义 | 学到的是什么 | 代价 |
|---|---|---|---|
| **(i) 更新指示** | `x_t^j = 1[槽位 j 在 t 被更新]` | **"哪类事实的更新事件预测哪类事实的更新事件"** —— 是事件结构，不是内容依赖 | 最便宜，无需任何表示决策 |
| (ii) 标量编码 | `x_t^j =` 值的标量编码 | 内容依赖 | categorical 编成 1,2,3 会**制造假的序关系**；只对真正数值/序数型槽位（年龄、日期、计数）成立 |
| **(iii) 向量** | `x_t^j ∈ R^k`（值的 embedding） | 内容依赖 | 已不是 GRACE 的 scalar formulation，需改架构 |

**(iii) 比听起来便宜。** GRACE 的 encoder 本来就是 per-`(cause, lag)` 的线性投影：

```
h_{c,ℓ} = W_{c,ℓ} x^c_{t-ℓ} + b_{c,ℓ}        （投到 H = 64）
```

把标量→64 的线性层换成 `k`→64，**其余（gate、L0、聚合、decoder）完全不动**。
`_NonlinearEncoder` 那条路（共享 MLP + per-(cause,lag) embedding, dim 8）改动更小。

**建议顺序**：先做 **(i)** 当 v0 —— 它不需要任何表示决策，且能直接回答"更新事件结构里到底有没有信号"；
若 (i) 有信号但太粗，再上 **(iii)**。**(ii)** 只用于确实是数值/序数的那部分槽位。

---

## 3. ⚠️ `T` 的问题比预想的严重（新核实）

### 3.1 MemoryAgentBench 只装了 S，没有 M

`configs/data_conf/Accurate_Retrieval/LongMemEval/` 下只有两个文件：

```yaml
# Longmemeval_s.yaml
dataset: Accurate_Retrieval
chunk_size: 4096
context_max_length: 150000
sub_dataset: longmemeval_s_-1_500
max_test_samples: 500
generation_max_length: 50

# Longmemeval_s_star.yaml
context_max_length: 400000
sub_dataset: longmemeval_s*
max_test_samples: 5
```

**没有 `longmemeval_m`。**

### 3.2 默认配置下 `T` 差一个数量级

| 配置 | `context_max_length / chunk_size` | ≈ chunk 数 |
|---|---|---|
| `Longmemeval_s` | 150,000 / 4096 | **≈ 37** |
| `Longmemeval_s_star` | 400,000 / 4096 | **≈ 98** |

而 GRACE 的合成实验是 `T ∈ {300, 500, 1000, 2000}`。

所以差距不是"50 vs 500"，是 **"37 vs 300+"**。

降 `chunk_size` 能把 T 抬上去（150k / 512 ≈ 293），但那样 chunk 就不再与 session 对齐，
gold evidence 的对齐就断了。

**结论：改用 LongMemEval_M（约 500 sessions/history）不是优化项，是必需项** ——
但它**不是免费的**：要自己把 `longmemeval_m.json` 拿进来并写一份新的 data config。
loader 支持本地文件（`load_data_localtxt`），所以可行，只是要算进工作量。

### 3.3 优先顺序（采纳批评意见）

1. **首选 LongMemEval_M**，`T ≈ 500`，正好落在 GRACE 验证过的区间
2. 其次找 MemoryAgentBench 里天然有长 sequential interaction 的任务
3. 最后才考虑 multi-episode estimation / 摊销（ACD）
4. **不要把互不相关的 conversation 首尾拼成一条序列** —— 那比普通的 regime shift 强得多，
   GRACE 的基础形式化是平稳多元时间序列，加个 regime indicator 也未必能把"世界彻底 reset"合理化

### 3.4 一条数据污染风险

HF 上的 `xiaowu0162/longmemeval` **已废弃**，替代为 `longmemeval-cleaned`，理由是
*"removes noisy history sessions that interfere with answer correctness"*。

MemoryAgentBench 打包的应是旧版。若那些 noisy session 会干扰答案正确性，
**基于 gold evidence 的 mask 评测就可能被污染**。跑之前要确认用的是哪一版。

---

## 4. scalability 该怎么讲

Form A 下 `d = 槽位数 ≈ 20–100`，不是几千。所以在 agent 实验里，**可扩展性不再是瓶颈**。

但这不代表 Yujia 的要求作废 —— 应当把两件事拆开：

| 实验 | `d` | 证明什么 |
|---|---|---|
| **Agent 实验** | 真实语义槽位（20–100） | causal structure 改善 memory selection / QA |
| **合成实验** | 100 / 500 / 1000 / …（模拟数据，成本低） | causal discovery 模块**本身**可扩展 |

这比硬说"3000 chunks = 3000 variables"健康得多，而且合成那半正是 Yujia 自己建议过的做法。

---

## 5. 下一步：先手工构造，再写 extractor

**不要立刻写代码。** 应当先拿 3–5 个**真实** LongMemEval 实例，手工写出

```
X_t , U_t , P_t , Y_q , A_q , C_q
```

并检验这套形式化能否自然覆盖全部六种 question type ——
尤其 `knowledge-update`（考 provenance）与 `temporal-reasoning`（考 lag 语义）。

- 若手工都能表示得自然 → 再写 extractor、再接 GRACE。
- 若手工已经很别扭 → 说明 **semantic-slot 不是正确的 Layer-1 observable state**，
  该换 representation，而不是继续调 GRACE。

**当前阻塞**：还没拿到真实实例。HF 的 dataset viewer 对该数据集报 `ConfigNamesError`，
原始 repo 的数据需单独下载。需要先取得 `longmemeval_m.json`（或 cleaned 版）才能做这一步。

---

## 6. 真实数据上的手工构造（已完成）

数据：`xiaowu0162/longmemeval-cleaned` → `longmemeval_s_cleaned.json`（277 MB，500 实例）。

### 6.1 数据的真实形状

| 量 | 值 |
|---|---|
| 实例数 | 500 |
| **sessions / instance** | min 38, **中位 48**, mean 47.7, max 62 |
| **evidence sessions / instance** | min 1, **中位 2**, mean 1.90, max 6 |
| turns / session | 中位 12, mean 10.3, max 132 |
| haystack 是否按时间升序 | **500/500 全部升序** → session 下标 ≡ 时间步 ✅ |

题型分布：`multi-session` 133、`temporal-reasoning` 133、`knowledge-update` 78、
`single-session-user` 70、`single-session-assistant` 56、`single-session-preference` 30；abstention 30。

> **正例极稀疏：1.9 / 47.7 ≈ 4%。** 任何 mask 指标都要在这个先验下读。

### 6.2 三个真实实例的 Form A 构造

**(a) knowledge-update `6a1eabeb`** —— Q: 我的 5K 个人最好成绩是多少？A: 25:50
- session #19（05/23）："personal best … 27:12"
- session #39（05/30）："hoping to beat my personal best time of 25:50"
- Form A（带 provenance）：`X^{pb_5k}` 在 t_q 的值 = 25:50，`P = #39` → **`C_q = {39}`**
- **gold = {19, 39}**

→ **provenance 精化版本会漏掉 #19，recall 0.5，即便因果模型完全正确。**
gold 标的是"提到该事实的所有 session"，不是"最小充分集"。

**(b) temporal-reasoning `gpt4_59149c77`** —— Q: 我参观 MoMA 与大都会"古代文明"展相隔几天？A: 7 天
- 证据 #4（01/08，MoMA）、#27（01/15，Met）
- 这两件事**之间没有任何因果依赖** —— 是两个独立事件，问题只是对它们的时间戳做减法
- `An*` 在 slot 实例层面**连不起来**；只有把它们归到同一个 slot **类型**（`museum_visit`）才连得上

**(c) multi-session `0a995998`** —— Q: 我有多少件衣物待取/待退？A: 3
- 证据 #11（干洗西装外套）、#19（Zara 靴子退换）、#30（靴子待取）
- 同样是同类型的独立事件聚合，彼此无因果边

### 6.3 ⚠️ 由此得到的两个硬结论

**结论一：能匹配 gold 的 mask 规则是"保留所有写入了 query 所涉 slot **类型** 的 session"。**

三个例子全部如此。而在这三个例子里 **`An*(Y_q) = Y_q`** ——
也就是说 **`G` 没有提供任何额外信息**。真正干活的是 **slot 类型归一化（extraction）**，不是 slot 之间的因果图。

> 这不推翻 Form A 的 representation，但它把 `G` 的地位降级了。
> `G` 要挣到位置，必须存在**系统性的、query 未直接点名的 slot 类型间依赖**。
> 这一点尚未被证实，**应当在承诺 GRACE 之前先测**。

**结论二：mask F1 不是干净的主指标。**

knowledge-update 的 gold 包含**已被覆盖的旧值**所在 session。所以"丢弃过期值"这一行为 ——
恰恰是因果形式化想要的 —— **会被 mask F1 惩罚，却可能提升下游 QA**。
至少对 knowledge-update，必须以下游 QA 为准。

### 6.4 BM25 召回：skeleton 假设成立，但空间在精度

一个 30 行的朴素 BM25（无调参、粗停用词），query → session：

| k | recall@k | 完全覆盖 gold 的实例比例 |
|---|---|---|
| 1 | 0.551 | 0.292 |
| 2 | 0.790 | 0.670 |
| 3 | 0.856 | 0.760 |
| 5 | 0.912 | 0.832 |
| **10** | **0.947** | 0.896 |
| 20 | 0.973 | 0.938 |

按题型：

| 题型 | @1 | @2 | @5 | @10 |
|---|---|---|---|---|
| single-session-assistant | 0.982 | 0.982 | 1.000 | 1.000 |
| single-session-user | 0.929 | 0.943 | 0.986 | 1.000 |
| knowledge-update | 0.487 | 0.923 | 0.987 | 0.994 |
| **temporal-reasoning** | 0.429 | 0.726 | 0.868 | 0.927 |
| **single-session-preference** | 0.400 | 0.633 | 0.833 | 0.900 |
| **multi-session** | 0.364 | 0.651 | 0.853 | 0.899 |

**读法：**

1. **S2 检验通过** —— 48 选 10 即得 94.7% 召回，"retriever 可充当高召回候选生成器"**经验上成立**。
2. **但召回空间只剩 5.3%。** 由于 gold 只占 4%，能加的价值几乎全在**精度**：把 10 条压到 ~2 条而不掉召回。
   → **因果模块必须被定位成精度工具，不是召回工具**（这正好对应 GRACE 里 skeleton 管召回、gating 管精度的分工）。
3. **两类题已被 BM25 基本解决**（single-session-user / assistant，@1 就 0.93–0.98），不必在它们上花力气。
4. **真正的难点是 multi-session、preference、temporal-reasoning** —— 它们低 k 失败的原因是
   **query 没有在字面上点名证据**。这恰恰是**类型化抽取**能直接解决的，
   而不是因果图能解决的 —— 又一条指向"价值在 extraction"的证据。

### 6.5 修正后的下一步

1. **先测 `G` 值不值**：抽取 slot 类型后，统计 gold session 是否系统性地涉及 query 未点名的 slot 类型。
   若基本没有，就走 §7 的退路，把叙事定成 gated selection 而非 TCD。
2. 主指标改为**下游 QA**；mask P/R 只作辅助，且 knowledge-update 单独看。
3. `T` 的实测中位是 **48**（38–62），确认 §3 结论：要够 GRACE 的 `T ∈ {300…2000}`，**必须换 M**。

---

## 6.6 `Y_q` vs `E(q)` 小样本实验（30 例，已完成）

**设计**：30 例分层抽样（multi-session 10、temporal-reasoning 8、knowledge-update 7、preference 5，剔除 abstention）。
**先只看题目盲写**语义扩展词、落盘固定，**之后才揭 gold**。用同一套 BM25 客观打分，
避免"我事后比对 slot 集合"式的自圆其说。

- **A** = query 原文（≈ 字面目标 `Y_q`）
- **B** = query + 盲写语义扩展（≈ `E(q)`）

| k | A recall | B recall | Δ |
|---|---|---|---|
| 1 | 0.408 | 0.536 | +0.128 |
| 2 | 0.750 | 0.867 | +0.117 |
| 3 | 0.836 | 0.925 | +0.089 |
| 5 | 0.914 | 0.958 | +0.044 |
| **10** | **0.958** | **0.969** | **+0.011** |

按题型（recall@5）：

| 题型 | A | B | Δ |
|---|---|---|---|
| multi-session | 0.917 | **1.000** | +0.083 |
| temporal-reasoning | 0.781 | 0.844 | +0.062 |
| knowledge-update | 1.000 | 1.000 | 0.000 |
| single-session-preference | 1.000 | 1.000 | 0.000 |

### 残差：`B@5` 仍漏掉的只有 3 例，且全是 temporal-reasoning

| # | 题 | 漏掉 |
|---|---|---|
| 11 | Which group did I join **first**, 'Page Turners' or 'Marketing Professionals'? | idx 14 |
| 15 | I mentioned participating in a sports event **two weeks ago**. What was the event? | idx 11, 32 |
| 17 | How many months since I participated in two charity events **on consecutive days**? | idx 6 |

**三例的共同点：约束是时间算术（"first"、"two weeks ago"、"consecutive days"），不是内容。**
字面与语义匹配都用不上这种约束 —— 但解决它的是**日期索引**（LongMemEval 现成提供
`question_date` 与 `haystack_dates`），**不是因果发现**。

### ❌ 结论：`G` 在 LongMemEval 上没有可证明的空间

```
E(q)  ≈  An_G(Y_q)        —— 语义扩展已经吃掉几乎全部可解释部分
残差   =  时间记账，用日期过滤解决，与因果结构无关
```

`k=10` 时语义扩展只比字面 query 多 **+0.011**；而 gold 只占 4%、召回天花板本就很近。
**没有出现"语义相关性解释不了、却能由时序依赖结构系统预测"的那部分。**

### 必须声明的三条局限

1. **n=30**，且偏向难题型，置信区间宽。
2. `E(q)` 是**我**盲写的，比朴素 LLM 扩展可能更强 —— 这会让 B 偏强、从而**偏向"因果无空间"这个结论**。
   但即便 B 弱一些，天花板仍受"gold 占 4%、BM25@10 已 0.95"限制。
3. **本实验只测了召回轴，没测压缩轴。** 因果结构仍有可能在
   "同等 QA 质量下保留更少记忆"上有贡献 —— 这一点**未被证伪，也未获得任何正信号**。

---

## 6.7 战略结论：LongMemEval 降级为诊断/压缩基准

| 组件 | 处置 | 理由 |
|---|---|---|
| **GRACE** | **保留** | 仍是合理的 Layer-1 TCD 引擎，问题不在它 |
| **MemoryAgentBench** | **保留** | 作为 plug-in 集成 / 评测 harness 很好用 |
| **LongMemEval** | **降级** | 任务语义主要是 evidence retrieval + 时间记账，不是生成机制中的因果依赖 |

**不要下载 `longmemeval_m`（2.7 GB）。** `T` 不足已经不是第一阻塞点了 ——
把 `T` 从 48 提到 500，只会让 GRACE 更稳定地学到一张**对该任务无用的图**。

### 主指标应改为 accuracy–compression Pareto

| 横轴 | 纵轴 |
|---|---|
| 保留的记忆量（sessions / tokens / 占原始历史比例） | 下游 QA accuracy |

对照：full memory / BM25 top-k / typed retrieval / semantic typed retrieval / causal typed retrieval。
想看到的是「**同等 accuracy，显著更少 memory**」。evidence recall 与 mask F1 退为诊断量。

### ⚠️ 一个反噬我自己 Task-2 选型的观察

Yujia 最初描述的是 `s_{t-k} → s_t → a_t` 这种**动态过程**：当前状态该依赖哪些过去状态、
并据此 condition 行动。LongMemEval 是 `{documents} + q → retrieve → a`，**不是同一回事**。

而"agent 行动 → 观测 → 写记忆 → 再行动"的结构，恰恰是 **MemoryArena 有、LongMemEval 没有**的。

我此前把 Task 2 判给 MemoryAgentBench，理由是 `M_t` 可枚举、插入方便 —— 那个理由在工程上仍然成立，
但本实验提示：**当时优化的可能是错的维度**（可插入性 vs 任务语义是否真的含因果结构）。
MemoryArena 的接口障碍（`wrap_user_prompt` 只返回拼好的字符串）是真的，但那是工程问题；
任务语义不对则是研究问题，后者更贵。

**这不意味着放弃因果记忆项目**，而是：**平台工程上选对了，任务语义没选对。**

---

## 6.8 压缩轴：accuracy 上界 vs 保留量（n=479，无需 LLM）

上一节只测了召回轴。这里补压缩轴，用 LongMemEval 的 **turn 级 `has_answer` 标注**做
**无需 LLM 的 QA accuracy 严格上界**：一个预算下若全部 `has_answer` turn 都被保留，
则该实例"可答"；否则必错。

| 方法 | 保留 token% | answerable 上界 |
|---|---|---|
| **oracle-turn** | **0.2%** | **100.0%** |
| BM25-turn@5 | 1.0% | 56.2% |
| recency@1 | 2.1% | 1.7% |
| **BM25-turn@10** | **2.3%** | **70.4%** |
| BM25-sess@1 | 2.7% | 32.4% |
| BM25-turn@20 | 4.9% | 76.6% |
| **oracle-sess** | **5.1%** | **100.0%** |
| BM25-sess@2 | 5.4% | 71.0% |
| BM25-sess@3 | 8.1% | 79.3% |
| BM25-turn@40 | 10.4% | 82.0% |
| recency@5 | 10.5% | 6.5% |
| BM25-sess@5 | 13.1% | 86.0% |
| recency@10 | 21.3% | 14.2% |
| BM25-sess@10 | 25.4% | 91.9% |
| full | 100.0% | 100.0% |

### 三条读数

**1. 压缩轴上确实有大空间 —— 与召回轴相反。**
答题所需信息只占全部历史的 **0.2% token**（oracle-turn），而 BM25-turn@10 花了 **2.3%** 只拿到 70.4%。
即**十倍以上的 token 差距 + 约 30pp 的上界差距**摆在那里。§6.6 说召回轴没空间，但**压缩轴有**。

**2. turn 级粒度是激进压缩下最大的单一杠杆。**
同样约 2.5% 预算：`BM25-turn@10` 70.4% vs `BM25-sess@1` **32.4%** —— 翻一倍还多。
session 是错的操作粒度；`has_answer` 本来就是 turn 级的。
（预算放宽到 >10% 后 session 级反超，但那已不是有意思的工作点。）

**3. ⚠️ recency 近乎无用，这是又一条不利于时序结构的证据。**
`recency@10` 花掉 21.3% token 只换来 **14.2%**，比 `BM25-turn@5` 花 1.0% 换 56.2% 差得远；
random 更差。**时近性在这个任务里几乎不携带信号。**
结合 §6.6 的残差分析，LongMemEval 的信号是**语义的**，不是**时序的**。

> **但要说清楚**：这里的空间是"把相关性判得更准"的空间，
> **是否需要因果结构来填，仍未被证明**。它把问题从"有没有空间"推进到了"什么东西能填这个空间"。

---

## 6.9 MemoryArena 四个环境的状态转移结构（已读源码）

| 环境 | 跨轮持久状态 | 逐步反馈 | 早期动作约束后期 |
|---|---|---|---|
| **webshop** (`webshop_env.py`) | `purchased_asins`、`purchased_prices`、`history`、`_current_observation`、`turn_count` | 可选（`need_judge`）；终局 `match_ground_truth` | ✅ 购买累积 + **prefix match** 逻辑 |
| **travel** (`travel_env.py`) | `history`、`step_count` | ✅ **hint 模式逐步纠错**：`"Feedback for {name}: The following slots need correction:"` | ✅ 可据中间反馈调整后续 |
| **search** (`browsecomp_plus_env.py`) | `memory_client`、逐 subquery trace | 每 subquery 有 judgement | subquery 链 |
| **math** (`math_env.py`) | `history`、`tool_trace`、`state.history_len` | ✅ 每步 `return observation, reward, {}` | ✅ 前一 subtask 的 tool 结果进入后续 |

**四个环境全部具备 `s_{t-k} → s_t → a_t`。** travel 的 hint 模式尤其有意思 ——
它给的是**逐步纠错反馈**，构成真正的"从反馈中学习并改写记忆"的闭环。
这正是 LongMemEval **完全没有**的结构。

### ✅ 修正：接口障碍被我高估了

此前判断：MemoryArena 的统一接口只返回拼好的 prompt 字符串，`C_t ⊙ M_t` 表达不出来 → 不适合。

**这个论证有个洞：我们不需要去 mask 别人的记忆，我们应该自己**就**是一个记忆系统。**

`memory/server.py` 的扩展点是现成的：

```python
MEMORY_FACTORIES: Dict[str, Callable[[], object]] = {"mirix": MirixMemorySystem, ...}
# /memory/add    →  memory_system.add_chunk(req.chunk)     ← 我们自己存，M_t 当然可枚举
# /memory/query  →  memory_system.wrap_user_prompt(req.question)  ← 在这里施加 mask 再拼 prompt
```

实现一个类、三个方法（init / `add_chunk` / `wrap_user_prompt`）、注册进 `MEMORY_FACTORIES` —— **就完成了**。
`M_t` 由我们自己持有，所以可枚举；mask 在 `wrap_user_prompt` 内部施加。
而且这样我们**天然与其余 13 套记忆系统在同一评测下正面对比**，正是 Yujia 要的"设计独立模块注入现有框架"。

**工程量估计：约一天**（另加打点）。远低于我此前的判断。

> 所以 Task 2 的正确结论应当修正为：
> **MemoryAgentBench 仍是最省事的 harness，但 MemoryArena 的任务语义才是对的，且接入成本并不高。**
> 两者并不冲突 —— 前者做压缩诊断，后者做因果结构的正面验证。

---

## 7. 若 Form A 通不过

退路是**放弃 TCD 形式化、只保留 gating**：不定义 `X_t / d / T`，
直接学一个 content-conditioned Hard Concrete gate over retrieved memories，用 task loss 训。

这条 Yujia 允许（pseudo-causal + 先看 empirical gain），但**叙事必须诚实**：

> ✅ GRACE-inspired causal/gated memory selection
> ❌ we directly plug GRACE TCD into MemoryAgentBench
