# TokenRhythm 按量中转测试与预算（2026-09-14）

<!-- recent-memory-completion:start -->
> **完整配对评估已完成：** 十臂均完成 IDs 111/112/113，官方评分与用量完整性检查通过。
> [结果表与逐 episode 比较](../results/real/p2_recent_baselines_tokenrhythm_v5_completed/results.md)；表中完整结果的用量估算 ¥25.3557。
> 新中转探针及全部开发/评估合计估算 ¥46.4821，
> 加旧账单 ¥230 后为 ¥276.4821。缺失用量与 aiaaa 未知费用未计入；不是对账总额。
> 这是三个复用 holdout episodes 的描述性配对复验；不证明 causal necessity 或真实 latent identifiability。
> summary 使用按预先记录的技术恢复规则完成的补跑，其余九臂保留原结果；原始批次的断流失败及费用另行保留。
<!-- recent-memory-completion:end -->
当前本地新运行配置为 `https://tokenrhythm.studio/v1` + `deepseek-flash`。
16 次生成测试全部成功，工具调用及 tool-result 回传通过；小样本未观察到整体变慢。
API key 仅写入 Git 忽略、0600 权限的本地配置；未使用用户提供的 session token。

## 连通性和延迟

`GET /v1/models` 返回 200，包含 `deepseek-flash`。Chat 使用 `/v1/chat/completions`。
实测返回模型名也是 `deepseek-flash`，无法仅凭别名验证它与此前 `deepseek-v4-flash`
为相同权重或版本。所有请求零重试、单并发；JSON、stream usage、默认 thinking、
禁用 thinking、OpenAI SDK 工具调用及工具结果回传均通过。

| 测试 | 成功次数 | 首个答案 token 中位数 | 完整响应中位数 |
|---|---:|---:|---:|
| 固定 JSON，thinking disabled | 3/3 | 1.40 秒 | 2.06 秒 |
| 行程结构更新，默认 thinking | 3/3 | 2.59 秒 | 2.73 秒 |
| 工具调用 + 结果回传 | 2/2 | 非流式未测 | 两步分别 1.49 / 0.92 秒 |

历史重放仍使用调用前固定的 8 条 development 请求（四任务 × oracle/full）；与旧
直连及 bboluo 的 prompt hash 全部一致。8/8 满足语义合同，非流式、temperature 0、
max_tokens 32768、原 seed、JSON-object，与旧重放一致；请求模型别名改变。

| 同一组 8 条请求 | 历史直连 | 先前 bboluo | TokenRhythm |
|---|---:|---:|---:|
| 耗时中位数 | 7.43 秒 | 5.98 秒 | 5.73 秒 |
| API 耗时合计 | 65.11 秒 | 52.88 秒 | 44.31 秒 |

相对 bboluo 为 5 条更快、3 条更慢，中位数约下降 4.3%，累计耗时约下降 16.2%。
这是不同时段、不同请求别名的历史对照，负载、缓存、输出长度及连接复用均可影响结果，
不能断言“中转本身必然更快”。小探针也不覆盖完整多步 agent、高并发和长上下文稳定性。

## 单价与本次测试费用

