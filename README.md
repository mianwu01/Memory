# Causal Memory / 因果记忆

> **2026-09-15 当前状态：实现已修复，完整验收因 API 余额不足中断。** Mem0 完整检索、
> A-Mem 论文 robust 实现、LightMem 完整机制已接通；三个 online 小例和两个 Travel 开发案例通过。
> aiaaa 与 TokenRhythm 的生成接口均已明确返回 `INSUFFICIENT_BALANCE`。三套完整 LoCoMo 验证未通过，
> 正式 100 cases 尚未冻结或启动；下方旧 v5 仅为历史探索性结果。
> [当前状态与待完成项](docs/yujia-progress-2026-09-15.md) · [修复与验收记录](docs/faithful-memory-remediation-2026-09-15.md)。

<!-- recent-memory-completion:start -->
> **历史探索性配对评估（已降级）：** 十臂均完成 IDs 111/112/113，官方评分与用量完整性检查通过。
> [结果表与逐 episode 比较](results/real/p2_recent_baselines_tokenrhythm_v5_completed/results.md)；表中完整结果的用量估算 ¥25.3557。
> 新中转探针及全部开发/评估合计估算 ¥46.4821，
> 加旧账单 ¥230 后为 ¥276.4821。缺失用量与 aiaaa 未知费用未计入；不是对账总额。
> 这是三个复用 holdout episodes 的描述性配对复验；不证明 causal necessity 或真实 latent identifiability。
> summary 使用按预先记录的技术恢复规则完成的补跑，其余九臂保留原结果；原始批次的断流失败及费用另行保留。
<!-- recent-memory-completion:end -->

**旧 v5 对照（不进入新主表）：** Ours 与同格式 noGcompact 的逐 episode PS/SPS/SR 全部持平，官方 person-PS 都为 90.91%（20/22）。输入从 245,599 降至 123,701 tokens，减少 49.63%；总费用估算为 ¥0.8067 / ¥0.7713，Ours 高 4.59%。这支持输入压缩的观察；相对这一对照，本轮未显示准确率或货币成本优势。

本项目把 agent memory 建模为可审计的时序因果结构：同一张图既用于选择更小的记忆上下文，也用于定位并 gate 被投毒记忆所驱动的动作。

> **9/04 会议执行更新（2026-09-14）：** 主线转为近期 memory baseline、公平比较、具体
> demo 与论文 outline；simulation 冻结。已接入 Mem0 OSS / 作者 A-Mem SDK / LightMem，
> 并增加 rolling summary、dense 和同格式 noGcompact 消融。旧中转曾返回
> **401 Invalid token**；现已切换 TokenRhythm，完整新配对评估已完成，结果见本页顶部。
> 已完成 [执行报告](docs/yujia-meeting-delivery-2026-09-14.md)、
> [具体 demo / PDF](results/real/yujia_meeting_2026_09_04/slides.pdf)、
> [可展开证据的可视化](results/real/yujia_meeting_2026_09_04/slides.html)、
> [变量口径](docs/yujia-setting-2026-09-04.md) 和
> [段落 / 句子目标 outline](docs/yujia-paper-outline-2026-09-04.md)。
> 英文 outline 已接入原 `causal_memory_formulation.tex`；历史负结果保留。

> **2026-09-14 API 路由更新：** 新运行通过 `https://tokenrhythm.studio/v1`，模型 `deepseek-flash`，凭据保存在
> Git 忽略的本地 `deepseek_apikey.md`。启动命令使用
> `python3 code/run_with_local_deepseek.py -- <原命令>`；wrapper 同时设置凭据与
> `OPENAI_BASE_URL` / `OPENAI_API_BASE`，覆盖继承的旧路由。历史冻结结果与配置保持原样，
> 更换路由后的实验应使用新结果目录。连通性与延迟实测见
> [按量中转测试与预算](docs/tokenrhythm-switch-2026-09-14.md)：16/16 探针通过，估算 ¥0.114。
> 旧正式协议 family 为 `p2_recent_baselines_tokenrhythm_v5`；
> [自动续跑状态](results/real/p2_recent_baselines_tokenrhythm_v5/recovery_state.json) 与
> [累计费用快照](results/development/tokenrhythm_cumulative_budget_2026_09_14.json) 独立记录。
> 旧约 300 元只是初步规划，完整开发的长推理与重跑费用须重新校准。

