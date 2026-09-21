# Session B 记录（2026-09-19，按 bridge-plan §7 执行）

本页只由 Session B 写。规则：不改 `code/`，不跑 git，不删不改已有目录，不重启已在运行的 shard。A 把表合并进结果包时以本页为准。

## 0. 环境与现状（16:10–16:20 PDT）

- **机器**：B 在 `dsw-933623-58c8fccdb9-g89ct`，系统 Python 3.12.13。§7.2 给的两个 pylib（`pylib2`、`pylib_tcd`）都是 cpython-3.13 编译的，在这台机器上 `import numpy` 直接失败。系统 site-packages 已有 numpy 2.5.0 / scipy 1.17.1 / sklearn 1.9.0 / openai 2.44.0，所以 B 一律用 `PYTHONPATH=$ROOT/code`，不挂任何 pylib；`hm3.llm`、`hm3.memsys_summary`、`hm3.panel_summary` 都能跑。memsys（mem0/amem/chroma）起初在这台机器上跑不了；用户允许后（16:25）B 在 scratchpad 建了 3.12 的 venv（`venv312`：torch 2.14 CPU、mem0ai 2.1.0、chromadb 1.5.9、sentence-transformers 6.1.0、qdrant-client 1.19.1、litellm 1.101.0、openai 2.54.0、socksio；all-MiniLM-L6-v2 与 nltk punkt_tab 已下载），对 travel-s30-test-000 的 native 档 A-Mem 冒烟格 EES=1、27 次写调用，与 A 机器上的口径一致。B3 由此可在 B 机器上跑。
- **shard 启动脚本**：`code/hm3/autodl_shards.sh` 把 `PYTHONPATH=$PYLIB:.` 写死，在这台机器上会让 pylib2 的 3.13 numpy 遮住系统 numpy。B 没改脚本，而是在 scratchpad 复制了一份，唯一差别是那一行改成 `PYTHONPATH=.`（`diff` 只有 26 行一处）。启动参数与 §7.4 完全相同。
- **memsys shard 状态**：`ps` 在 B 的机器上看不到 A 机器的进程，只能看账本 mtime。
  - `mem0_raw/{travel,shopping32}_{native,100}`：四个条件都已 64/64，账本最后写入 14:34–14:50，`infrastructure_failure` 行数四个条件均为 **0**。
  - `amem16k/{travel,shopping32}_100`：仍在跑（shard.log 在 16:07 仍有写入，cell 数 16:09 → 16:19 从 25 涨到 35）。8 个 shard 里有 6 个各有一条 actor 阶段的 `Connection error.`（15:10–15:51 之间，episode travel-002/019/050、shopping32-020/036/050），脚本对该错误是 `continue`，进程没停。按 §7.4 不重跑。
- **B2**：16:11 启动 prompt v2 的 12 个 shard（key 2/3，`SHARDSUB=shards_key`，`SERS=verbose`，`MAXTOK=16384`），16:19 进度 100 档 11/64、500 档 14/64、c100 16/64；机器负载 6。v1 的 12 个等 v2 结束后再启动，保持 ≤ 16 个进程。

## 1. B1：memsys 表

### 1.1 mem0_raw（原样存储 + embedding 检索，k=16，16k 上限，prompt v2，compact 序列化）

`python3 -m hm3.memsys_summary --system mem0_raw --ref 16k --domains travel shopping32` 原样输出：

| domain | history | mem0_raw EES (mem0_raw) | n | cap hits | write LLM calls / tokens per episode | actor input tok | vs graph_seg/verbose (16k) | vs graph_closed/verbose (16k) | vs full/verbose (16k) |
|---|---|---:|---:|---:|---|---:|---|---|---|
| travel | native | 0.27 | 64 | 11 | 0 / 0 | 4406 | -0.156 [-0.297, -0.016] (n=64) | -0.016 [-0.156, +0.125] (n=64) | -0.375 [-0.531, -0.219] (n=64) |
| travel | 100 | 0.05 | 64 | 44 | 0 / 0 | 10239 | -0.312 [-0.438, -0.188] (n=64) | -0.312 [-0.453, -0.172] (n=64) | -0.156 [-0.266, -0.047] (n=64) |
| shopping32 | native | 0.53 | 64 | 15 | 0 / 0 | 5951 | — (n=0) | — (n=0) | — (n=0) |
| shopping32 | 100 | 0.30 | 64 | 4 | 0 / 0 | 4687 | -0.047 [-0.203, +0.109] (n=64) | -0.250 [-0.391, -0.094] (n=64) | -0.125 [-0.266, +0.016] (n=64) |

注意：
- 上表是 16:13 用当时的 summariser 跑的，**cap hits 列按 4096 数**（§2.1）。A 在 17:05 前已修好；17:19 重跑修好的版本，cap hits 为 travel/native **8**/64、travel/100 **28**/64、shopping32/native **10**/64、shopping32/100 **2**/64，其余列相同（`scratchpad/b1_mem0_raw_fixed.txt`）。
- shopping32/native 三个对比列为 `— (n=0)`：`results/real/hm3/long_out` 里没有 `shopping32_native`（§7.1 的 16k 面板 Shopping 只做了 100/500），所以没有 16k 同序列化参照。4096 口径的 `results/real/hm3/scaling/shopping32_native` 存在，但 mem0_raw 本身是 16k 跑的，混口径对比没意义，未做。
- write LLM calls 0 / 0 是设计如此（raw 模式不抽取，只 embedding）。每格选中记录数中位数 16（shopping32/native 为 14），对象数 20–25。

按上限是否打满拆开（EES 均值）：

| 条件 | n | 打满 16k | EES 全部 | EES 打满格 | EES 未打满格 |
|---|---:|---:|---:|---:|---:|
| travel/native | 64 | 8 | 0.27 | 0.12 | 0.29 |
| travel/100 | 64 | 28 | 0.05 | 0.00 | 0.08 |
| shopping32/native | 64 | 10 | 0.53 | 0.20 | 0.59 |
| shopping32/100 | 64 | 2 | 0.30 | 0.00 | 0.31 |

