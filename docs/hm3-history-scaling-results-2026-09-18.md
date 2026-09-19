# HM3 history-length scaling 与 backward provenance：执行记录与结果（2026-09-18）

设计：[scaling](hm3-history-scaling-design-2026-09-18.md)、[provenance](hm3-provenance-design-2026-09-18.md)。
本页只记录实际执行与结果；表格由 `python3 -m hm3.run_scaling --summarize <json>` 与
`results/real/hm3/scaling/*/llm_summary.json` 生成后粘贴，不手改数字。

## 1. 执行时间线与偏离设计的地方

1. 2026-09-18 设计页提交（`788428d`）后完成 dev 校准修订（设计 §9，`80eb014`）。
2. **API 在 dev P1/P2 判定之前启动**（用户指示：时间紧，先用 API）。dev 确定性面板由第二个 session
   并行运行；两者结果并列报告，API 结果不以 dev 门槛为前提。这是相对设计 §7 的偏离。
3. 端点：AutoDL OpenAI-compatible，`deepseek-v4-flash`（返回 `DeepSeek-V4-Flash-0731`）。该模型默认
   reasoning；首次启动的 4 个 native shard 产生了 1–2 个 cell（每 cell 约 18k 输出 token）后被停止，
   目录改名为 `results/real/hm3/scaling/travel_native_thinking_probe/`，不计入结果。之后 client 按
   MINJA AutoDL campaign 的做法发送 `thinking: disabled, reasoning_effort: none`，探针输出 1 token。
4. 费用按 `llm.py` 的 DeepSeek 费率估计（uncached input 2.5 / cached 0.25 / output 10 美元每百万）；
   AutoDL 实际计费未知。shard 预算：Travel native $3、100 $6、500 $10；Shopping 相同。native 档的
   预算按实际单价（约 $0.033/cell）不足以覆盖 16 个 episode × 8 cells，用同一目录带 `--resume_from`
   续跑补齐。
5. Shopping32 首次进入 LLM 臂：新增 OP card 与 catalog 序列化（`fd65fdb`）；Travel 的 prompt 不受影响。
6. 4 个 API key，每档 4 个 shard（episode 0–15 / 16–31 / 32–47 / 48–63），test seed 30，prompt v2，
   temperature 0，selections `graph_closed / full / bm25_k16 / recency_k16` × serializations
   `compact / verbose`。

## 2. dev 确定性面板（第二个 session 填写）

（`python3 -m hm3.run_scaling --summarize results/development/hm3/scaling/det_dev_travel.json`）

**第二个 session 的中期快照（Travel；seed 0 全部 8 个条件、seed 1 的 native/50/100 完成；Shopping 尚在运行）**

#### travel

| condition | native | 50 | 100 | 500 | a100 | b100 | c100 | d100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mean records / objects | native | 50 / 138 | 100 / 141 | 500 / 626 | 26 / 34 | 100 / 142 | 100 / 141 | 100 / 141 |
| eval drop rate | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| A implied-differs / keys | — | 224/399 | 224/399 | 113/201 | 113/201 | — | — | — |

**ees** (mean ± sd over seeds)

| method | native | 50 | 100 | 500 | a100 | b100 | c100 | d100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| exact_kv | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| source_union | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| source_regime | 0.033 ± 0.000 | 0.033 ± 0.000 | 0.033 ± 0.000 | 0.033 ± 0.000 | 0.033 ± 0.000 | 0.033 ± 0.000 | 0.033 ± 0.000 | 0.033 ± 0.000 |
| knn | 0.317 ± 0.017 | 0.333 ± 0.050 | 0.292 ± 0.042 | 0.367 ± 0.000 | 0.300 ± 0.000 | 0.233 ± 0.000 | 0.283 ± 0.000 | 0.233 ± 0.000 |
| superset | 0.017 ± 0.017 | 0.017 ± 0.017 | 0.017 ± 0.017 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| program | 0.650 ± 0.033 | 0.042 ± 0.025 | 0.192 ± 0.192 | 0.000 ± 0.000 | 0.667 ± 0.000 | 0.183 ± 0.000 | 0.217 ± 0.000 | 0.000 ± 0.000 |
| program_reg | 0.675 ± 0.008 | 0.642 ± 0.008 | 0.667 ± 0.017 | 0.683 ± 0.000 | 0.683 ± 0.000 | 0.650 ± 0.000 | 0.667 ± 0.000 | 0.650 ± 0.000 |
| graph | 0.833 ± 0.000 | 0.808 ± 0.025 | 0.808 ± 0.025 | 0.800 ± 0.000 | 0.833 ± 0.000 | 0.800 ± 0.000 | 0.733 ± 0.000 | 0.833 ± 0.000 |
| graph_pooled | 0.842 ± 0.025 | 0.825 ± 0.042 | 0.850 ± 0.017 | 0.833 ± 0.000 | 0.817 ± 0.000 | 0.833 ± 0.000 | 0.800 ± 0.000 | 0.817 ± 0.000 |
| rh_oracle | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| oracle | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| retrieval_k8 | 0.417 ± 0.050 | 0.033 ± 0.000 | 0.033 ± 0.000 | 0.033 ± 0.000 | 0.217 ± 0.000 | 0.033 ± 0.000 | 0.033 ± 0.000 | 0.033 ± 0.000 |
| retrieval_k16 | 0.933 ± 0.017 | 0.275 ± 0.058 | 0.033 ± 0.000 | 0.033 ± 0.000 | 0.683 ± 0.000 | 0.033 ± 0.000 | 0.033 ± 0.000 | 0.033 ± 0.000 |
| recency_k16 | 0.942 ± 0.025 | 0.708 ± 0.008 | 0.483 ± 0.100 | 0.367 ± 0.000 | 0.967 ± 0.000 | 0.717 ± 0.000 | 0.667 ± 0.000 | 0.500 ± 0.000 |

**required_read_recall** (mean ± sd over seeds)

| method | native | 50 | 100 | 500 | a100 | b100 | c100 | d100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| exact_kv | 0.113 ± 0.000 | 0.113 ± 0.000 | 0.113 ± 0.000 | 0.113 ± 0.000 | 0.113 ± 0.000 | 0.113 ± 0.000 | 0.113 ± 0.000 | 0.113 ± 0.000 |
| source_union | 0.579 ± 0.004 | 0.579 ± 0.004 | 0.579 ± 0.004 | 0.583 ± 0.000 | 0.583 ± 0.000 | 0.583 ± 0.000 | 0.583 ± 0.000 | 0.583 ± 0.000 |
| source_regime | 0.381 ± 0.004 | 0.381 ± 0.004 | 0.381 ± 0.004 | 0.377 ± 0.000 | 0.377 ± 0.000 | 0.377 ± 0.000 | 0.377 ± 0.000 | 0.377 ± 0.000 |
| knn | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| superset | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| program | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| program_reg | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| graph | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| graph_pooled | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| rh_oracle | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| oracle | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| retrieval_k8 | 0.832 ± 0.005 | 0.717 ± 0.006 | 0.669 ± 0.006 | 0.611 ± 0.000 | 0.768 ± 0.000 | 0.658 ± 0.000 | 0.657 ± 0.000 | 0.681 ± 0.000 |
| retrieval_k16 | 0.973 ± 0.000 | 0.801 ± 0.004 | 0.722 ± 0.007 | 0.621 ± 0.000 | 0.906 ± 0.000 | 0.731 ± 0.000 | 0.728 ± 0.000 | 0.722 ± 0.000 |
| recency_k16 | 0.968 ± 0.002 | 0.895 ± 0.003 | 0.806 ± 0.018 | 0.747 ± 0.000 | 0.971 ± 0.000 | 0.868 ± 0.000 | 0.869 ± 0.000 | 0.794 ± 0.000 |

