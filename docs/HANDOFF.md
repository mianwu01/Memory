# Handoff — causal-memory experiment state (updated 2026-09-15)

> **当前续跑入口（2026-09-15，优先于下方历史记录）：** `faithful_memory_aiaaa_v2` 已因余额不足停止，没有在后台继续运行。
> 最新逐项快照：[readiness.json](../results/development/faithful_memory_aiaaa_v2/readiness.json)；5/16 个开发门槛通过，正式 0/100。
> aiaaa 的生成探针返回 403 `INSUFFICIENT_BALANCE`，TokenRhythm 返回 402 同一错误；不是实现验收全部完成。
> 三个 online 机制小例、noGcompact/query_only 的 ID101 已完成；其余 8 个 Travel 和 3 个完整 LoCoMo 验证待恢复。
> 默认仍为 aiaaa / deepseek-v4-flash-0731；memory 使用 `reasoning_effort=none`，A-Mem 保留作者 1000 上限；actor 原版。
> 检索配置 Mem0 200 / LightMem 60 / A-Mem 10，详见登记文件。不要恢复 v1 的 16000 A-Mem 校准配置。
> 已记录修复新增 ¥44.03236976，累计 ¥320.51447876；未知用量/价格未对账。失败记录全部保留。
> 需要账户恢复后先小额验证，再事前登记技术恢复目录；不能直接重启旧 supervisor、覆盖失败或重复调用已完成门槛。
> suite 已增加遇到失败停止启动新案例的保护；在途任务允许结束，避免丢失实际响应与费用。
> [当前交付与 outline](yujia-progress-2026-09-15.md)；正式结果、对应新对比 demo/PDF 仍未完成。
> [已导出离线审阅包](../results/development/yujia_offline_update_2026_09_15/README.md)：进展、中文 outline、重编译 LaTeX 和历史示例副本；中文字体已嵌入。


> **当前任务：** 用户已授权全部修复并重新运行有效比较。v5 只保留为历史探索性结果，不能继续作为主表。
> 新环境 `.tmp/memory-faithful-venv`，新代码 `code/faithful_memory*.py`，
> 开发产物 `results/development/faithful_memory_v1`、`v2`、`v3`；原生 LoCoMo 全历史检查 `faithful_memory_native_v1`。见 [修复与验收记录](faithful-memory-remediation-2026-09-15.md)。

> **旧 v5 状态的 2026-09-15 验收补充：** 上游来源、冻结哈希和十臂运行完成已核实，方法忠实度与研究要求仅部分满足。
> Mem0 缺失依赖使关键词检索关闭；A-Mem 当前为作者 SDK 普通 search 路径，论文复现另有仓库；
> LightMem 是关闭预压缩/主题分段、每轮全量 consolidation 的适配配置。十臂共用本地 v3 decoder。
> 下方“完成”只指既定配置的执行，不能当作研究验收全部通过。详见
> [来源与方法验收审查](baseline-fidelity-audit-2026-09-15.md)。原结果和冻结生成代码保留。

<!-- recent-memory-completion:start -->
> **历史探索性配对评估（已降级）：** 十臂均完成 IDs 111/112/113，官方评分与用量完整性检查通过。
> [结果表与逐 episode 比较](../results/real/p2_recent_baselines_tokenrhythm_v5_completed/results.md)；表中完整结果的用量估算 ¥25.3557。
> 新中转探针及全部开发/评估合计估算 ¥46.4821，
> 加旧账单 ¥230 后为 ¥276.4821。缺失用量与 aiaaa 未知费用未计入；不是对账总额。
> 这是三个复用 holdout episodes 的描述性配对复验；不证明 causal necessity 或真实 latent identifiability。
> summary 使用按预先记录的技术恢复规则完成的补跑，其余九臂保留原结果；原始批次的断流失败及费用另行保留。
<!-- recent-memory-completion:end -->

**旧 v5 对照（不进入新主表）：** Ours 与同格式 noGcompact 的逐 episode PS/SPS/SR 全部持平，官方 person-PS 都为 90.91%（20/22）。输入从 245,599 降至 123,701 tokens，减少 49.63%；总费用估算为 ¥0.8067 / ¥0.7713，Ours 高 4.59%。这支持输入压缩的观察；相对这一对照，本轮未显示准确率或货币成本优势。

> 旧协议为 `p2_recent_baselines_tokenrhythm_v5`：流式汇总、共享请求节流和有限 HTTP 重试。
> 开发验证采用 v2/v3 已通过的方法与 v5 LightMem；正式十臂共同冻结并完成。
> 启动任何实验前先检查 [续跑状态](../results/real/p2_recent_baselines_tokenrhythm_v5/recovery_state.json)，避免重复调用。
> [aiaaa 备用接口](aiaaa-relay-2026-09-14.md) 4 次短请求已通过，单价待核对。

> **2026-09-14 最新中转：** 已验证并激活 TokenRhythm `https://tokenrhythm.studio/v1`
> + `deepseek-flash`。16/16 生成探针通过（含工具回传）；估算 ¥0.114。公开标价输入 2、
> 输出 8、缓存命中 0.04 元/M tokens。旧 bboluo 用户确认已花 230 元单独保留。
> 初始 267–277 元预测未覆盖传输修复和完整长推理；使用
> [累计费用与开发校准](../results/development/tokenrhythm_cumulative_budget_2026_09_14.json) 更新规划。
> 约 300 元不是硬上限；旧 5,000 元按次报价已被新路由预算替代。aiaaa 单价仍未知。
> 详见 [测试、单价与预算](tokenrhythm-switch-2026-09-14.md)。凭据只在 ignored 0600 本地文件。