读法（供 A 取舍）：Travel native 档 mem0_raw 0.27 与 graph_closed/verbose 持平（−0.02），低于 graph_seg/verbose（−0.16）和 full/verbose（−0.38）；100 档 0.05，三个参照都显著更好（−0.16 到 −0.31）。Shopping 100 档 0.30 与 graph_seg 持平（−0.05，区间含 0），低于 graph_closed（−0.25）。即 embedding 检索在 native 档拿到的记录够用，历史一长就找不到对的记录；这与 bm25_k16 的走势一致。

### 1.2 A-Mem 16k（`--dir amem16k`；A 已修好 cap-hit 列，本表为 17:19 用修好的 `hm3.memsys_summary` 重跑）

100 档仍在 A 的机器上跑（17:19：travel 42/64、shopping32 45/64，各 3 格 `Connection error.`）；native 档见 §4。

| domain | history | amem EES (amem16k) | n | cap hits | write LLM calls / tokens per episode | actor input tok | vs graph_seg/verbose (16k) | vs graph_closed/verbose (16k) | vs full/verbose (16k) |
|---|---|---:|---:|---:|---|---:|---|---|---|
| travel | native | 0.34 | 64 | 7 | 17 / 20003 | 4126 | -0.078 [-0.234, +0.078] (n=64) | +0.062 [-0.062, +0.203] (n=64) | -0.297 [-0.453, -0.141] (n=64) |
| travel | 100 | 0.00 | 42 | 22 | 97 / 125325 | 12166 | -0.310 [-0.452, -0.167] (n=42) | -0.381 [-0.524, -0.238] (n=42) | -0.167 [-0.286, -0.071] (n=42) |
| shopping32 | native | 0.57 | 40 | 7 | 13 / 17404 | 6310 | — (n=0) | — (n=0) | — (n=0) |
| shopping32 | 100 | 0.47 | 45 | 1 | 98 / 141843 | 4488 | +0.156 [-0.044, +0.333] (n=45) | -0.067 [-0.244, +0.111] (n=45) | +0.022 [-0.133, +0.178] (n=45) |

- travel/native（64/64，B 跑的）：0.34，与 graph_closed/verbose 持平（+0.06）、与 graph_seg/verbose 持平（−0.08，区间含 0）、低于 full/verbose（−0.30）；4096 口径是 0.28 / 7 格打满，16k 后 7 格仍打满（output_tokens ≥ 16384），EES 变化 +0.06。
- travel/100（42/64）：0.00，22 格打满；与 4096 口径的 0.03 一致，A-Mem 在 100 条历史上选不到该读的记录。
- shopping32/100（45/64）：0.47，与三个参照持平（区间都含 0）。
- 首条 `infrastructure_failure`：`{"event": "infrastructure_failure", "cell": "travel/travel-s30-test-002/amem_k16/compact", "stage": "actor", "error": "Connection error."}`。A 的 §7.1 补充说结束后用相同命令再启动一次补这 6 格；这要在 A 的机器上做（或用 B 的 venv312）。

### 1.3 A-Mem native 档（4096 口径，未重跑）

`python3 -m hm3.memsys_summary --system amem --ref 4096 --domains travel shopping32`：

| domain | history | amem EES (amem) | n | cap hits | write LLM calls / tokens per episode | actor input tok | vs graph_closed/compact (4096) | vs full/verbose (4096) | vs bm25_k16/compact (4096) |
|---|---|---:|---:|---:|---|---:|---|---|---|
| travel | native | 0.28 | 64 | 7 | 17 / 19911 | 2768 | +0.062 [-0.078, +0.188] (n=64) | -0.266 [-0.406, -0.125] (n=64) | -0.078 [-0.172, +0.016] (n=64) |
| travel | 100 | 0.03 | 64 | 44 | 99 / 128082 | 6763 | -0.312 [-0.438, -0.188] (n=64) | -0.031 [-0.109, +0.047] (n=64) | +0.016 [+0.000, +0.047] (n=64) |
| shopping32 | native | 0.55 | 64 | 10 | 13 / 17869 | 4022 | +0.125 [-0.016, +0.266] (n=64) | +0.062 [-0.094, +0.219] (n=64) | +0.078 [-0.047, +0.219] (n=64) |
| shopping32 | 100 | 0.34 | 64 | 8 | 99 / 144969 | 5076 | -0.156 [-0.312, +0.000] (n=64) | +0.094 [-0.062, +0.250] (n=64) | -0.094 [-0.235, +0.047] (n=64) |

这张表的 cap hits 是对的（cell 里没有 max_tokens 字段时回退 4096，恰好等于这批的上限）。travel/100 44/64 打满 4096，与 §3.3 的截断混淆同源，所以 100 档以 §1.2 的 16k 重跑为准。

## 2. 异常与代码建议（B 不改 code/，请 A 处理；A 的 §7.5 说 1–3 已改，17:19 重跑确认 cap hits 列已正确）

1. **`hm3/memsys_summary.py:82` 的 cap hits 阈值**：`mm[0].get("max_tokens") or 4096`，但 `memsys_llm` 写的 cell 记录里没有 `max_tokens` 字段（它在同目录的 `llm_protocol.json` 里），所以 16k 目录的 cap hits 实际按 4096 数。建议从 `llm_protocol.json` 读 `max_tokens`，或在 cell 记录里写入。上面 §1.1 已给出正确数字。
2. **`output_tokens` 是所有 attempt 之和**（`memsys_llm.py:276`），格式修复那次也计入，所以 amem16k 里出现 25k–27k 的 output_tokens。按 `≥ max_tokens` 判打满仍基本可靠（第一次打满 + 修复），但严格应看第一次 attempt。`finish_reason` 记的是最后一次 attempt，对打满判断没用（mem0_raw travel/100 只有 1 格 `length`，却有 28 格 ≥ 16384）。这和 §3.3 对 `scaling_v2` 账本的发现是同一个问题。
3. **`memsys_summary.py:67-68` 对参照目录的账本没有存在性检查**：B2 刚建好的 `shards_key/*/` 在第一格写入前没有 `llm_ledger.jsonl`，`--ref 16k` 直接 `FileNotFoundError`，表只打印了一行。第 25 行对 memsys 目录有检查，参照目录也应加一句 `if not os.path.exists(lp): continue`。B 用 scratchpad 里加了这一行的副本跑出 §1 的表。
4. **`autodl_shards.sh` 的 `PYLIB` 写死**：建议 `PYLIB=${PYLIB:-...}` 并允许 `PYTHONPATH` 为空，跨机器就不用复制脚本。
5. **§7.2 的 `PYTHONPATH` 三段都假设 Python 3.13**：在 3.12 机器上要写成 `PYTHONPATH=$ROOT/code`（memsys 除外）。