**n_reads** (mean ± sd over seeds)

| method | native | 50 | 100 | 500 | a100 | b100 | c100 | d100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| exact_kv | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| source_union | 5.667 ± 0.033 | 5.667 ± 0.033 | 5.667 ± 0.033 | 5.700 ± 0.000 | 5.700 ± 0.000 | 5.700 ± 0.000 | 5.700 ± 0.000 | 5.700 ± 0.000 |
| source_regime | 3.508 ± 0.042 | 3.508 ± 0.042 | 3.508 ± 0.042 | 3.467 ± 0.000 | 3.467 ± 0.000 | 3.467 ± 0.000 | 3.467 ± 0.000 | 3.467 ± 0.000 |
| knn | 53.300 ± 0.050 | 187.867 ± 0.067 | 240.508 ± 0.925 | 1125.500 ± 0.000 | 60.167 ± 0.000 | 242.000 ± 0.000 | 241.417 ± 0.000 | 240.667 ± 0.000 |
| superset | 11.483 ± 0.250 | 12.108 ± 0.225 | 12.350 ± 0.150 | 12.267 ± 0.000 | 11.233 ± 0.000 | 12.150 ± 0.000 | 12.117 ± 0.000 | 11.233 ± 0.000 |
| program | 53.300 ± 0.050 | 187.867 ± 0.067 | 240.508 ± 0.925 | 1125.500 ± 0.000 | 60.167 ± 0.000 | 242.000 ± 0.000 | 241.417 ± 0.000 | 240.667 ± 0.000 |
| program_reg | 53.300 ± 0.050 | 187.867 ± 0.067 | 240.508 ± 0.925 | 1125.500 ± 0.000 | 60.167 ± 0.000 | 242.000 ± 0.000 | 241.417 ± 0.000 | 240.667 ± 0.000 |
| graph | 11.483 ± 0.250 | 12.108 ± 0.225 | 12.350 ± 0.150 | 12.267 ± 0.000 | 11.233 ± 0.000 | 12.150 ± 0.000 | 12.117 ± 0.000 | 11.233 ± 0.000 |
| graph_pooled | 11.483 ± 0.250 | 12.108 ± 0.225 | 12.350 ± 0.150 | 12.267 ± 0.000 | 11.233 ± 0.000 | 12.150 ± 0.000 | 12.117 ± 0.000 | 11.233 ± 0.000 |
| rh_oracle | 9.550 ± 0.033 | 9.550 ± 0.033 | 9.550 ± 0.033 | 9.583 ± 0.000 | 9.583 ± 0.000 | 9.583 ± 0.000 | 9.583 ± 0.000 | 9.583 ± 0.000 |
| oracle | 9.550 ± 0.033 | 9.550 ± 0.033 | 9.550 ± 0.033 | 9.583 ± 0.000 | 9.583 ± 0.000 | 9.583 ± 0.000 | 9.583 ± 0.000 | 9.583 ± 0.000 |
| retrieval_k8 | 13.250 ± 0.033 | 13.217 ± 0.017 | 13.217 ± 0.017 | 13.200 ± 0.000 | 13.167 ± 0.000 | 13.200 ± 0.000 | 13.200 ± 0.000 | 13.200 ± 0.000 |
| retrieval_k16 | 20.525 ± 0.308 | 21.283 ± 0.017 | 21.217 ± 0.017 | 21.200 ± 0.000 | 20.900 ± 0.000 | 21.200 ± 0.000 | 21.200 ± 0.000 | 21.200 ± 0.000 |
| recency_k16 | 20.525 ± 0.308 | 21.358 ± 0.008 | 21.350 ± 0.017 | 21.300 ± 0.000 | 20.917 ± 0.000 | 21.367 ± 0.000 | 21.350 ± 0.000 | 21.333 ± 0.000 |


P1–P4 判定（Travel，dev，中期）：P1 成立——graph 的 n_reads 11.5 → 12.3（500 档 / native = 1.07 ≤ 1.25）；
P2 成立——graph EES 0.833 → 0.800（|Δ| = 0.03 ≤ 0.05）；P3 成立——retrieval_k16 的 required-record recall
0.97 → 0.62（下降 0.35 ≥ 0.20），EES 0.93 → 0.03；P4 成立——knn / program_reg 的 reads 53 → 1125，与总记录数
同阶。单类型条件：c100（冲突 witness）对 graph 影响最大（0.733），b100 / d100 无影响；a100（stale 克隆）
无影响。program_reg 的 EES 在四档基本不变（0.64–0.68，它读取全部历史），与 P4 一致，不预注册其下降。
Shopping 与三个 seed 的完整表由第二个 session 补齐。


## 3. API 面板（本 session 填写）

（`python3 -m hm3.llm --summarize --out_dir results/real/hm3/scaling/<domain>_<cond>`，按档位合并）

**中期快照（2026-09-18 晚，shard 仍在运行；每档 64 个 episode 的目标尚未完成，下表 n 为当时已完成数；由 `python3 -m hm3.scaling_api_summary` 生成，正式表在全部 shard 落盘后替换）**

#### travel

