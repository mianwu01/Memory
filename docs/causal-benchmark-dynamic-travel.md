# Dynamic Travel：从 T0 干预传播到 T1 train-only 结构学习

本文是 `code/causal_benchmarks/dynamic_travel.py` 的权威实验说明。Dynamic Travel
是本仓内的确定性隔离原型，不是对 `benchmarks/MemoryArena` 上游环境的修改，也不是
LLM agent 端到端结果。

## 1. 为什么必须重新定义 Travel

原 MemoryArena Travel 让新 traveler 修改 query 明示的 cells，并物化所有先前最终计划。
因此 `(traveler, day, slot)` 精确索引就能完成 memory selection。Dynamic Travel 改成：
先形成一份已经预订的 itinerary，再对其状态实施 intervention，并评价完整反事实传播。

例如：

```text
flight.arrival_hour
  -> transfer.end_hour
      -> attraction.status -> attraction.end_hour
      -> dinner.status     -> dinner.end_hour
      -> hotel.checkin_status
```

当前 query 只说航班新的到达时间、景点/餐厅关闭、酒店 deadline 改变或紧急联系人更新，
不会枚举 downstream cells。attraction/dinner flexibility、availability 和 hotel late-check-in
会门控传播，所以相同干预可在不同 regime 中产生不同结果。

这与原任务的差别不是“检索器更复杂”，而是评价语义从“覆盖显式 slot”变为“发现并维护
未点名的受影响状态”。

## 2. DGP、事件和 evaluator gold

原型遵循 `causal-memory-benchmark/v1`，包含五类平衡事件：

1. `flight_delay`；
2. `attraction_closure`；
3. `dinner_closure`；
4. `hotel_deadline_change`；
5. `independent_profile_update`，作为无传播负对照。

前四类需要传播；第五类只应改变 intervention cell，防止“把所有 cell 都选中”取得虚假
高 recall。

Runtime 可见：

- `history`：自然语言 itinerary facts 和 distractors；
- `memory_state`：干预前的 19-cell 结构化状态；
- `query.text` 与 oracle-parsed 单一 `query.intervention`；
- entity、event kind 和 generalization metadata。

Evaluator-only `gold` 包含潜在图、当前 regime 的 active edges、required reads、真实
affected nodes 与 simulator post-state。正式 selector 不得读取 `gold`。

## 3. Train-only outcome isolation

数据按完整的五事件 block 划分：70% train、10% dev、20% test。在
`500 episodes / seed 0` 中对应 350/50/100。

只有 train episode 额外暴露已经完成的历史转移：

```json
{
  "observed_transition": {
    "pre_state": "...",
    "intervention": "...",
    "post_state": "..."
  }
}
```

该对象没有 `gold.graph`、`gold.active_edges`、`gold.affected_nodes` 或 required-read 标签。
`runtime_view(episode, training=True)` 只在 train 返回 outcome；dev/test 原始 episode 不含
`observed_transition`，普通 test runtime view 也同时排除 `gold` 和 outcome。

`LearnedImpactSelector.fit` 若收到 evaluator gold、非 train record 或缺失 completed
transition 会报错；`predict` 若收到 gold 或 observed outcome 同样报错。测试覆盖了
runtime projection 删除 `gold` 后 fit/predict 仍能运行。

学习器只比较 train transition 的 pre/post：对于每个 intervention source key，收集至少
一次被改变过的 target cells，形成 type-level interventional impact graph。它偏向 recall，
没有直接复制 gold adjacency，也**没有学习 regime gate**；不同 regime 的影响取并集，
所以 false positives 会反映在 precision 和成本上。

## 4. Novel test split

T1 不是在 train episode 上回放。固定 test split 包含：

- **未见实体**：train 的 Alice/Bao/Camila/Dev 与 test 的 Farid/Grace 及其城市完全不重叠，
  `train_test_entity_overlap = 0`；
- **未见数值**：`flight.arrival_hour` 的 22、23 和 `hotel.deadline` 的 15 只在 test 干预；
- **未见表面模板**：test 使用 `paraphrased` query template；
- **held-out regime combination**：`[attraction.flexible=false,
  dinner.flexible=false, hotel.late_checkin=false]` 未出现在 train。

需要准确理解这个 generalization 边界：train/test 使用同一组 state-variable names 和同一
SCM schema；学习器预测时主要按 intervention source key 查 impact set。因此这里检验的是
已知 schema 下对新 traveler、数值、措辞和 regime 组合的影响泛化，不是从语言中发现
新变量或新本体。

## 5. T0：先证明单 key update 不够

运行：

```bash
PYTHONPATH=code python3 code/causal_benchmarks/dynamic_travel.py \
  --episodes 500 --seed 0 \
  --out results/development/causal_benchmarks/dynamic_travel.json \
  --audit-out results/development/causal_benchmarks/dynamic_travel_audit.json
```

Exact-KV 只应用显式 intervention；oracle propagation 用已知 SCM 重算状态。当前代码的
确定性结果：

| 指标 | Exact-KV | Oracle propagation |
|---|---:|---:|
| affected precision | 1.0000 | 1.0000 |
| affected recall | 0.4681 | 1.0000 |
| affected-state accuracy | 0.4681 | 1.0000 |
| full-state cell accuracy | 0.8951 | 1.0000 |
| episode success | 0.2000 | 1.0000 |

400/500 episodes 需要传播，query downstream leakage 为 0/997。Exact-KV 的 20% success
全部来自独立联系人负对照，不代表它能解决四类 itinerary propagation。T0 admission
通过只表示这个任务有传播 headroom，不表示 causal learning claim 已成立。

## 6. T1 六臂实验

生成 T1 报告：

