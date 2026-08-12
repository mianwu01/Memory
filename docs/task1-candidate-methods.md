# 任务一候选方法表（按实现核实）

> 判据取自 Yujia 的优先级：**能跑 > 能扩展 > 容易接入 > 效果好 > 理论最漂亮**。
> 本表只收**我实际读过实现**的方法；未核实的单列在 §5，不参与结论。
> 目标输出形式：`A^(0), A^(1), …, A^(L)`（lag-wise 邻接）。

---

## 1. 已核实的候选

| 方法 | 官方实现 | License | 核心参数是否按变量身份索引 | lag-wise 输出 | 端到端可微 | 已验证规模 |
|---|---|---|---|---|---|---|
| **GRACE** | `bloomberg/causal-ts`（`causalts/grace/gated_discovery.py`） | GPL-3.0-or-later | ✅ `log_alpha[N, L+1, N]` | ✅ | ⚠️ 仅 gating 段；skeleton 是离散预处理 | d=100，F1 0.92 |
| **UnCLe** | `etigerstudio/uncle-causal-discovery`（`bin/experimental_utils.py`） | ❌ **无 license 文件** | ✅ `var_mat[N, N, C, lag]` | ✅ 静态 | ⚠️ 静态段可微；动态段是推理期扰动，不参与训练 | static d=100 / **dynamic d≤8** |
| **CUTS+** | `jarrycyx/UNN` → `CUTS_Plus/cuts_plus.py` | MIT | ✅ `GT = nn.Parameter[n_groups, n_nodes]` | ❌ **`[N,N]`，无 lag 维** | ✅ Gumbel-softmax(hard) + L1 | coarse-to-fine 分组扩展 |
| **JRNGC** | `ElleZWQ/JRNGC` | MIT | ⚠️ 单一共享模型（无 per-target 模型），但因果矩阵由 Jacobian **post-hoc** 提取 | ✅ summary + full-time | ⚠️ Jacobian 正则在目标里，矩阵提取在训练后 | CausalTime（AQI / Traffic / Medical） |
| **ACD** | `loeweX/AmortizedCausalDiscovery`（`codebase/model/MLPEncoder.py`） | MIT | ❌ **无任何按 N 索引的参数** —— 权重全部在 node/edge 间共享，`rel_rec`/`rel_send` 逐 batch 传入，**N 可变** | ❌ 输入被摊平成 `[num_atoms, T×dims]`，**时间塌进特征轴**，输出 `[sims, edges, edge_types]` | ✅ | springs / Kuramoto / Netsim，N 小 |
| **AVICI** | `larslorch/avici` | MIT | 置换等变 | ❌ **仅 i.i.d. 观测/介入，无时序能力** | ✅ | 训练分布 ≤100 节点 |

### 关键核实点（逐条来自源码）

```python
# GRACE —— 每条边一个自由标量
self.log_alpha = nn.Parameter(torch.zeros(num_vars, Lp1, num_vars))
# UnCLe —— 按变量身份
self.var_mat   = nn.Parameter(torch.zeros(c_in, c_in, channels, lag).normal_(0, 0.01))
# CUTS+ —— 分组矩阵仍按节点身份
Graph = torch.einsum("nm,ml->nl", G_prob, torch.sigmoid(GT_prob))   # GT: [n_groups, n_nodes]
# ACD —— MLP 权重与 N 无关，图结构靠 rel_rec/rel_send 逐 batch 给
```

**六个里只有 ACD 的参数不绑定变量身份。** 但它没有 lag 维，且把时间塌进了特征轴。
**AVICI 直接出局** —— 无时序。

---

## 2. ⚠️ 一处自我修正：摊销不是硬需求

先前的判断是"变量身份跨样本不共享 → 必须摊销 → 只有 amortized 一行可用"。**这话说过头了。**

我们有两种架构，摊销只是其中一种：

| | 做法 | 是否需要 N 无关的参数化 | 代价 |
|---|---|---|---|
| **(A) 逐 episode 重拟合** | 每个 conversation 单独跑一次 TCD（`N ≈ 50`, `T ≈ 32`） | ❌ **不需要** —— 身份索引完全可用 | 500 次拟合。GRACE 在 d=100 约 345 s → 单线程约 48 h，可并行 |
| **(B) 摊销** | 跨 500 个 conversation 训一个编码器 | ✅ 需要 | 统计上更强（共享 500 个样本），但目前只有 ACD 能做，且无 lag 输出 |

按 Yujia 的"能跑 > 能扩展"，**第一版走 (A)**。这样"必须摊销"这个约束整个消失，六个候选全部重新可选。
(B) 留给第二版 —— 那时 ACD 是唯一起点。

---

## 3. 结论：主方法 / baseline / 备选

### 主方法 —— **GRACE，经 `causal-ts`，逐 episode 重拟合，skeleton 槽位换成非 CI 预筛**

| Yujia 的判据 | 满足情况 |
|---|---|
| 能跑 | ✅✅ **唯一** pip 可装、有 docs/tests/CI、8 个 CI 检验全 GPU 加速（2.0–2.9×）、Python 3.10–3.12 的维护中库 |
| 能扩展 | ⚠️ 库自述 "Best for High-dim, **d≤100**"；我们 `N≈50`（session 级）落在范围内 |
| 容易接入 | ✅ `run_cdnots_gated(df, max_lag, skeleton=…, gate_threshold, lambda_cv)` —— **skeleton 是参数，可传非 CI 候选集** |
| 效果好 | ✅ d=100 F1 0.92 / precision 0.97，是整张 taxonomy 里最好的 |
| neural / 可微 | ✅ gating 段 Hard Concrete + 解析 L0 |
| lag-wise 输出 | ✅ |