来源：[TokenRhythm 公共模型页](https://tokenrhythm.studio/models)，2026-09-14 抓取。
`deepseek-flash` 页面状态为 testing，币种 CNY，计费单位 1,000,000 tokens：

| 项目 | 元 / 百万 token |
|---|---:|
| 未命中缓存的输入 | 2.00 |
| 命中缓存的输入 | 0.04 |
| 输出 | 8.00 |

估算公式：`(未缓存输入 × 2 + 缓存输入 × 0.04 + 输出 × 8) / 1,000,000`。
输出使用 API 的 completion_tokens，包含推理消耗，不能只计算可见答案。

16 次探针：输入 **18,047**（其中缓存命中 128），输出 **9,730**，估算 **¥0.11368312**。
这是公共标价 × 返回 usage，不是已核对的后台扣款。`/models` 和公共页面读取未计入生成费。
旧 bboluo 已花 **¥230** 为用户确认账单，继续独立保留，不按新单价追溯改写。

## 初始规划估算（历史，已需重新校准）

下表保留切换时的初始预测。完整开发出现更多 memory 调用、长推理和传输修复迭代，
当前累计用量与完成开发后的重新预测以
[累计预算说明](recent-memory-current-budget-2026-09-14.md) 和
[用量快照](../results/development/tokenrhythm_cumulative_budget_2026_09_14.json) 为准。
快照由 `code/arena_recent_budget.py` 离线生成，包含各次中断开发已返回的 usage。

沿用 10 个方法、开发 ID 101、评估 IDs 111/112/113 的范围。以旧开发日志的 actor /
summary / Mem0 / A-Mem / LightMem 各类平均输入输出长度，乘原规划各类调用次数，
重新按本页 token 单价计价。未来输入一律按缓存未命中估算，不预支缓存折扣。

| 项目 | 新中转估算（元） |
|---|---:|
| 完整十臂开发 | 7.49–9.25 |
| 十臂 × 3 episodes 配对评估 | 23.53–29.38 |
| 后续实验合计 | 31.02–38.63 |
| 后续实验加 20% 预留 | 37.23–46.36 |
| 加旧已花 230 及本次探针后的整轮合计 | **267.34–276.47** |

可先按 **整轮约 300 元、后续约 70 元余量**做规划。这是估计，不是已设置的硬上限。
旧 5,000 元建议仅针对每调用 2 元的 bboluo；不再适用于按量 TokenRhythm。

旧开发中有截断、失败和未完成样本，平均长度未必代表完整新运行；模型别名改变、重试和
memory 增长也会改变 token。LightMem 的低/高调用增长情景均不是严格上界。新开发完成后
需要用实际 actor + memory usage 校准。上游 MemoryArena 的 `cost` 字段仍是其静态参考价，
当前费用须从两套 usage ledger 按本页 CNY 单价汇总，不能直接使用那个字段。

## 配置与记录

统一入口保持：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=code \
  .tmp/memory-baselines-venv/bin/python code/run_with_local_deepseek.py -- \
  .tmp/memory-baselines-venv/bin/python code/arena_recent_suite.py \
  --phase development --workers 4
```

Wrapper 将 API key、route 和 model 一起覆盖旧环境变量；识别 `sk_tr_`，显式 API key
赋值优先，拒绝 session token。新 suite 读取模型/路由，当前结果 family 为
`p2_recent_baselines_tokenrhythm_v5`；旧目录与历史冻结协议保留。正式冻结会检查模型、
路由、IDs、arms 和源码 hash，已有 arm 输出不可静默重复追加。

新增三项凭据/路由隔离测试与四项近期 baseline integrity 测试通过；Python 语法及
`git diff --check` 通过。开发轮于连通性测试通过后恢复，完整评估结果另行记录。

原始记录：

- [认证与模型列表](../results/development/tokenrhythm_models_probe_2026_09_14.json)
- [流式与工具调用](../results/development/tokenrhythm_latency_2026_09_14.json)
- [项目历史请求重放](../results/development/tokenrhythm_historical_probe_2026_09_14.json)
- [公开价格快照](../results/development/tokenrhythm_pricing_2026_09_14.json)
- [按量预算计算明细](../results/development/tokenrhythm_usage_budget_2026_09_14.json)

## 完整开发暴露的长请求问题与处理

原非流式开发 `p2_recent_baselines_tokenrhythm_v1` 中，ours 与 noG 完成 ID 101，
noGcompact 与 BM25 在长请求返回 HTTP 504 Gateway Time-out。已停止其他未完成作业，
保留全部记录。长成功调用也达到约 174 秒；SDK 自动重试可能包含在这一时长中，
不能解释为单次生成延迟。原短探针结论只适用于短请求。

该轮 58 条返回 usage 的响应，按缓存计价估算 ¥2.10263348；没有返回 usage 的失败、
重试与中断调用可能另外收费，这不是完整账单。见该目录的 `usage_integrity_audit.json`
与 `interruption.json`。旧规划表未包含这次新开发中断的额外重跑开销。

新增 `relay_chat_transport.py` 将流式 delta 汇总为原 SDK ChatCompletion 对象，
保留消息、工具参数、finish_reason、推理字段及最后 usage；缺失结束标志或 usage 时拒绝
输出部分计划。保持原模型、prompt、thinking 与 token cap，SDK 自动重试改为 0，
原一次格式/长度修复仍保留。10 项当前离线检查通过，真实两步工具回传通过
（另 2 次生成、输入 412 / 输出 48 tokens，独立记录）。

流式开发使用新 family `p2_recent_baselines_tokenrhythm_v2`，先检查此前失败的 noGcompact
以及三个 native memory arm。全套完成后再冻结评估，不能把 v1 的完成臂拼入 v2 排名。
流式只是针对网关超时的工程修复，尚不能宣称已解决所有长任务稳定性问题。

用户另授权的 [aiaaa 中转](aiaaa-relay-2026-09-14.md) 也已通过短请求/工具测试，
其单价未知；不同模型/路由单独记录。

流式 noGcompact 开发已完成 ID 101，7 轮 / 14 次 actor 调用，无 API 错误。
完整十臂仍需完成；这是新 transport 的开发验证，不是正式排名。

## 高调用量下的限流与服务繁忙

LightMem 流式 v2 在连续更新时遇到 429；单独的小探针随后恢复 200，响应给出
`cost_cny=0.00003000`（输入 7 / 输出 2），与本页单价计算一致。v3 的共享请求间隔
为 2.1 秒，并对 429 有限退避，但该轮后来遇到 503 `SERVICE_BUSY`。

当前 v4 还对流开始之前的 HTTP 500/502/503/504 做最多三次显式重试，退避
15/30/60 秒，逐次记录状态、耗时和等待。已经打开但中断的流仍判失败，避免把
部分响应当完成。无法恢复的 memory API 错误会阻止本实例继续发请求；上游即使
吞掉异常，完整性检查也拒绝将该 episode 当有效结果。

noGcompact、Mem0、A-Mem 的开发验证在 v2 完成；ours/noG/full/summary/BM25/dense 在 v3 完成；
LightMem 单独在 v4 复测。开发迭代修复的是 transport、
节流和错误记账，未改变 memory 算法、模型、prompt、decoder 或 token cap。
这些开发验证不会拼成方法排名。正式比较待全部接口通过后，以共同 v4 协议冻结。

Mem0 的默认推理会反复用满 32768 token，完整开发耗时约 29.7 分钟；小探针不能
代表它的任务耗时。当前原始预算表只用于初步规划，未涵盖新增中断/重跑，也低估了
这类长推理，需要用完整开发 usage 校准；约 300 元不是承诺或硬上限。

## v4 最后一轮超时与 v5 续跑

v4 LightMem 在 7/7 actor 轮完成后，最后一次 memory consolidation 遇到响应头之前的
`APITimeoutError`（60.33 秒）。17 次 actor 和 749 次 memory usage 均保留；最后 write 未完成，
因此开发完整性检查拒绝评分，正式评估未启动。v4 的协议匹配源码另存 `frozen_source/`，
[中断记录](../results/development/p2_recent_baselines_tokenrhythm_v4/interruption.json) 不回填。

v5 将 read timeout 改为 180 秒（connect 30 / write 60 / pool 60），并对响应开始前的
APIConnectionError / APITimeoutError 使用相同的最多三次 15/30/60 秒退避。每个失败 attempt
标记 `billing_unknown`，因为服务端可能已生成但未返回 usage；已经打开的中断流仍不重试。
新增离线检查覆盖超时恢复、重试耗尽、流内超时不重试和未知计费保留。真实 v5 最小探针成功，
6.15 秒、输入 37 / 输出 5，平台返回 `cost_cny=0.00011400`；这是兼容性探针，不是速度对照。

当前由 `code/arena_recent_pipeline.py` 单一进程负责 LightMem 开发复测、检查已有九个有效
开发接口、正式冻结、十臂评估、官方评分和离线交付。最新状态见
[v5 续跑状态](../results/development/p2_recent_baselines_tokenrhythm_v5/continuation_state.json)。
此前停止的 v4 控制器和 finalizer 不再重启。
