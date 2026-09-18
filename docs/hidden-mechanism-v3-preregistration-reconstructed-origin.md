# Hidden Mechanism v3：四任务重建预注册（待 Yujia double-check）

## 0. 决策与冻结边界

本预注册取代“把 v1 task 继续调到正结果”的路线。

- 原 Travel 是 query-explicit slot update，对 causal necessity 为 NO-GO。
- dynamic/formal v1 有真实 intervention/propagation，但 dev killer audit 显示四项
  `source_union` 或 `query_signature` 都能形成 100% sufficient write superset；整体 stop。
- real-API six-arm v1 已执行，但 domain arm 偏弱、node-set semantic error 被旧策略重试；
  只能作为 conditional execution/efficiency evidence。
- hidden-routing v2 仍是四个同构外壳；history 逐边列 potential graph，公平的
  train-enabled codebook program 与 learner 完全并列；总体 verdict 为 PARTIAL。

因此 v3 不以“稀疏 mask F1 更高”代替 correctness。方法必须提交可执行、非幂等的 repair
transaction；多写一个 unaffected object 会真实改变 revision、费用、price lock、receipt 或
proof version，从而让 conservative superset endpoint 失败。

本页先冻结 formulation 与准入条件。按 Yujia 8-15 遗留要求，四个环境的 generator/API
实现和 confirmatory test 必须在她 double-check 本页后再冻结；此前只能做 development
generator、identifiability 与 baseline feasibility，不得调用 test API。

## 1. 统一 sample、variable 与 trajectory

统计单位是一个独立 world/template，而不是同一 world 下的相关 query。默认生成 80 个
world，每个 world 六个单干预 episode：

| Split | Worlds | Episodes | 用途 |
|---|---:|---:|---|
| train | 48 | 288 | 所有 non-oracle 方法共享 completed transitions |
| dev | 12 | 72 | generator、learner、baseline 与 API prompt 开发 |
| test | 20 | 120 | 一次冻结的 held-out confirmatory evaluation |

一个 transition sample 是：

\[
e=(H,S_0,I,A,S_1,R),\qquad S_0\xrightarrow{do(I),A}S_1,
\]

其中 `H` 是 pre-query 部分观测 history，`I` 是一个 intervention，`A` 是执行 action
trace，`R` 是 receipt。一个 trajectory 是同一 world/mechanism 下的 pre-query probes 与
completed transition；bootstrap/CI 以 world 为 cluster。

一个 variable 是一个有 opaque ID 的 scalar/categorical/object state cell。对象可包含多个
typed fields，但 discovery 与 read/write accounting 必须展开到 `(object_id, field)`；不能把
整段文本或整个 embedding 悄悄当成一个 causal variable。

Runtime 与 evaluator artifact 物理分离。Test runtime 只含：

```json
{
  "task": "...",
  "episode_id": "...",
  "split": "test",
  "history": [],
  "memory_state": {},
  "runtime_resources": {},
  "query": {
    "text": "...",
    "intervention": {
      "node": "...", "field": "...", "old_value": null,
      "new_value": null, "kind": "..."
    }
  }
}
```

Train runtime 才额外含：

```json
{
  "observed_transition": {
    "pre_state": {}, "intervention": {}, "action_trace": [],
    "post_state": {}, "receipt": {}
  }
}
```

Evaluator-only gold 包含 potential/pre-active/post-active graph、affected objects、instrumented
required reads/history IDs、oracle actions、post-state、receipt、topology hash 与
anti-shortcut pair ID。所有 non-oracle arm 共享同一个 train manifest hash。

## 2. 可执行输出与 primary endpoint

方法输出：

```json
{
  "declared_reads": ["history/resource/state IDs"],
  "actions": [
    {
      "op": "...",
      "object_id": "...",
      "expected_revision": 3,
      "payload": {}
    }
  ]
}
```

Evaluator 执行 action，而不是接受模型提交一张任意 post-state。Action 非幂等：即使 payload
等于当前值，也会增加 revision，并按领域消耗 token/lock、产生费用、更新 confirmation、
package、promotion 或 proof certificate。未写对象自然继承。

Primary：

```text
Executable Exact Success =
    all transactions legal
    AND materialized post_state == oracle post_state
    AND receipt == oracle receipt
```

同时报告 exact action/write set、affected P/R/F1、collateral transactions、instrumented
required-read recall、value accuracy、full-state exact match、utility regret、token/cost/latency。
Mask F1 是诊断，不是 primary。

必须有 superset mutation test：在 oracle plan 中加入一个 same-value unaffected write，
`Executable Exact Success` 必须从 1 变 0。

## 3. Dynamic Travel v3

### 3.1 Variables and DGP