| condition | cell | n | EES | legal | affected F1 | input tok | output tok | est $/cell |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| native | bm25_k16/compact | 40 | 0.38 | 0.97 | 0.59 | 2566 | 1855 | 0.025 |
| native | bm25_k16/verbose | 39 | 0.33 | 0.97 | 0.51 | 5840 | 1747 | 0.029 |
| native | full/compact | 41 | 0.56 | 0.98 | 0.82 | 4089 | 2439 | 0.034 |
| native | full/verbose | 40 | 0.50 | 0.95 | 0.80 | 8493 | 2253 | 0.041 |
| native | graph_closed/compact | 42 | 0.31 | 0.95 | 0.75 | 2321 | 1553 | 0.021 |
| native | graph_closed/verbose | 41 | 0.37 | 0.93 | 0.75 | 3799 | 1653 | 0.026 |
| native | recency_k16/compact | 39 | 0.28 | 0.97 | 0.63 | 2695 | 1966 | 0.025 |
| native | recency_k16/verbose | 38 | 0.26 | 0.95 | 0.55 | 5058 | 1384 | 0.023 |
| 100 | bm25_k16/compact | 20 | 0.00 | 0.90 | 0.29 | 6249 | 3003 | 0.043 |
| 100 | bm25_k16/verbose | 20 | 0.00 | 0.85 | 0.12 | 11845 | 3074 | 0.053 |
| 100 | full/compact | 24 | 0.00 | 0.96 | 0.27 | 17108 | 3766 | 0.067 |
| 100 | full/verbose | 21 | 0.05 | 1.00 | 0.22 | 54307 | 3858 | 0.122 |
| 100 | graph_closed/compact | 24 | 0.50 | 0.92 | 0.83 | 2510 | 1786 | 0.024 |
| 100 | graph_closed/verbose | 24 | 0.38 | 0.96 | 0.73 | 5601 | 1876 | 0.028 |
| 100 | recency_k16/compact | 20 | 0.10 | 1.00 | 0.27 | 2597 | 1828 | 0.025 |
| 100 | recency_k16/verbose | 20 | 0.10 | 1.00 | 0.28 | 6517 | 2056 | 0.036 |
| 500 | bm25_k16/compact | 21 | 0.00 | 0.81 | 0.16 | 7222 | 3581 | 0.050 |
| 500 | bm25_k16/verbose | 19 | 0.05 | 0.89 | 0.14 | 11864 | 3044 | 0.053 |
| 500 | full/compact | 21 | 0.05 | 0.95 | 0.24 | 70120 | 3855 | 0.143 |
| 500 | full/verbose | 21 | 0.10 | 0.95 | 0.16 | 237340 | 4058 | 0.385 |
| 500 | graph_closed/compact | 23 | 0.57 | 1.00 | 0.83 | 2782 | 1982 | 0.027 |
| 500 | graph_closed/verbose | 22 | 0.32 | 0.95 | 0.80 | 4389 | 1587 | 0.023 |
| 500 | recency_k16/compact | 19 | 0.21 | 0.74 | 0.23 | 2938 | 2186 | 0.029 |
| 500 | recency_k16/verbose | 19 | 0.16 | 0.95 | 0.30 | 6068 | 1744 | 0.032 |

| condition | paired comparison (EES) | n episodes | mean [95% CI] | W/T/L | input reduction |
|---|---|---:|---|---|---:|
| native | graph_closed/compact − full/verbose | 40 | -0.175 [-0.350, +0.000] | 3/27/10 | 74% |
| native | graph_closed/verbose − full/verbose | 40 | -0.150 [-0.350, +0.050] | 6/22/12 | 55% |
| native | full/compact − full/verbose | 40 | +0.050 [-0.150, +0.250] | 9/24/7 | 51% |
| native | bm25_k16/compact − full/verbose | 40 | -0.125 [-0.300, +0.050] | 4/27/9 | 70% |
| native | recency_k16/compact − full/verbose | 39 | -0.231 [-0.410, -0.051] | 3/24/12 | 67% |
| 100 | graph_closed/compact − full/verbose | 21 | +0.476 [+0.238, +0.714] | 11/9/1 | 96% |
| 100 | graph_closed/verbose − full/verbose | 21 | +0.381 [+0.190, +0.571] | 8/13/0 | 89% |
| 100 | full/compact − full/verbose | 21 | -0.048 [-0.143, +0.000] | 0/20/1 | 69% |
| 100 | bm25_k16/compact − full/verbose | 20 | -0.050 [-0.150, +0.000] | 0/19/1 | 88% |
| 100 | recency_k16/compact − full/verbose | 20 | +0.050 [-0.100, +0.200] | 2/17/1 | 95% |
| 500 | graph_closed/compact − full/verbose | 21 | +0.524 [+0.238, +0.763] | 13/6/2 | 99% |
| 500 | graph_closed/verbose − full/verbose | 21 | +0.238 [-0.048, +0.476] | 7/12/2 | 98% |
| 500 | full/compact − full/verbose | 21 | -0.048 [-0.238, +0.095] | 1/18/2 | 70% |
| 500 | bm25_k16/compact − full/verbose | 21 | -0.095 [-0.238, +0.000] | 0/19/2 | 97% |
| 500 | recency_k16/compact − full/verbose | 19 | +0.105 [-0.105, +0.316] | 3/15/1 | 99% |

Same 19 episodes completed in all conditions (graph_closed/compact and full/verbose):

| condition | graph_closed/compact EES | full/verbose EES | graph input tok | full input tok |
|---|---:|---:|---:|---:|
| native | 0.37 | 0.58 | 2240 | 9745 |
| 100 | 0.53 | 0.05 | 2351 | 54002 |
| 500 | 0.58 | 0.11 | 2977 | 235536 |

#### shopping32

| condition | cell | n | EES | legal | affected F1 | input tok | output tok | est $/cell |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| native | bm25_k16/compact | 21 | 0.43 | 1.00 | 0.67 | 3865 | 2239 | 0.026 |
| native | bm25_k16/verbose | 19 | 0.63 | 0.95 | 0.81 | 7552 | 1808 | 0.023 |
| native | full/compact | 21 | 0.71 | 0.95 | 0.84 | 3538 | 1928 | 0.028 |
| native | full/verbose | 21 | 0.48 | 0.86 | 0.68 | 7503 | 1728 | 0.035 |
| native | graph_closed/compact | 21 | 0.52 | 0.95 | 0.78 | 2696 | 1359 | 0.020 |
| native | graph_closed/verbose | 21 | 0.52 | 0.90 | 0.77 | 6716 | 1416 | 0.030 |
| native | recency_k16/compact | 18 | 0.61 | 0.94 | 0.82 | 3653 | 2098 | 0.025 |
| native | recency_k16/verbose | 17 | 0.65 | 0.88 | 0.89 | 7162 | 1750 | 0.022 |
| 100 | bm25_k16/compact | 15 | 0.27 | 0.93 | 0.39 | 5218 | 2069 | 0.033 |
| 100 | bm25_k16/verbose | 14 | 0.21 | 0.93 | 0.35 | 10879 | 1136 | 0.037 |
| 100 | full/compact | 16 | 0.50 | 1.00 | 0.62 | 16473 | 3152 | 0.062 |
| 100 | full/verbose | 15 | 0.33 | 1.00 | 0.52 | 40312 | 3339 | 0.107 |
| 100 | graph_closed/compact | 17 | 0.41 | 1.00 | 0.56 | 4633 | 1934 | 0.029 |
| 100 | graph_closed/verbose | 17 | 0.53 | 1.00 | 0.77 | 9195 | 1830 | 0.038 |
| 100 | recency_k16/compact | 13 | 0.46 | 0.92 | 0.57 | 5489 | 1980 | 0.032 |
| 100 | recency_k16/verbose | 13 | 0.38 | 1.00 | 0.58 | 12733 | 1690 | 0.043 |

