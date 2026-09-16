# Dynamic Shopping：从状态追踪改造成干预传播基准

本页记录一个**隔离原型**，不是对 `benchmarks/MemoryArena` 上游 checkout 的
补丁。实现位于 `code/causal_benchmarks/dynamic_shopping.py`，遵循
`causal-memory-benchmark/v1` 通用协议。

## 1. 为什么原 shopping 不能直接承担 causal claim

对 MemoryArena `bundled_shopping` 150 个任务、900 个步骤的既有审计显示：

- 150/150 个任务在指令中明示全局预算；
- 后 750 个步骤全部明示“须与此前购得商品兼容”；
- 900/900 个步骤把兼容性映射写在当前步骤文本里；
- 历史中真正需要记住的是此前买到的属性值和累计花费，而不是隐藏的依赖结构。

因此原任务适合评价 history-borne state tracking，但 query-aware parser 已知道应当
检查前序购买和预算。它不能单独回答“学习到的依赖结构是否发现了 query 未点名的
downstream state”。完整审计见 `docs/benchmark-audit-c1c4.md`。

## 2. 改造后的任务语义

每个 episode 先在历史中建立一张已经购买完成的 PC 配件订单，之后只给一条简短的
现实事件，例如：

> The retailer cancelled CPU-A from this order. Repair the order using the
> existing requirements.

当前 query 只暴露单一 intervention key，例如
`availability.cpu_a := false`，不会列出 motherboard、memory、cooler、power supply、
monitor 或账本等 downstream cells。系统必须从记忆中读取当前订单，并按依赖传播：

```text
availability.cpu_a
  -> cart.cpu
      -> cart.motherboard -> cart.memory
      -> cart.cooler      -> cart.case
      -> cart.power_supply
      -> price.* -> subtotal -> total -> remaining_budget
```

原型覆盖三类干预：

1. CPU/GPU 被取消，必须寻找替代品并检查后续兼容链；
2. 已购 CPU 价格修正，必须更新累计预算，hard-cap regime 下还会触发后续商品降级；
3. display-adapter policy 改变，可能使已有显示设备失效。

负对照 `cart.keyboard`、`account.shipping_region` 和 `account.gift_message` 必须保持
不变。`case` 等潜在 descendant 也可能经检查后保持不变；因此 gold 区分
`required_reads`（必须检查）与 `affected_nodes`（反事实中实际改变）。

## 3. Regime-dependent edge

同一个 `GPU-Compact cancelled` 干预生成配对 regime：

- `policy.display_mode = strict`：GPU 输出变化会使 monitor 失配，
  `cart.gpu -> cart.monitor` 为 active edge；
- `policy.display_mode = adapters_allowed`：adapter 吸收输出变化，monitor 不变，
  该 edge 不激活。

预算也有 gated edge：只有 `policy.budget_mode = hard_cap` 且变化造成超支时，
`ledger.subtotal_before_monitor -> cart.monitor` 才传播到商品重选；flexible regime
只更新账本。T1 test 还保留训练中没有出现过的组合：CPU cancellation × hard cap。
训练只分别见过 CPU cancellation × flexible 和 price change × hard cap，学习器必须组合
两种历史机制。

## 4. Episode schema 与泄漏边界

每条数据包含：

- runtime-observable：`history`、`memory_state`、`query.text`、
  `query.intervention`；
- evaluator-only：`gold.graph`、`gold.active_edges`、`gold.affected_nodes`、
  `gold.affected_state`、`gold.required_reads`、`gold.required_tool_queries`、
  `gold.propagation_paths`、`gold.post_state` 和 generalization/negative-control
  `gold.audit_annotations`。scenario、novelty 与 control 标注不放进 runtime-visible
  `metadata`，避免 selector 利用评测标签。

只有 `split=train` 额外包含 runtime-visible：

```text
observed_transition = {pre_state, intervention, post_state}
```

这是已经完成的历史干预结果，不含 `graph`、`active_edges`、`affected_nodes` 或
`required_reads`。dev/test 原始 episode 都没有 `observed_transition`；调用统一
`runtime_view(..., training=False)` 后也没有 outcome。learner 的 `fit` 若收到带 `gold`
的对象会直接拒绝。

