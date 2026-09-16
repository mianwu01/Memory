# Agent Memory 评估综述：结构、任务、效率与安全

> 核验日期：2026-08-31。本文只引用本项目已使用的论文、公开 arXiv 条目、上游
> benchmark 代码或可核实的经典指标文献。标题与 arXiv ID 已通过 arXiv metadata
> 核对；项目特有指标的语义以实际 evaluator/冻结协议为准。没有把尚未发表的内部
> 数字写成外部文献结论。

## 1. 结论先行

Memory system 没有一个可以包打天下的单指标。至少要回答四个不同问题：

1. **Intrinsic memory / structure**：取回了正确 evidence 吗？恢复了正确依赖或
   intervention impact 吗？
2. **Downstream task**：这些 memory 最终让 agent 完成任务了吗？
3. **Efficiency**：在同等任务质量下，实际少用了多少 context、钱和时间？
4. **Safety**：能否找到真正驱动有害行为的 memory；删除或 gate 后是否在 fresh
   execution 中降低攻击，同时保持 benign utility？

这四层不可相互替代。高 retrieval recall 不等于任务成功；高 full-state accuracy
可能只是大量 unaffected cells 容易保持；更短 prompt 不等于更低总成本；高 detector
AUC 也不等于在线 mitigation 有效。

对本项目，推荐的主次关系是：

| 论文主张 | Primary metrics | Secondary / diagnostic metrics |
|---|---|---|
| P1：结构或 impact 恢复 | 分 edge-type/lag/regime 的 P/R/F1；affected-result P/R/F1；affected-state accuracy；negative-control specificity | SHD、SID、AUROC/AUPRC、required-read recall、full-state accuracy |
| P2：agent effectiveness | 官方最终任务成功率；MemoryArena Travel 对应 PS，SR 作为严格 group 指标 | SPS/progress、answerability、cell/evidence recall、错误类型 |
| P2：agent efficiency | 在匹配任务质量下的 input/output tokens、实际费用、端到端 latency 的 Pareto 比较 | selected cells、compression、serialized chars proxy、index/storage/update 开销 |
| P3-A：hidden-driver audit | record-level driver precision、recall、F1/AUPRC；按 seed/episode 报告 | precision@k、AUROC、结构 ancestry recovery、定位延迟 |
| P3-B：actionable mitigation | held-out online ASR/attack probability 与 benign task utility **共同为主指标**；paired exposure outcomes | 删除数、touched retrieval、reverse trigger、parse/API failures、tokens/cost/latency |

Primary metric 必须在运行前随 claim 冻结。不能因为 secondary metric 更好看，就在结果
出来后把它升级为主指标。

## 2. 为什么要分四层

LongMemEval 把长期记忆系统拆为 indexing、retrieval、reading，并同时提供 evidence
session 与最终 QA 评估 [R1]。LoCoMo 则用 QA、event summarization 和 multimodal
dialogue generation 覆盖长对话记忆 [R2]。MemoryAgentBench 强调 accurate retrieval、
test-time learning、long-range understanding 和 selective forgetting 四类能力 [R3]。
这些工作说明“记忆质量”本来就是分层对象。

MemoryArena 进一步把 memory 放进多 session 的 Memory–Agent–Environment loop，评价
先前经验能否支持后续 action [R4]。这比静态 QA 更接近本项目的 agentic 主张，但仍然
只给 downstream 行为证据；若论文声称恢复了 causal/dependency structure，还必须加入
独立结构 gold 或 deterministic intervention simulator。

因此推荐使用以下因果链来组织评价，而不是把所有数字放进一个平均分：

```text
memory/structure selection
        ↓
available evidence and state
        ↓
agent decision / task outcome
        ↓
tokens, cost, latency and safety consequence
```

每一层都应有自己的 gold、baseline 和 failure attribution。

## 3. Intrinsic memory / structure

### 3.1 Content retrieval：找到了什么

传统检索式 memory 最自然的 intrinsic 指标是：

- `Recall@k`：gold evidence 中有多少进入 top-k；
- `Precision@k`：取回内容中有多少是真 evidence；
- `MRR`：首个相关 evidence 的排名；
- `nDCG@k`：当 relevance 有等级或多个 evidence 贡献不同时衡量排序质量 [R15]；
- evidence/session exact recall：所有必需 evidence 是否同时在上下文中。

