# Causal Memory / 因果记忆

本项目把 agent memory 建模为可审计的时序因果结构：同一张图既用于选择更小的记忆上下文，也用于定位并 gate 被投毒记忆所驱动的动作。

截至 2026-08-30，各实验部分均已有真实系统结果。P3 按原始 auditing 问题与后来追加的
online mitigation 验收分开报告：

| 部分 | 状态 | 关键结果 |
|---|---|---|
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
export OPENAI_API_KEY='<DeepSeek key>'
export OPENAI_BASE_URL='https://api.deepseek.com/v1'
python3 -u code/minja_causal_audit.py \
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
