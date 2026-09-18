# HM3 / P3-B / E0 v2 分支交接（2026-09-18）

本页描述分支 `claude/hm3-handoff-2026-09-18` 的内容、来源和核验方法。该分支不合并到
`claude/artifact-ordering-inzyf3`，由整合方从 `fcc0805` 建 integration branch 后自行合并核验。
在核验通过前，本分支内容应视为“很可能真实、尚未交接完成”，不进入论文。

## 1. 共同祖先与提交顺序

- 共同祖先：`9e0373c` Complete P2 and P3 causal-memory experiments。
- `origin/claude/artifact-ordering-inzyf3` 在其后有 4 个提交（`fdc5744` → `fcc0805`）。
- 本分支在其后有 14 个提交（全部作者日期 2026-09-03），再加本页所在的 1 个交接提交。
- 两侧同时改动的文件只有两个：`docs/HANDOFF.md`（两侧各自追加）与
  `docs/hidden-mechanism-v3-preregistration.md`（**两侧各自独立重建**，见 §6）。

| # | commit | 内容 | 文件数 |
|---|---|---|---:|
| 1 | `275422b` | Hidden Mechanism v3: generator, killer baselines, dev gate, test and API runs | 55 |
| 2 | `5973273` | HM3 follow-ups: regularised program learner, Shopping v3.1, thinking probe | 18 |
| 3 | `88d9aef` | HM3 round 2: prompt v2 API rerun, fresh-seed replication, Shopping v3.2 | 37 |
| 4 | `cea15ec` | Strip trailing whitespace in the v3 results document | 1 |
| 5 | `4da798f` | End-to-end progress and results report for the 2026-09-03 meeting | 1 |
| 6 | `29a0f7e` | P3-B round 3: frozen MINJA protocol, four-arm gate with expansion and quarantine | 4 |
| 7 | `8420e80` | API rounds 3-4 and P3-B round 4: power, witness closure, block design | 8 |
| 8 | `b90ecad` | API rounds 3-4 results: witness closure halves Travel's gap; EES cost 0.10-0.19 at 70-74% less input | 24 |
| 9 | `cb82da2` | P3-B round 3 results: quarantine removes every attack, block consistency unevaluable | 14 |
| 10 | `a0396ab` | Progress report: P3-B round-3 section and mitigation ledger row | 1 |
| 11 | `5391c41` | P3-B round 4 passes: same-stem expansion and quarantine mitigate MINJA online | 17 |
| 12 | `d421c76` | Presenter script and report: mitigation slides, closure appendix, deck map | 2 |
| 13 | `6db703d` | P3-B: freeze the AgentPoison round-3 protocol and its block judgement | 2 |
| 14 | `580d547` | P3-B AgentPoison round 3: frozen matrix and launcher | 4 |
| 15 | 本提交 | 交接页、artifact hashes、E0 v2 代码与部分结果、P3-B power audit、AgentPoison r3 gate 输出 | — |

未纳入：`slides/`（pptx 与 .bak，11 MB）、`meeting/`（script.zip）、`*.log`（gitignore）。

## 2. HM3 内容分类：dev / 冻结 test / post-hoc / API 各轮

预注册：`docs/hidden-mechanism-v3-preregistration.md`（本分支版本，§5 gate、§6 数据边界、
§8–§12 各轮追加）。结果：`docs/hidden-mechanism-v3-results.md`。代码：`code/hm3/`。

| 类别 | seeds | 文件 | 备注 |
|---|---|---|---|
| dev（gate、方法选择、prompt 检查） | eval 0/1/2；train 200 / dev 60 | `results/development/hm3/det_dev*.json`、`gate*.json` | `det_dev_shopping31.json`、`gate_shopping31.json` 只跑了 dev，无 test |
| 冻结 test round 1 | eval 10/11/12；train 110/111/112（offset 100） | `results/real/hm3/det_test*.json` | 13 个方法，confirmatory |
| test 之后的 post-hoc（预注册 §8） | 同上 | `results/real/hm3/det_test_program_reg.json`、`exploratory_thinking/` | `program_reg` 是 learner 配置改动，在 test 评分之后加入；`program` 原数字保持 confirmatory |
| round 2 deterministic（预注册 §10，评分前冻结） | eval 20/21/22；train 120/121/122 | `results/real/hm3/round2/det_test2*.json` | 加 `shopping32`（generator 改动）、`program_reg`、`graph_pooled`；与 round 1 并列报告 |
| API round 1 | test seed 10，episode 0–19，5 selection × 2 serialization | `results/real/hm3/llm_ledger.jsonl`、`llm_summary.json`、`llm_protocol.json`、`shards/` | prompt v1；`llm_ledger_v1_empty_replies.jsonl.bak` 是首次尝试的空回复账本，不计入 |
| API round 2（预注册 §9） | 同 round 1 episodes | `results/real/hm3/round2/llm_summary.json`、`paired_bootstrap.json`、`round2/shards/` | **runtime 改动**：system prompt v2；selector、模型、参数不变 |
| API round 3（预注册 §11） | test seed 10，episode 0–79，4 cells | `results/real/hm3/round3/llm_summary.json`、`paired_analysis.json`、`round3/shards/` | 功效补样；预算 $12 在 527/640 cells 到达 |
| API round 4（预注册 §12） | 同 round 3 episodes，2 cells | `results/real/hm3/round4/llm_summary.json`、`paired_analysis.json`、`round4/shards/` | **selection 改动**：`graph_closed` = graph reads ∪ referent 对象 ∪ 1-hop 邻居；配对对象为 round 3 的 full/verbose |