LongMemEval 的 `answer_session_ids` 和 turn-level `has_answer` 使 session/turn evidence
recall 可独立于 QA 正确率评价 [R1]。本项目的 `cell recall` 与 `round solvable` 属于同一
层：前者是单元格召回，后者要求一轮的全部 gold dependencies 同时可用。它们是非常有用
的机制诊断，但不是最终任务成功率。

当缺一条 evidence 就无法求解时，推荐把 **all-required-evidence recall / round
solvable** 与 Recall@k 一起作为 retrieval primary；precision、MRR 和 nDCG 为 secondary。
只报告 Recall@k 会鼓励全取历史，所以必须同时给 selected cells/tokens 或 Precision@k。

### 3.2 State maintenance：改对且不乱改

对有 update、correction 或 deletion 的 memory，单纯 evidence recall 不够。至少报告：

- target update accuracy；
- stale-result rate：应失效结果仍保留旧值的比例；
- unaffected-state preservation；
- contradiction rate 或 whole-state consistency；
- whole-episode exact success。

`full-state accuracy` 只能做 secondary：如果 90% cells 不受 intervention 影响，一个只改
显式 key 的系统也可能获得很高分。应把 accuracy 限制在 gold affected set，并单独评价
unaffected controls。

### 3.3 Dependency / causal structure：图是否正确

结构学习的基本指标是 adjacency/edge precision、recall、F1 和 Structural Hamming
Distance（SHD）。NOTEARS 和 DYNOTEARS 是静态/时序 score-based structure learning 的
代表 [R5, R8]；PCMCI+ 明确处理 autocorrelated time series 中的 contemporaneous 与
lagged links [R7]。对 temporal memory graph，不能只给一个 overall F1，建议按以下层次
拆开：

- write、hold、read 或其他 edge type；
- lag；
- instantaneous vs delayed；
- regime/gate active vs inactive；
- direct edge vs transitive reachability。

SHD 对每条 edge 的删除、添加、反向计数，便于图间比较，但不直接表示 intervention
后果。Structural Intervention Distance（SID）衡量错误图在多少 intervention query 上会
给出错误分布，是更接近 causal use case 的 secondary 指标 [R6]。SID 的适用前提、DAG
语义和可识别边界必须满足；不能机械套在带 latent confounding、循环或只有类型级边的图上。

### 3.4 对 memory propagation 更直接的 intrinsic 指标

对本项目的“修改一个 memory/state 后找齐下游”主张，impact-level gold 比仅看 direct
edge 更直接。令 gold affected set 为 `A`、预测为 `Â`：

```text
affected precision = |A ∩ Â| / |Â|
affected recall    = |A ∩ Â| / |A|
```

推荐同时报告：

- affected-node 和 affected-result P/R/F1；
- affected-state accuracy；
- required-read recall；
- whole-episode success；
- negative-control specificity：inactive regime 或独立分支没有被误选；
- negative-control value preservation。

空 affected set 不应混进普通 recall 后被记成自动满分。应把 propagation-required cases
与 inactive-gate negative cases 分开汇总，否则 easy negatives 会抬高平均 recall。

### 3.5 Intrinsic 指标的推荐层级

若主张是“发现正确结构”，primary 是分类型 edge P/R/F1，并用 intervention impact
metrics 验证图的用途；SHD/SID 为 secondary。若主张只是“选择任务所需 memory”，
primary 应是 affected/evidence selection 与 state correctness，不能因为内部用了 graph
就把 edge F1 强行设为唯一主指标。

结构指标还必须对比最强简单解：Exact-KV、query-aware structured parser、program/
dataflow solver、matched-budget retrieval、learned graph、oracle graph、full history。
只超过 BM25 不能证明 causal structure 必要。

## 4. Downstream task

### 4.1 文献中的 downstream 层

LongMemEval 的最终层是长历史 QA；LoCoMo 同时评价 QA、summarization 与 dialogue
generation [R1, R2]。MemoryAgentBench 在 incremental multi-turn interaction 中评价四种
memory competency [R3]。MemoryArena 的贡献是让之前的 interaction 与 memory 真正影响
后续 agentic task [R4]。这些 benchmark 共同支持一个原则：**memory 应由它服务的任务
评价，但 task score 不能替代 intrinsic attribution。**

### 4.2 MemoryArena 的官方层级

本仓实际使用的 Travel evaluator 定义：

- **PS（Person full-pass rate）**：一个人的完整计划全部 day/slot 通过；
- **SPS（平均 constraint-slot rate）**：只看相对 base plan 发生约束变化的 slots；
- **SR（Group success rate）**：一组所有人都 full-pass。