| condition | paired comparison (EES) | n episodes | mean [95% CI] | W/T/L | input reduction |
|---|---|---:|---|---|---:|
| native | graph_closed/compact − full/verbose | 21 | +0.048 [-0.190, +0.286] | 4/14/3 | 64% |
| native | graph_closed/verbose − full/verbose | 21 | +0.048 [-0.238, +0.333] | 5/12/4 | 10% |
| native | full/compact − full/verbose | 21 | +0.238 [+0.000, +0.476] | 7/12/2 | 53% |
| native | bm25_k16/compact − full/verbose | 21 | -0.048 [-0.238, +0.143] | 2/16/3 | 48% |
| native | recency_k16/compact − full/verbose | 18 | +0.111 [-0.111, +0.333] | 3/14/1 | 53% |
| 100 | graph_closed/compact − full/verbose | 15 | +0.067 [-0.200, +0.333] | 3/10/2 | 88% |
| 100 | graph_closed/verbose − full/verbose | 15 | +0.200 [-0.067, +0.467] | 4/10/1 | 77% |
| 100 | full/compact − full/verbose | 15 | +0.133 [-0.200, +0.467] | 4/9/2 | 58% |
| 100 | bm25_k16/compact − full/verbose | 15 | -0.067 [-0.267, +0.133] | 1/12/2 | 87% |
| 100 | recency_k16/compact − full/verbose | 13 | +0.154 [-0.231, +0.538] | 4/7/2 | 86% |


中期读法（只对 Travel）：native 档复现 round 3/4 的方向（graph_closed/compact 低于 full/verbose 约 0.18）；100 与 500 档反转，graph_closed/compact 在同一批 episode 上高于 full/verbose 0.45 与 0.52，配对区间在 0 以上；graph 的 input tokens 三档持平（约 2.3k–2.7k），full/verbose 从 9k 升到 235k。bm25_k16 与 recency_k16 在 100/500 档接近 full 的水平或略高，均远低于 graph。这是预注册预测 P1（reads 平坦）在 actor 侧的对应现象；EES 的档间比较使用同一批 episode（表末）。n 尚小，结论等全部 64 个 episode 完成后再写。



### 3.1 复核：graph_closed 在 100/500 档比 native 档更高的原因（2026-09-18 晚）

同一批 62 个 episode 上 graph_closed/compact 的 EES 为 native 0.21、100 档 0.39、500 档 0.34，而它的 prompt 本应
只依赖真实对象与记录。检查 ledger：三档 prompt 长度完全相同的只有 28/62 个 episode；其余 episode 在增广档位的
选择更大（例如 test-004：native 9 个对象 / 3 条记录，100 档 19 / 7）。原因是 selector 按设计在同一档位的增广
train 上重新拟合（设计 §4），拟合出的决策模型在增广数据上判定更多对象为 changed，read 集合与 closure 随之变大，
actor 因此拿到更多上下文。returned_model、parse_ok（1.00）、finish_reason（stop）三档相同，排除了模型或截断差异。

结论：graph 臂跨档位的 EES 上升来自 selector 重拟合导致的选择变大，不来自干扰记录本身；这与 round 3/4 的
"closure 越完整 actor 越好"一致。为把长度效应与 selector 重拟合分开，增加 `--selector_history native`：
selector 只在 native train 上拟合，此时 graph 的选择按构造与档位无关、prompt 逐字相同。100/500 档的
`travel_{100,500}_natsel` 正在运行（只跑 graph_closed 两种序列化），其 EES 应与 native 档一致（差异即
actor 的采样噪声）；论文主表将同时给出两种 selector 口径。full / bm25 / recency 臂不受此影响。

### 3.2 更强 backbone：DeepSeek-V4-Pro（返回 `DeepSeek-V4-Pro-0813`，thinking off，Travel native 与 500）


#### travel

| condition | cell | n | EES | legal | affected F1 | input tok | output tok | est $/cell |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| native | bm25_k16/compact | 64 | 0.16 | 0.86 | 0.46 | 2766 | 1776 | 0.024 |
| native | bm25_k16/verbose | 64 | 0.22 | 0.80 | 0.55 | 5460 | 1142 | 0.023 |
| native | full/compact | 64 | 0.23 | 0.80 | 0.78 | 3227 | 1582 | 0.023 |
| native | full/verbose | 64 | 0.38 | 0.83 | 0.75 | 7797 | 1298 | 0.031 |
| native | graph_closed/compact | 64 | 0.31 | 0.86 | 0.73 | 2159 | 1422 | 0.020 |
| native | graph_closed/verbose | 64 | 0.20 | 0.78 | 0.73 | 3830 | 956 | 0.017 |
| 500 | bm25_k16/compact | 63 | 0.10 | 0.67 | 0.45 | 3817 | 1565 | 0.024 |
| 500 | bm25_k16/verbose | 63 | 0.05 | 0.56 | 0.43 | 6494 | 678 | 0.022 |
| 500 | full/compact | 63 | 0.10 | 0.52 | 0.60 | 42433 | 1104 | 0.104 |
| 500 | full/verbose | 63 | 0.16 | 0.62 | 0.59 | 175716 | 2182 | 0.348 |
| 500 | graph_closed/compact | 63 | 0.25 | 0.83 | 0.62 | 3264 | 1950 | 0.027 |
| 500 | graph_closed/verbose | 63 | 0.19 | 0.68 | 0.68 | 4266 | 1051 | 0.020 |

| condition | paired comparison (EES) | n episodes | mean [95% CI] | W/T/L | input reduction |
|---|---|---:|---|---|---:|
| native | graph_closed/compact − full/verbose | 64 | -0.062 [-0.234, +0.125] | 15/30/19 | 72% |
| native | graph_closed/verbose − full/verbose | 64 | -0.172 [-0.328, +0.000] | 10/33/21 | 51% |
| native | full/compact − full/verbose | 64 | -0.141 [-0.297, +0.031] | 11/33/20 | 59% |
| native | bm25_k16/compact − full/verbose | 64 | -0.219 [-0.359, -0.062] | 7/36/21 | 65% |
| 500 | graph_closed/compact − full/verbose | 63 | +0.095 [-0.063, +0.254] | 15/39/9 | 98% |
| 500 | graph_closed/verbose − full/verbose | 63 | +0.032 [-0.095, +0.175] | 10/45/8 | 98% |
| 500 | full/compact − full/verbose | 63 | -0.063 [-0.175, +0.048] | 4/51/8 | 76% |
| 500 | bm25_k16/compact − full/verbose | 63 | -0.063 [-0.190, +0.048] | 6/47/10 | 98% |


读法：Pro 在 native 档把 graph_closed/compact 与 full/verbose 的差距从 flash 的 −0.33 收窄到 −0.10
[−0.28, +0.08]；500 档 full/verbose 从 0.38 跌到 0.17（flash 为 0.53 → 0.07），graph_closed/compact 0.28 → 0.24。
Pro 的整体 legal 率低于 flash（0.79–0.85 对 0.95），主要是 expected_revision 错误。费用按 flash 费率估计，
实际 Pro 计费更高。