各轮改动了实现的地方：§8 `program_reg`（learner 超参）、`shopping31`/`shopping32`（generator）、
round 2 prompt v2（runtime）、round 4 `graph_closed`（LLM 侧 selection）。确定性 `graph` 与
`program` learner 自 round 1 起未改。

每个 API shard 目录都有自己的 `llm_protocol.json`（冻结配置）与 `llm_ledger.jsonl`
（逐 cell：episode、selection、serialization、input/output/cached tokens、cost、
`returned_model`、`parse_ok`、`finish_reason`、原始回复）。

## 3. 唯一汇总命令

```bash
cd code
PYTHONPATH=. python3 -m hm3.report --det ../results/real/hm3/round2/det_test2.json
```

2026-09-18 在本机重跑，输出与结果文档 §7.2 的 15 行 × 5 列表格逐格一致（fresh test seeds
20/21/22）。其他表格同一命令换 `--det` 路径：`results/development/hm3/det_dev.json`（§3）、
`results/real/hm3/det_test.json`（§4）。API 汇总在各轮 `llm_summary.json` 与
`paired_analysis.json` / `paired_bootstrap.json`。

## 4. 复现命令

```bash
python3 -m compileall -q code/hm3 code/e0v2          # 本机 OK
cd code
# dev + gate（seeds 0/1/2）
PYTHONPATH=. python3 -m hm3.run_det --domains travel shopping search formal \
  --seeds 0 1 2 --n_train 200 --n_eval 60 --split dev --out ../results/development/hm3/det_dev.rerun.json
PYTHONPATH=. python3 -m hm3.gate --results ../results/development/hm3/det_dev.rerun.json \
  --out ../results/development/hm3/gate.rerun.json
# fresh test seeds 20/21/22（train offset 100 → 120/121/122），含 shopping32
PYTHONPATH=. python3 -m hm3.run_det --domains travel shopping search formal shopping32 \
  --seeds 20 21 22 --train_seed_offset 100 --n_train 200 --n_eval 60 --split test \
  --out ../results/real/hm3/round2/det_test2.rerun.json
PYTHONPATH=. python3 -m hm3.report --det ../results/real/hm3/round2/det_test2.rerun.json
```

`det_*.json` 里每个 `runs/<domain>/seed<k>/learners/<name>` 都保留逐 episode 行，
汇总可从行重新计算。

## 5. 数据边界（供核验 learner / evaluator 未读 test gold）

- `code/hm3/run_det.py` `run()`：train 用 `generate_split(domain, seed + offset, "train", n)`，
  eval 用 `generate_split(domain, seed, split, n)`；`learner.fit(domain, train)` 之后才
  `evaluate_learner(domain, learner, evals)`。learner 只接收 train episodes。
- `oracle` 与 `rh_oracle` 按设计读取 gold plan（`code/hm3/learners.py` 顶部说明），只作上界。
- API：`code/hm3/llm.py` 从环境变量 `OPENAI_API_KEY` 读取凭据（经
  `code/run_with_local_deepseek.py` 注入子进程），不写入账本。

## 6. 预注册文件的 add/add 冲突

`docs/hidden-mechanism-v3-preregistration.md` 在共同祖先中不存在。本分支的版本是 9/03 与代码
一起重建、并被 §8–§12 逐轮追加的版本；origin 的版本是 9/18 前后在另一工作区独立重建的
“四任务重建预注册（待 Yujia double-check）”，没有对应的运行。合并时建议保留本分支版本作为
与结果对应的预注册，把 origin 版本改名为 `...-reconstructed-origin.md` 并列保存，不要合并成一份。

## 7. Artifact hashes 与密钥扫描

- `results/real/hm3/ARTIFACT_HASHES.sha256`：`code/hm3/*.py`、`results/development/hm3/*`、
  `results/real/hm3/**`、两份 HM3 文档共 110 个文件的 sha256，可用 `sha256sum -c` 校验。
- 密钥扫描：对 14 个提交相对 `9e0373c` 的全部新增行，以及本提交新增的文件，用
  `sk-[A-Za-z0-9]{10,}`、`Bearer …`、`api_key = "…"`、`DEEPSEEK_API_KEY=…` 扫描，均无命中。
  `.gitignore` 已排除 `.env`、`deepseek_apikey.md`、`.tmp/`。

## 8. 本提交新增的非 HM3 内容

- `code/e0v2/`、`results/e0v2/`、`docs/e0-v2-design-2026-09-03.md`、
  `results/diagnostics/e0_blind_power_sweep.json`：E0 v2（regime-specific 系数）。**未完成**：
  `results/e0v2/summary.md` 只有 σ=0、每臂 2–3 seeds；C1 行的 FAIL 是覆盖不足，不是识别失败。
  `code/e0v2/run_all.sh` 里的缓存路径是本机绝对路径，换机需改。
- `code/p3b_power_audit.py`、`results/real/p3b_power_audit.json`、
  `docs/p3b-round3-preregistration-draft-2026-08-30.md`：P3-B round 3 的功效审计与草案。
- `results/real/p3b_round3/agentpoison/`：AgentPoison round-3 gate 的冻结协议、输出与用量账本
  （launcher 见 `580d547`）。
- `docs/yujia-meeting-2026-08-30-round1.md`。

## 9. 整合方的核验清单

1. 从 `fcc0805` 建 integration branch，合并本分支；预期冲突仅 `docs/HANDOFF.md` 与 §6 的预注册文件。
2. `sha256sum -c results/real/hm3/ARTIFACT_HASHES.sha256`。
3. §3 命令重现 §7.2 表格；再用 §4 的 fresh-seed 命令重跑一次并比较。
4. 从 `det_test2.json` 的逐 episode 行重新计算均值 ± sd，与表格一致。
5. 检查 §5 的三处边界。