## 3. B2：graph_key2 / verbose 同序列化臂（Travel，100 / 500 / c100）

### 3.1 prompt v2（16:11–16:37 完成，64 / 63 / 63 格，`infrastructure_failure` 0）

`python3 -m hm3.panel_summary --domain travel` 已自动把 `graph_key2/verbose` 配进 16k / v2 面板。只摘同序列化的行与差值（完整面板在 `results/real/hm3/long_out/panel_summary_travel.md`）：

| 条件（v2，16k） | 臂 | n | EES | affected F1 | value acc | 打满 | legal | collateral | med in | med out |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | graph_seg/verbose | 64 | 0.36 | 0.73 | 0.64 | 12 | 0.98 | 0.48 | 4428 | 1496 |
| 100 | **graph_key2/verbose** | 64 | **0.38** | 0.65 | 0.60 | 17 | 0.91 | 0.50 | 6678 | 3018 |
| 100 | graph_key2/compact（旧） | 64 | 0.36 | 0.72 | 0.62 | 16 | 0.94 | 0.59 | 2582 | 2806 |
| 100 | full/verbose | 64 | 0.20 | 0.42 | 0.33 | 45 | 0.94 | 0.16 | 70003 | 16389 |
| c100 | graph_seg/verbose | 63 | 0.41 | 0.76 | 0.65 | 10 | 0.98 | 0.49 | 4298 | 1324 |
| c100 | **graph_key2/verbose** | 63 | **0.35** | 0.61 | 0.52 | 20 | 0.97 | 0.33 | 6678 | 5855 |
| c100 | graph_key2/compact（旧） | 63 | 0.33 | 0.71 | 0.48 | 18 | 0.94 | 0.29 | 2572 | 3131 |
| c100 | full/verbose | 63 | 0.19 | 0.33 | 0.22 | 38 | 0.97 | 0.16 | 68761 | 16389 |
| 500 | graph_seg/verbose | 63 | 0.56 | 0.83 | 0.74 | 4 | 0.97 | 0.56 | 4443 | 1398 |
| 500 | **graph_key2/verbose** | 63 | **0.29** | 0.63 | 0.64 | 19 | 0.97 | 0.60 | 7772 | 3215 |
| 500 | graph_key2/compact（旧） | 63 | 0.24 | 0.59 | 0.54 | 22 | 0.87 | 0.56 | 2941 | 3687 |
| 500 | full/verbose | 63 | 0.11 | 0.33 | 0.28 | 50 | 0.89 | 0.37 | 260795 | 16389 |

配对差值（EES，95% 区间，同一批 episode）：

| 条件（v2，16k） | graph_key2/verbose − graph_seg/verbose | graph_key2/verbose − full/verbose |
|---|---|---|
| 100 | +0.02 [−0.14, +0.17] | +0.17 [+0.03, +0.31] |
| c100 | −0.06 [−0.21, +0.08] | +0.16 [+0.00, +0.32] |
| 500 | **−0.27 [−0.41, −0.11]** | +0.17 [+0.05, +0.30] |

读法：verbose 口径下，parser-free 选择在 100 与 c100 档与 parser 版（graph_seg/verbose）持平，对 full 的优势与 parser 版同量级（+0.16/+0.17）。500 档不持平：graph_key2 掉到 0.29，比 graph_seg 低 0.27，与 §3.2 选择阶梯里 key_select2 在 500 条的 0.82 对应——同 key 无信息先例把该读的记录挤掉了，actor 层把这个损失放大了。graph_key2/verbose 的输入 tokens（6.7–7.8k）是 graph_seg 的 1.5–1.8 倍，仍是 full 的 3–10%。打满 16k 的格 graph_key2 有 17–20 个（graph_seg 4–12），说明多读的无关记录也在拖 v2 prompt 的终止。

### 3.2 prompt v1（16:38–17:14 完成，64 / 63 / 63 格，`infrastructure_failure` 0）

| 条件（v1，16k） | 臂 | n | EES | affected F1 | value acc | 打满 | legal | collateral | med in | med out |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | graph_seg/verbose | 64 | 0.33 | 0.84 | 0.60 | 2 | 0.81 | 0.67 | 4016 | 594 |
| 100 | **graph_key2/verbose** | 64 | **0.31** | 0.77 | 0.69 | 1 | 0.81 | 1.12 | 6044 | 641 |
| 100 | full/verbose | 64 | 0.25 | 0.80 | 0.59 | 5 | 0.81 | 0.69 | 26779 | 690 |
| c100 | graph_seg/verbose | 63 | 0.33 | 0.80 | 0.58 | 3 | 0.76 | 0.83 | 4048 | 599 |
| c100 | **graph_key2/verbose** | 63 | **0.25** | 0.74 | 0.63 | 3 | 0.71 | 1.10 | 5968 | 621 |
| c100 | full/verbose | 63 | 0.14 | 0.71 | 0.41 | 3 | 0.75 | 0.92 | 26844 | 597 |
| 500 | graph_seg/verbose | 63 | 0.33 | 0.80 | 0.65 | 2 | 0.75 | 0.92 | 4124 | 614 |
| 500 | **graph_key2/verbose** | 63 | **0.19** | 0.78 | 0.61 | 1 | 0.79 | 0.97 | 6764 | 640 |
| 500 | full/verbose | 63 | 0.16 | 0.72 | 0.41 | 5 | 0.73 | 0.81 | 123218 | 593 |