`query.explicit_state_keys` 是泄漏审计标注，永远只有 intervention target。正式 runtime
不得读取 `gold`。商品事实由模块内的确定性 `CATALOG` 支撑 simulator；正式 agent 集成时
应作为环境 search/catalog tool 提供，而不是塞进 memory selector 的输入。结构化
`memory_state` 只是为了把 parser failure 与 propagation failure
解耦；它能证明的最多是给定变量映射后的传播能力，不能证明从自然语言中发现变量。

生成器和 simulator 都是 deterministic 的。给定相同 `--episodes/--seed` 会得到逐字
一致的数据。候选商品按 `(price, product_id)` 排序，保持当前商品优先；只有当前商品
不可用/不兼容，或 hard budget 超限时才替换。

## 5. Baselines 与 T0

实现两个零 LLM baseline：

- `exact_key_baseline`：只执行 query 显式点名的 key/value，不做传播；
- `oracle_propagation_baseline`：只读取 runtime state 和 intervention，调用确定性规则，
  不读取 `gold`。

命令：

```bash
python3 code/causal_benchmarks/dynamic_shopping.py \
  --episodes 60 --seed 7 --audit --t1

python3 code/causal_benchmarks/dynamic_shopping.py \
  --episodes 60 --seed 7 \
  --out /tmp/dynamic-shopping.json --audit

PYTHONPATH=code python3 -m unittest \
  causal_benchmarks.tests.test_dynamic_shopping -v
```

`60 episodes / seed 7` 的确定性结果：

| 指标 | Exact-KV | Oracle propagation |
|---|---:|---:|
| episode success | 0.0000 | 1.0000 |
| affected-node recall | 0.1607 | 1.0000 |
| affected-state accuracy | 0.1607 | 1.0000 |
| full-state cell accuracy | 0.8642 | 1.0000 |

额外 admission checks 均通过：

- propagation-required：60/60；
- query 未枚举 downstream：100%；
- 至少两跳传播：100%；
- 负对照保持：100%；
- strict/adapters regime contrast：通过；
- 综合 `t0_pass = true`。

这里同时说明为什么不能只报告 full-state cell accuracy：Exact-KV 虽然整张稀疏状态表
有 86.42% cells 偶然保持正确，却没有一个 episode 完整完成，且只召回 16.07% 的
真实变化。

## 6. T1：只从历史 outcome 学 impact selector

`ObservedImpactSelector.fit` 的输入是 train `runtime_view`，它通过比较可见的 pre/post
outcome 得到变化 cells，按以下 runtime 特征统计稳定 impact template：

- intervention kind；
- 被干预 state namespace 与商品 slot；
- display/budget regime；
- concrete intervention entity 被抽象成 `$target`。

`CPU-Nova` 虽未出现在 train/dev runtime state，selector 仍使用环境 `CATALOG` 将新 ID
映射到已知 `cpu` slot；因此这是 **known-schema 下的新实体泛化**，不是无监督本体发现。

此外，它从 train 中 price hard-cap 与 flexible 的差集学习
`{cart.monitor, price.monitor}` 这一 hard-budget residual，并把它与 test-only 的
CPU cancellation × hard cap 组合。这里的 `learned_graph` arm 实际是一个很小的
**observed-impact learner**，不是 GRACE，也不是从自然语言发现完整 SCM；名称只表示它
承担 learned dependency selector 的实验位置。

### Novel test split

`60 episodes / seed 7` 固定划分为 train/dev/test = 30/12/18：

- train query 只有 `train:*` templates，并且保存 observed outcomes；
- test 18/18 使用未见 query templates，template vocabulary overlap = 0；
- 5 个 test episodes 使用 train/dev runtime state 中完全未出现的 `CPU-Nova`；
- 4 个 test episodes 使用未见价格 intervention values；
- 2 个 test episodes 是 held-out `CPU cancellation × hard cap`，成功率 1.0；
- train/test episode ID overlap、runtime gold leakage、dev/test outcome leakage 均为 0。

### 六臂与共同 decoder

