# Hidden Routing v2：fail-closed microbenchmark audit

`code/causal_benchmarks/hidden_routing_v2.py` 是一个与 v1 完全隔离的、API-free
合成环境。它不修改 MemoryArena 注册、六臂 prompt/protocol、API runner 或既有正式结果。

当前审计结论是 **PARTIAL**，不是 confirmatory PASS。它支持的范围仅为：

- 从 train completed transitions 识别一个小型 latent route/gate codebook；
- 将该 codebook 应用于 test 的显式 route records；
- 精确恢复稀疏 affected-node mask。

它不支持以下更强结论：

- learned hidden causal structure 对任务正确性是必要的；
- learner 完成了从事件中发现图结构；
- Travel、Shopping、Search、Formal 构成四个独立领域复现；
- 当前 mask-only 结果可以外推到 end-to-end causal memory。

## 环境与已知信息边界

每个 episode 包含一个 opaque state node 的单点 intervention、多跳路由、checkpoint
gate、evaluator-only graph/post-state，以及仅 train 可见的 completed
`(pre, intervention, post)` transition。

Runtime history 的每条 `route_observation` 会给出：

- 一条 potential edge 的两个 endpoint；
- route code；
- 可选的 gate node 与 gate code。

History 不直接解释 route direction 和 gate polarity。但是当前生成器对每条 evaluator
potential edge 都生成恰好一条这样的 record。因此，runtime 已经逐边暴露 potential graph
的无向 endpoint skeleton，隐藏的只是每个领域 2 个 route-direction bits 和 2 个
gate-polarity bits。审计将此报告为 `history_potential_edge_exposure_rate = 1.0`，并使
confirmatory admission fail。

## 公平的 train-enabled program

所有 non-oracle baseline 都允许访问同一批 train runtime `observed_transition`；是否利用
这些信息是方法自己的选择。新增 `ConsistentCodebookProgram`：

1. 枚举 history 中 route/gate alphabets 对应的全部 codebook；
2. 只保留与所有 train pre/post deltas 完全一致的配置；
3. test 时对所有剩余配置的 directed active reachability 取并集。

该 program 不读取 evaluator gold、designer codebook、dev/test outcome 或 task-card
equations。若 train evidence 有歧义，它会输出 recall-safe superset；若 evidence 唯一确定
codebook，则输出 exact mask。当前数据每领域有 16 个候选，训练后只剩 1 个，program 与
`learned_graph` 都达到 exact-mask rate 1.0。因此 learned arm 没有相对这个公平程序的
独占 headroom。

## Baseline matrix

| Baseline | 运行方式与信息边界 |
|---|---|
| Exact-KV | 只返回 query target；允许但不需要 train outcomes |
| Source union | 用 train deltas 学 source-level conservative union |
| Source + visible regime table | 用 train deltas 与可见 boolean counts 建表 |
| Matched retrieval | query-target 一跳共现排序；预算与 learned mask 对齐 |
| Learned graph | train-only codebook selection + eval history reachability |
| Consistent-codebook program | 同一 train outcomes 上枚举一致 codebooks，test 取 union |
| Zero-shot conservative program | 将 eval history routes 当无向且 active，不使用 code semantics |
| Oracle graph | evaluator-only active graph reachability |

原 `gold_free_program` 仍保留用于度量 zero-shot conservative closure，但不再称为
“strongest gold-free baseline”，因为它主动忽略了可见 codes 和允许使用的 train outcomes。

## 三项 fail-closed 检查

### 1. Runtime 是否逐边暴露 potential graph

审计比较 history endpoint pairs 与 evaluator potential-edge endpoint pairs。当前 exposure
rate 为 1.0，所以 `history_does_not_enumerate_potential_graph = false`。

### 2. 保守充分超集是否已经解决 mask-only 目标

Mask scorer 同时报告 exactness 与 `sufficient_mask_rate`。如果非精确 baseline 满足
`gold affected_nodes ⊆ predicted mask` 的比例为 1.0，那么在当前没有 value decoder、真实
错误写入或强制 context budget 的层面，它已经提供完成任务所需的全部节点。精确 mask 的
F1/写入量优势只能证明稀疏性或效率，不能证明 correctness necessity。

当前 source union、source-regime table 和 zero-shot conservative program 均是 100%
sufficient supersets。因此：

- `mask_only_task_solved_by_sufficient_superset = true`；
- `correctness_necessity_supported = false`。

### 3. 四域是否只是 surface relabeling

Suite audit 会移除 opaque IDs、code words、domain nouns、raw values 和 intervention
magnitude，同时保留 directed/gated topology、active graph 和 normalized response，再对每域
episode distribution 计算 fingerprint。当前四个 fingerprint 完全相同：四域是同一结构
DGP 的重命名副本，所以 `structurally_independent_domains = false`，总体 admission 必须失败。

## Verdict 语义

- `PASS`：confirmatory admission 的所有必要条件都成立；
- `PARTIAL`：codebook/sparse-mask microbenchmark 本身成立，但更强 necessity 或 replication
  claim 至少一项失败；
- `NO-GO`：连 microbenchmark 的访问边界、传播或精确恢复条件也不成立。

当前默认 artifact 的 verdict 是 `PARTIAL`，`all_domains_pass = false`。这是有意的
fail-closed 结果，不应通过调整阈值或数据分布把它改成 PASS。

## 访问边界

Non-oracle 方法允许：

- 同一批 train completed runtime transitions；
- eval pre-query history、pre-state 和结构化单点 intervention。

禁止：

- evaluator graph/active edges；
- evaluator affected nodes/required reads/post-state；
- generator designer codebook；
- task-card equations；
- dev/test completed outcomes。

`audit_dataset()` 先冻结全部 non-oracle masks，再读取 gold 做 post-hoc scoring。Oracle
单独读取 evaluator active graph。

## 运行

```bash
PYTHONPATH=code python3 -m unittest \
  causal_benchmarks.tests.test_hidden_routing_v2 -v

PYTHONPATH=code python3 code/causal_benchmarks/hidden_routing_v2.py \
  --episodes-per-domain 36 --seed 17 \
  --out results/development/causal_benchmarks/hidden_routing_v2_admission.json
```

当前层不包含自然语言 parser、value decoder、工具调用或真实领域 agent。后续若要支持
confirmatory causal-memory claim，需要让依赖结构从 partial trajectories/events 中推断，加入
真实 false-positive cost 或固定 context budget，并将四个 domain 改成不同机制的 DGP。