| 条件（v1，16k） | graph_key2/verbose − graph_seg/verbose | graph_key2/verbose − full/verbose |
|---|---|---|
| 100 | −0.02 [−0.17, +0.14] | +0.06 [−0.08, +0.20] |
| c100 | −0.08 [−0.22, +0.06] | +0.11 [+0.00, +0.22] |
| 500 | −0.14 [−0.29, +0.00] | +0.03 [−0.11, +0.16] |

读法：会终止的 prompt 下（打满 ≤ 5 格），parser-free 臂在 100 档与 parser 版持平，c100 与 500 档各低 0.08 / 0.14（500 档区间上沿恰为 0）；对 full 只在 c100 显著（+0.11）。两种 prompt 合起来：**parser-free 的 actor 层在 ≤ 100 条历史上与 parser 版持平，500 条上落后 0.14–0.27，落后的来源是选择阶段（key_select2 在 500 条 0.82）而不是 actor**；collateral 在 v1 下偏高（1.10–1.12 对 graph_seg 0.67–0.92），多读的同 key 先例让 actor 多写了几笔。

结果包 §3.3 的"parser-free 与 parser 版持平"这句建议改成"≤ 100 条持平、500 条落后"，并同时报 verbose 口径。完整面板：`results/real/hm3/long_out/panel_summary_travel.md`（B 未改它，`panel_summary` 自己会重写）。

## 4. B3：A-Mem native 档 16k —— 与 A 撞车，以下是发生的事

- 16:38 B 用 venv312 启动 travel_native 四个 shard（B 机器）。启动失误一次：`api/api.txt` 是 6 行、隔行空白，B 第一次按原始行号取第 4 行拿到空串，shard 16 与 48 在 `Client()` 处 `Missing credentials` 退出（未写 cell），16:41 用 `grep -v '^\s*$'` 后的第 4 个 key 重启。四个 shard 17:02–17:14 各自跑完 16 个 episode（B 的日志 `amem16k/travel_native_{0,16,32,48}.log` 各 16 行 cell）。
- A 在 17:05 把计划改为"B3 改由 A 做"，并在 A 的机器上对**同一 out_dir** 启动了 travel_native（当时 60/64）与 shopping32_native。runner 只跳过账本里已有的 cell，所以 A 的 travel 进程从各 shard 的尾部接着跑，与 B 的进程**同时写同一 episode**：账本里 travel_native 四个 shard 各有 16 个 episode 但 21 / 21 / 19 / 25 行 cell（test-011–015、027–031 等各出现两次）。`memsys_summary` 按 episode 去重（n=64），表没受影响，但**账本里有 20 行重复 cell，A 合并时请知道**；重复的两次是独立抽样，取哪一次由 `cells()` 的覆盖顺序决定（后读的覆盖先读的）。
- 17:15 B 没看到 A 的改动，又启动了 shopping32_native 四个 shard，17:17 发现账本已有 33 格（A 的进程在写）后立即 kill 了自己的四个进程（它们没写任何 cell）。但 B 的启动用 `>` 截断了 `amem16k/shopping32_native_{0,16,32,48}.log`——若 A 的进程也写这四个文件，A 的日志前半段已丢（账本不受影响，A 的 shard 目录里另有 `shard.log`）。
- 现状（17:19）：travel_native 64/64 完成（B 跑的，表在 §1.2）；shopping32_native 40/64，A 的进程在跑。B 不再碰 B3。
- 教训：启动前先 `stat` 计划文件，A 会在 session 中间改 §7/§8。

## 5. 待更新

- [ ] amem16k travel_100 / shopping32_100（A 机器，17:19 为 42 / 45）完成后重跑 §1.2 并替换；再按 A 的 §7.1 补充用相同命令补 6 格连接失败（B 的 venv312 也能跑）。
- [x] B2 v2 → §3.1。
- [x] B2 v1 → §3.2。
- [x] B3 travel_native → §1.2；shopping32_native 由 A 跑完后由 A 收表。

## 6. 9/20 下午：§7.5 的 B4–B8（13:22 PDT 起，全部在 B 机器，Python 3.12 系统包，sklearn 1.9 / openai 2.44 可用）

启动方式：B4/B5/B6/B7 共 17 个 CPU 任务由一个队列脚本按优先级启动，最多 8 个并发（`OMP_NUM_THREADS=2`）；B8 的 2 个 v2 多数票发现进程与 16 个 `frontier_exec` shard 走 key 2/3。启动前核对：`frontier_select_o1_t30_seg / t70 / t50_seg` 在 `scaling_learners()` 里能解析；`api/api.txt` 四个 key 都在；本机没有遗留 hm3 进程；输出路径全是新的。

### 6.1 B4：重放次数 vs 历史长度，test seeds 30/31/32（13:22–13:31 完成）

`results/real/hm3/replay/length_{travel,shopping32}.json`；下表是三个 seed 的均值（每格 60 个 episode，`full_ok` 全为 60）。

| 领域 | 历史 | 记录数 | frontier 大小 | 重放次数 | 重放 p90 | 秒/episode |
|---|---|---|---|---|---|---|
| Travel | native | 18.5 | 2.51 | 13.6 | 22.7 | 0.8 |
| Travel | 100 | 100 | 2.67 | 19.3 | 32.0 | 4.4 |
| Travel | 500 | 500 | 2.73 | 25.2 | 42.1 | 33.1 |
| Shopping32 | native | 14.8 | 2.23 | 14.4 | 22.5 | 3.1 |
| Shopping32 | 100 | 100 | 2.23 | 18.5 | 27.0 | 13.2 |
| Shopping32 | 500 | 500 | 2.23 | 20.9 | 30.3 | 119.9 |

读法：与 dev seeds 一致——frontier 大小随记录数不变（Travel 2.5→2.7，Shopping 2.2 不动），重放次数从 native 到 500 条只增 1.5–1.9 倍（记录数增 27–34 倍）。原始行在 `length_test.log`。

### 6.2 B6：用同一原语定位肇事记录（Travel 100 / c100、Shopping native / 500，13:24–16:20 完成）

`results/real/hm3/replay/localise_{travel_100abcd,travel_100c,shopping32_native}.json`。每格是三个 seed 的中位数（seed30/31/32），括号里是均值与命中率；A 的 native / 500 也列出便于对照。