| Arm | 信息和作用 |
|---|---|
| Exact-KV | 只选择显式 intervention cell |
| Domain solver | 手写完整 compatibility/budget 规则，最强领域基线 |
| Matched retrieval | lexical + state-key structured ranking；逐 episode 与 learned arm 完全相同 cell budget |
| Learned graph | 仅从 train observed transitions 拟合的 impact selector |
| Oracle graph | evaluator-only gold active graph reachability，不直接读取 gold affected set |
| Full state/history | 选择全部 materialized state/history |

所有臂共享 `shared_oracle_value_decoder`：它只为 selector 预测的 nodes 写入 evaluator
counterfactual value。因此下面的 `task success` 只隔离 **impact selection**，不是商品搜索、
值生成或 agent end-to-end success。false positive 不破坏状态，漏掉任何真实变化则失败。

### T1 结果

| Arm | affected P | affected R | neg. specificity | required-read R | cells | compact chars | task success |
|---|---:|---:|---:|---:|---:|---:|---:|
| Exact-KV | 1.0000 | 0.1501 | 1.0000 | 0.0579 | 1.00 | 133.1 | 0.0000 |
| Domain solver | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 21.33 | 707.3 | 1.0000 |
| Matched retrieval | 0.2205 | 0.2205 | 0.8889 | 0.2078 | 7.83 | 342.5 | 0.0000 |
| Learned graph | 1.0000 | 1.0000 | 1.0000 | 0.2515 | 7.83 | 337.7 | 1.0000 |
| Oracle graph | 0.8114 | 1.0000 | 1.0000 | 0.3633 | 10.28 | 403.7 | 1.0000 |
| Full state/history | 0.1724 | 1.0000 | 0.0000 | 1.0000 | 45.28 | 1495.9 | 1.0000 |

`required-read R` 单列是为了避免新的混淆：learned impact selector 虽然完美预测了哪些
cells 最终会改变，但只覆盖 25.15% 的 simulator required reads；它没有读取那些经检查后
保持不变的兼容项，也没有收齐重算账本所需的全部 price cells。其 100% task success
依赖共同 oracle value decoder，不能外推成真实 decoder 已经可解。

### Serialization 正交消融

每个 selector 固定完全相同的 selected-cell set，再分别序列化为：

- `compact`：紧凑 key/value state；
- `verbose`：同一组 state cells 的带来源记录和冗余历史证据。

选择指标在两种格式间不变，只报告字符数和 `ceil(chars/4)` token proxy。例如 learned
arm 为 337.7 vs 1831.9 chars；domain solver 为 707.3 vs 4382.7 chars。因而不能把
compact serialization 的收益归因于 learned selection。

## 7. 科学结论与下一道门

T1 的诚实结论是：learned selector 在相同 7.83-cell budget 下显著超过当前 matched
lexical/structured retrieval，并且能泛化到本原型定义的未见实体、值、表面模板和一个
held-out regime combination；但它在 task success 上只是 **追平** domain solver 的
100%，没有击败它。报告因此固定输出：

```text
learned_beats_domain_solver_on_task_success = false
learned_matches_domain_solver_on_task_success = true
causal_advantage_established = false
```

所以目前可以说“历史 outcome 能学习一个有效的 dependency-aware impact selector”，
不能说“causal graph 对 shopping 是不可替代的”。

下一阶段至少需要：

1. 学习 required-read selector，而不只学习最终 changed-node template；
2. 用不读取 evaluator post-state 的真实 compatibility/value decoder 做 end-to-end；
3. 扩大 catalog、机制和 regime 数，避免六类模板被频率表记忆；
4. 加多用户、多订单和不可见 distractors，并在 matched token/cell budget 下重跑；
5. 将 simple observed-impact learner 换成冻结的 GRACE/结构学习器，再与 domain solver 比；
6. 单独评价自然语言到 state key 的 mapping。

## 8. 保留的总体限制

尤其要避免混淆：dictionary 适合**存储和精确读取一个 cell**；这里的 causal claim 只
针对“干预后还应读取、验证和改写哪些未点名 cells”。如果 hard-coded schema solver 与
learned graph 持平，就只能表述为 dependency-aware state maintenance，而不能声称图学习
不可替代。
