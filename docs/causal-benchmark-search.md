# Dynamic Search：从静态检索改造成干预传播任务

## 结论

MemoryArena 现有 `search` 不能作为 causal memory 的主实验。它把一个
BrowseComp-Plus 问题拆成 subquery，逐个搜索并把预测答案和 trace 写入 memory，最后再用
原问题读取这些 memory 做聚合：

- `browsecomp_plus_env.py:189-222` 逐个执行 subquery，并写入
  `Subquery / Predicted Answer / Trace`；
- `browsecomp_plus_env.py:281-314` 最终再次执行原始 query；
- `agent/search.py:55-60` 只在执行搜索前调用 `wrap_user_prompt` 做一般记忆检索；
- 官方 runner 的指标是最终回答、qrel recall 和工具调用数
  (`run_search.py:346-364`)。

这里没有“来源被撤回后，哪些旧结论失效”的环境转移，也没有 intervention 或
counterfactual gold。因此，现有任务最多检验一般检索和多证据聚合。为避免污染上游
checkout，本原型全部放在：

- `code/causal_benchmarks/dynamic_search.py`
- `code/causal_benchmarks/tests/test_dynamic_search.py`

没有修改 `benchmarks/MemoryArena`。

T1 的最终结论也必须先说清楚：learned impact selector 在 novel test 上达到 oracle，但与
强 provenance parser/domain solver 在相同 8-cell budget 下完全持平。因此本任务当前证明了
“从 observed transitions 学到的 gate 可以泛化”，却**没有**证明 learned causal structure
优于 dependency/provenance memory；`supports_causal_learning_claim = false`。

## 新任务的世界模型

每个 episode 是一个动态证据库，包含一个目标实体和三个 distractor 实体。节点使用不透明
ID，不能由 query 中的实体名直接拼出下游 key：

```text
source:S...... ─┐
                ├─[trust / independence gate]─> claim:C......
document:D..... ┘                                  │
                                                   v
                                             answer:A......
                                                   │
                                                   v
                                              brief:B......
```

每个实体有四类来源：官方 registry、journal、低可信 newswire、citation mirror。claim 的
结构方程为：

- high-trust 独立证据权重 3；
- medium-trust 独立证据权重 1；
- low-trust 证据被 gate 掉；
- citation mirror 不是独立证据，即使高可信也不能重复计票；
- 总分 `>= 2` 为 `verified`，`<= -2` 为 `disproved`，其他为 `unresolved`；
- answer 映射为 `YES / NO / UNCERTAIN`，brief 再映射为发布、纠正或暂缓。

query 只给一个 source 或 document intervention，例如：

```text
document:D0000574172 is replaced by version 2, which reports refute.
Apply this event and bring the evidence memory up to date.
```

query 不给 `claim:C...`、`answer:A...`、`brief:B...`。这些 ID 与依赖关系只存在于更早的
history/provenance 记录和 evaluator-owned graph 中。因此，Exact-KV 可以正确写入
`document:D0000574172`，但无法仅靠当前 query 知道要重算哪份 dossier。

## Intervention 与 regime

六类场景等比例生成：

| 场景 | 干预 | 正确传播 |
|---|---|---|
| `pivotal_retraction` | 高可信原始文档撤回 | document → claim → answer → brief |
| `entity_version_correction` | v1 support 被 v2（test 为 held-out v3）refute 替换 | document → claim → answer → brief |
| `source_trust_demotion` | train: high→low；test: held-out high→medium | source → claim → answer → brief |
| `source_trust_promotion` | train: low→high；test: held-out medium→high | source → claim → answer → brief |
| `low_trust_update_negative` | 被隔离的低可信文档更新 | 只改 document，不传播 |
| `citation_mirror_retraction_negative` | 非独立 mirror 撤回 | 只改 document，不传播 |

后两类是必要负对照。一个无条件沿图扩散的系统会在它们上产生 false positive；oracle 必须
先判断 trust/independence regime，再决定 edge 是否 active。edge 关闭和 edge 开启都可能是
干预结果，所以 simulator 使用静态 structural graph 找 potential child，再用结构方程判断
child 是否真的变化。