```bash
PYTHONPATH=code python3 code/causal_benchmarks/dynamic_travel.py \
  --episodes 500 --seed 0 \
  --t1-out results/development/causal_benchmarks/dynamic_travel_t1.json

PYTHONPATH=code python3 -m unittest \
  causal_benchmarks.tests.test_dynamic_travel -v
```

六个冻结 arm 为：

| Arm | 实际含义 |
|---|---|
| `exact_kv` | 只预测显式 intervention node |
| `domain_solver` | 手写 `_recompute` SCM，读取 runtime state 后精确计算 changed nodes |
| `matched_lexical` | query-aware lexical cell ranking，每个 episode 与 learned arm 使用相同 cell budget |
| `learned_graph` | 只从 train observed transitions 得到的 source→impact union |
| `oracle_graph` | evaluator upper bound；当前实现直接使用 gold affected nodes，而非可部署 runtime selector |
| `full_state` | 把 19 个 state cells 全部视为 selected/affected，作为 full-context 上界 |

### 共享 oracle value decoder 边界

六臂都调用同一个 `_prediction_from_impacted`：它用确定性 SCM 计算 oracle post-state，但
**只写 selector 预测的 nodes**。因此 `task_success_rate` 检验的是 predicted impact set
是否足以重建最终状态；它不评价：

- 自然语言到 intervention key 的解析；
- dependency/value equation 的学习；
- 搜索、重订和工具调用；
- LLM 生成计划的正确性。

所以 T1 是 selection-isolation 实验，不是 end-to-end travel agent 结果。`oracle_graph`
和共享 decoder 都是 evaluator upper bound，不能作为部署方法。

### 结果

以下均为 100 个 test episodes 的 macro 指标：

| Arm | affected P | affected R | neg. spec. | cells | compact chars | compact token proxy | verbose chars | task success |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Exact-KV | 1.0000 | 0.4638 | 1.0000 | 1.00 | 27.45 | 7.47 | 74.45 | 0.2000 |
| Domain solver | 1.0000 | 1.0000 | 1.0000 | 3.12 | 85.01 | 21.63 | 235.89 | 1.0000 |
| Matched lexical | 0.6857 | 0.6914 | 1.0000 | 3.20 | 87.01 | 22.27 | 241.81 | 0.4000 |
| Learned graph | 0.9886 | 1.0000 | 1.0000 | 3.20 | 87.65 | 22.27 | 242.45 | 1.0000 |
| Oracle graph | 1.0000 | 1.0000 | 1.0000 | 3.12 | 85.01 | 21.63 | 235.89 | 1.0000 |
| Full state | 0.1642 | 1.0000 | 0.0000 | 19.00 | 489.14 | 122.69 | 1418.14 | 1.0000 |

Learned selector 在与 matched lexical 相同的 3.20-cell budget 下，把 recall 从 0.6914
提高到 1.0，并完整保留负对照。它的 0.9886 precision 也如实暴露了“跨 regime 取并集、
尚未学 gate”带来的少量 over-selection。

## 7. Selection × serialization 正交报告

对每个 arm，先冻结 selected-node set，再分别序列化：

- `compact`：相同 selected values 的紧凑 JSON；
- `verbose`：相同 selected values 的自然语言完整句。

两种格式不改变 selector、affected P/R 或 task success，只改变字符数和
`ceil(chars/4)` token proxy。因此 learned-vs-lexical 是 selection 对比，compact-vs-verbose
是 serialization 对比，不能把两种收益捆绑解释。

例如 learned arm 固定 3.20 cells 时是 87.65 vs 242.45 chars；domain solver 固定
3.12 cells 时是 85.01 vs 235.89 chars；full state 固定 19 cells 时是 489.14 vs
1418.14 chars。

## 8. 为什么 `causal_learning_claim_pass = false`

T1 admission 的以下条件通过：

- train/test runtime isolation；
- unseen entities 和 numeric values；
- held-out regime combination；
- learned 在匹配预算下超过 lexical retrieval；
- learned negative-control specificity = 1.0。

但最关键的 `learned_pareto_dominates_domain_solver` 为 false：

```text
                         task success   selected cells   compact chars   precision
domain solver                1.0            3.12             85.01         1.0000
learned graph                1.0            3.20             87.65         0.9886
```

Learned graph 只追平 domain solver 的正确率，却选择略多 cells、使用略多字符、precision
略低；它没有在 correctness/cost 上 Pareto 支配最强手写基线。因此报告必须输出：

```text
learned_pareto_dominates_domain_solver = false
causal_learning_claim_pass = false
```

击败同预算 lexical retrieval 说明 observed transitions 对 impact selection 有用，但不能
证明 causal graph 对这个已知、小型 itinerary SCM 是不可替代的。当前最诚实的 claim 是：

> train-only interventional outcomes 可以学习一个高 recall 的 dependency-aware impact
> selector，并泛化到本原型定义的新实体、值、模板和 regime；但没有优于已知领域规则。

## 9. 后续必须补齐

1. 学习 regime-conditioned gates，而不是把各 regime impact 简单取并集；
2. 用不共享 oracle SCM 的真实 value decoder 做 end-to-end；
3. 扩大 schema、机制和 itinerary 数，避免 source-key impact table 记忆五类机制；
4. 加入多 traveler、多日、大规模 distractors，并匹配 selected-cell/token budget；
5. 单独评价自然语言到变量的 mapping；
6. 将 learned selector 替换为冻结的 GRACE/结构学习器，再与 domain solver 比较。

在这些条件完成前，Dynamic Travel 可作为可审计的 train-only impact-selection 原型，
不能作为“causal memory 已经优于简单领域程序”的主证据。