> **9/04 会议主线：** 不扩展 simulation；变量口径、三页具体 slide 与段落/句子 outline 已完成。
> 三套 native baseline 已适配，当前 family 为 `p2_recent_baselines_tokenrhythm_v5`。
> 开发验证来源不拼成排名，正式十臂比较须全部完成再报告。
> 完整交付见 [执行报告](yujia-meeting-delivery-2026-09-14.md)。旧
> `p2_recent_baselines_v0_debug` / `v1` 保留，不能把初版 A-Mem（evolution schema 失败）
> 的单例 100% 当有效成绩。不要用 upstream 静态 cost 作为新中转金额，需汇总 actor/memory usage。
> 先检查开发，再 freeze evaluation；111–113 是旧 holdout IDs 的描述性配对复验。
> 不推进 synthetic v3，不发消息给 Yujia；四个上游源码保持不动。

后续交互命令使用用户指定的 `tts-sft/.venv/grpo-pilot`（Python 3.10.16）；它与已运行
实验的 transformers 版本不同且缺少 native memory 依赖。本轮实验继续固定使用
`.tmp/memory-baselines-venv/bin/python`，不要为了切换交互环境重启或混用冻结依赖。

> **2026-08-31 superseding audit:** 本页保留 P2/P3 冻结实验的完整证据，但不再单独代表
> 项目的最新总体 claim。四个 redesigned task 的 train-only/novel-split/六臂 T1 已完成：
> learned 四项均胜 matched generic retrieval，却与四项强 domain solver 的 1.0 task
> success 全部持平，所以 causal-necessity 判据为 **0/4**。Simulation v2 observed
> linear/MLP 五 seed 通过，latent identification 不支持；P3-A auditing 仍为有边界支持，
> P3-B actionable mitigation 仍失败。最新 machine-readable 裁决、精确定义和 8-15
> 遗留状态见 [`yujia-story-audit-2026-08-31.md`](yujia-story-audit-2026-08-31.md) 与
> `results/development/yujia_story_audit.json`。下表中“学得图优于手工图”只指原 Travel
> answerability/context-compression 比较，不能解释为相对 task-specific domain solver 的
> causal necessity 证据。

> **2026-08-31 real-API addendum:** 本地 `deepseek_apikey.md` 已用于真实调用。四任务
> six-arm v1 已产生 288/288 results、309 ledger events，integrity/full-scope 均完整，费用
> `$6.607622`；284 rows 可评分，4 个 full-state rows 为未评分工程/合同缺失，因此 summary
> 正确 fail-closed 为 `experiment_complete=false`。learned arm 的 valid-only endpoint 四项
> 都为 1.0，但不能升级为 causal necessity：v1 `domain_solver` 只是 potential reachability，
> Travel/Shopping/Formal 仍有 structured shortcut，且旧重试策略把 node-set semantic
> contract mismatch 与工程格式错误混在一起。权威结果说明为
> [`causal-api-six-arm-v1-results.md`](causal-api-six-arm-v1-results.md)；原 artifacts 不回填、
> 不 gold-repair。

> **Anti-shortcut addendum:** `killer_lookup_dev_audit.json` 在四个现有 task 上都触发
> sufficient-mask stop rule。随后独立构造的 hidden-routing v2 也没有被硬写成正结果：公平
> train-enabled codebook program 与 learner exact tie，history 暴露 100% potential-edge
> skeleton，四个 domain 的 normalized fingerprint 相同，artifact verdict 为 `PARTIAL`、
> `all_domains_pass=false`。因此没有启动下一轮 API。四个真正不同的 transactional v3 DGP、
> sample/variable、baseline 与 endpoint 已预注册在
> [`hidden-mechanism-v3-preregistration.md`](hidden-mechanism-v3-preregistration.md)，下一外部
> 依赖是 Yujia double-check，而不是 API key。

这是当前工作区的权威状态页。早期逐轮过程保留在 `docs/session-status-2026-08-27.md`，但其中的 P3 负结果和 “e2e 0 episodes” 已被本页的新实测取代。

## 旧修复过程的定位

v1 的 16000-token A-Mem 调整、stream recovery 与旧 supervisor 均已停止；它们是失败的开发过程，
不再是续跑入口。完整历史记录见 [修复记录](faithful-memory-remediation-2026-09-15.md)。
当前状态与恢复前提以上方 v2 快照为准，后面的 P1/P2/P3 内容保留历史科学证据。

## 1. 一句话结论

项目已经跑通“发现 → 记忆选择 → 约束解码 → 时序审计 → regime gate”。P2 新冻结轮 IDs 111–120 中，compact query-ancestry 相对 noG 的 episode-mean PS 仅低 1.43 点，同时 input 减少 39.55%，正式 `pass=true`；旧 IDs 101–110 的 14.7% input 失败仍原样保留。P3 必须拆成两个结论：原始的 hidden-driver auditing 问题由 MINJA 的结构恢复与 AgentPoison 的 label-free record recovery **支持，但有识别边界**；后来追加的 online mitigation 在两个载体上都只有 1/3 seed blocks 改善，冻结判断仍为 `pass=false`。不能用后者覆盖前者，也不能把支持性综合事后写成新的 confirmatory PASS。

## 2. 主张与证据状态