## 输出契约

每行是一个 `causal-memory-benchmark/v1` JSON episode，兼容统一协议：

- runtime 可见：`history`、`memory_state`、`query.text`、已解析的单一
  `query.intervention`；
- 只有 train episode 带 runtime-visible
  `observed_transition={pre_state, intervention, post_state}`；
- `runtime_view(..., training=False)` 对 dev/test 删除 `gold`，且不返回任何 outcome；
- evaluator-only：`gold.graph`、`pre_active_edges`、`active_edges`、
  `affected_nodes`、`required_reads`、`post_state`、`final_answers`；
- `affected_nodes` 严格等于 pre/post counterfactual delta；
- `required_reads` 对正例包含被干预节点、同一 claim 的 co-parent evidence、旧的
  claim/answer/brief；对 gate 明确关闭的负例只需文档和其 source gate。

统一 runner 可调用：

```python
generate_dataset(episodes=120, seed=17) -> list[dict]
audit_dataset(dataset) -> dict
```

## 无 LLM T0

运行：

```bash
python3 code/causal_benchmarks/dynamic_search.py \
  --episodes 120 \
  --seed 17 \
  --out /tmp/dynamic_search_120.jsonl \
  --audit
```

seed 17 的确定性结果：

| 指标 | Query-only / Exact-KV | Oracle propagation |
|---|---:|---:|
| affected-node precision | 1.000 | 1.000 |
| affected-node recall | 0.500 | 1.000 |
| affected-state accuracy | 0.500 | 1.000 |
| final-answer accuracy（全体） | 0.333 | 1.000 |
| final-answer accuracy（需传播的 80 例） | 0.000 | 1.000 |
| required-read recall | 0.227 | 1.000 |
| negative-control specificity | 1.000 | 1.000 |

额外诊断：

- 120 个 episode 中 80 个（66.7%）确实需要多节点传播；
- 40 个（33.3%）为 gated negative control；
- 六个场景各 20 个；
- query 中下游 affected-node ID 泄漏率为 0；
- Oracle 的 full-state、final answer 和 brief 均为 1.0。

Exact-KV 的 full-state accuracy 仍有 0.955，因为大量 distractor 节点无需变化。这说明不能用
全状态准确率掩盖传播失败，主指标必须是 affected recall、affected-state accuracy 和
propagation-only answer accuracy。

测试：

```bash
PYTHONPATH=code python3 -m unittest \
  causal_benchmarks.tests.test_dynamic_search -v
```

目前 11 个 Search 测试覆盖确定性、schema、query 无 descendant 泄漏、正例传播、regime
负对照、runtime 隔离、删除 evaluator `gold` 后 learner/provenance 仍可运行、novel split、
六臂、selection × serialization 正交消融、CLI 和 T0/T1 admission。

## T1：只从 observed transitions 学 impact selector

### Split 与禁止泄漏

120 episodes 按完整六场景 block 划分为 train/dev/test = 84/24/12，每个 split 都覆盖六类
场景。节点 ID 包含 episode namespace，所以 train/test overlap 为 0；实体池和 query template
也完全分离。test 还保留两类机制外推：

- train trust transitions：`high→low`、`low→high`；
- test held-out transitions：`high→medium`、`medium→high`；
- train correction 写入 version 2，test positive correction 写入 held-out version 3。

`LearnedImpactSelector.fit` 只接收 `runtime_view(train, training=True)`，从 pre/post delta 学到
typed impact edges、可信度 gate 和 independence gate；`predict` 拒绝含 `gold` 或
`observed_transition` 的对象。12 个 test runtime view 均不含 `gold`/outcome。单测还会直接把
raw evaluator episode 传给 `fit`，确认它抛错。

### 六臂与共享 decoder

| Arm | Selector / graph 来源 | Value decoder |
|---|---|---|
| Exact-KV | 当前 query 的 intervention key | 只写显式 key |
| Provenance-domain | 强 NL grammar parser 重建 citation/derivation graph，并按已知 gate 选 family | 共享 domain SCM |
| Matched lexical/structured | exact key + lexical/简单结构打分，cell budget 与 learned 逐例相同 | 读全 required family 才调用共享 SCM |
| Learned graph | train observed deltas 学 typed impact/gate；test 用 runtime provenance 实例化 opaque IDs | 共享 domain SCM |
| Oracle graph | evaluator-owned graph | 共享 domain SCM |
| Full history | 44 个状态 cell 全取 | 共享 domain SCM |

