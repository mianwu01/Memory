# 四任务真实 API 六臂 v1：结果、缺失与 claim 边界

本页记录 2026-08-31 冻结并执行的 DeepSeek API test。它不覆盖 calibration 失败，
不把 oracle arm 写成 learned discovery，也不把未评分响应补成语义零分。

## 1. 冻结范围与完整性

- model：`deepseek-v4-flash`，temperature 0，paired decoder seed；
- 4 task × 12 novel-test episodes × 6 arms = **288 requests**；
- protocol case-manifest SHA-256：
  `c93488bf499264cae350186255dfd15725b35b22e026320fd798f265c09dd223`；
- 结果：288/288 request rows，309 ledger events；protocol/result/ledger/prompt/seed/
  response hashes 的 integrity audit 为 `complete=true`；
- ledger 总量：514,032 input tokens、187,648 cached input tokens、574,475 output
  tokens、`$6.607622`、累计 API duration 4,959.22 秒；并发 wall time 不能由该累计值替代；
- scope 为 `full_scope_complete=true`，但最终为 `experiment_complete=false`。

最后一项不是方法得了 0 分。284/288 requests 有可评分响应；4 个 full-state requests
在三次尝试后仍未满足输出合同，作为 missing 保留：Travel 2、Shopping 1、Search 1。
summary 的 `semantic_coverage` 因而分别为 `0.833/0.917/0.917`。这些 missing 不进入
`endpoint_success_valid_only` 的分母。

## 2. 六臂结果

下表的 Selection F1 是四任务 macro；Endpoint 是各 task 的 valid-only episode-success
再做 macro。它们必须与 Coverage 一起读。tokens/cost 是四任务总和。

| Arm | Coverage | Selection F1 | Endpoint valid-only | Input | Output | Cost |
|---|---:|---:|---:|---:|---:|---:|
| Exact-KV | 1.000 | 0.485 | 0.167 | 38,782 | 9,995 | $0.192 |
| Domain reachability | 1.000 | 0.887 | 1.000 | 77,116 | 49,220 | $0.583 |
| Matched retrieval | 1.000 | 0.433 | 0.167 | 72,691 | 156,457 | $1.738 |
| Learned selector | 1.000 | **1.000** | 1.000 | **71,381** | **42,113** | **$0.533** |
| Oracle potential graph | 1.000 | 0.867 | 1.000 | 78,327 | 51,262 | $0.606 |
| Full state/history | 0.917 | 0.284 | 1.000 valid-only | 175,735 | 265,428 | $2.957 |

Task-level endpoint/selection 结果：

| Task | Exact endpoint | Matched endpoint | Learned F1 / endpoint | Domain F1 / endpoint | Full coverage |
|---|---:|---:|---:|---:|---:|
| Dynamic Travel | 0.167 | 0.167 | 1.000 / 1.000 | 0.893 / 1.000 | 0.833 |
| Dynamic Shopping | 0.000 | 0.000 | 1.000 / 1.000 | 0.857 / 1.000 | 0.917 |
| Dynamic Search | 0.333 | 0.333 | 1.000 / 1.000 | 0.800 / 1.000 | 0.917 |
| Causal Formal | 0.167 | 0.167 | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 |

这些数字支持一个窄结论：给定冻结的 selection plan，compact learned context 能让真实
API 完成 value update；它比 full-state 少输入、输出、费用与累计 API duration。它不支持
“learned causal structure 是四任务完成所必需”。

## 3. 为什么本轮不能写成 confirmatory causal win

### 3.1 v1 的 `domain_solver` 不是 strongest domain baseline

冻结 arm 实际是 conservative potential reachability。仓库已有的 Travel simulator rule、
Shopping compatibility/budget program、Search provenance program 和 Formal executable
dataflow 都能在 gold-free runtime state 上求当前 delta。因而 learned arm 的 precision/
context 优势只能解释为胜过保守 reachability，不能解释为胜过最强领域程序。

### 3.2 三个 task 仍有 structured shortcut

- Search：episode-specific opaque provenance 在 history 中，query 不能命名 descendants；
  task validity 为 PASS，但 learned arm 是 learned gate + provenance parser 的 hybrid。
- Shopping：真实 intervention/gate/multihop 均存在，但 `(kind, slot, observable regime)`
  impact-table 可以复制 learner；PARTIAL。
- Travel：真实 propagation 存在，但固定小 schema 下的 `source → train impact union` 可以
  复制 learner；PARTIAL。
- Formal：`intervention.kind` 暴露 active/inactive gate，固定拓扑允许
  `(task,node,kind) → affected template`；对 hidden-dependency claim 为 NO-GO。

因此四任务 v1 整体对 **learned hidden causal-structure necessity = NO-GO**。这是一项静态
设计审计结论，不是看见 API 分数后才调出的结果。

### 3.3 重试策略混合了工程错误和语义合同错误

ledger 中有 25 个 error attempts：1 个 value type mismatch，24 个
`update-node set does not exactly match allowed_write_nodes`。后者是可解析输出的内容合同
错误，不能安全地一概视为 provider/format engineering error 并重试到成功。本轮有 11 个
request 在重试后变为可评分，故 `endpoint_success_valid_only=1.0` 只能读作“条件于最终
合同有效响应的 value accuracy”，不能读作一次调用的真实 endpoint reliability。

runner 已实现 `causal-api-failure-policy/v2`：只对 transport、empty/truncated、JSON
syntax/type-level failure 重试；节点集/identity/unknown/duplicate node 不匹配作为 terminal
semantic endpoint failure 原样落盘。该修复只作用于未来新 protocol，v1 artifacts 不回填、
不 gold-repair、不重新筛选响应；新 auditor 会明确拒绝把 v1 的 semantic retry-sifting 当成
修复后协议证据。

## 4. Artifact lineage

| Artifact | SHA-256 |
|---|---|
| `api_six_arm_test_v1_protocol.json` | `d3dbf5fe1aae17a213fc6a2147eb3fb86fae40718f9f5e88382046a9f011ff35` |
| `api_six_arm_test_v1_results.jsonl` | `6e96501abab0d8c1476ecb2f7aa716e21c87a43e0ee1703e24a7d0a1c84cfcf9` |
| `api_six_arm_test_v1_usage.jsonl` | `9779f6816ef82946404198ffe825fb889b6a988fe2013cab5a004916b6181a42` |
| `api_six_arm_test_v1_summary.json` | `066513cd6f27616d6c65dea680b02674a2f113b9e7cb75b8e16b2f5f5cc06c17` |

dev v1–v8 是 calibration lineage，均保留；v9 是 96-call decoder gate，证明 oracle
write/context 条件下 decoder 能工作，不证明 selection。六臂 v1 是第一次把 value-free
SelectionPlan 接到真实 API；它的负面设计审计和工程缺失同样属于最终结果。