### 3.3 全部 shard 落盘后的 API 面板（2026-09-18 深夜；Travel 三档 63–64 个 episode 完成；Shopping 100/500 档尚在补齐）


#### travel

| condition | cell | n | EES | legal | affected F1 | input tok | output tok | est $/cell |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| native | bm25_k16/compact | 64 | 0.36 | 0.98 | 0.56 | 2473 | 1883 | 0.025 |
| native | bm25_k16/verbose | 64 | 0.34 | 0.98 | 0.51 | 5572 | 1678 | 0.028 |
| native | full/compact | 64 | 0.58 | 0.95 | 0.83 | 3744 | 2351 | 0.032 |
| native | full/verbose | 64 | 0.55 | 0.97 | 0.82 | 8638 | 2287 | 0.042 |
| native | graph_closed/compact | 64 | 0.22 | 0.95 | 0.68 | 2338 | 1568 | 0.022 |
| native | graph_closed/verbose | 64 | 0.36 | 0.91 | 0.77 | 3737 | 1576 | 0.025 |
| native | recency_k16/compact | 64 | 0.31 | 0.97 | 0.57 | 3016 | 2114 | 0.028 |
| native | recency_k16/verbose | 64 | 0.28 | 0.97 | 0.51 | 5653 | 1682 | 0.026 |
| 100 | bm25_k16/compact | 64 | 0.05 | 0.88 | 0.23 | 6101 | 3252 | 0.045 |
| 100 | bm25_k16/verbose | 64 | 0.03 | 0.86 | 0.15 | 10470 | 2845 | 0.049 |
| 100 | full/compact | 64 | 0.05 | 0.95 | 0.22 | 18081 | 3760 | 0.069 |
| 100 | full/verbose | 64 | 0.05 | 0.98 | 0.20 | 54209 | 3906 | 0.123 |
| 100 | graph_closed/compact | 64 | 0.38 | 0.89 | 0.79 | 2573 | 1708 | 0.023 |
| 100 | graph_closed/verbose | 64 | 0.34 | 0.91 | 0.70 | 5047 | 1782 | 0.026 |
| 100 | recency_k16/compact | 64 | 0.09 | 0.95 | 0.23 | 3087 | 1888 | 0.026 |
| 100 | recency_k16/verbose | 64 | 0.11 | 1.00 | 0.25 | 6515 | 2011 | 0.035 |
| 500 | bm25_k16/compact | 63 | 0.02 | 0.87 | 0.17 | 7049 | 3401 | 0.048 |
| 500 | bm25_k16/verbose | 63 | 0.03 | 0.90 | 0.11 | 11428 | 2923 | 0.051 |
| 500 | full/compact | 63 | 0.02 | 0.95 | 0.21 | 67881 | 3754 | 0.142 |
| 500 | full/verbose | 63 | 0.06 | 0.89 | 0.19 | 236498 | 3892 | 0.384 |
| 500 | graph_closed/compact | 63 | 0.33 | 0.95 | 0.72 | 2593 | 1761 | 0.024 |
| 500 | graph_closed/verbose | 63 | 0.29 | 0.95 | 0.69 | 4499 | 1741 | 0.025 |
| 500 | recency_k16/compact | 63 | 0.06 | 0.89 | 0.18 | 2917 | 1970 | 0.027 |
| 500 | recency_k16/verbose | 63 | 0.05 | 0.92 | 0.18 | 6943 | 1964 | 0.035 |

| condition | paired comparison (EES) | n episodes | mean [95% CI] | W/T/L | input reduction |
|---|---|---:|---|---|---:|
| native | graph_closed/compact − full/verbose | 64 | -0.328 [-0.469, -0.188] | 3/37/24 | 73% |
| native | graph_closed/verbose − full/verbose | 64 | -0.188 [-0.328, -0.047] | 7/38/19 | 57% |
| native | full/compact − full/verbose | 64 | +0.031 [-0.125, +0.188] | 14/38/12 | 57% |
| native | bm25_k16/compact − full/verbose | 64 | -0.188 [-0.328, -0.047] | 6/40/18 | 71% |
| native | recency_k16/compact − full/verbose | 64 | -0.234 [-0.375, -0.094] | 6/37/21 | 65% |
| 100 | graph_closed/compact − full/verbose | 64 | +0.328 [+0.203, +0.469] | 23/39/2 | 95% |
| 100 | graph_closed/verbose − full/verbose | 64 | +0.297 [+0.172, +0.406] | 20/43/1 | 91% |
| 100 | full/compact − full/verbose | 64 | +0.000 [-0.062, +0.062] | 2/60/2 | 67% |
| 100 | bm25_k16/compact − full/verbose | 64 | +0.000 [-0.078, +0.078] | 3/58/3 | 89% |
| 100 | recency_k16/compact − full/verbose | 64 | +0.047 [-0.031, +0.125] | 5/57/2 | 94% |
| 500 | graph_closed/compact − full/verbose | 63 | +0.270 [+0.127, +0.413] | 21/38/4 | 99% |
| 500 | graph_closed/verbose − full/verbose | 63 | +0.222 [+0.095, +0.349] | 17/43/3 | 98% |
| 500 | full/compact − full/verbose | 63 | -0.048 [-0.111, +0.016] | 1/58/4 | 71% |
| 500 | bm25_k16/compact − full/verbose | 63 | -0.048 [-0.111, +0.016] | 1/58/4 | 97% |
| 500 | recency_k16/compact − full/verbose | 63 | +0.000 [-0.079, +0.079] | 3/57/3 | 99% |

Same 63 episodes completed in all conditions (graph_closed/compact and full/verbose):

| condition | graph_closed/compact EES | full/verbose EES | graph input tok | full input tok |
|---|---:|---:|---:|---:|
| native | 0.21 | 0.54 | 2346 | 8667 |
| 100 | 0.38 | 0.05 | 2585 | 54135 |
| 500 | 0.33 | 0.06 | 2593 | 236498 |

#### shopping32