这里的 endpoint accuracy 只能解释为“selector 是否提供了足够状态”。因为 value equation 没有
被学习，它不是 learned end-to-end causal equation 的证据。

### seed 17 的确定性 T1 结果

以下均只在 12 个 novel test episodes 上评价：

| Arm | affected P/R | answer / brief | negative specificity | required-read recall | cells |
|---|---:|---:|---:|---:|---:|
| Exact-KV | 1.000 / 0.500 | 0.333 / 0.333 | 1.000 | 0.227 | 1 |
| Provenance-domain | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 | 1.000 | 8 |
| Matched lexical/structured | 1.000 / 0.500 | 0.333 / 0.333 | 1.000 | 0.803 | 8 |
| Learned graph | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 | 1.000 | 8 |
| Oracle graph | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 | 1.000 | 8 |
| Full history | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 | 1.000 | 44 |

learned selector 学出的 typed edges 为 `document/source→claim→answer→brief`，同时从负例学到
independence gate；它成功泛化到 held-out trust transitions 和 version 3。它显著优于同为
8-cell 的 lexical arm，但没有优于同为 8-cell 的 provenance-domain arm。

### Selection × serialization 正交结果

每个 arm 的 selection 先冻结，再分别序列化为 verbose JSON 和 compact line format；因此同一
arm 的 affected/endpoint 指标和 selected cells 在两行完全相同。字符数仅作 token proxy，
没有宣称是真 tokenizer 计数。它只衡量送给共享 decoder 的 payload；provenance index 构建和
selector 扫描 history 的 CPU/延迟未计入，正式 e2e 必须另行打点，不能把下表当总系统成本。

| Arm | chars verbose → compact | char/4 proxy compact |
|---|---:|---:|
| Exact-KV | 649 → 244 | 61 |
| Provenance-domain | 3507 → 1262 | 316 |
| Matched lexical/structured | 1836 → 1082 | 270 |
| Learned graph | 3507 → 1262 | 316 |
| Oracle graph | 3777 → 1262 | 316 |
| Full history | 18021 → 6517 | 1629 |

compact serialization 不改变任何效果指标。learned 相对 full history 少 81.8% cells、约 80.6%
compact chars；但相对 provenance-domain 没有效果或成本优势。

## 科学边界：不要把 provenance 自动叫成 causal

必须区分三层问题：

1. **一般检索**：给问题，从静态 corpus 找相关文档。原 MemoryArena Search 属于这一层。
2. **provenance / dataflow memory**：记住 `D → C → A` 的引用或派生关系，并沿关系找下游。
   只恢复或遍历 citation chain，还不能证明 causal discovery。
3. **intervention propagation**：对 source/document 做 surgical update，按 regime-conditioned
   structural equation 重新计算 counterfactual post-state，同时正确处理“不应传播”的负例。

本原型因为有 `do` 风格干预、确定性 counterfactual simulator、active/inactive gate 和
post-state delta，可以检验第 3 层的**传播能力**。T1 也确实满足 train-only fit、test gold
隔离、novel IDs/entities/templates/regimes、matched-cell baseline 和正交序列化消融。

但结果触发了诚实 stop rule：learned 与强 provenance-domain 在效果、8-cell selection 和
compact chars 上完全相同。citation traversal 是 dependency baseline；没有 matched-budget
优势就不能把 learned 的 1.0 endpoint 写成 causal-learning 胜利。下一版若要翻转这个裁决，
必须让依赖不能被显式 provenance grammar 完整恢复，例如从多次不完全 observational/
interventional trajectories 中识别 latent routing 或 context-dependent edge，并继续保留当前
强 baseline。当前 Search 可以作为合格的 intervention-propagation benchmark，但不是
“causal discovery 优于 provenance”正结果。