| 条件 | 事故数（3 seed 合计） | 结构顺序 | 读集优先 | 历史顺序 |
|---|---|---|---|---|
| Travel native（A） | 161 | 1/1/2（均 2.5，命中 1.00） | 4/4/4（均 3.8） | 8/8/7.5（均 7.1） |
| Travel 100 | 169 | 1/1/2（均 3.0，命中 1.00） | 4/6/4（均 4.8） | 13/13/13（均 13.1） |
| Travel c100 | 169 | 1/1/2（均 3.6，命中 1.00） | 4/6/4（均 5.2） | 13/13/13（均 13.1） |
| Travel 500（A） | 168 | 1/1/2（均 3.0，命中 1.00） | 4/6/4（均 4.7） | 18/18/18（均 17.9） |
| Shopping native | 85 | 4/4/4（均 4.1，命中 1.00） | 6.5/6/6（均 5.4） | 6/6/6（均 6.1） |
| Shopping 500 | 62 | 4/6/2（均 8.1，命中 1.00） | 6/8/6（均 10.1） | 18/18/18（均 18.0） |

读法：Travel 的结构顺序中位数在四个长度上都是 1–2 次，历史顺序随 log(记录数) 增长（8→13→18）；c100 与 100 相同。Shopping native **不是**预期的"多数腐蚀不产生事故"边界：三个 seed 各 28–29 起事故（60 个 episode），全部命中；只是 native 档记录太少（15 条），结构顺序 4 次与历史顺序 6 次差距小。Shopping 500 条：事故数降到 62（每 seed 16–23，多数腐蚀在 500 条下不再改变计划），结构顺序中位数 2–6、均值 8.1（比 Travel 的 3 高，方差也大：seed31 中位 6），历史顺序 18，与 Travel 500 相同。定位在 Shopping 上成立但优势比 Travel 小（2–9 倍 vs 6–18 倍）。

### 6.3 异常：定位表里的 `bm25` 列等于 `history` 列（所有条件、所有 seed，含 A 的 native 与 500）

`hm3.replay_localise` 第 92 行取 `baseline_rankings(bad, anomalies).get("bm25", [])`，但 `hm3.provenance.baseline_rankings` 返回的键是 `recency / bm25_anomaly / source_heuristic`（没有 `bm25`），所以拿到空列表，`orders["bm25"]` 退化成 `hist_order`。核对：Travel 100 的 169 行里 169 行的 `bm25` 与 `history` 的 `found` 与 `calls` 完全相同；A 的 `localise_travel_native / 500abcd` 也是逐 seed 相同。B 不改代码，请 A：改成 `.get("bm25_anomaly", [])`（注意它只有 top-5，之后仍回落到历史顺序；若要整段 BM25 排序需把 `k` 提到 `len(ep.H)`），然后重跑六个定位文件（每个 1–3 分钟）。**在修好前，状态文档里"18 without it"这类对照只能写历史顺序，BM25 那列不能引用。** 上表因此没有列 bm25。

### 6.4 B5：p_θ 折中扫描，dev seeds 1/2，100 与 500 条（13:22–13:45 完成，每个 3–20 分钟）

`results/development/hm3/replay/sweep_{travel,shopping32}_s{1,2}_{100,500}.json`。EES 列是 seed1/seed2；records、frontier recall/precision 是两个 seed 的均值（60 个 dev episode）。frontier recall/precision 以每个 eval episode 的重放验证 frontier 为参照。

**shopping32 100 条**

| balanced | thr | seg | EES s1/s2 | records | frontier recall | frontier precision |
|---|---|---|---|---|---|---|
| True | 0.2 | False | 0.92/0.87 | 6.4 | 0.93 | 0.37 |
| True | 0.2 | True | 1.00/1.00 | 11.6 | 0.98 | 0.22 |
| True | 0.3 | False | 0.92/0.85 | 6.0 | 0.93 | 0.39 |
| True | 0.3 | True | 1.00/0.98 | 11.0 | 0.97 | 0.23 |
| True | 0.5 | False | 0.88/0.83 | 5.3 | 0.91 | 0.44 |
| True | 0.5 | True | 0.98/0.97 | 9.6 | 0.95 | 0.26 |
| True | 0.7 | False | 0.87/0.82 | 3.4 | 0.90 | 0.65 |
| True | 0.7 | True | 0.98/0.93 | 6.8 | 0.94 | 0.36 |
| False | 0.2 | False | 0.85/0.73 | 2.3 | 0.82 | 0.77 |
| False | 0.2 | True | 0.93/0.83 | 4.2 | 0.85 | 0.46 |
| False | 0.3 | False | 0.83/0.70 | 2.1 | 0.80 | 0.80 |
| False | 0.3 | True | 0.93/0.83 | 3.9 | 0.85 | 0.49 |
| False | 0.5 | False | 0.73/0.70 | 1.8 | 0.73 | 0.77 |
| False | 0.5 | True | 0.87/0.78 | 3.3 | 0.78 | 0.47 |
| False | 0.7 | False | 0.67/0.70 | 1.7 | 0.71 | 0.77 |
| False | 0.7 | True | 0.85/0.78 | 3.1 | 0.77 | 0.48 |

**shopping32 500 条**

| balanced | thr | seg | EES s1/s2 | records | frontier recall | frontier precision |
|---|---|---|---|---|---|---|
| True | 0.2 | False | 0.92/0.87 | 8.0 | 0.95 | 0.29 |
| True | 0.2 | True | 1.00/1.00 | 16.1 | 0.98 | 0.16 |
| True | 0.3 | False | 0.92/0.87 | 7.8 | 0.95 | 0.30 |
| True | 0.3 | True | 1.00/1.00 | 15.7 | 0.98 | 0.16 |
| True | 0.5 | False | 0.92/0.87 | 6.1 | 0.93 | 0.38 |
| True | 0.5 | True | 1.00/1.00 | 12.2 | 0.98 | 0.21 |
| True | 0.7 | False | 0.92/0.85 | 5.2 | 0.92 | 0.45 |
| True | 0.7 | True | 1.00/1.00 | 10.2 | 0.97 | 0.26 |
| False | 0.2 | False | 0.82/0.70 | 2.2 | 0.79 | 0.76 |
| False | 0.2 | True | 0.93/0.80 | 4.3 | 0.85 | 0.46 |
| False | 0.3 | False | 0.80/0.68 | 1.9 | 0.77 | 0.80 |
| False | 0.3 | True | 0.90/0.78 | 3.5 | 0.81 | 0.49 |
| False | 0.5 | False | 0.80/0.63 | 1.8 | 0.75 | 0.80 |
| False | 0.5 | True | 0.88/0.77 | 3.2 | 0.80 | 0.50 |
| False | 0.7 | False | 0.68/0.58 | 1.6 | 0.65 | 0.69 |
| False | 0.7 | True | 0.75/0.67 | 2.7 | 0.68 | 0.44 |