| condition | cell | n | EES | legal | affected F1 | input tok | output tok | est $/cell |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| native | bm25_k16/compact | 64 | 0.47 | 0.92 | 0.70 | 4025 | 2261 | 0.028 |
| native | bm25_k16/verbose | 64 | 0.44 | 0.91 | 0.66 | 7591 | 1801 | 0.025 |
| native | full/compact | 64 | 0.62 | 0.98 | 0.76 | 3817 | 2204 | 0.031 |
| native | full/verbose | 64 | 0.48 | 0.94 | 0.69 | 7520 | 1738 | 0.035 |
| native | graph_closed/compact | 64 | 0.42 | 0.94 | 0.70 | 3249 | 1742 | 0.025 |
| native | graph_closed/verbose | 64 | 0.47 | 0.94 | 0.70 | 6769 | 1623 | 0.031 |
| native | recency_k16/compact | 64 | 0.55 | 0.94 | 0.75 | 3673 | 2161 | 0.026 |
| native | recency_k16/verbose | 64 | 0.53 | 0.94 | 0.75 | 7582 | 1823 | 0.024 |
| 100 | bm25_k16/compact | 57 | 0.35 | 0.96 | 0.48 | 4787 | 1742 | 0.029 |
| 100 | bm25_k16/verbose | 57 | 0.44 | 0.95 | 0.54 | 11167 | 1313 | 0.039 |
| 100 | full/compact | 57 | 0.32 | 0.98 | 0.46 | 16865 | 3414 | 0.065 |
| 100 | full/verbose | 57 | 0.39 | 1.00 | 0.55 | 40339 | 3366 | 0.107 |
| 100 | graph_closed/compact | 57 | 0.39 | 0.93 | 0.63 | 3772 | 1760 | 0.026 |
| 100 | graph_closed/verbose | 57 | 0.46 | 0.95 | 0.69 | 8697 | 1750 | 0.037 |
| 100 | recency_k16/compact | 57 | 0.40 | 0.93 | 0.54 | 5515 | 2117 | 0.033 |
| 100 | recency_k16/verbose | 57 | 0.37 | 0.98 | 0.51 | 12647 | 1986 | 0.047 |
| 500 | bm25_k16/compact | 47 | 0.15 | 0.94 | 0.22 | 6718 | 1878 | 0.033 |
| 500 | bm25_k16/verbose | 47 | 0.26 | 0.87 | 0.34 | 13203 | 1247 | 0.043 |
| 500 | full/compact | 47 | 0.30 | 0.98 | 0.40 | 58426 | 3380 | 0.131 |
| 500 | full/verbose | 47 | 0.28 | 0.98 | 0.41 | 174811 | 3407 | 0.318 |
| 500 | graph_closed/compact | 47 | 0.34 | 0.94 | 0.62 | 4513 | 2189 | 0.032 |
| 500 | graph_closed/verbose | 47 | 0.32 | 0.94 | 0.60 | 9190 | 1825 | 0.038 |
| 500 | recency_k16/compact | 47 | 0.34 | 0.96 | 0.53 | 6404 | 2131 | 0.035 |
| 500 | recency_k16/verbose | 47 | 0.36 | 0.94 | 0.49 | 16069 | 2117 | 0.052 |

| condition | paired comparison (EES) | n episodes | mean [95% CI] | W/T/L | input reduction |
|---|---|---:|---|---|---:|
| native | graph_closed/compact − full/verbose | 64 | -0.062 [-0.203, +0.078] | 9/42/13 | 57% |
| native | graph_closed/verbose − full/verbose | 64 | -0.016 [-0.188, +0.156] | 14/35/15 | 10% |
| native | full/compact − full/verbose | 64 | +0.141 [-0.016, +0.297] | 19/35/10 | 49% |
| native | bm25_k16/compact − full/verbose | 64 | -0.016 [-0.141, +0.125] | 9/45/10 | 46% |
| native | recency_k16/compact − full/verbose | 64 | +0.062 [-0.078, +0.203] | 13/42/9 | 51% |
| 100 | graph_closed/compact − full/verbose | 57 | +0.000 [-0.158, +0.158] | 12/33/12 | 91% |
| 100 | graph_closed/verbose − full/verbose | 57 | +0.070 [-0.070, +0.211] | 11/39/7 | 78% |
| 100 | full/compact − full/verbose | 57 | -0.070 [-0.228, +0.088] | 8/37/12 | 58% |
| 100 | bm25_k16/compact − full/verbose | 57 | -0.035 [-0.193, +0.140] | 11/33/13 | 88% |
| 100 | recency_k16/compact − full/verbose | 57 | +0.018 [-0.140, +0.175] | 12/34/11 | 86% |
| 500 | graph_closed/compact − full/verbose | 47 | +0.064 [-0.128, +0.255] | 11/28/8 | 97% |
| 500 | graph_closed/verbose − full/verbose | 47 | +0.043 [-0.128, +0.213] | 10/29/8 | 95% |
| 500 | full/compact − full/verbose | 47 | +0.021 [-0.128, +0.170] | 7/34/6 | 67% |
| 500 | bm25_k16/compact − full/verbose | 47 | -0.128 [-0.277, +0.000] | 3/35/9 | 96% |
| 500 | recency_k16/compact − full/verbose | 47 | +0.064 [-0.128, +0.255] | 11/28/8 | 96% |

Same 47 episodes completed in all conditions (graph_closed/compact and full/verbose):

| condition | graph_closed/compact EES | full/verbose EES | graph input tok | full input tok |
|---|---:|---:|---:|---:|
| native | 0.45 | 0.51 | 3292 | 7818 |
| 100 | 0.45 | 0.38 | 3582 | 40750 |
| 500 | 0.34 | 0.28 | 4513 | 174811 |


### 3.4 selector 口径对照（Travel；`travel_{100,500}_natsel` 只跑 graph_closed）

| condition | selector | n | graph_closed/compact EES | full/verbose EES (same episodes) | graph − full | graph − graph@native | graph input tok | identical prompt to native |
|---|---|---:|---:|---:|---|---|---:|---:|
| 100 | refit on same condition (preregistered) | 64 | 0.38 | 0.05 | +0.328 [+0.203, +0.453] | +0.156 [+0.016, +0.281] | 2573 | 38/64 |
| 100 | fitted on native train | 64 | 0.31 | 0.05 | +0.266 [+0.156, +0.391] | +0.094 [-0.031, +0.219] | 2760 | 38/64 |
| 500 | refit on same condition (preregistered) | 63 | 0.33 | 0.06 | +0.270 [+0.127, +0.413] | +0.127 [-0.016, +0.270] | 2593 | 29/63 |
| 500 | fitted on native train | 63 | 0.30 | 0.06 | +0.238 [+0.111, +0.365] | +0.095 [-0.048, +0.238] | 2219 | 29/63 |

复核结论：即使 selector 固定在 native train 上拟合，100/500 档的 graph prompt 也只在约一半 episode 与 native
逐字相同。逐 episode 重算选择（12 个 episode）显示新增记录全部是外来世界的 witness（`x` 前缀 rid），对应
被评估对象的 policy key 在原生历史里没有 witness、而 B/C 型外来 segment 给了一个；closure 再把这些
witness 的外来对象带入 state。也就是说，长历史里同一 provider/hotel/restaurant 的额外 witness 会被
graph 选中，actor 因而拿到原本缺失的 policy 证据（B 型正确、C 型冲突），净效果是 EES 上升 0.09。
reads 仍在 native 的 1.25 倍以内（P1 成立）；P2 的"配对差绝对值 ≤ 0.05"在上方向不成立，原因如上，
不是干扰记录压低了 graph。full / bm25 / recency 三臂不受此机制影响。

## 4. backward provenance（dev，seeds 0/1/2，各 60 episode）

smoke（seed 0，40 episode，实现修订前）：Travel 31 个事件，p@1 0.39、p@3 0.84、MRR 0.62；
替换 top-1 后 EES 恢复 0.39，matched random 0.13，similar non-ancestor 0.03，recency 0.00；配对差
predicted − random +0.26 [+0.03, +0.48]。Shopping32 14 个事件，p@1 0.07、p@3 0.36；13 个 episode
找不到改变解析值的最小污染，12 个 episode 的干净计划本身已错。

