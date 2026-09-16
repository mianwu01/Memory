# Causal Formal：可干预的形式推理记忆原型

## 结论

原版 MemoryArena `formal_reasoning_math/phys` 是四类任务中最接近目标的真实
候选：当前子问题经常省略历史中的定义和符号来源。但它原样只能检验隐式依赖
检索，不能检验“一个历史定义被纠正后，系统是否找齐并重算所有下游结论”，
因为原数据没有 intervention、反事实状态或依赖图 gold。

本原型在不修改上游 checkout 的前提下，新增两个确定性 sequential notebook：

- `causal_formal_math`：仿射递推、lemma、theorem 与条件 twist 公理；
- `causal_formal_phys`：动量/阻力推导、theorem 与条件 field 公理。

每次 query 只给出一个上游参数/定义/公理的纠正，不列出任何 descendant。模拟器
产生完整反事实 notebook。120 条 T0 中 Exact-KV 的整集成功率为 **16.67%**，
oracle propagation 为 **100%**，因此已经排除“只改 query 点名 key 即可”的简单解。

T1 进一步只用 84 条 train 的可观察 pre/intervention/post transition 学习 impact
selector，并在 24 条 outcome-isolated test 上跑六臂。learned selector 达到 100%，
但强程序/dataflow solver 同样达到 100%。因此最终结论不是“causal graph 对形式推理
不可替代”，而是：这个载体能复现正确传播和约 26.9% 的 compact-context 节省；
形式公式一旦可执行，domain solver 就是无法回避的 killer baseline。

实现位于 `code/causal_benchmarks/causal_formal.py`，使用 Python 标准库并遵循
`causal-memory-benchmark/v1` 统一协议。

## 1. 对原版 math/phys 的审计

仓库已有的 HF 全量审计（40 个 math paper、20 个 phys paper）给出：

| 指标 | math | phys |
|---|---:|---:|
| 子问题 | 354 | 86 |
| 有显式 `\ref` / Lemma 引用 | 26（7.3%） | 18（20.9%） |
| `k>=2` 且 background 为空 | 68% | 77% |
| 引用落在历史子任务 | 12/28 | 23/35 |
| 悬空引用 | 16/28 | 5/35 |

典型 phys 子问题只写：

> For $\mathcal{A}=\{1,3\}$ with $\sigma=4$, determine $(c_2,c_3,c_0)$.

其中符号和方程只存在于更早的子问题，当前问题没有词法引用。这说明原任务确实
包含 history-borne implicit dependency，而不是 Travel 那样由 query 显式给出
`(person, day, slot)`。

但这仍缺三项核心标注：

1. 上游定义/公理发生变化的 intervention；
2. 哪些历史结论应当失效并被重算；
3. intervention 下的 active gated edges 与唯一 post-state。

所以不能把原任务上的 retrieval 改进直接写成 causal propagation。上述数字来源于
`docs/benchmark-audit-c1c4.md`；本原型没有伪称重新下载并审计 HF 数据。

## 2. 任务语义

### 2.1 Math notebook

稳定机制为：

```text
parameter.base ─┐
                ├→ lemma.term_2 → lemma.term_3 → theorem.core
definition.step ┘          ↑                          │
                           └── definition.step       ↓
axiom.twist_enabled ───────────────────────→ lemma.active_branch → theorem.final
definition.twist ──[twist_enabled=true]────→         ↑                 ↑
parameter.base ──────────────────────────────────────┴─────────────────┘

control.notation_scale → control.notation_invariant
```

Query 示例：

```text
A referee asks us to correct `parameter.base` to 8.
Update the notebook conclusions.
```

Query 没有写 `term_2`、`term_3`、`core`、`active_branch` 或 `final`。只覆盖
`parameter.base` 会留下互相矛盾的旧结论。

### 2.2 Physics notebook

稳定机制为：

```text
mass, velocity → inertial_momentum ─┐
                                    ├→ net_momentum → active_force → displacement_score
drag_coefficient, velocity → drag_loss ┘                ↑                  ↑
field_enabled ───────────────────────────────────────────┤                duration
field_strength ──[field_enabled=true]────────────────────┘

detector_bias → calibration_checksum
```