| 主张 | 状态 | 证据 |
|---|---|---|
| 四任务 SelectionPlan + 真实 API decoder 可执行 | 支持，但仅为条件性执行证据 | 288-case scope、284 semantic-scored；learned valid endpoint 4/4 为 1.0，详见 `results/causal_benchmarks/api_six_arm_test_v1_summary.json` |
| 四任务真实 API v1 证明 learned causal necessity | **不支持** | 弱 domain reachability、三任务 shortcut、4 missing 与 semantic-contract retry 边界，见结果说明 |
| Regime-conditioned discovery 恢复标准方法漏掉的 gated read edge | 已支持 | `results/regime_grace_e0.json`：σ∈{0,0.01,0.1} 均为 ours 2/2，blind/additive 0/2 |
| 学得图优于手工图做记忆选择 | 已支持 | `results/real/p2_benchmark_v2_summary.json`：learned 1.000/1.000 @1558，hand scaffold 0.993/0.973 @1896 |
| 不使用 query 人名 oracle 时仍优于检索 baseline | 已支持 | `results/real/p2_benchmark_pure_summary.json`：pure 0.962/0.845 @1142；BM25 0.920/0.719 @1951 |
| 插件真实接入 MemoryArena | 已支持 | 真实 HTTP memory API、运行时 factory 注册；上游仓库无改动 |
| P2 constraint satisfaction / efficiency 改善 | 已支持 | 固定 IDs 1–5：pure−BM25 配对 SPS +3.47 点，95% bootstrap [+1.11,+5.83]；input/cost 各少 34.2%/36.0% |
| P2 原始方案的总体任务成功率提升 | 不支持并已复核 | run A 与独立 run B 的 pure/learned 在同一 IDs 1–5 上均为 PS=0%；run A 的 BM25=10.81%、long context=16.22%，结果 mixed |
| P2 query-only inheritance repair | exploratory positive | fresh online：pure 30/37=81.08%，learned 37/37=100%；learned−pure episode-mean PS +18.69 点，95% bootstrap [+12.86,+28.33]；同 IDs 上 post-hoc 开发，不能当作 confirmatory generalization |
| P2 graph-held-out pure vs BM25 | 通过确认协议主判断 | IDs 101–110：episode-mean PS +16.55 点，95% bootstrap [+9.17,+25.24]，W/T/L 8/2/0 |
| P2 v1 graph vs noG（IDs 101–110） | 未通过次级条件 | PS +1.90 点且无超过 5 点的损失，但 input 只减少 14.7%，低于冻结的 30% |
| P2 compact-v3 graph vs noG（IDs 111–120） | **通过新冻结协议** | episode-mean PS −1.43 点（95% [−4.29,0.00]，0/9/1），input 减少 39.55%；两个合取条件均通过 |
| MINJA hidden memory pathway 在真实 LLM 上成立 | 已支持但跨 seed 可变 | 三 seed decisive cell 22/76=0.289，2/3 seeds >0.20；test ASR 8/36，见 §4 |
| MINJA 恢复隐藏 read edge 和写入轮 | 已支持但有 oracle/顺序假设 | Regime-GRACE 3/3 找到 `poison_retr→anomalous@0`、2/3 gated；provenance 每 seed 定位写入祖先；但 `poison_retr` 由 `is_poison` 构造，lag-0 方向也使用运行时先 retrieve 后 act 的测量顺序 |
| AgentPoison label-free record recovery | 支持原始 P3-A，但非独立 confirmatory PASS | driver 决策前不读 poison label/source 或 test outcome；直接恢复 1/2 poison records（precision 100%、recall 50%），冻结 cluster expansion 后恢复 2/2（precision/recall 100%）；development query 20 与 calibration 0–31 有重叠，且未预注册独立 recovery PASS |
| 我们在投毒检测上击败 MemAudit | 不支持 | 三 seed CMIS macro AUC 0.866、precision@k 0.874；项目主张是 temporal ancestry 与同图双用，不是 detection score 胜出 |
| ancestry + regime gate 的离线覆盖 | replay-only | 保存轨迹上覆盖 102/107=95.3% 异常轮；没有重新调用 LLM，不能称在线 prevention |
| P3-B / MINJA label-free driver → held-out online gate | 未通过确认协议 | micro ASR 6/36→5/36，但只有 1/3 seeds 改善；touched queries 中 2 prevention、1 reverse trigger、2 attack unchanged |
| P3-B / AgentPoison-StrategyQA paired gate | 未通过新冻结协议 | gated 3/72→0/72 且低于 no-op 4/72；三次 touched 均 prevention，但仅 1/3 seed blocks 改善，严格判断 FAIL |

## 3. P2 — MemoryArena

### 3.1 Answerability-at-cost，60 episodes / 401 rounds

| 系统 | cell recall | round solvable | avg context | compression |
|---|---:|---:|---:|---:|
| no-graph ablation | 1.000 | 1.000 | 2487 | 0.824× |
| learned + query-name seed | 1.000 | 1.000 | 1558 | 0.516× |
| long context | 0.999 | 0.994 | 3077 | 1.020× |
| hand scaffold | 0.993 | 0.973 | 1896 | 0.628× |
| constraint-only rule graph | 0.989 | 0.952 | 1045 | 0.346× |
| **learned pure discovery** | **0.962** | **0.845** | **1142** | **0.378×** |
| BM25 | 0.920 | 0.719 | 1951 | 0.647× |

对 pure discovery 的正确解读：移除人名 oracle 后仍比 BM25 多 4.2 点 cell recall、12.5 点 round solvable，同时少 41.5% context tokens。因此是双轴正结果；但它低于带 query-name seed 的 1.000/1.000，oracle gap 必须保留。