**travel 100 条**

| balanced | thr | seg | EES s1/s2 | records | frontier recall | frontier precision |
|---|---|---|---|---|---|---|
| True | 0.2 | False | 0.88/0.87 | 11.3 | 0.97 | 0.26 |
| True | 0.2 | True | 0.93/0.95 | 21.4 | 0.98 | 0.14 |
| True | 0.3 | False | 0.82/0.87 | 10.1 | 0.96 | 0.28 |
| True | 0.3 | True | 0.90/0.93 | 18.9 | 0.98 | 0.16 |
| True | 0.5 | False | 0.80/0.85 | 7.8 | 0.94 | 0.37 |
| True | 0.5 | True | 0.85/0.92 | 14.9 | 0.96 | 0.21 |
| True | 0.7 | False | 0.78/0.82 | 6.1 | 0.91 | 0.44 |
| True | 0.7 | True | 0.82/0.90 | 11.8 | 0.93 | 0.25 |
| False | 0.2 | False | 0.67/0.62 | 3.3 | 0.79 | 0.65 |
| False | 0.2 | True | 0.83/0.80 | 7.0 | 0.86 | 0.37 |
| False | 0.3 | False | 0.63/0.53 | 2.5 | 0.73 | 0.71 |
| False | 0.3 | True | 0.78/0.75 | 5.3 | 0.80 | 0.42 |
| False | 0.5 | False | 0.57/0.53 | 2.0 | 0.67 | 0.73 |
| False | 0.5 | True | 0.65/0.63 | 3.9 | 0.71 | 0.45 |
| False | 0.7 | False | 0.45/0.43 | 1.6 | 0.58 | 0.71 |
| False | 0.7 | True | 0.58/0.58 | 3.2 | 0.66 | 0.44 |

**travel 500 条**

| balanced | thr | seg | EES s1/s2 | records | frontier recall | frontier precision |
|---|---|---|---|---|---|---|
| True | 0.2 | False | 0.82/0.92 | 33.9 | 0.96 | 0.09 |
| True | 0.2 | True | 0.87/0.97 | 66.0 | 0.96 | 0.05 |
| True | 0.3 | False | 0.82/0.88 | 25.0 | 0.95 | 0.12 |
| True | 0.3 | True | 0.88/0.95 | 49.1 | 0.96 | 0.07 |
| True | 0.5 | False | 0.78/0.77 | 14.7 | 0.93 | 0.19 |
| True | 0.5 | True | 0.87/0.87 | 29.0 | 0.95 | 0.10 |
| True | 0.7 | False | 0.77/0.77 | 10.8 | 0.91 | 0.26 |
| True | 0.7 | True | 0.87/0.82 | 21.3 | 0.93 | 0.13 |
| False | 0.2 | False | 0.55/0.67 | 3.7 | 0.76 | 0.59 |
| False | 0.2 | True | 0.73/0.85 | 6.6 | 0.81 | 0.37 |
| False | 0.3 | False | 0.53/0.65 | 3.2 | 0.74 | 0.63 |
| False | 0.3 | True | 0.73/0.82 | 5.7 | 0.80 | 0.41 |
| False | 0.5 | False | 0.45/0.52 | 2.3 | 0.62 | 0.62 |
| False | 0.5 | True | 0.60/0.70 | 4.1 | 0.67 | 0.40 |
| False | 0.7 | False | 0.40/0.45 | 1.8 | 0.55 | 0.62 |
| False | 0.7 | True | 0.50/0.60 | 3.2 | 0.60 | 0.41 |

读法（与 A 的 seed 0 / 500 条结论对照）：
- balanced 在所有阈值与粒度上都高于 unbalanced；unbalanced 的 frontier recall 只有 0.55–0.86，precision 0.6–0.8，是"读得太少"的一端。
- 整段（seg）比单条多 +0.05 到 +0.12 EES，记录数约 2 倍。
- Travel 500 条的过度选择在这里复现：balanced/seg 在 thr 0.2–0.3 读 49–66 条（precision 0.05–0.07）；thr 0.7/seg 读 21 条，EES 0.87/0.82，只低 0.0–0.15。Travel 100 条 thr 0.3/seg 读 19 条，EES 0.90/0.93。
- Shopping 的 balanced/seg 在任何阈值都是 EES 0.97–1.00，thr 0.7/seg 只读 7 条（100）/ 10 条（500），过度选择确实是 Travel 特有。
- 对 B7 三个新臂的预期：`t30_seg` 最高 EES 但 Travel 500 读得多；`t70`（单条）记录最少但 Travel 掉 0.1；`t50_seg` 居中。

### 6.5 B7：frontier 阶梯的三个新臂（Travel dev/test 13:27–13:52；Shopping dev/test 13:28–16:20，500 条的 discover 慢）

`results/development/hm3/replay/ladder_frontier2_dev_travel.json`、`results/real/hm3/replay/ladder_frontier2_test_travel.json`（`--train_seed_offset 100`，每格 60 episode）。EES 是三个 seed 的均值（括号里逐 seed），reads 是 `n_reads` 均值；graph_select 作为 parser 上界一起跑。旧阶梯（`ladder_frontier_*`）里的单条 t30 / t50 也列出便于比较。