两类 notebook 共享相同的实验语义，但不是同一套节点名称，防止只记忆一个固定
key 列表就冒充通用传播能力。

## 3. Intervention 与 regime

生成器每六条循环覆盖：

| 类型 | 示例 | 预期 |
|---|---|---|
| parameter correction | `base: 6 -> 8` | 多跳重算 |
| definition correction | `step: 5 -> 6` | 多路径、多跳重算 |
| axiom retraction | `twist_enabled: true -> false` | 关闭 gated edge 并重算 |
| axiom activation | `field_enabled: false -> true` | 激活 gated edge 并重算 |
| active gate update | field 开启时修改 strength | 沿 gated edge 传播 |
| inactive gate update | field 关闭时修改 strength | 只改源，不污染下游 |

最后一种不是无意义 easy case：它检验系统是否理解 regime，而不是对任何表面相关
变量都过度传播。每条主链 intervention 还带独立的 notation/calibration 分支作为
unaffected negative control，评价器要求它保持不变。

## 4. 数据契约与隔离

Runtime 可见：

- `history`：旧定义、推导式和旧结果；
- `memory_state`：干预前的 materialized notebook；
- `query.text`；
- `query.intervention`：T0 使用的 oracle semantic parse，统一为
  `node/old_value/new_value/kind`。

T1 额外规定：

- 仅 `split=train` 含 runtime-visible
  `observed_transition={pre_state, intervention, post_state}`；
- `dev/test` episode 不含 `observed_transition`；
- `runtime_view(..., training=False)` 无条件删除 `gold` 和训练 outcome；
- learner 的 `fit` 拒绝带 `gold` 的对象，`predict` 拒绝带 `gold` 或
  `observed_transition` 的对象。

Evaluator 独占 `gold`：

- `graph`：含 gated 条件的完整 dependency graph；
- `active_edges`：post-intervention regime 下的实际边；
- `intervention`；
- `affected_nodes` / `affected_results`；
- `required_reads`；
- `final_values` / 完整 `post_state`；
- `unaffected_controls`。

Oracle baseline 只调用独立的 `simulate(task, pre_state, intervention)`。测试会在
fit/predict 前删除整个 `gold`，并显式验证污染对象被拒绝。

`query.intervention` 是为隔离 propagation 能力而提供的结构化 parse；它不意味着
自然语言 parser 已经解决。未来端到端实验必须单独报告 intervention parsing，不能
把 oracle parse 的结果包装成 language understanding。

## 5. T1 六臂与共享 decoder 边界

| Arm | Impact selection | Value execution | 作用 |
|---|---|---|---|
| Exact-KV | 只选 intervention node | 更新显式 key | killer simple baseline |
| program/dataflow | 从可执行 notebook program 求 active descendants | 共享 deterministic executor | 最强 domain baseline |
| matched-budget retrieval | lexical rank，update-cell 数与 learned 完全相同 | 共享 executor | 通用检索对照 |
| learned graph | 只从 train transition delta 学 source/regime→impact set | 共享 executor | 被测 selector |
| oracle graph | simulator pre/post delta | 共享 executor | selector 上界 |
| full history | 重算和暴露整个 notebook | 共享 executor | 性能上界、上下文下界 |

Learned arm 的名称沿用统一实验矩阵，但实现准确说是
`train-delta-modal-impact-v1`：它学习的是**传递 impact relation**，不声称从这些
有限 transition 唯一识别 direct causal edge。

所有 selector 使用同一个可执行 value decoder。这样能把错误归因到“哪些结果应被
更新”，不会把算术失败混入 selection；但它也意味着本实验**没有证明 selective
retrieval + LLM execution 的端到端能力**。`selected_context_nodes` 是 decoder 对已选
result 做 active ancestor closure 后实际所需的上下文。

program/dataflow solver 读取 notebook 的可执行机制并精确求 closure；learned selector
若不能优于它，就不能声称 learned causal structure 在该 task 上具有必要性。

## 6. T0 结果

复现：

```bash
python3 code/causal_benchmarks/causal_formal.py t0 --count 120 --seed 17
```

结果（60 math + 60 phys）：