> **2026-08-31 benchmark redesign:** 对原 MemoryArena Travel 的复核确认其
> query-aware structured lookup 已接近 oracle，因此旧 P2 只保留为结构化记忆压缩证据，
> 不再单独承担“causal discovery 必要”的主张。本仓已在不修改上游 checkout 的前提下，
> 并行新增 Dynamic Travel、Dynamic Shopping、Dynamic Search 与 Causal Formal 四个
> intervention/propagation 原型；统一 480-episode 零 LLM T0 schema/admission 全部通过。
> 这只说明任务值得进入 learned-method 实验，不是 learned graph 已获胜。设计、边界与
> 强 baseline 矩阵见 [四任务重设计](docs/causal-benchmark-redesign.md) 和
> [统一准入协议](docs/causal-benchmark-protocol.md)。

> **2026-08-31 T1 + simulation-v2 status:** 四个重设计任务的 train-only、novel-split、
> 六臂 T1 已全部完成。learned selector 在四项任务都优于 matched generic retrieval，且相对
> full history 使用更少 compact context；但四项的最强 domain baseline 也都达到 `1.0`
> task success，learned 没有一项胜出。因此 `tasks_beating_domain_solver=[]`、
> `tasks_supporting_causal_learning_claim=[]`：T1 支持结构化 dependency/impact selection，
> **不支持 causal structure necessity**。P1 simulation v2 也已完成 3 个 DGP family × 5 seeds：
> observed linear/nonlinear 上 regime-conditioned discovery 为 `1.0` overall/read F1；latent
> observed-only 为 `0.8/0.667`，只有明确标作 measured-proxy fallback 的 grouped arm 达到
> `1.0`。它证明已知 DGP 下 regime conditioning 的价值，不证明 latent identification 或
> agent-memory utility。
>
> 当前总体 claim matrix、精确 sample/variable 定义、8-15 遗留状态与禁止表述见
> [Yujia 故事线总审计](docs/yujia-story-audit-2026-08-31.md)；指标选择依据见
> [Agent Memory 评估综述](docs/memory-evaluation-literature-review.md)。机器可读裁决为
> `results/development/yujia_story_audit.json`。

> **2026-08-31 real-API six-arm status:** DeepSeek key 已通过本地
> `deepseek_apikey.md` wrapper 使用，不再受“没有 key”阻塞。冻结的 4 task × 12 test
> episodes × 6 arms 已完成 288/288 request rows 与 309 条 usage-ledger events，总费用
> `$6.607622`。hash/integrity 与 full scope 均完整；284/288 responses 可评分，4 个
> full-state responses 在冻结重试预算后仍为未评分 missing，所以
> `experiment_complete=false`，**没有把工程缺失记成语义 0 分**。learned selector 在四项
> valid cases 的 selection F1/endpoint 都为 1.0，并显著少于 full-state context；但静态
> 审计发现 v1 domain arm 只是 conservative reachability，且 Travel/Shopping/Formal 仍有
> structured shortcut。故本轮是 real-API execution/efficiency 证据，不是 causal-necessity
> confirmatory PASS。完整数字、失败分类与 artifact hashes 见
> [真实 API 六臂 v1 结果](docs/causal-api-six-arm-v1-results.md)。

> **2026-08-31 anti-shortcut stop:** dev-only killer audit 在四项 v1 task 上都发现
> 100% sufficient 的 lookup write superset，故四项都触发 causal-necessity stop rule。
> hidden-routing v2 也被独立反驳审计 fail-closed：公平 train-enabled program 与 learner
> 完全并列、history 逐边暴露 potential skeleton、四个 domain 的结构 fingerprint 完全
> 相同，最终 verdict 为 `PARTIAL`、`all_domains_pass=false`，未调用新 API。证据见
> [hidden-routing v2](docs/hidden-routing-v2.md)。真正不同的四领域、non-idempotent
> executable transaction 与 strongest relational baseline 已写成
> [Hidden Mechanism v3 预注册](docs/hidden-mechanism-v3-preregistration.md)，按 8-15 要求
> 等待 Yujia double-check 后才实现/冻结 test。