实现修订（dev 阶段，结果前）：增加 top-3 联合替换与 matched-random-3 对照；similar 对照在全部对象
都在路径上时退回"最相似且不在 top-3 内的记录"，并记录退回类型；Shopping 的 replace_line 污染尝试目录
中全部变体。

正式 dev 结果（`results/development/hm3/provenance/dev.json`；每行一个 seed，60 episode；恢复率 = 替换后 forward graph 的 EES 恢复比例；配对差为 bootstrap 95% 区间）：

| run | incidents | p@1 | p@3 | MRR | restore top-1 | random-1 | similar | recency | restore top-3 | random-3 | top-1 − random-1 | top-3 − random-3 | graph SHA |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| travel/seed0 | 44/60 | 0.50 | 0.82 | 0.67 | 0.50 | 0.16 | 0.02 | 0.02 | 0.82 | 0.14 | +0.34 [+0.11, +0.57] | +0.68 [+0.45, +0.86] | `076b641c60406666` |
| travel/seed1 | 41/60 | 0.46 | 0.78 | 0.65 | 0.46 | 0.10 | 0.00 | 0.02 | 0.78 | 0.17 | +0.37 [+0.17, +0.56] | +0.61 [+0.37, +0.80] | `64bd9d08bd2e6695` |
| travel/seed2 | 47/60 | 0.49 | 0.79 | 0.64 | 0.49 | 0.13 | 0.02 | 0.04 | 0.79 | 0.06 | +0.36 [+0.15, +0.55] | +0.72 [+0.55, +0.87] | `4350ea2ba1148370` |
| shopping32/seed0 | 24/60 | 0.08 | 0.33 | 0.21 | 0.08 | 0.08 | 0.12 | 0.12 | 0.33 | 0.21 | +0.00 [-0.17, +0.17] | +0.12 [-0.17, +0.42] | `085ff5a8b00b371b` |
| shopping32/seed1 | 31/60 | 0.03 | 0.23 | 0.12 | 0.03 | 0.13 | 0.10 | 0.10 | 0.23 | 0.19 | -0.10 [-0.26, +0.03] | +0.03 [-0.19, +0.26] | `85f1a5b280a8d762` |
| shopping32/seed2 | 24/60 | 0.04 | 0.25 | 0.13 | 0.04 | 0.04 | 0.08 | 0.08 | 0.25 | 0.04 | +0.00 [-0.12, +0.12] | +0.21 [+0.00, +0.42] | `afadc22c5c4f574e` |

事件之外的 episode：Travel 每 seed 1–4 个找不到改变解析值的污染、3–10 个干净计划本身已错、5–7 个污染后计划未变；Shopping 每 seed 17–19 个找不到污染、9–15 个干净计划已错。

读法：Travel 三个 seed 一致——top-1 命中率 0.46–0.50、top-3 0.78–0.82；替换 top-1 的恢复率是 matched random 的 3–4 倍，similar 与 recency 对照接近 0；top-3 联合替换恢复 0.78–0.82，对照 0.06–0.17；全部配对区间在 0 以上。p@1 受每个 key 的 witness 三元组（intervention 记录 + 两条结果记录）限制，同一 key 内部无法从内容判断哪条被改，因此 top-3 是与设计一致的公平口径。Shopping32 未通过：p@1 ≤ 0.08，与三种对照无差别；原因是 skeleton 从任一 source 可达整个 cart（similar 对照全部退回 non_traced），路径排序没有区分力，且约 30% 的 episode 找不到改变解析值的最小污染。按 provenance 设计 §6 如实报告为边界。


### 4.1 正式结果（修订后的方法，provenance 设计 §7；dev 与 test 并列）

**dev seeds 0/1/2，native 长度**（`results/development/hm3/provenance/dev_v2.json`；LOO = 结构候选经 leave-one-out 重排的正式排序；struct = 首版结构排序；恢复率 = 替换后 forward graph 的 EES 恢复比例；top-3 − random-3 为配对 bootstrap 95% 区间）

| run | incidents | p@1 (LOO) | p@3 (LOO) | p@1 struct | p@3 struct | BM25 p@1 / p@3 | source p@3 | restore top-1 | random-1 | similar | BM25 top-1 | restore top-3 | random-3 | top-3 − random-3 |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| travel/seed0 | 44/60 | 0.55 | 0.98 | 0.48 | 0.80 | 0.14 / 0.34 | 0.20 | 0.55 | 0.09 | 0.02 | 0.14 | 0.98 | 0.00 | +0.98 [+0.93, +1.00] |
| travel/seed1 | 41/60 | 0.63 | 0.98 | 0.54 | 0.80 | 0.20 / 0.32 | 0.15 | 0.63 | 0.07 | 0.00 | 0.20 | 0.98 | 0.00 | +0.98 [+0.93, +1.00] |
| travel/seed2 | 47/60 | 0.57 | 0.91 | 0.55 | 0.83 | 0.15 / 0.32 | 0.19 | 0.57 | 0.11 | 0.02 | 0.15 | 0.91 | 0.00 | +0.91 [+0.83, +0.98] |
| shopping32/seed0 | 24/60 | 0.08 | 0.33 | 0.04 | 0.33 | 0.08 / 0.92 | 0.42 | 0.08 | 0.12 | 0.04 | 0.08 | 0.33 | 0.25 | +0.08 [-0.21, +0.38] |
| shopping32/seed1 | 32/60 | 0.06 | 0.19 | 0.03 | 0.19 | 0.03 / 0.97 | 0.62 | 0.06 | 0.12 | 0.06 | 0.03 | 0.19 | 0.19 | +0.00 [-0.22, +0.22] |
| shopping32/seed2 | 24/60 | 0.12 | 0.29 | 0.12 | 0.29 | 0.08 / 1.00 | 0.62 | 0.12 | 0.04 | 0.00 | 0.08 | 0.29 | 0.12 | +0.17 [-0.08, +0.42] |

**test seeds 30/31/32，native 长度**（`results/real/hm3/provenance/test_v2.json`；LOO = 结构候选经 leave-one-out 重排的正式排序；struct = 首版结构排序；恢复率 = 替换后 forward graph 的 EES 恢复比例；top-3 − random-3 为配对 bootstrap 95% 区间）