| 指标 | Exact-KV | Oracle propagation | Headroom |
|---|---:|---:|---:|
| affected-node precision | 1.0000 | 1.0000 | — |
| affected-node recall | 0.3944 | 1.0000 | +0.6056 |
| affected-state accuracy | 0.3944 | 1.0000 | +0.6056 |
| affected-result recall | 0.0000 | 1.0000 | +1.0000 |
| full-state cell accuracy | 0.7890 | 1.0000 | +0.2110 |
| whole-episode success | 0.1667 | 1.0000 | +0.8333 |

附加准入量：

- 100/120（83.33%）episode 确实要求至少一个 derived result 传播；
- 20/120 是 inactive-gate negative cases，正确行为是不传播；
- query descendant string leakage 为 0；
- 按统一 stop rule，T0 admission 为 `PASS`。

`full-state cell accuracy=78.90%` 看起来不低，是因为大量未受影响 cell 容易原样保留；
因此它不能单独作为主指标。whole-episode success 和 affected-result recall 才直接回答
“是否完成了所有应传播的修改”。

## 7. T1 split：可见 transition 与 held-out generalization

120 条固定数据的分配为：

| Split | Episodes | Runtime outcome | 值域/模板 |
|---|---:|---|---|
| train | 84 | 可见 `observed_transition` | low-value bands；`train_*` templates |
| dev | 12 | 隔离 | middle-value bands；held-out dev template |
| test | 24 | 隔离 | high-value bands；`test_*` templates |

可执行检查结果：

- 非布尔 primitive 的 train 与 dev/test 值交集为 0；
- train 与 dev/test template ID 交集为 0；
- test 有 8 条 held-out target×regime 组合：base/step 或 mass/drag 首次与 inactive
  gate 组合；
- dev/test 有 12 条至少影响四个 derived results 的长传播实例；
- train、dev、test 都覆盖六类 intervention，拓扑本身不是 held out。

最后一点很重要：这是 novel value/template/target-regime combination split，**不是
unseen topology generalization**。而且 T1 直接使用结构化 `query.intervention`，所以
held-out natural-language template 只验证没有 outcome 泄漏，尚不验证 parser 泛化。

## 8. T1 结果

复现：

```bash
python3 code/causal_benchmarks/causal_formal.py t1 --count 120 --seed 17
```

以下为 24 条 test 的确定性结果：

| Arm | Result F1 | Episode success | Neg. control preservation | Context cells | Compact chars |
|---|---:|---:|---:|---:|---:|
| Exact-KV | 0.0000 | 0.1667 | 1.0000 | 1.00 | 129.63 |
| program/dataflow | 1.0000 | 1.0000 | 1.0000 | 8.00 | 291.50 |
| matched-budget retrieval | 0.5444 | 0.1667 | 1.0000 | 7.71 | 290.96 |
| learned graph/impact | 1.0000 | 1.0000 | 1.0000 | 8.00 | 291.50 |
| oracle graph | 1.0000 | 1.0000 | 1.0000 | 8.00 | 291.50 |
| full history | 1.0000 | 1.0000 | 1.0000 | 12.00 | 398.63 |

补充审计：

- learned 和 matched-budget 的 mean selected update cells 都是 3.50；matched retrieval
  不是靠更小预算被故意做弱；
- learned 的 affected-node P/R、affected-state accuracy、required-read recall、
  unaffected-state accuracy 都是 1.0；
- matched retrieval 有 62.5% 的 episode 错选 negative-control cell；虽然共享 executor
  重算出相同旧值，negative-control value preservation 仍为 1.0，所以必须同时看
  selection 与 preservation；
- fit 收到 gold = false，fit/test ID overlap = 0，test outcome leak = 0，query descendant
  leak = 0；
- learned compact 相对 learned verbose 少 54.33% chars；
- learned compact 相对 full-history compact 少 26.86% chars，效果相同；
- program/dataflow 与 learned 在效果、selected context 和 serialization 上完全持平；
  它直接调用 benchmark 提供的 executable domain program，因此无需训练或扫描文本。
  这正是该载体无法证明 learned graph 必要性的原因，而不是需要藏掉的弱点。

因此 verdict 分开报告：