这些指标只检查 query 指向的金标单元格是否进入上下文，是任务表现的上游机制，不是 PS/SPS/SR。

### 3.2 官方 e2e，固定 5 个共同 episodes

预注册共同 IDs 1–5，共 37 persons：

| 系统 | PS | SPS | SR | input tokens | output tokens | cost | duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| causal-learned-pure | 0.00% | 84.38% | 0.00% | 712,338 | 338,997 | $5.1708 | 2438.49s |
| causal-learned | 0.00% | **96.90%** | 0.00% | **645,660** | 249,397 | **$4.1081** | 1659.42s |
| BM25 | 10.81% | 80.91% | 0.00% | 1,083,238 | 537,475 | $8.0828 | 3783.08s |
| long context | **16.22%** | 93.21% | 0.00% | 1,386,446 | **166,919** | $5.1353 | **1128.21s** |

episode 配对结果：pure−BM25 SPS `+3.47` 点（bootstrap 95% `[+1.11,+5.83]`，W/T/L `3/2/0`）；learned−BM25 `+15.99` 点（`[+8.06,+27.14]`，`5/0/0`）；learned−long context `+3.69` 点（`[0.00,+8.69]`，`2/3/0`）。

pure 相对 BM25 少 34.2% input 和 36.0% cost；learned 相对 long context 少 53.4% input、低 20.0% cost，但多 49.4% output、慢 47.1%。SPS/efficiency 是正结果，PS 是负结果，SR 全平。N=5 的诚实结论仍是 mixed，不能外推“总体任务成功率提升”。

### 3.3 对 PS=0 的确认性 run B

用户质疑两个方法臂 PS 同为 0%。按照执行前固定的 `docs/ps-rerun-protocol-2026-08-28.md`，run B 保持 `deepseek-v4-flash`、全部 agent/env/memory 参数和 IDs 1–5 不变，只写入新目录；run A 没有覆盖，也没有按结果挑选一次：

| 系统 | PS A / B | SPS A / B | unparseable A / B | constraint failures A / B | non-constraint failures A / B |
|---|---:|---:|---:|---:|---:|
| causal-learned-pure | 0.00% / 0.00% | 84.38% / 83.01% | 1 / 1 | 15 / 16 | 306 / 278 |
| causal-learned | 0.00% / 0.00% | 96.90% / 91.37% | 0 / 0 | 3 / 6 | 241 / 239 |

run B 的两个 submission 都覆盖 37/37 persons、0 missing。learned 仍是 0 parse failures；其中 31/37 persons 只在非 query-constraint slots 上失败，6/37 同时有 constraint failure。离 full pass 最近的 Aaron（ID 3 / person 1）在 run A 与 B 都只错了 `day 3 dinner`，而该槽位不是 query constraint；因此 SPS 可很高，PS 仍把整人判失败。pure run B 的空计划是 Mary（ID 1 / person 8），但去掉这个单例也不能改变其余 36 人均至少错一槽的事实。

逐 episode 的 A/B SPS 变化：pure `−1.37` 点，bootstrap 95% `[−8.10,+4.94]`，W/T/L `2/1/2`；learned `−5.54` 点，`[−11.25,−0.95]`，`0/2/3`。两臂 PS 和 SR 的五个 episode 均为 0→0。

usage 也不选优：pure run B 相对 A 的 input `−4.2%`，output `+15.1%`，cost `+8.5%`，duration `+10.6%`；learned 分别为 `+4.3%/+6.4%/+5.6%/+10.6%`。复核结论是 **0% 可复现且由严格 full-plan 分母解释，不是 scorer coverage/parse bug**；同时 run B 的 learned SPS 下降也必须保留。

### 3.4 用户质疑后的 exploratory base-inheritance repair

失败审计显示 run B 的 learned 有 31/37 persons 只错 query 未要求变化的槽位。随后新增 `query-target/base-inheritance-v1`：从当前 query 解析允许变化的 `(day, slot)`，只采纳这些槽位的 LLM 结果，其他槽位从环境已经公开给 agent 的 base itinerary 原样继承。运行时不读取 person gold，也不调用 evaluator 选择答案。

parser 的离线开发审计覆盖全部 270 groups / 1,869 rounds：12,227 个 query 明示目标覆盖官方 10,170 个 changed cells，TP=10,170、FN=0、recall=100%；额外 2,057 个是 query 明确要求、但 gold 恰好等于 base 的目标。该审计使用 evaluator，因此只用于验证 parser，不能当成未见测试。

先对保存的 run B generation 做 counterfactual postprocess（0 个新 LLM calls），再使用新目录做 fresh online generation：

| arm | run B 原 PS / SPS | offline counterfactual PS / SPS | fresh online PS / SPS / SR |
|---|---:|---:|---:|
| pure | 0.00% / 83.01% | 51.35% / 83.01% | 81.08% / 90.26% / 0.00% |
| learned | 0.00% / 91.37% | 72.97% / 91.37% | **100.00% / 100.00% / 100.00%** |

online 两臂均覆盖 37/37、0 missing、0 unparseable。pure 有 7 persons 失败、共 13 个 failed slots；12 个被官方 changed-cell finder 标为 constraint，另 1 个是 query 明示但 gold 等于 base 的目标。按 decoder 的 query-explicit 口径，13/13 都是允许变化的目标，继承槽位失败为 0。learned 的两类失败均为 0。

