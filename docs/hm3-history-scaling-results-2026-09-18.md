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

## 4. backward provenance（dev，seeds 0/1/2，各 60 episode）

smoke（seed 0，40 episode，实现修订前）：Travel 31 个事件，p@1 0.39、p@3 0.84、MRR 0.62；
替换 top-1 后 EES 恢复 0.39，matched random 0.13，similar non-ancestor 0.03，recency 0.00；配对差
predicted − random +0.26 [+0.03, +0.48]。Shopping32 14 个事件，p@1 0.07、p@3 0.36；13 个 episode
找不到改变解析值的最小污染，12 个 episode 的干净计划本身已错。

实现修订（dev 阶段，结果前）：增加 top-3 联合替换与 matched-random-3 对照；similar 对照在全部对象
都在路径上时退回"最相似且不在 top-3 内的记录"，并记录退回类型；Shopping 的 replace_line 污染尝试目录
中全部变体。

正式 dev 结果：待填。

## 5. 结论槽

待 dev 面板、API 面板与 provenance 正式结果齐后按设计 §5 / provenance §5 逐条填写。