| run | incidents | p@1 (LOO) | p@3 (LOO) | p@1 struct | p@3 struct | BM25 p@1 / p@3 | source p@3 | restore top-1 | random-1 | similar | BM25 top-1 | restore top-3 | random-3 | top-3 − random-3 |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| travel/seed30 | 52/60 | 0.62 | 1.00 | 0.48 | 0.83 | 0.17 / 0.46 | 0.15 | 0.62 | 0.10 | 0.00 | 0.17 | 1.00 | 0.00 | +1.00 [+1.00, +1.00] |
| travel/seed31 | 48/60 | 0.65 | 0.98 | 0.58 | 0.85 | 0.02 / 0.29 | 0.17 | 0.65 | 0.12 | 0.00 | 0.02 | 0.98 | 0.00 | +0.98 [+0.94, +1.00] |
| travel/seed32 | 42/60 | 0.55 | 0.98 | 0.57 | 0.79 | 0.19 / 0.60 | 0.33 | 0.55 | 0.10 | 0.00 | 0.19 | 0.98 | 0.00 | +0.98 [+0.93, +1.00] |
| shopping32/seed30 | 20/60 | 0.10 | 0.25 | 0.10 | 0.25 | 0.05 / 0.90 | 0.45 | 0.10 | 0.00 | 0.00 | 0.05 | 0.25 | 0.20 | +0.05 [-0.25, +0.35] |
| shopping32/seed31 | 20/60 | 0.00 | 0.20 | 0.00 | 0.20 | 0.05 / 1.00 | 0.55 | 0.00 | 0.05 | 0.05 | 0.05 | 0.20 | 0.05 | +0.15 [-0.05, +0.35] |
| shopping32/seed32 | 21/60 | 0.10 | 0.29 | 0.10 | 0.29 | 0.05 / 0.90 | 0.43 | 0.10 | 0.05 | 0.10 | 0.05 | 0.29 | 0.05 | +0.24 [+0.00, +0.48] |

**test seeds 30/31/32，500 条记录（abcd 混合增广）**（`results/real/hm3/provenance/test_500_v2.json`；LOO = 结构候选经 leave-one-out 重排的正式排序；struct = 首版结构排序；恢复率 = 替换后 forward graph 的 EES 恢复比例；top-3 − random-3 为配对 bootstrap 95% 区间）

| run | incidents | p@1 (LOO) | p@3 (LOO) | p@1 struct | p@3 struct | BM25 p@1 / p@3 | source p@3 | restore top-1 | random-1 | similar | BM25 top-1 | restore top-3 | random-3 | top-3 − random-3 |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| travel/seed30 | 51/59 | 0.59 | 0.98 | 0.51 | 0.73 | 0.06 / 0.25 | 0.18 | 0.59 | 0.04 | 0.00 | 0.06 | 0.98 | 0.00 | +0.98 [+0.94, +1.00] |
| travel/seed31 | 49/60 | 0.53 | 0.94 | 0.45 | 0.73 | 0.06 / 0.14 | 0.06 | 0.53 | 0.12 | 0.00 | 0.06 | 0.94 | 0.00 | +0.94 [+0.86, +1.00] |
| travel/seed32 | 45/59 | 0.64 | 0.98 | 0.62 | 0.84 | 0.09 / 0.36 | 0.31 | 0.64 | 0.02 | 0.00 | 0.09 | 0.98 | 0.00 | +0.98 [+0.93, +1.00] |

读法：Travel 在 test seeds 上 top-1 命中 0.55–0.65、top-3 0.98–1.00；替换 top-3 后 forward graph 的 EES 恢复 0.98–1.00，matched random-3 为 0，similar 与 recency 对照为 0；BM25 定位基线 p@1 ≤ 0.19、p@3 ≤ 0.60。500 条记录下几乎不变（p@3 0.94–0.98）。首版结构排序的 p@3 为 0.73–0.85，LOO 重排把同一 key 内的 witness 三元组分开。Shopping32 在 dev 与 test 均未通过（p@3 ≤ 0.33，与 random-3 无差别）；BM25 基线 p@3 0.90–1.00 但 top-1 替换恢复 ≤ 0.08：污染记录写在异常对象本身且大多使 parser 失去该 key 的 witness（provenance 设计 §7.4），这是 witness-based 反向审计的边界。

### 4.2 首版结构排序在 test seeds 上的结果（`test.json`、`test_500.json`，修订前，保留备查）

Travel native p@1 0.46 / 0.51 / 0.57，500 档 0.51 / 0.45 / 0.62；Shopping p@1 0.19 / 0.00 / 0.19。

## 5. 结论槽

当前可以写的结论（2026-09-18 深夜；Shopping 100/500 档 API 与三 seed 确定性面板仍在补齐）：

1. **确定性层（Travel）**：学得图的读取量与 EES 在 native → 500 条记录下持平（P1、P2），固定 K 的检索
   丢失必需记录（P3），读取全部历史的方法读取量线性增长（P4）。selection ladder 上 graph_select 三档全为
   1.000，三个重接线的 wrong_select 为 0.60 / 0.03 / 0.03，bm25_k16 从 0.95 跌到 0.03。
2. **actor 层（Travel，DeepSeek-V4-Flash，test seed 30，63–64 episode）**：native 档 graph_closed/compact
   低于 full/verbose 0.33 [0.19, 0.47]（round 3/4 的方向）；100 与 500 档反转为 +0.33 [+0.20, +0.46] 与
   +0.27 [+0.13, +0.43]，graph 的 input tokens 三档 2.2k–2.8k，full/verbose 8k → 55k → 237k；bm25_k16 与
   recency_k16 在 100/500 档与 full 同样接近 0。selector 固定在 native train 上时结论不变（+0.27 / +0.24）。
   graph 臂自身跨档位上升 0.09–0.16 的机制是长历史里同一实体的额外 witness 被图选中（§3.4），如实报告。
3. **更强 backbone（DeepSeek-V4-Pro）**：native 差距收窄到 −0.10 [−0.28, +0.08]；500 档 +0.07
   [−0.09, +0.22]，full/verbose 0.38 → 0.17。方向一致，幅度更小。
4. **Shopping32（actor 层）**：native 档 graph 与 full 无差别（−0.07 [−0.21, +0.08]），100/500 档 graph 与
   full/recency 相近（+0.00 / +0.06），full 未像 Travel 那样崩溃（0.40 / 0.24）。Shopping 的 cart 两跳内
   全连通，图对选择的增量小，这与 selection ladder 上 wrong_select 无区分力一致。
5. **同图反向 provenance（Travel，test seeds 30–32）**：top-1 命中 0.55–0.65、top-3 0.98–1.00；替换 top-3
   后 EES 恢复 0.98–1.00，matched random-3 为 0，similar / recency 为 0，BM25 定位基线 p@3 ≤ 0.60；500 条
   记录下 p@3 0.94–0.98。正向选择与反向追踪使用同一 graph SHA。Shopping32 未通过（witness 被污染静默，
   provenance 设计 §7.4），作为边界报告。
6. **未完成 / 边界**：Shopping 100/500 档 API 还差 7 与 17 个 episode；三 seed 确定性面板由第二个 session
   补齐；Mem0 / dense 未做（无 embedding 端点，用户决定不做）；A-Mem 依赖已装（`benchmarks/A-mem`，
   sentence-transformers / chromadb / litellm），LightMem 源码已克隆但其包要求 Python < 3.12（本机 3.13.9），
   只能以源码路径方式接入，两者尚未接入 HM3，属于 MemoryArena 层的工作。