learned−pure 的 episode 配对结果：PS `+18.69` 点，bootstrap 95% `[+12.86,+28.33]`，W/T/L `5/0/0`；SPS `+9.74` 点，`[+4.21,+19.58]`，`5/0/0`；SR 五组均为 `+100` 点。online usage：pure 312,685 input / 270,234 output / $3.4841 / 1777.15s；learned 327,525 / 195,083 / $2.7696 / 1236.88s。

解释是：inheritance 消除了 full-plan PS 中的无关重规划噪声；此后 pure 的剩余错误集中在 query 指定槽位，常对应未检索到被点名的早期 traveler，learned 则取回相关计划并避免错误继续污染后续 memory。这个结果回答了“怎么改”，但它是看过失败后在相同 IDs 上完成的 exploratory repair。原 run A/B 不覆盖，论文级主张需要锁定 decoder 后在 unseen IDs 上确认。

### 3.5 Graph-held-out / LLM-e2e-held-out，固定 IDs 101–110

四臂统一 `query-target/base-inheritance-v1` decoder；类型图和 persistence 只用其余 260 groups，明确排除 101–110：

| arm | PS | SPS | SR | input | output | cost | duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| pure graph | **91.78%** | **98.19%** | **60%** | **858,445** | 663,528 | $8.7814 | 4068.41s |
| noG | 89.04% | 97.97% | **60%** | 1,006,049 | 619,642 | **$8.7115** | 3848.87s |
| BM25 | 75.34% | 90.24% | 10% | 1,965,551 | 1,131,231 | $16.2262 | 7066.50s |
| long context | 86.30% | 96.25% | 30% | 3,165,105 | **493,654** | $12.8493 | **3014.27s** |

pure−BM25 的 episode-mean PS `+16.55` 点（bootstrap 95% `[+9.17,+25.24]`，W/T/L `8/2/0`），所以 P2 主判断通过。pure−long PS `+5.18`（`[+0.00,+10.54]`，`3/7/0`）。pure−noG PS `+1.90`（`[−6.13,+11.90]`，`2/6/2`），没有超过 5 点的损失；但 input 只减少 `14.7%`，未达到 `30%`，所以 graph/noG 次级条件失败。

long-context 首次运行在 8/10 后因交互进程中断且未写 usage；该目录保留为 `long-context-inherit-holdout-interrupted-8of10`，不参与评分。正式 long-context 是查看分数前承诺采用、同参数从空目录完成的 10/10 run。旧 parser 曾用 evaluator 审计全部 270 groups，所以这不是 pristine untouched benchmark。

### 3.6 Compact query-ancestry v3，新冻结 IDs 111–120

先在 development IDs 101–103 冻结 `query-target/base-inheritance-v3`，再固定新的
LLM-e2e / graph-held-out IDs 111–120。四臂共享 `deepseek-v4-flash`、thinking=`default`、
32,768 max tokens、12 max steps、decoder、env、tools 和 episode order。graph/typegraph
只从其余 260 episodes 学习并明确排除 111–120；protocol、config 与图 artifact SHA 均通过
机器审计。

| arm | PS | SPS | SR | input | output | estimated cost | API / wall duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| query-ancestry graph | 93.94% | 99.35% | 70% | **434,162** | 321,216 | **$4.2976** | 2,062.87s / 2,071.42s |
| noG | **95.45%** | **99.48%** | **80%** | 718,215 | 331,166 | $5.1072 | 2,142.08s / 2,149.88s |
| BM25 | 72.73% | 91.91% | 30% | 1,458,020 | 1,166,215 | $15.3072 | 7,894.49s / 7,904.54s |
| long context | 92.42% | 98.70% | **80%** | 2,064,625 | **303,546** | $8.1970 | **1,894.82s / 1,902.81s** |

paired episode-mean PS：pure−noG `−1.43` 点（bootstrap 95% `[−4.29,0.00]`，
W/T/L `0/9/1`）；pure−BM25 `+19.80`（`[+10.04,+29.70]`，`7/3/0`）；
pure−long `+1.07`（`[−4.29,+7.50]`，`1/8/1`）。完整 SPS/SR bootstrap/W/T/L
见 `results/real/p2_compact_v3/round_summary.json`。

冻结验收要求 pure 相对 noG 的 PS 损失不超过 5 点且 input 至少减少 30%。实际
episode-mean PS 损失为 1.43 点，input 减少 **39.55%**，所以合取判断为
**`pass=true` / PASS**。pure 同时相对 noG 少 15.9% cost；相对 BM25 少 70.2% input、
71.9% cost；相对 long context 少 79.0% input、47.6% cost，但 output 多 5.8%、慢 8.9%。
BM25 的 6 个 length finish 与 4 个统一 repair calls 全部保留。每 episode 的 usage 和覆盖
在 round summary 的 `arms.*.usage.per_episode` 中。这是 bundled graph selection + compact
serialization intervention，不是只对 adjacency mask 的单因素估计，也不是 pristine split。

## 4. P3-A — 复用 MINJA failure scenario 恢复 hidden driver

正式配置：`deepseek-v4-flash`、`nutrition_test`、6 templates、8 pre、12 test、25 benign、3 injection retries、seeds 0/1/2；每 seed 81 rounds，共 243 rounds。

| seed | held-out ASR | decisive note-free ∧ poison-retrieved | verdict | Regime-GRACE |
|---:|---:|---:|---|---|
| 0 | 6/12 | 12/37=0.324 | positive | found / gated |
| 1 | 1/12 | 6/31=0.194 | 未越过阈值 | found / gated |
| 2 | 1/12 | 4/8=0.500 | positive | found / not gated |