| 条件 | 臂 | dev EES | dev reads | test EES | test reads |
|---|---|---|---|---|---|
| native | t30_seg（新） | 0.989 (1.00/0.97/1.00) | 24.3 | 0.972 (0.98/0.93/1.00) | 23.1 |
| native | t50_seg（新） | 0.950 | 22.0 | 0.967 | 20.4 |
| native | t70（新，单条） | 0.828 | 11.7 | 0.861 | 11.3 |
| native | t30（旧，单条） | 0.933 | 15.5 | 0.944 | 14.4 |
| native | graph_select | 1.000 | 11.4 | 1.000 | 11.2 |
| 100 | t30_seg | 0.933 (0.97/0.90/0.93) | 46.2 | 0.939 (0.95/0.93/0.93) | 43.4 |
| 100 | t50_seg | 0.917 | 36.0 | 0.922 | 34.9 |
| 100 | t70 | 0.833 | 19.8 | 0.804 | 18.8 |
| 100 | t30（旧） | 0.878 | 30.9 | 0.838 | 29.7 |
| 100 | graph_select | 1.000 | 12.3 | 1.000 | 12.1 |
| c100 | t30_seg | 0.878 (0.93/0.83/0.87) | 46.2 | 0.910 (0.88/0.97/0.88) | 48.2 |
| c100 | t50_seg | 0.844 | 36.7 | 0.899 | 37.9 |
| c100 | t70 | 0.767 | 20.8 | 0.759 | 21.1 |
| c100 | t30（旧） | 0.789 | 31.1 | 0.814 | 33.0 |
| c100 | graph_select | 1.000 | 12.3 | 1.000 | 12.0 |
| 500 | t30_seg | 0.928 (0.95/0.88/0.95) | 125.2 | 0.949 (0.97/0.95/0.93) | 132.8 |
| 500 | t50_seg | 0.872 | 77.2 | 0.933 | 93.2 |
| 500 | t70 | 0.800 | 34.4 | 0.776 | 33.0 |
| 500 | t30（旧） | 0.822 | 81.6 | 0.786 | 84.1 |
| 500 | graph_select | 1.000 | 12.4 | 1.000 | 12.1 |

读法：
- 整段选择把 parser-free 选择器在 Travel 四个长度上都推到 0.93–0.97（test），比旧的单条 t30 高 0.03–0.16，且 native/100/c100/500 之间几乎平（不随长度掉）。代价是读得多：500 条读 125–133 条（graph_select 12 条），比 B5 扫描里同设置的 49 条多一倍多——两处 `reads` 口径可能不同（扫描里是 `predict` 选出的记录数，阶梯里是 `n_reads`，疑似含整段展开后的记录），请 A 确认后再在文档里并排引用。
- t70 单条：读得最少（11–34 条）但 EES 0.76–0.86，比 t30_seg 低 0.1–0.17；t50_seg 在两者之间，500 条 test 0.933 / 93 条。
- 建议文档里的 parser-free 主臂用 `t30_seg`（EES），并把 `t50_seg` 作为 tokens 折中一起报。

**Shopping32**（`ladder_frontier2_{dev,test}_shopping32.json`；旧阶梯的单条 t30 在 500 条只有两个 seed）：

| 条件 | 臂 | dev EES | dev reads | test EES | test reads |
|---|---|---|---|---|---|
| native | t30_seg | 0.967 (0.95/1.00/0.95) | 18.4 | 0.894 (0.98/0.88/0.82) | 18.1 |
| native | t50_seg | 0.928 | 16.8 | 0.878 | 16.8 |
| native | t70 | 0.622 (0.27/0.82/0.78) | 11.2 | 0.772 | 11.6 |
| native | t30（旧） | 0.911 | 13.4 | 0.856 | 13.2 |
| native | graph_select | 0.989 | 18.3 | 0.972 | 18.7 |
| 100 | t30_seg | 0.994 | 26.4 | 0.989 (1.00/0.97/1.00) | 22.0 |
| 100 | t50_seg | 0.983 | 24.0 | 0.956 | 20.5 |
| 100 | t70 | 0.861 | 12.8 | 0.794 | 12.8 |
| 100 | t30（旧） | 0.911 | 16.4 | 0.850 | 14.6 |
| 100 | graph_select | 0.989 | 21.1 | 0.972 | 21.5 |
| 500 | t30_seg | 1.000 | 34.2 | 0.983 (1.00/0.98/0.97) | 25.4 |
| 500 | t50_seg | 1.000 | 26.8 | 0.972 | 23.7 |
| 500 | t70 | 0.906 | 15.0 | 0.828 | 14.6 |
| 500 | t30（旧，2 seed） | 0.942 | 18.9 | 0.858 | 16.4 |
| 500 | graph_select | 0.989 | 21.4 | 0.978 | 21.5 |

读法：Shopping 上 `t30_seg` 在 100 与 500 条与 graph_select 持平（test 0.99 / 0.98 vs 0.97 / 0.98），读 22–25 条，与 parser 版相当，没有 Travel 的过度选择；native 档低 0.08（0.89 vs 0.97，seed32 0.82）。`t70` 单条在 Shopping 明显不够（0.77–0.83，dev seed0 native 只有 0.27）。旧单条 t30 在所有条件低 0.04–0.14。两领域合起来：整段选择是必须的，阈值 0.3 或 0.5 差别在 0.01–0.03 内，0.5 在 Travel 500 条少读 30%。

### 6.6 B8-2：`frontier_exec` actor 臂补齐的四格（13:22–13:50 完成，v1、verbose、16k，64/64 全部落账，`infrastructure_failure` 0）

`results/real/hm3/frontier_llm/{travel_native,travel_100,shopping32_100,shopping32_500}_exec/`。**注意** `hm3.panel_summary` 的 SOURCES 只登记了 `{d}_c100_exec` 与 `{d}_500_exec`，没有 `{d}_native_exec` / `{d}_100_exec`，直接跑面板看不到 Travel native/100 与 Shopping 100 这三格。B 没改代码，用 scratchpad 里一个 6 行的包装（`P.SOURCES += [...]` 后调 `summarise`）生成的完整面板存在 `results/real/hm3/frontier_llm/panel_exec_{travel,shopping32}.md`；请 A 把这两个 pattern 加进 SOURCES。下表是 prompt v1 / cap 16k 的三臂（含 A 已有的 c100 与 500）：