每个 world 有 12–24 个 opaque reservations：flight/rail/transfer/activity/meal/hotel。公开
fields 包括 start/end、location、status、provider descriptor、confirmation、revision、
locked price、change tokens。候选 alternatives 通过相同 runtime resources 给所有 arm。

Generator latent mechanism：episode-specific temporal/location/resource prerequisite graph、
protected-bundle hypergraph、contextual transfer time、provider flexibility/change-token gate、
bundle-protection gate 与 alternative availability。Repair 用冻结的 lexicographic policy：

1. 保住 mandatory commitments；
2. 最大化 feasible reservation utility；
3. 最小化 fee；
4. 最少 transactions；
5. opaque candidate ID tie-break。

History 是同一 provider/world 的部分 probes：历史 connection quote、接受/拒绝改签、bundle
receipt、capacity observation 与 distractor；不直接列完整 graph/公式，也不 probe 最终
target 的同 value intervention。

### 3.2 Intervention and endpoint damage

Interventions：arrival/departure correction、service cancellation、terminal/location change、
provider deadline change。传播可跨 transfer → activity → protected meal → hotel/fallback。

Actions：shift/cancel/rebook/consume-token/accept-quote。对 unaffected reservation 做同值
shift 也会 `revision += 1`、消耗 token、更新 confirmation、收 fee、丢失 price lock。

Test 使用新 reservation/provider/city IDs、更长 timeline，以及 train-seen atomic motifs 的
held-out composition。相同 query/source/public summary 必须有 history 不同、gold action
不同的 paired worlds。

## 4. Dynamic Shopping v3

### 4.1 Variables and DGP

每个 world 有 8–16 个 cart lines、20–50 个 candidates。公开 fields 包括 slot descriptor、
opaque SKU、quantity、price、price lock、merchant descriptor、package、revision；catalog 只
给 attribute tokens、quote、inventory observation、merchant descriptor。

Generator latent mechanism 是 personalized compatibility factor graph、bundle/promotion
hyperedges、shipping partition、substitute utility 与 price-lock transition。Repair 是 factor/
hypergraph 上的全局 lexicographic optimizer：mandatory coverage → user utility/promotion →
checkout cost → transaction cost → opaque ID tie-break。

History 给 accepted/rejected substitution、aborted checkout、pairwise swap、bundle/package/
promotion receipt、preference 和 price-lock 案例；不提供 compatibility matrix、hyperedge、
utility weights或最终 repair。

### 4.2 Intervention and endpoint damage

Interventions：inventory loss、locked-price correction、promotion revoke、merchant/package
policy observation change。传播可经 substitute → incompatibility → bundle loss → budget →
second replacement → package/shipping/receipt。

Actions：remove/add/replace/reprice/repackage/apply/release promotion。任何 extra touch 都会
增加 revision、使 price lock 失效，并可能产生 fee、promotion/package 变化。

Test 使用新 merchant/user/SKU IDs 和 train-seen factors 的新 hypergraph composition；同一
source/visible regime 的 paired worlds 必须由 history 决定不同 factor/action。

## 5. Dynamic Search v3

每个 world 包含 6 sources、10 documents、4 claims、2 decisions、2 briefs、3 policy/gate
cells，均使用 opaque UUID。History 给 document card 的 source/route code/cluster/stance/
active 与 claim card 的 socket/window/threshold；不列 document→claim 或 claim→decision
incidence。

稳定但隐藏的 route/socket compatibility 从 train interventions 学。有效 evidence 还受
source trust/license、time window、independence-cluster dedup gate 控制。Claim 聚合 stance ×
trust weight，decision 再做 strict/lenient multi-claim aggregation，brief downstream 更新。

Interventions：source trust/license、document stance/version、pivotal retraction、decision
policy；out-of-window update 与 losing duplicate update 是 matched negative controls。
Test 组合 train-seen local route/window/dedup motifs为新 fan-out/diamond/multi-claim topology，
并包含 observational twins：相同 pre-state output、不同 hidden route、对 intervention 的
post-state不同。

Extra declared claim/decision/brief write 会增加 provenance revision/certificate version，
使 exact receipt 失败。

## 6. Causal Formal v3

每个 notebook world 有 6–8 primitive definition/axiom cells、4–6 binding/scope cells、
10–16 lemma/theorem cells与 independent controls。Derived value 为
`{status: proved|disproved|undefined, value}`。

History 给 declaration chronology、scope ID、producer port code、公开 arithmetic/logical rule
token、consumer socket codes与当前 recorded value；不列 resolved parent edges。稳定但隐藏的
port compatibility与shadowing precedence只能从 train interventions学习。Binding edit 可改变
post-intervention topology；axiom gate控制 operand edge；undefined 沿 active descendants传播。

