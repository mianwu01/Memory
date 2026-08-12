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

## 6. 若 Form A 通不过

退路是**放弃 TCD 形式化、只保留 gating**：不定义 `X_t / d / T`，
直接学一个 content-conditioned Hard Concrete gate over retrieved memories，用 task loss 训。

这条 Yujia 允许（pseudo-causal + 先看 empirical gain），但**叙事必须诚实**：

> ✅ GRACE-inspired causal/gated memory selection
> ❌ we directly plug GRACE TCD into MemoryAgentBench