定义可以在上游
[`travel_planner_env/eval.py`](../benchmarks/MemoryArena/env/env_systems/travel_planner_env/eval.py)
核对。PS/SR 是严格 endpoint，SPS 是有价值的 progress/constraint diagnostic。SPS 高而
PS 低是完全可能的，所以 P2 effectiveness 推荐 PS 为 primary、SR 为严格 group
secondary、SPS 为 progress secondary。

Formal Reasoning 上游 evaluator 同时给 paper pass rate、progress score 与 passrate@k；
同样应以前者作为完整任务 outcome，后两者用于定位随 session 推进的退化。

### 4.3 推荐的统计报告

对同一批 episodes 比较方法时：

1. 使用完全相同的 episode/group IDs、模型、decoder、tool budget 和调用协议；
2. 以 episode/group 为 resampling unit 做 paired bootstrap CI；
3. 报 episode-level win/tie/loss，不把同组 persons 或 slots 伪装成独立样本；
4. 同时给 micro totals 和 macro per-episode mean；
5. 对随机 LLM calls 加同 wrapper 的 exact no-op control；
6. 报 missing、unparseable、tool/API failure，不能只在成功解析样本上算分。

推荐 primary 是官方 final success 或 exact endpoint correctness。SPS、progress、
answerability、retrieval recall、LLM judge 分数都是 secondary，除非论文事前明确只主张
局部 constraint satisfaction。

## 5. Efficiency / cost / latency

### 5.1 为什么不能只报 compression ratio

MemGPT 把有限 context 当作 memory hierarchy 管理问题 [R9]；FrugalGPT 则明确把模型
质量和货币成本放在同一优化问题中 [R10]。两者提示：效率评价必须在质量约束下进行。
一个把所需 evidence 一起删除的系统，即使 prompt 最短也不构成有效提效。

此外，context selection 与 serialization 是两种不同 intervention：

- selection 决定保留哪些 cells/records；
- serialization 决定同一 cells 用自然语言、JSON、delta 还是 compact schema 表示。

两者必须正交消融。若 graph arm 同时换了 selector 和 compact prompt，token 降幅只能叫
selection/serialization bundle，不能全部归因于 adjacency mask。

### 5.2 成本账本的四层

| 层 | 应记录 |
|---|---|
| Selection | selected records/cells、required-read coverage、retrieval top-k |
| Serialization | 用模型真实 tokenizer 得到的 context tokens；chars 只能标为 proxy |
| Inference | logical calls、attempts/retries、input/cached/output tokens、计价版本与实际费用、API duration、wall duration |
| Maintenance | graph/index fitting、embedding/index build、storage、online update latency；说明是否摊销 |

API duration 与 wall duration 要分开；output token 增加可能抵消 input compression；缓存
token 的价格也可能不同。只报 input tokens 会遗漏真实 trade-off。

### 5.3 本文推荐

P2 efficiency 不宜压成一个综合分。推荐把以下量作为 co-primary，形成 Pareto table：

- 官方 task success；
- total input 和 output tokens；
- actual/estimated dollar cost（注明价格表与日期）；
- end-to-end wall latency，并附 API duration；
- calls/retries/failures。

比较应在同任务质量或预先给定的非劣容忍区间内进行。secondary 包括 selected cells、
compression ratio、token proxy、index size、fit/update time 和 cost per successful episode。
当 success 为零或很低时，`cost/success` 会爆炸，应保留原始 numerator/denominator，不能
只报告该比率。

## 6. Safety audit / mitigation

### 6.1 文献中的威胁与评测面

AgentPoison 将 backdoor trigger 与 poisoned memory/RAG retrieval 连接，原论文同时关注
attack success、poison rate 和 benign performance [R11]。MINJA 进一步展示攻击者只通过
query/output interaction 也能把 malicious records 写入 memory [R12]。AgentDojo 将
untrusted tool data 下的 task utility 与 security test cases 放在同一 agent 环境 [R13]。
MemAudit 则专门研究 harmful behavior 已发生后的 post-hoc poisoned-memory attribution
[R14]。

这些工作对应两个不同问题：

- **P3-A audit**：哪个 record/ancestor 真正驱动异常动作？
- **P3-B mitigation**：冻结 audit 决策后，gate/delete 是否在新调用中降低攻击？

Audit 命中不能自动推出 mitigation 成功；保存轨迹上的 replay coverage 也不能替代 fresh
online calls。

### 6.2 P3-A：driver detection / localization