聚合 held-out ASR `8/36=0.222`，Wilson 95% `[0.117,0.381]`；decisive cell `22/76=0.289`，Wilson 95% `[0.200,0.400]`；无 poison retrieval 的 note-free control 为 `0/77`。正确结论是 pathway 可复现但 seed 异质性显著，不能用 seed 0 的 0.500 test ASR 代替总体结果。

Regime-GRACE 对同轮有序事件开放受约束的 lag-0：

- edge：`poison_retr→anomalous@0`，FOUND `3/3`，GATED `2/3`。
- seed 0 coefficients：trigger=0 `0.0202`（p=`0.8479`），trigger=1 `0.7729`（p=`2.93e-6`）。
- 顺序来源：instrumented runtime 明确记录 retrieval 先于 action。这不是从无序同时观测值中无假设辨向。

这里恢复的是 oracle-tagged event channel 上的结构：运行器通过 record 的 `is_poison` 构造
`poison_retr`，再让 Regime-GRACE 恢复该 read event 到异常动作的边，并由 provenance 回溯
写入轮。因此它支持“门控 read pathway 与写入 ancestry 可恢复”，但不能单独声称完全盲地
发现了哪个 record 是 poison。

传统 PCMCI 结果必须同时报告：blind PCMCI `0/3`；additive u-as-node PCMCI `2/3`；regime-subsampled PCMCI `1/3`。

## 5. P3-A baseline / 第二载体 recovery 与 P3-B mitigation

MemAudit 三 seed：CMIS AUC 分别 `0.670/0.937/0.992`，macro `0.866`；precision@k 分别 `0.758/0.900/0.963`，macro `0.874`。

- 论文未发布实现；本仓按论文复现，并以 lexical overlap 替代 DeBERTa-v3 NLI。不得据此宣称全面击败原方法。

离线 replay gate 三 seed micro：

| gate | prevention | collateral |
|---|---:|---:|
| ancestry + regime | 102/107 = 95.3% | 12/136 = 8.8% |
| ancestry, no regime | 104/107 = 97.2% | 55/136 = 40.4% |
| CMIS + regime | 39/107 = 36.4% | 4/136 = 2.9% |

Regime 条件只少覆盖 2 个异常动作，却少触碰 43 个 benign rounds；这支持“什么时候 edge 激活”是候选策略的重要维度。但这些数字来自保存轨迹上的覆盖计数，不是真实 intervention。

冻结协议的 label-free calibration → held-out online intervention：

| seed | ungated ASR | gated ASR | ungated accuracy | gated accuracy | touched / removed |
|---:|---:|---:|---:|---:|---:|
| 0 | 1/12 | 1/12 | 9/12 | 10/12 | 6 / 7 |
| 1 | 3/12 | 2/12 | 8/12 | 9/12 | 11 / 21 |
| 2 | 2/12 | 2/12 | 9/12 | 10/12 | 3 / 3 |
| micro | 6/36 | 5/36 | 26/36 | 29/36 | 20 / 31 |

micro ASR 下降，但只有 seed 1 同方向改善，未满足至少 2/3 seeds，故 `pass=false`。真正删除记录的 20 题中有 2 prevention、1 reverse trigger、2 attack unchanged；未触碰的 16 个负对照中也出现 1 次表面 prevention 与 1 次 reverse trigger，说明独立调用波动不能归因于 gate。post-hoc driver micro precision `28/38=73.7%`、poison-record recall `28/100=28.0%`。

### 5.1 AgentPoison-StrategyQA：label-free recovery 支持 P3-A

固定矩阵为 64 calibration + 288 held-out trajectories；attack track 每题 3 replicates，
并有 exact no-op 与 trigger-free clean 三臂。requested/returned model 为
`deepseek-chat` / `deepseek-v4-flash`，测试 writeback=false。矩阵、paired decoder seeds、
protocol SHA 与 1,815-event API ledger 均验证通过，0 API failures。

| seed block | ungated | no-op | gated | direction |
|---:|---:|---:|---:|---|
| 0 / IDs 100–107 | 0/24 | 0/24 | 0/24 | tied |
| 1 / IDs 108–115 | 3/24 | 3/24 | 0/24 | improved |
| 2 / IDs 116–123 | 0/24 | 1/24 | 0/24 | tied |
| micro | 3/72 | 4/72 | 0/72 | — |

driver 直接 implicated 1 个 record，cluster expansion 后删除 2 个；post-hoc expanded
precision/recall 均为 100%。三次 gated-vs-ungated prevention 都实际触碰删除集合，且均为
seed 1 / query 114 的固定 replicates；0 reverse trigger。可是只有 `1/3` seed blocks 改善，
未达到 frozen `2/3`，所以尽管 gated 同时低于 ungated/no-op，合取判断仍是 **FAIL**。

这里应先读取 recovery，再读取防御结果。driver 的固定输入只有 record ID、retrieval event、
机械异常动作、temporal ancestry 与 frozen embedding cluster；poison membership 在 driver 与
全部 held-out calls 完成后才附加。直接 implicated 集合为 1 个且命中 1 个 poison record，
precision/recall `100%/50%`；冻结 expansion 后 2 个均命中，precision/recall `100%/100%`。
这为原始 P3-A 提供 label-free record-level 支持，但没有事先冻结独立的 recovery PASS，且
development query 20 也位于 calibration IDs 0–31，故状态是 `SUPPORTED`，不是追溯生成的
confirmatory `pass=true`。