截至 2026-08-31，各实验部分均已有可复核结果；T1/simulation 为 deterministic CPU
实验，P2/P3 含真实 agent/LLM 运行。P3 按原始 auditing 问题与后来追加的 online
mitigation 验收分开报告：

| 部分 | 状态 | 关键结果 |
|---|---|---|
| Four-task real API v1 | **完成 scope；confirmatory 不通过** | 288 rows / 309 ledger events / $6.607622；284 可评分、4 missing；learned valid endpoint 4/4 为 1.0，但弱 domain arm、task shortcut 与语义合同重试阻止 causal-win 解读 |
| Anti-shortcut / hidden-routing v2 | **STOP / PARTIAL** | v1 lookup sufficient-mask 4/4 触发 stop；v2 fair program 与 learner tie、四域同构，未授权新 API |
| Causal benchmark T1 | **完成；necessity 0/4** | 四任务 novel split 与 runtime gold isolation 均通过；learned 四项均胜 generic retrieval，但与 task-success=1.0 的强 domain baseline 持平，causal-learning claim 全部 `false` |
| P1 simulation v2 | **完成（有 latent 边界）** | 240 episodes/seed、5 seeds、`delta=10`；linear/MLP observed 的 regime-conditioned overall/read F1 均 1.0；latent observed-only 0.8/0.667，grouped measured-proxy fallback 1.0 |
| 方法 E0 | 完成 | 三档噪声下 Regime-GRACE 均恢复 2/2 gated read edges；blind 与 additive baseline 均为 0/2 |
| P2 / MemoryArena | 新冻结 graph/noG 验收通过；旧轮失败保留 | compact-v3 IDs 111–120：pure−noG episode-mean PS `−1.43` 点、95% `[−4.29,0.00]`、W/T/L `0/9/1`，input 减少 `39.55%`，协议 `pass=true`；旧 IDs 101–110 仅减少 14.7% 的结果不覆盖 |
| P3-A / hidden-driver auditing | **SUPPORTED（有识别边界）** | MINJA hidden-memory pathway 22/76、Regime-GRACE 3/3 找到 edge、3/3 定位写入祖先；AgentPoison 的 label-free driver 直接恢复 1/2 poison records，冻结 cluster expansion 后恢复 2/2 |
| P3-B / held-out online mitigation | **FAIL（两轮冻结负结果均保留）** | MINJA ASR 6/36→5/36、AgentPoison 3/72→0/72 且低于 no-op 4/72，但两者都只有 1/3 seed blocks 改善，各自协议均 `pass=false` |

详细结论与诚实边界见：

- [最终交接与状态](docs/HANDOFF.md)
- [P2 MemoryArena 结果](docs/p2-memoryarena-plugin-results.md)
- [P3 MINJA 因果审计结果](docs/p3-minja-causal-audit-results.md)
- [P2/P3 2026-08-30 新轮冻结协议](docs/p2-p3-next-round-preregistration-2026-08-30.md)
- [自动生成实验报告](artifacts/experiments.html)

## 目录

```text
code/                    实验、插件、审计、gate 与报告脚本
results/real/            真实平台 / 真实 LLM 结果
artifacts/               四部曲网页与自动生成实验报告
docs/                    设计、复核、结果与交接文档
benchmarks/MemoryArena/  本地恢复的上游仓库，不提交其内容
benchmarks/MINJA/        本地恢复的上游仓库，不提交其内容
benchmarks/AgentPoison/  第二个投毒载体的本地上游仓库，不提交其内容
```

原始“因果记忆四部曲”网页仍位于 `artifacts/01-overview.html` 至 `artifacts/04-execution.html`；本 README 现在以可复现实验为主入口。

## 快速复核

以下命令不调用外部 LLM：

```bash
python3 -m compileall -q code
PYTHONPATH=code python3 code/causal_benchmarks/run_t1_suite.py \
  --episodes 120 --seed 17 \
  --out results/development/causal_benchmarks/suite_t1.json
python3 code/yujia_simulation_v2.py \
  --episodes 240 --delta 10 --seeds 5 \
  --out results/development/yujia_simulation_v2.json
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
python3 code/p3_hidden_driver_summary.py
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure causal-learned bm25 long_context \
  --out results/real/e2e_scores.json
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure-rerun causal-learned-rerun \
  --out results/real/e2e_scores_rerun.json \
  --reference results/real/e2e_scores.json
python3 code/arena_e2e_failure_audit.py \
  --arms causal-learned-pure causal-learned bm25 long_context \
         causal-learned-pure-rerun causal-learned-rerun \
  --out results/real/e2e_failure_audit.json
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
python3 code/make_report.py
```