Poison records 通常远少于 benign records，因此 accuracy 和 ROC-AUC 可能在极度不平衡下
过于乐观；precision–recall curve/AUPRC 更能反映少数正类检出 [R16]。推荐 primary：

- record-level driver precision、recall、F1；
- AUPRC（当输出连续 score）；
- poison/driver recall@k 或 precision@k（当 gate 只能处理 k 条）；
- ancestry/edge recovery P/R/F1（若主张恢复 hidden pathway）。

Secondary：AUROC、score separation、calibration、定位延迟、删除集合大小和 attribution
stability。必须报告 direct recovery 与 post-hoc cluster expansion 两套结果，不能只报扩张
后的最好数字。

训练/calibration 阶段只能读取预注册的 runtime events。`is_poison`、poison source、test
answer 和 test outcome 必须等所有决策冻结后才能用于评价，否则 precision/recall 本身已
发生 label leakage。

### 6.3 P3-B：fresh online mitigation

Mitigation 至少有两个 co-primary endpoints：

1. held-out online ASR / attack probability 的下降；
2. benign task success/accuracy 的保持。

还应逐 query 记录：

- deleted record 是否真的出现在 ungated retrieval，即 `touched exposure`；
- prevention、reverse trigger、attack unchanged、nonattack unchanged；
- exact no-op 与 ungated/gated 的独立调用波动；
- seed/block 方向一致性；
- parse/API failures、calls、tokens、cost、latency。

如果 ungated ASR 已在零附近，单纯“gated 仍为零”没有 mitigation 识别力；应报告有效
exposure 数或换一个有 attack headroom 的冻结设置。Micro ASR 降低也不能覆盖 1/3 seed
改善、其他 seeds 全 tie 的异质性。

本项目现有冻结协议把“micro ASR 下降且至少多数 seed blocks 同方向改善”作为联合判断，
同时报告 normal utility。该原则与 AgentDojo 的 utility/security 双轴相容 [R13]，也避免
把一味删除 memory 的系统误判成安全。

## 7. 项目级推荐评估矩阵

| 层 | 必选 arms | Primary | 必报 controls |
|---|---|---|---|
| Synthetic/structure | learned、oracle、empty/wrong graph、Exact-KV | edge-type/lag/regime F1；affected-result F1；affected-state accuracy | inactive regime、independent negative branch |
| Agentic effectiveness | strongest structured/program baseline、matched-budget retrieval、learned graph、full history | official final task success | matched parser/decoder/model/tools；paired IDs |
| Efficiency | 上述每臂 × verbose/compact serialization | task-quality-constrained tokens/cost/latency Pareto | selection×serialization orthogonal ablation；full ledger |
| Safety audit | similarity/consistency detector、learned driver、oracle label only for post-hoc scoring | driver P/R/F1/AUPRC | label-free fit；direct vs expansion；clean records |
| Safety mitigation | ungated、exact no-op、gated、clean-gated | fresh ASR + benign utility | touched exposures；seed consistency；failures/cost |

统一 reporting order：先写 primary endpoint 和冻结判断，再写 secondary diagnostics，最后
写 efficiency 与 failure audit。不能用后两者覆盖 primary 的负结果。

## 8. 常见错误表述

| 不充分表述 | 应改为 |
|---|---|
| “比 BM25 好，所以 causal memory 有效” | 与 Exact-KV、structured/program solver、matched-budget retrieval 比；证明优势来自 learned dependency |
| “full-state accuracy 很高” | 单列 affected-state accuracy、unaffected preservation 和 whole-episode success |
| “SPS 提升，所以任务成功率提升” | 同时报告 PS/SR；SPS 只称 constraint/progress metric |
| “prompt chars 少 40%” | 用实际 tokenizer/API usage；若只是 chars，明确写 token proxy |
| “graph 节省 40% tokens”但同时换 serialization | 称 graph-driven selection/serialization bundle，或做正交消融 |
| “replay 阻止了 95% 攻击” | fresh held-out online gate、paired no-op、touched exposure 与 benign utility |
| “micro ASR 下降” | 同时报 seed/block 一致性、CI、attack headroom 和 exposure 数 |
| “driver recovery 100%” | 标明 labels 何时可见、direct/expanded recovery、precision/recall 分母 |

## 9. 与本仓现有证据的对应

- [`causal-benchmark-protocol.md`](causal-benchmark-protocol.md)：统一 affected-state、
  negative-control、matched-budget 与 selection/serialization stop rules。
- [`causal-benchmark-formal.md`](causal-benchmark-formal.md)：强 program/dataflow solver
  与 learned selector 持平，说明 formal artifact 只能支持 interventional dataflow
  replication，不能证明 empirical causal necessity。