### 5.2 P3-B：两个 online mitigation 协议都 FAIL

MINJA 的 ASR `6/36→5/36` 与 AgentPoison 的 `3/72→0/72` 都有 micro 下降，但两者都只有
`1/3` seed blocks 同方向改善。AgentPoison 虽还满足 gated 低于 no-op `4/72`，仍未满足冻结
合取条件。两个结果文件中的 `pass=false` 原样保留；它们回答的是部署期防御稳定性，不是
原始的 post-failure hidden-driver auditing 问题。

clean / clean-noop / clean-gated accuracy 为 11/24、8/24、6/24；clean-gated 没有一次
retrieval 被删除，却相对 clean 有 10/24 答案变化。因此 normal accuracy 差不能当成删除
collateral，而是强烈的独立调用噪声证据。完整 usage、parse failures 与分层转移见
`docs/p3-minja-causal-audit-results.md` 和
`results/real/p3_agentpoison_round2/summary.json`。

## 6. 代码与结果入口

核心代码：

- `code/regime_grace.py`：regime-conditioned estimator；支持由 `within_step_order` 限定的 lag-0 边。
- `code/arena_causal_memory.py`：MemoryArena 插件与 pure-discovery arm。
- `code/arena_serve_causal.py`：不修改上游的运行时注册服务。
- `code/arena_p2_benchmark.py`：answerability-at-cost。
- `code/arena_e2e_run.py`：固定 episode subset，管理两类 server 生命周期，可恢复。
- `code/arena_e2e_inherit.py`：query target parser、base inheritance decoder、offline counterfactual 与 parser audit。
- `code/arena_e2e_score.py`：解析 JSONL 后调用官方 evaluator，并合并 usage。
- `code/arena_context_audit.py`：拆分 memory/scaffold/tool/query/dynamic-history 输入开销。
- `code/arena_p2_round_summary.py`：验证 frozen manifest、四臂覆盖、runtime、公平性与 P2 判断。
- `code/arena_e2e_failure_audit.py`：逐 person/day/slot 复用官方检查，分解 constraint 与其他槽位失败。
- `code/minja_causal_audit.py`：忠实 schedule、API 错误日志、逐轮原子 checkpoint、`--resume`。
- `code/minja_causal_analysis.py`：decisive cell、provenance、PCMCI 与 Regime-GRACE。
- `code/minja_replication_summary.py`：按 seed 独立分析后做 micro/macro、Wilson 与 gate 聚合，不跨 seed 构造时序 lag。
- `code/minja_online_gate.py`：不读 poison 标签的 calibration、冻结 driver、真实 held-out 双臂调用。
- `code/minja_online_gate_summary.py`：聚合 arm endpoint，并按 touched/untouched 分层配对转移。
- `code/agentpoison_strategyqa_gate.py`：AgentPoison-StrategyQA immutable-snapshot paired gate。
- `code/agentpoison_strategyqa_summary.py`：验证固定 288-cell 矩阵、API ledger 与 P3 判断。
- `code/p3_hidden_driver_summary.py`：分离 P3-A recovery evidence 与 P3-B 冻结 online judgement；不会追溯生成 recovery PASS。
- `code/memaudit_baseline.py`、`code/causal_gate.py`：baseline 与防御闭环。
- `code/run_with_local_deepseek.py`：只在 child environment 注入 ignored 本地 key。
- `code/make_report.py`：读取旧轮与新冻结轮结果并生成 `artifacts/experiments.html`。

正式结果：

- `results/real/p2_benchmark_v2_summary.json`
- `results/real/p2_benchmark_pure_summary.json`
- `results/real/e2e_scores.json`
- `results/real/e2e_scores_rerun.json`
- `results/real/e2e_failure_audit.json`
- `results/real/e2e_scores_inherit.json` / `e2e_failure_audit_inherit.json`（offline counterfactual）
- `results/real/e2e_scores_inherit_online.json` / `e2e_failure_audit_inherit_online.json`（fresh online）
- `results/real/e2e_inherit_target_audit.json`
- `results/real/e2e_scores_holdout_101_110.json`
- `results/real/typegraph_holdout_101_110.json`
- `results/real/travel_learned_graph_holdout_101_110.json`
- `results/real/minja_trace_v2.csv`
- `results/real/minja_trace_v2.transcript.json`
- `results/real/minja_trace_seed1.csv` / `.transcript.json`
- `results/real/minja_trace_seed2.csv` / `.transcript.json`
- `results/real/minja_audit_report_v2.json`
- `results/real/minja_audit_report_seed1.json`
- `results/real/minja_audit_report_seed2.json`
- `results/real/minja_replication_summary.json`
- `results/real/memaudit_baseline_v2.json`
- `results/real/causal_gate_v2.json`
- `results/real/minja_online_gate_seed0.json`、`seed1.json`、`seed2.json`
- `results/real/minja_online_gate_summary.json`
- `results/real/p2_compact_v3/frozen_protocol.json`
- `results/real/p2_compact_v3/e2e_scores.json`
- `results/real/p2_compact_v3/round_summary.json`
- `results/real/p3_agentpoison_round2/frozen_protocol.json`
- `results/real/p3_agentpoison_round2/agentpoison_strategyqa_gate.json`
- `results/real/p3_agentpoison_round2/summary.json`
- `results/real/p3_hidden_driver_recovery_summary.json`

## 7. 环境、数据与安全