- train-only pipeline：`PASS`；
- effectiveness replication（相对 Exact-KV/retrieval）：`PASS`；
- compact-context efficiency replication（相对 full history）：`PASS`；
- learned-graph necessity（相对强 program/dataflow）：**`FAIL`**。

### Selection × serialization 正交化

每个 selection arm 都同时生成 `verbose` 和 `compact` 两种 serialization。确定性
executor 在两列保持相同 prediction，因此 effectiveness 严格不变；只比较 chars、
token proxy 和 scan chars。这里 compact 的 54.33% 降幅是 serialization 主效应，不能
归给 graph selection。learned 对 full-history compact 的 26.86% 差才是固定 compact
格式后的 selection 差异。

## 9. 运行与测试

生成 JSONL：

```bash
python3 code/causal_benchmarks/causal_formal.py generate \
  --count 120 --seed 17 --family both --output /tmp/causal-formal.jsonl
```

只打印一条完整样例：

```bash
python3 code/causal_benchmarks/causal_formal.py example --family math --seed 17
```

运行单测：

```bash
PYTHONPATH=code python3 -m unittest \
  causal_benchmarks.tests.test_causal_formal -v
```

测试覆盖确定性、统一 schema、query 无 descendant、active/inactive gate、公理撤销、
unaffected controls、train-only outcome、删除 gold 后 fit/predict、held-out split、六臂、
matched budget、selection×serialization、T0/T1 CLI。

## 10. 论文 claim 边界

本次 T1 可以主张：

- train-only impact learner 能在 held-out values/templates/target-regime combinations 上
  选择并重算受影响 formal results；
- 它优于 Exact-KV 和 matched-budget lexical retrieval；
- 它能识别 active/inactive gate 并保持独立 negative-control 分支；
- 相对 full history，它在相同 compact serialization 下减少 context。

不能主张：

- 从 observational text 识别了现实世界的物理因果关系；
- 在原版 MemoryArena math/phys 上已有 causal discovery 或 LLM-e2e 结果；
- oracle propagation 是 learned method 的能力；
- learned selector 优于可执行 program/dataflow solver；
- held-out query text 已验证自然语言 parser；
- formal dependency 等同于 empirical causality。

最准确的术语是 **interventional dependency / change propagation in a mutable
formal artifact**。这里的 intervention 是对计算制品的 edit/do 操作，gold 来自程序
语义；本质仍是 interventional dataflow，不外推 empirical causal discovery。

## 11. 在 Yujia 两卖点 / 三实验中的位置

Yujia 的两条卖点是：（1）memory effectiveness/efficiency；（2）recover hidden driver
后用于 trustworthiness/actionable safety。三部分实验是 simulation、真实 agentic
效果/效率、agent safety。

Causal Formal 的合适位置最多有两个：

1. 作为 Part 1 的 simulation-like boundary / 可执行 change-propagation sanity check；
2. 作为 Part 2 effectiveness/efficiency 的**补充 replication**，说明 impact-aware
   selection 在 formal artifact 上能避免 stale result 并减少 context。

它不能承担 Part 3：任务中没有 LLM-agent 决策、malicious memory、hidden behavioral
driver、online gate 或安全 outcome，所以绝不能把 theorem propagation 冒充 agent
safety/auditing。它也不能替代 Part 2 的真实 LLM-agentic 主实验；program solver 的
100% 结果进一步表明这更接近 simulation/program-maintenance boundary。

## 12. 下一步（若保留为附录/补充实验）

1. 增加 symbol renaming、跨 notebook mechanism 和 unseen topology，防止背 key；
2. 增加值抵消但仍需 invalidate 的版本，把 changed-value 与 affected-result 分开；
3. 用真实 parser 替换 oracle structured intervention，并单列 parse accuracy；
4. 用 LLM executor 做一次端到端运行，同时保留共享 oracle decoder 的 selector 消融；
5. 若要回接原 HF task，先用 proof assistant/可执行 DSL 建立可验证表达式，不能靠
   LLM 自举的依赖标签作为唯一 gold。

当前最诚实的归位是：T1 已完成，但 learned-graph necessity 被强程序 baseline 否决；
把它保留为 effectiveness/efficiency replication 或 simulation-like appendix，不作为
论文因果必要性或安全性的主证据。