Interventions：primitive correction、rule-token patch、axiom activation/retraction、binding
rebasing；shadowed definition和gated-off operand是 negative controls。生成器制造
counterfactual ambiguity：多个 candidate wiring 对 pre-state 给同值，但对 intervention 的
post-state不同。

Extra theorem write 会增加 proof revision、重签 certificate/依赖摘要，导致 receipt失败。
Test 使用新 UUID、deeper DAG、nested scope、diamond/fan-out/fan-in，以及 train-seen operator/
gate/shadow motifs的 held-out composition；完全 unseen operator只作 OOD diagnostic，不进入
主验收。

## 7. 公平 baseline matrix

所有 non-oracle 方法共享 train completed transitions、runtime 与计算/上下文预算：

| Baseline | 作用 |
|---|---|
| Exact-KV | 只执行 query target transaction |
| Flat/source lookup | source kind、intervention kind、delta shape → modal impact/action |
| Source + visible-regime | 加不含 history 的公开摘要；检验 query/state shortcut |
| Transition kNN | 完整 observable 上最近 train transition，做 ID alignment |
| Flat black-box | canonical serialization classifier/direct transition predictor |
| Permutation-equivariant black-box | DeepSets/Set Transformer/GNN-like direct action predictor，不要求显式 graph |
| Conservative superset | public type/temporal/slot closure，对全部可能对象执行 action |
| Relational/program learner | 从相同 train outcome 归纳 clauses/factors/compatibility，再执行 CSP/ILP/fixed point |
| Learned causal graph | 学 typed edges、history-conditioned gates、local value heads，再传播/优化 |
| Oracle | generator graph/parameters + deterministic executor |
| Full runtime | 全 history/state/resources，测 context ceiling，不拥有 gold |

关系程序不能被故意削弱。如果它或 permutation-equivariant black-box 与 graph 持平，只支持
“可组合 relation/structure 有用”；不能声称 causal representation 独有优势。

## 8. Admission gates（未全部通过不得调用 API test）

1. 四个 domain 的 normalized structural/process fingerprints 两两不同；禁止换名复制 DGP。
2. 每个 test world 至少两跳真实变化，并含 active/inactive matched gate controls。
3. Train/test node/entity/provider/merchant/template IDs完全不重叠。
4. Query 不含 downstream IDs、gate label、scenario/composition。
5. Final target 未被 history 以同 intervention/value直接 probe。
6. 每个 source/visible-regime signature 有 history不同、gold actions不同的 paired worlds。
7. 每个 atomic mechanism 在 train 有正负 intervention evidence；test只组合，不引入不可识别规则。
8. Test canonical topology hash 不与 train/dev 重叠；统计按 world cluster。
9. Exact-KV、flat lookup、regime table、kNN 与 conservative superset 均不能完成 endpoint。
10. Superset mutation 必须产生 revision/fee/receipt damage并使 endpoint失败。
11. Runtime-history oracle（使用可学习的 mechanism，不读 evaluator graph）必须可解，排除不识别。
12. Learned graph 在至少三个 dataset seeds 的 dev 上优于 matched flat/black-box；报告
    world-clustered CI 与 counterfactual-twin slice。
13. Strongest relational/program baseline必须运行。若 tie，则 causal-necessity stop。
14. 所有 predictions、raw API responses与 usage ledger 先落盘，再加载 test gold评分。
15. 合法 JSON 的错 node/action/value 是 semantic failure，不重试；只有 transport/empty/
    truncated/JSON syntax/type-level错误可在冻结预算内重试。

## 9. Yujia 两卖点中的位置

- P1 simulation：继续由已知 DGP linear/nonlinear/latent-boundary 表承担；v3 不替代它。
- P2 effectiveness/efficiency：v3 测 hidden mechanism → learned structure → executable memory
  maintenance；Travel/Search 作为建议的 1–2 个真实 API representative setups，Shopping/
  Formal 先做 CPU deterministic replication。
- P3 trustworthiness/auditing：现有 MINJA/AgentPoison hidden-driver evidence保留；当前 online
  mitigation FAIL 不由 v3 覆盖。若以后把 v3 graph用于 gate action，必须另立 held-out ASR/
  benign utility协议。

Scalability 另做变量数、distractor、trajectory length、fit/update time、memory sweep；grouping
必须由 train observables学习，不能预先知道 latent proxy group。

## 10. 冻结顺序

1. Yujia double-check 本页的 sample/variable/transaction semantics 与 claim wording；
2. development generator + identifiability/pair/mutation tests；
3. dev 上运行完整 killer baseline matrix；
4. 只有 admission gates 全过才冻结 test manifest、API failure policy、price 与 seed；
5. 先做 Travel/Search representative API，Shopping/Formal保留 deterministic replication；
6. 一次 test；任何失败作为结果或新 version，不回填原 artifact。