忠实 MINJA LLM 重跑命令如下。它有逐轮原子 checkpoint，可用 `--resume` 恢复：

```bash
python3 code/run_with_local_deepseek.py -- python3 -u code/minja_causal_audit.py \
  --backend openai --model deepseek-v4-flash \
  --file_name nutrition_test --num_templates 6 \
  --num_pre 8 --num_test 12 --num_benign 25 \
  --extra_benign_subjects 0 --inject_attempts 3 --seed 0 \
  --out results/real/minja_trace_v2.csv --verbose
```

仅在进程中断且同参数 checkpoint 存在时追加 `--resume`；已完成的正式结果没有 checkpoint。

## MemoryArena e2e

先按 `benchmarks/MemoryArena/setup_travel.md` 获取 travel 数据库，并将 `clean_Flights_2022.csv` 放在：

```text
benchmarks/MemoryArena/env/env_systems/travel_planner_env/database/flights/
```

本仓的 wrapper 会以同一 episode 子集运行四臂、管理 env/memory servers 的生命周期，并跳过已有输出：

```bash
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned-pure.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_bm25.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_long_context.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure causal-learned bm25 long_context
```

对 PS=0 的两个方法臂，确认性 run B 使用同一模型、参数和 IDs 1–5，但写入新目录；run A 不覆盖：

```bash
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned-pure-rerun.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned-rerun.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure-rerun causal-learned-rerun \
  --out results/real/e2e_scores_rerun.json \
  --reference results/real/e2e_scores.json
```

用户质疑后新增的 exploratory repair 只允许模型改 query 明确指定的 day/slot，其他槽位继承公开 base itinerary。它不读取 person gold，也不调用 evaluator 决定输出；原 run A/B 不覆盖：

```bash
python3 code/arena_e2e_inherit.py --validate_targets
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned-pure-inherit.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned-inherit.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure-inherit causal-learned-inherit \
  --out results/real/e2e_scores_inherit_online.json
```

## 环境与安全

- 本节点可见 4 张 H100，但当前真实 LLM 实验走 DeepSeek API；MemoryArena runner 为避免上游可选依赖误占 GPU，显式按 CPU 路径运行。
- 依赖包括 `pandas`、`numpy`、`scikit-learn`、`tigramite`、`python-Levenshtein`、`gdown`，以及 MemoryArena / MINJA 各自的上游依赖。
- DeepSeek key 保存在本地 `deepseek_apikey.md`，该文件已加入 `.gitignore`。不要打印、提交或复制到报告。
- 本节点 `/tmp` 空间充足；不要设置项目内 `TMPDIR`。该设置曾导致 DeepSeek governor authentication failure。
- MemoryArena 没有 LICENSE；本项目只做运行时注册，不修改或分发上游源码。完成后 MemoryArena、MINJA、AgentPoison 三份上游仓库的 `git status --short` 都应为空。

## 结论边界

