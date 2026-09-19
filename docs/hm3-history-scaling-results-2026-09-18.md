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

P1–P4 判定：待填。

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

## 5. 结论槽

待 dev 面板、API 面板与 provenance 正式结果齐后按设计 §5 / provenance §5 逐条填写。