> ⚠️ **「用相似度预筛顶替 skeleton」这一说法已作废**（类型不匹配）：
> skeleton 是 `S ∈ {0,1}^{d×d×(L+1)}`，即**候选边**；top-200 是**候选记忆项**。二者不是同一个数学对象。
>
> **修正后的立场**：v1 **保留原始 CI skeleton**，先得到一个 faithful 的 GRACE 基线。
> 相似度/时近 top-K 保留，但正名为 **memory candidate prefilter**，不叫 skeleton。
> 将来若真要换非 CI skeleton，替代物必须同样产出 candidate-edge tensor，
> 实验对照才写成 `CDNOTS skeleton + GRACE` vs `our candidate-edge generator + GRACE`。

### baseline —— **CDNOTS+**（同库、同 API、零集成成本）

它本身就是 CI-based（PCMCI+ skeleton 阶段）。拿它当对照，**正好用来证明换掉 CI skeleton 有收益** ——
这是最省事也最说明问题的 baseline。

### 备选 —— **JRNGC**（MIT，单一共享模型）

用输入-输出 Jacobian 正则替代权重稀疏约束，**一个模型覆盖所有目标变量**，绕开了 neural Granger 那类
component-wise 设计的 O(N²) 参数问题。代价是因果矩阵**训练后才提取**，不在可微路径里。

### 第二版方向 —— **ACD**

**唯一验证过能处理可变变量集的方法。** 若将来要做真正的摊销版（跨 conversation 共享一个编码器），
它是唯一起点。但要先解决它**没有 lag 维**、时间被塌进特征轴的问题。

### 排除

| 方法 | 排除理由（均已核实） |
|---|---|
| AVICI | 仅 i.i.d.，无时序 |
| UnCLe | dynamic 仅验到 d≤8；动态段不可微不参与训练；**仓库无 license 文件**（比 GPL 更麻烦，默认保留全部权利） |
| CUTS+ | 图是 `[N,N]`，**无 lag 维**，不满足 `A^(0..L)` 的输出要求 |

> **可借鉴**：CUTS+ 的 coarse-to-fine 分组（`n_groups` 每若干 epoch `*= group_mul`，并从上一尺度插值参数）
> 是个针对高维的实用技巧。若第二版要直接吞数千 chunk，这个思路比"预筛 + 精炼"更原生。

---

## 4. 与任务二的接法

任务二选 **MemoryAgentBench**，决定性理由是 Yujia 的公式要求 `M_t` 可枚举可索引：

```
M_t → TCD → C_t ;   M_t^causal = C_t ⊙ M_t ;   → existing memory system → LLM
```

- **MemoryAgentBench**：`all_context_chunks` 就是 `List[List[str]]`，`initialization.py::_memorize_context_chunks` 逐条喂 → `M_t` 可枚举 ✅
- **MemoryArena**：统一接口只有 `add_chunk` / `wrap_user_prompt`，后者返回拼好的 prompt 字符串而非记忆列表；
  13 个异构后端没有统一的"枚举当前记忆集"操作。

> ⚠️ **上面那条对 MemoryArena 的否定判断已修正**（见 `form-a-representation.md` §6.9）。
> 它只在"去 mask 别人的记忆系统"这个前提下成立。正确做法是**我们自己注册成一个记忆系统** ——
> 实现 `add_chunk` / `wrap_user_prompt` 并注册进 `MEMORY_FACTORIES`，`M_t` 由我们自己持有因而可枚举，
> mask 在 `wrap_user_prompt` 内部施加。约一天工作量，且天然与其余 13 套同台对比。

> ⚠️ **本节原先那句「数千 chunk 正是 500–5000 变量区间」已作废** —— 那是把时间步当成了变量。
> chunk 是按序喂入的**时间步**（`T`），不是变量（`d`）。
> 正确的 representation 与 `G → C_t` 映射见 **`form-a-representation.md`**。

**首次跑通路径**：

1. `pip install causalts`
2. 取一条 LongMemEval 实例的 `all_context_chunks`，定义 session 级变量
3. 抽取 `(X_t, U_t, P_t)` → `run_cdnots_gated(df, max_lag, skeleton=<CI skeleton 或候选边生成器>, …)` → `G` → 经 provenance 得 `C_t`
4. `C_t ⊙ M_t` → 送进既有 RAG 路径 → 用现成 `llm_based_eval/` 比对

**先清一个已核实的路障**：`chunk_text_into_sentences()` 返回裸字符串（下游 `assert isinstance(chunks[0][0], str)`），
`utils/eval_data_utils.py` 不保留任何 session id。gold evidence 对齐需先补 `stage1-experiment-design.md` §3 的三个补丁。

---

## 5. 尚未核实实现的方法

以下仅有论文/表格层面的了解，**未读实现**，故不参与上面的结论：

LCM、SEA、CauScale、DOT、CausalFormer（`arXiv 2406.16708`）、SC3D、Rhino、NTS-NOTEARS、
eSRU、cMLP / cLSTM、SPACETIME、TTCD、Cedar、以及 coarse-grained 那一支。

已知仓库但未读源码：`M-Nauta/TCDF`、`bartbussmann/NAVAR`、`i6092467/GVAR`。

其中**最值得补核的是 DOT / CausalFormer** —— 它在 taxonomy 表里 n=100 线性 F1 0.97，
但表里同时标了"需要 5×10⁴–10⁶ 样本"。我们每条 episode 只有 `T ≈ 32`、共 500 条，
**样本量这一条大概率直接排除它**，不过应当读过实现再下断言。