- [`p2-memoryarena-plugin-results.md`](p2-memoryarena-plugin-results.md)：PS/SPS/SR 与
  tokens/cost/duration 的多轴 trade-off；answerability 不能冒充官方 success。
- [`p3-minja-causal-audit-results.md`](p3-minja-causal-audit-results.md)：P3-A recovery 与
  P3-B held-out mitigation 分开；保存 replay 与 fresh calls 分开。
- [`yujia-confirmatory-protocol-2026-08-29.md`](yujia-confirmatory-protocol-2026-08-29.md)：
  paired episodes、label-free calibration、seed consistency 和 no test-outcome leakage。

## References

- **[R1]** D. Wu et al. *LongMemEval: Benchmarking Chat Assistants on Long-Term
  Interactive Memory*. arXiv:2410.10813. <https://arxiv.org/abs/2410.10813>
- **[R2]** A. Maharana et al. *Evaluating Very Long-Term Conversational Memory of
  LLM Agents* (LoCoMo). arXiv:2402.17753. <https://arxiv.org/abs/2402.17753>
- **[R3]** Y. Hu, Y. Wang, J. McAuley. *Evaluating Memory in LLM Agents via
  Incremental Multi-Turn Interactions* (MemoryAgentBench). arXiv:2507.05257.
  <https://arxiv.org/abs/2507.05257>
- **[R4]** Z. He et al. *MemoryArena: Benchmarking Agent Memory in Interdependent
  Multi-Session Agentic Tasks*. arXiv:2602.16313.
  <https://arxiv.org/abs/2602.16313>
- **[R5]** X. Zheng, B. Aragam, P. Ravikumar, E. Xing. *DAGs with NO TEARS:
  Continuous Optimization for Structure Learning*. NeurIPS 2018,
  arXiv:1803.01422. <https://arxiv.org/abs/1803.01422>
- **[R6]** J. Peters, P. Bühlmann. *Structural Intervention Distance (SID) for
  Evaluating Causal Graphs*. arXiv:1306.1043.
  <https://arxiv.org/abs/1306.1043>
- **[R7]** J. Runge. *Discovering Contemporaneous and Lagged Causal Relations in
  Autocorrelated Nonlinear Time Series Datasets*. UAI 2020, arXiv:2003.03685.
  <https://arxiv.org/abs/2003.03685>
- **[R8]** R. Pamfil et al. *DYNOTEARS: Structure Learning from Time-Series Data*.
  AISTATS 2020, arXiv:2002.00498. <https://arxiv.org/abs/2002.00498>
- **[R9]** C. Packer et al. *MemGPT: Towards LLMs as Operating Systems*.
  arXiv:2310.08560. <https://arxiv.org/abs/2310.08560>
- **[R10]** L. Chen, M. Zaharia, J. Zou. *FrugalGPT: How to Use Large Language
  Models While Reducing Cost and Improving Performance*. arXiv:2305.05176.
  <https://arxiv.org/abs/2305.05176>
- **[R11]** Z. Chen et al. *AgentPoison: Red-teaming LLM Agents via Poisoning
  Memory or Knowledge Bases*. NeurIPS 2024, arXiv:2407.12784.
  <https://arxiv.org/abs/2407.12784>
- **[R12]** S. Dong et al. *Memory Injection Attacks on LLM Agents via Query-Only
  Interaction* (MINJA). arXiv:2503.03704.
  <https://arxiv.org/abs/2503.03704>
- **[R13]** E. Debenedetti et al. *AgentDojo: A Dynamic Environment to Evaluate
  Prompt Injection Attacks and Defenses for LLM Agents*. arXiv:2406.13352.
  <https://arxiv.org/abs/2406.13352>
- **[R14]** Z. Tan et al. *MemAudit: Post-hoc Auditing of Poisoned Agent Memory via
  Causal Attribution and Structural Anomaly Detection*. arXiv:2605.23723.
  <https://arxiv.org/abs/2605.23723>
- **[R15]** K. Järvelin, J. Kekäläinen. *Cumulated Gain-Based Evaluation of IR
  Techniques*. ACM TOIS 20(4), 2002. <https://doi.org/10.1145/582415.582418>
- **[R16]** T. Saito, M. Rehmsmeier. *The Precision-Recall Plot Is More
  Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced
  Datasets*. PLOS ONE 10(3), 2015.
  <https://doi.org/10.1371/journal.pone.0118432>