- 当前节点 4×H100 可用；本轮真实 LLM 走 DeepSeek API，P2 runner 保持 CPU 路径，未因“有 GPU”而改写实验条件。
- live key 位于本地 `deepseek_apikey.md`，已被 `.gitignore` 排除。不得输出或提交。
- `deepseek-v4-*` 为 reasoning model，`max_tokens` 过小会返回空 content + `finish_reason=length`；当前审计默认 6000。
- 不要设置项目内 `TMPDIR`：它曾稳定触发 `Authentication Fails (governor)`；本节点 `/tmp` 约 1.9TB 可用。
- MemoryArena travel 需要 `clean_Flights_2022.csv`，SHA256：`8dafdb0e3f8b79ce599a1e612a772865295bc226b46e5fb278368f7255b11cee`。
- MemoryArena 没有 LICENSE；MemoryArena、MINJA、AgentPoison 三个上游 checkout 均必须保持 clean。

## 8. 复核命令

```bash
python3 -m compileall -q code
python3 code/regime_grace.py
python3 code/minja_causal_analysis.py \
  --trace results/real/minja_trace_v2.csv \
  --out results/real/minja_audit_report_v2.json
python3 code/memaudit_baseline.py \
  --transcript results/real/minja_trace_v2.transcript.json \
  --out results/real/memaudit_baseline_v2.json
python3 code/causal_gate.py \
  --transcript results/real/minja_trace_v2.transcript.json \
  --out results/real/causal_gate_v2.json
python3 code/minja_replication_summary.py
python3 code/minja_online_gate_summary.py
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure causal-learned bm25 long_context
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure-rerun causal-learned-rerun \
  --out results/real/e2e_scores_rerun.json \
  --reference results/real/e2e_scores.json
python3 code/arena_e2e_failure_audit.py \
  --arms causal-learned-pure causal-learned bm25 long_context \
         causal-learned-pure-rerun causal-learned-rerun \
  --out results/real/e2e_failure_audit.json
python3 code/arena_e2e_inherit.py --validate_targets
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure-inherit causal-learned-inherit \
  --out results/real/e2e_scores_inherit_online.json
python3 code/arena_e2e_failure_audit.py \
  --arms causal-learned-pure-inherit causal-learned-inherit \
  --out results/real/e2e_failure_audit_inherit_online.json
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure-inherit-holdout \
         causal-noG-inherit-holdout \
         bm25-inherit-holdout \
         long-context-inherit-holdout \
  --out results/real/e2e_scores_holdout_101_110.json
python3 code/arena_e2e_score.py \
  --e2e_dir results/real/p2_compact_v3/e2e \
  --model deepseek-v4-flash \
  --arms query-ancestry-v3-heldout-111-120 \
         noG-v3-heldout-111-120 \
         bm25-v3-heldout-111-120 \
         long-context-v3-heldout-111-120 \
  --pairs \
    query-ancestry-v3-heldout-111-120:noG-v3-heldout-111-120 \
    query-ancestry-v3-heldout-111-120:bm25-v3-heldout-111-120 \
    query-ancestry-v3-heldout-111-120:long-context-v3-heldout-111-120 \
  --out results/real/p2_compact_v3/e2e_scores.json
python3 code/arena_p2_round_summary.py \
  --input results/real/p2_compact_v3/e2e_scores.json \
  --pure query-ancestry-v3-heldout-111-120 \
  --nog noG-v3-heldout-111-120 \
  --bm25 bm25-v3-heldout-111-120 \
  --long-context long-context-v3-heldout-111-120 \
  --expected-ids 111 112 113 114 115 116 117 118 119 120 \
  --graph results/real/p2_compact_v3/travel_learned_graph_holdout_111_120.json \
  --configs \
    results/real/p2_compact_v3/configs/travel_query-ancestry-v3-heldout-111-120.json \
    results/real/p2_compact_v3/configs/travel_noG-v3-heldout-111-120.json \
    results/real/p2_compact_v3/configs/travel_bm25-v3-heldout-111-120.json \
    results/real/p2_compact_v3/configs/travel_long-context-v3-heldout-111-120.json \
  --protocol-document docs/p2-p3-next-round-preregistration-2026-08-30.md \
  --out results/real/p2_compact_v3/round_summary.json
python3 code/agentpoison_strategyqa_summary.py \
  --input results/real/p3_agentpoison_round2/agentpoison_strategyqa_gate.json \
  --out results/real/p3_agentpoison_round2/summary.json
python3 code/p3_hidden_driver_summary.py
python3 code/make_report.py
git diff --check
git -C benchmarks/MemoryArena status --short
git -C benchmarks/MINJA status --short
git -C benchmarks/AgentPoison status --short
```

## 9. 后续边界

截至 2026-08-30，本轮冻结矩阵均已完成并停止：P2 compact-v3 graph/noG 验收通过；P3-A
hidden-driver auditing 有支持性证据和明确识别边界；P3-B 的 MINJA 与
AgentPoison-StrategyQA online mitigation 均因只有 1/3 seed blocks 改善而失败。没有待补跑的
正式 cell。若继续，必须另写新协议：P2 可在另一任务检验 bundled
selection/serialization 是否泛化，并设计能拆开两部分贡献的 ablation；P3-A 若要升级为
独立 confirmatory recovery，应排除 development/calibration overlap，并让 MINJA record
discovery 不读取 oracle-derived `poison_retr`。P3-B 若继续则需提高实际 deletion exposure、
避开两个 seed 的 0-ASR floor，并进一步减少独立调用噪声。不得补抽有利 seed/ID、增加
结果导向的 replicate，或回写任一冻结负结果。