| 条件 | full/verbose | graph_seg/verbose | frontier_exec/verbose | exec − full（EES [95% CI]） | exec − graph_seg |
|---|---|---|---|---|---|
| Travel native | 0.48 (n=64, in 6.5k) | 0.48 (in 3.5k) | 0.41 (in 3.4k) | −0.08 [−0.23, +0.09] | −0.08 [−0.23, +0.06] |
| Travel 100 | 0.25 (in 26.8k) | 0.33 (in 4.0k) | 0.31 (in 5.7k) | +0.06 [−0.09, +0.22] | −0.02 [−0.17, +0.13] |
| Travel c100（A） | 0.14 (n=63) | 0.33 | 0.25 (in 6.1k) | +0.11 [−0.02, +0.24] | −0.08 [−0.22, +0.06] |
| Travel 500（A） | 0.16 (n=63, in 123k) | 0.33 | 0.21 (in 15.9k) | +0.05 [−0.08, +0.17] | −0.13 [−0.27, +0.02] |
| Shopping 100 | 0.48 (in 25.8k) | 0.50 (in 9.9k) | 0.56 (in 5.9k) | +0.08 [−0.08, +0.23] | +0.06 [−0.06, +0.19] |
| Shopping 500 | 0.52 (in 103k) | 0.36 (in 10.3k) | 0.56 (in 6.1k) | +0.05 [−0.09, +0.19] | +0.20 [+0.03, +0.38] |

其他列（affected F1、value acc）：Travel 100 exec − full value acc +0.10 [−0.03, +0.24]；Shopping 100 exec − full affected F1 +0.17 [+0.06, +0.28]、value acc +0.13 [+0.00, +0.25]；Shopping 500 exec − graph_seg value acc +0.12 [+0.01, +0.23]。

读法：actor 层 exec 臂在 Travel 与 full 持平到略高（区间都含 0），比 parser 版 graph_seg 低 0.02–0.13；在 Shopping 两个长度都是三臂里最高（0.56），500 条显著高于 graph_seg（+0.20）且输入只有 full 的 6%。A 的状态文档里 "c100 EES 0.25 vs full 0.14 vs 0.33" 那句现在可以扩成四个 Travel 长度 + 两个 Shopping 长度。Travel 500 的 exec 臂 med in 15.9k 与 B7 里 t30_seg 读 125 条对应，是过度选择在 tokens 上的体现。

### 6.7 B8-1：v2 prompt 多数票发现（k=3），13:22–14:05 完成，两个 shard 都在预算内跑完 24 个 episode

`results/real/hm3/replay_llm/travel_s30_v2_k3_{0,24}/summary.json`（key 2/3；`--n_train 24 --repeats 3 --budget_usd 12`）。A 的 v1 k3 两个 shard 列出对照。

| run | episodes | full_ok | 花费 | frontier（LLM） | executor frontier | 重放次数 | LLM 覆盖 exec frontier | type edges（支持数） | vs skeleton（5 条） |
|---|---|---|---|---|---|---|---|---|---|
| v2 k3 shard 0 | 24 | 9 | $9.24 | 3.11 | 3.25 | 16.7 | 0.25 | flight→transfer (27), transfer→stay (3) | P 1.0 / R 0.4 |
| v2 k3 shard 24 | 24 | 8 | $11.45 | 2.38 | 2.40 | 19.4 | 0.33 | flight→transfer (13), transfer→stay (2) | P 1.0 / R 0.4 |
| v1 k3 shard 0（A） | 24 | 7 | $4.24 | 2.29 | 2.83 | 16.4 | 0.42 | flight→transfer (14) | P 1.0 / R 0.2 |
| v1 k3 shard 24（A） | 19（预算触顶） | 7 | $13.63 | 5.86 | 2.40 | 35.3 | 0.70 | flight→transfer (30), stay→dinner (6), transfer→stay (16) | P 1.0 / R 0.6 |

读法：v2 下 LLM 的全历史重放通过率仍只有 17/48 = 35%（v1 为 14/43 = 33%）；`full_ok=False` 的 episode 一次调用就判失败，几乎不花钱，所以 24 个 episode 只用了 $9–11。两个 shard 独立都恢复 flight→transfer 与 transfer→stay，缺 stay→{activity, bundle, dinner}；v1 的 shard 24 多出 stay→dinner，v2 没有。LLM 发现的 frontier 与 executor frontier 大小接近（3.1 vs 3.3、2.4 vs 2.4），但覆盖率只有 0.25–0.33，也就是 LLM 判定的充分读集与 executor 的多数不重合。合并两个 shard 的 `sets.jsonl` 做整体 vs_skeleton 需要 A 的脚本（`hm3.replay_llm` 只按 shard 汇总）。

### 6.8 收尾（16:25）

- 17 个 CPU 任务与 18 个 API 进程全部结束，本机没有遗留 hm3 进程；所有日志无 Traceback。总耗时 13:22–16:20，长尾是 Shopping 500 条的 discover（两个阶梯各约 2.9 小时）。
- 新产物：`results/real/hm3/replay/{length_travel,length_shopping32,localise_travel_100abcd,localise_travel_100c,localise_shopping32_native,localise_shopping32_500abcd,ladder_frontier2_test_travel,ladder_frontier2_test_shopping32}.json`；`results/development/hm3/replay/{sweep_*_s{1,2}_{100,500},ladder_frontier2_dev_travel,ladder_frontier2_dev_shopping32}.json`；`results/real/hm3/frontier_llm/{travel_native,travel_100,shopping32_100,shopping32_500}_exec/` 与 `panel_exec_{travel,shopping32}.md`；`results/real/hm3/replay_llm/travel_s30_v2_k3_{0,24}/`。
- 请 A 处理的两处代码：§6.3（`replay_localise` 的 bm25 键名）与 §6.6（`panel_summary.SOURCES` 缺两个 pattern）；一处口径确认：§6.5 阶梯 `n_reads` 与 §6.4 扫描 `records` 的关系。