- 四任务 T1 的 learned arm 都达到 perfect task endpoint，也都胜过 matched generic retrieval；但它们与强 domain solver 在 task success 上全部持平。因而这里能主张的是 train-only impact selection、novel-split generalization 和相对 full history 的上下文效率，不能主张 learned causal graph 的必要性。所有 T1 endpoint 共用 deterministic/oracle value decoder，selection 与 serialization 已正交，但尚不是语言解析或方程学习的端到端结果。
- Simulation v2 的线性、非线性和 latent-confounded family 都是 generator-owned known DGP。对 unobserved `h` 的 incident edges 不作为 observed-only estimator 可恢复边评分；`h_group` 是两项 noisy measurements 的显式 grouped-proxy fallback，不是从原始语言自动发现 latent variable。该实验不能替代 agent benchmark。
- P2 的 60-episode 主结果测量 answerability-at-cost，不等于任务成功率；原始四臂和确认性 run B 的负结果必须保留。inheritance 是看过失败模式后提出、并在相同 IDs 上开发/验证的 exploratory repair，不是对原预注册结果的替换，也尚未证明可泛化到 unseen IDs。
- fresh online inheritance arm 中 learned 为 PS/SPS/SR `100/100/100%`，pure 为 `81.08/90.26/0%`；learned−pure 的 episode-mean PS 差为 `+18.69` 点，bootstrap 95% `[+12.86,+28.33]`，5/0/0。满分 learned 仍使用 query 人名作为 seed；pure 移除了该 oracle，oracle gap 仍然存在。
- graph-held-out / LLM-e2e-held-out IDs 101–110 上，pure 相对 BM25 的 PS 主判断通过（`+16.55` 点，95% `[+9.17,+25.24]`，`8/2/0`）；但相对 noG input 只减少 `14.7%`，所以“PS 损失不超过 5 点且 input 至少减少 30%”的图/noG 次级条件失败。旧 parser 曾用 evaluator 审计全部 270 groups，因此这不是 pristine untouched benchmark。
- 同一确认实验中，pure/long-context PS 为 `91.78%/86.30%`，episode-mean 差 `+5.18` 点（95% `[0,+10.54]`，`3/7/0`）。pure 少 72.9% input、低 31.7% cost，但多 34.4% output、慢 35.0%，必须保留多轴 trade-off。
- 新冻结 IDs 111–120 的 compact query-ancestry arm 相对 noG 的 episode-mean PS 为 `−1.43` 点（95% `[−4.29,0.00]`，`0/9/1`），input 从 718,215 降到 434,162（`−39.55%`），因此两个合取条件均通过。pure−BM25 PS 为 `+19.80` 点（`[+10.04,+29.70]`，`7/3/0`）；pure−long 为 `+1.07`（`[−4.29,+7.50]`，`1/8/1`）。这是 graph selection + compact serialization 的 bundled intervention，且 parser 曾审计全量 groups，仍不能称 pristine untouched benchmark。
- 原始 P3 问题是复用近期 safety failure scenario 后恢复 hidden driver；online gate 是后续扩展，不能用它的 `pass=false` 覆盖 auditing 证据。`results/real/p3_hidden_driver_recovery_summary.json` 将 P3-A 标为 `SUPPORTED_WITH_IDENTIFICATION_BOUNDARIES`，但 `confirmatory_pass=null`：这是对既有冻结证据的诚实综合，不是事后新造的二元验收。
- P3 的三 seed 结果有明显异质性；聚合 decisive rate 为 22/76，但单 seed 只有 2/3 越过阈值。MINJA 的 `poison_retr` 由 `is_poison` 构造，因此 3/3 edge recovery 是 oracle-tagged event channel 上的结构恢复，不等于完全盲的 record discovery；lag-0 方向还来自 instrumented runtime order（先 retrieve、后 act），不是在无假设的同时观测数据上自动辨向。
- P3 旧 gate 的 `95.3% prevention` 是保存轨迹上的 replay coverage，不是真实重调 LLM。冻结协议的 online gate micro ASR 为 `6/36→5/36`，只有 `1/3` seeds 改善，未达到至少 `2/3` 的验收要求；untouched 负对照也出现答案差异，不能把全部 accuracy 变化归因于 gate。
- AgentPoison-StrategyQA 的 recovery 与 mitigation 必须分开：driver 在不读 poison label/source 或 test outcome 的情况下直接恢复 1/2 poison records，冻结 cluster expansion 后为 2/2，支持 P3-A；但该 recovery 没有独立预注册的二元 PASS，且 development query 20 也包含在 calibration 0–31 中。在线 gated attack probability 为 `0/72`，低于 ungated `3/72` 和 exact no-op `4/72`，却只有 `1/3` seed blocks 改善，所以 P3-B 的冻结判断仍为 FAIL。clean-gated 没有触碰 retrieval 却相对 clean 改变 10/24 答案，normal accuracy 差不能归因于删除。
- blind PCMCI 在 P3 上仍 miss；MemAudit CMIS 也没有被本方法在“投毒检测分数”上击败。项目的正面主张是时序 ancestry、regime gating 与同图双用。
