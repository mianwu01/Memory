# Memory baseline 修复与重新验收（进行中）

> **最新状态：v2 因 API 余额不足停止，正式 0/100。** 5/16 个开发门槛已通过；
> aiaaa 403、TokenRhythm 402 均明确返回 `INSUFFICIENT_BALANCE`。完整验收尚未通过。
> 当前恢复前提与可审阅 outline 见 [9/15 进展](yujia-progress-2026-09-15.md)。下文保留各阶段过程。

用户于 2026-09-15 授权全部解决不完整实现、强行适配与实验有效性问题，并重新运行有效比较。
旧 v5 仅保留为历史探索性结果，不进入修复后的主表；原始失败、费用、代码和结果不覆盖。

## 必须通过的验收

1. Mem0：使用固定官方 OSS 实现，启用该版本的关键词、语义与实体检索路径；缺失依赖或静默降级直接失败。
2. A-Mem：使用作者指定 `WujiangXu/AgenticMemory` 论文仓库的正式入口；真实调用生成 metadata、演化、links 与关联检索。
3. LightMem：启用官方预压缩、主题分段、metadata/summary、检索和离线更新；使用上游支持的 OpenAI-compatible manager，去掉跨 manager 方法拼接。
4. 官方任务：保留 MemoryArena 原 actor 提示、工具与完整计划输出；去掉本地继承 decoder 和 query 工具过滤。
5. 机制验证：开发例必须核对写入内容、演化状态和实际检索；不接受仅实例化或接口返回成功。
6. 预算/完整性：memory 输出截断、解析降级、检索功能缺失必须记录并拒绝当作方法验收通过；原版 actor 达到其原生 token 上限属于模型作答失败，原样传回原 actor 并评分，不修复答案、不删除难例。此区分在正式评估前登记；评估期间不挑分、不修改方法。
7. 研究表述：执行完成与研究结论分别判定；必要性、安全缓解、跨任务效果只能依据实验支持，不能把负结果修成正结果。

## 执行顺序

- 独立环境与上游复现路径检查，冻结版本与依赖。
- 全功能离线机制测试、真实 API 开发验证与预算校准。
- 预先登记新评估范围、actor 配置、检索参数与技术失败规则，再运行所有方法。
- 用官方 evaluator 评分，更新主表、demo、outline 和交付状态；旧表明确标为已替代。

另需使用作者原始 memory 任务检查复现路径，避免仅在 Travel 特化设置中验证。
选择与范围在开发验证后、正式打分前登记。不会用新的手工检索器冒充作者方法。

## 2026-09-15 修复进展

独立 CPU 环境 `.tmp/memory-faithful-venv` 已建立；旧 v5 环境、冻结生成代码和结果保留。
三种作者方法的真实 API 小例与离线机制验证均已通过。文件位于
`results/development/faithful_memory_v1/validation`，有效版本分别为：

- Mem0：`mem0_offline_2` / `mem0_online`。安装 fastembed、spaCy 和英文模型，观察实际 sparse、dense、entity boost 路径。
- A-Mem：`amem_offline` / `amem_online_2`。使用论文仓库推荐的 robust agent；保留查询生成、metadata、evolution、links 和关联检索。
- LightMem：`lightmem_offline_2` / `lightmem_online`。真实预压缩/分段、metadata 与原生 offline update 均执行。压缩器因本地别名不含其硬编码 BERT 家族名曾静默失败，已修正缓存路径名称，未修改压缩算法；首个假阳性测试另有 `review.json` 撤销验收。

原版 MemoryArena actor 开发：`faithful_memory_v2/travel`，失败的 ours 保留；
`faithful_memory_v3/travel/ours_101` 验证原生 actor 长度上限的保留策略。
其他运行若未出现长度上限，其输出不受这个校验策略变化影响。
开发补充在 `faithful_memory_v2/actor_failure_policy_amendment.json`；不拼接成开发排名。

模型调用保留原 actor 提示、全部工具、30 steps 和 32,768 token 上限，完整生成计划。
仅恢复 DeepSeek 工具回传要求的**实际已观察** `reasoning_content` 字段，不生成/修改该字段。
Ours/noGcompact/query_only 使用同一可见公共 base 与序列化；query_only 去掉学得的类型边，保留引用解析，进一步分离图与解析器。
Dense 和滚动摘要明确标为本地常规 baseline，不能称作者论文实现。

## 作者任务路径与适用边界

已启动 `code/faithful_locomo_validate.py`：选择 LoCoMo 中完整发言数最少的
`conv-30`（原索引 1，19 sessions、369 条发言），不裁剪历史。
全量写入后，用每个作者支持题型的首题作接口检查；不按答案挑题，不作为 accuracy 主表。
各方法的输入转换、检索与 QA prompts 来自其作者代码，保留差异。
每个运行启动前写 `protocol.json`；产物 `results/development/faithful_memory_native_v1`。

Mem0 官方 `memory-benchmarks` 支持 OSS 与 Cloud，但其 OSS server 仍用旧参数名，
当前 v2 SDK 要求 `top_k` / `filters`。接口检查仅映射参数名，使用真实 OSS 核心。
官方 server 当前没有把 observation timestamp 传给 SDK，本检查保留该行为并记录来源日期；
不声称复现托管产品分数，也不偷偷添加记忆内容补偿。

LightMem 原 LoCoMo ingestion 结束才 offline update；Travel 为每个已完成 session 后的空闲时段更新。
Travel 用核心 API 原生检索默认 10；LoCoMo 用作者任务脚本 combined top 60。
这是任务协议差异，不能把 Travel 适配称为 LoCoMo 论文分数复现。
LoCoMo 的可选 StructMem 扩展不是 LightMem 核心，不混入本 baseline。

## 来源与版本

| 源码 | 固定 commit |
|---|---|
| MemoryArena | `6cd9de14b71915e39ac742a20dc33785e14b6aab` |
| Mem0 OSS | `c7ee362aff94a369af70f13f2b4f853f6793ff4c` |
| Mem0 memory-benchmarks | `4b61c5d31b9c668a12b4f5e78064248a02c82d2b` |
| AgenticMemory 论文仓库 | `0c8039f28fdcc08189a23c07a3437d9d2482f9c2` |
| LightMem | `8449d574df6bae1bdf3314a1564da65e2f37e046` |

正式评估拟覆盖 10 arms × 原 graph holdout IDs 111–120，共 100 个独立 arm/episode。
该范围仍是复用的历史 holdout，不宣称全新确认性测试。**本节更新时尚未冻结或启动正式评估。**
评分收集器 `code/faithful_report.py` 要求所有 episode/person、生成哈希与原 actor 合同完整；
官方 evaluator 只遍历提交者，所以额外检查缺失 person，防止分母缩小。

费用通过 `code/faithful_report.py` 汇总全部新 `events.jsonl`（包括失败尝试）；
`results/development/faithful_remediation_usage.json` 是可刷新的账本。
旧累计 ¥276.482109 与本次新增费用分列；未记录用量与未知中转单价不伪装成已对账金额。


## 中转与原生输出预算补充（正式评估前）

TokenRhythm 已在开发中返回 402 `INSUFFICIENT_BALANCE`，导致 dense/Mem0/LightMem Travel
和三套 native LoCoMo 检查中断，原失败保留。使用用户已授权的 aiaaa 备用接口，
新 family 为 `faithful_memory_aiaaa_v1`，模型 `deepseek-v4-flash-0731`。
默认本地凭据文件现指向此路由；原 TokenRhythm 配置保留在 ignored 0600 备份。
不把两个中转的部分结果拼表。

备用接口三套 online 机制测试均通过。API 返回 `cost_cny` 且 `billing_pending=false`
时记录该值；未知价格的调用不套用 TokenRhythm 单价。这仍不等于平台账单对账。

完整 LoCoMo 检查进一步发现：A-Mem 原 `RobustOpenAIController` 硬编码输出上限 1000；
备用中转有少数请求虽然收到 `thinking=disabled`，usage 仍含 reasoning tokens。
在 conv-30 第 18 条发言的一次演化调用中，1000 tokens 全部用于推理且无正文，触发验收失败。
保留 `native/amem` 的失败；**仅把 A-Mem 输出预算配置为 16000**（与 Mem0/LightMem 相同），
保留作者 prompt、解析器、演化与检索流程。新的验收为 `validation/amem_online_budget16k`
及 `native_amem_budget16k`。不能再写成“作者所有默认配置完全不变”。
具体预算登记和变更前后代码哈希见 `amem_budget_amendment.json`。

其余九臂的行为分支不受该参数修改影响。开发验收允许该记录明确列出的旧哈希分支，
不重跑已经完成的无关验证；正式所有臂采用同一最终冻结代码。
新测试验证 actor 上限和其他方法调用参数均不受此变更影响。
正式 worker 固定每进程 2 个 CPU 线程，避免继承 shell 的 72 线程而过度竞争；
先前开发时延不与正式时延混用。

自动推进工具 `code/faithful_campaign.py` 必须等 10 个 Travel 开发、3 个 online 机制、
3 个完整 native 检查全部通过后，生成验收 manifest、冻结、运行 100 cases 并用官方 evaluator 收集。
第一次 supervisor 因 A-Mem 原生预算失败停止；预算修复后的状态为
`results/development/faithful_memory_aiaaa_v1/campaign_budget16k_state.json`。


A-Mem 16k online 小例的复核：原测试要求必须新建 link，这错误地排除了作者合法的
`UPDATE_NEIGHBOR` 分支。实际保存的响应两次更新了旧日期/审批状态，`evo_cnt=2`，
检索含全部所查事实，无截断或 API 错误。复核以 `review.json` 记录，原 `passed=false`
文件保留；没有重新抽样直到出现期望的分支。链接扩展仍由独立原生离线测试验证。
当前 supervisor 为 `campaign_reviewed_state.json`。

`embedding_provenance.json` 核实作者规范模型名缓存与本地 MiniLM：两条检查文本的
embedding 差异为 0，窗口均为 256，作者缓存 commit 为
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`。正式冻结同时记录两处模型文件哈希，
worker 从缓存加载 HF 模型/数据，避免运行中自动换版本。


## 已定位中转参数问题：当前 v2（优先于上方过程记录）

同一个 LightMem 失败请求的配对模式探针：`thinking=disabled` 两次均仅推理无正文；
附加 `enable_thinking=false` 或 `reasoning_effort=minimal` 仍如此。
**`reasoning_effort=none` 两次均输出正文、无报告的 reasoning tokens**。
`deepseek-v4.1-flash` 的两次探针则超时，没有切换到它。
原始记录：`results/development/faithful_memory_protocol_probe_2026_09_15.json`。

因此停止尚在运行的 aiaaa v1 开发配置，完整保留 `protocol_superseded.json` 与全部费用。
**恢复 A-Mem 作者原生 1000 上限**；先前 16000 调整仅属失败的开发校准，不进入新正式配置。
Memory API 现通过适配此中转的标准 `reasoning_effort=none` 确实关闭推理；
若仍出现 memory reasoning tokens，运行直接失败。Actor 保持原版默认设置。

当前唯一推进中的 family 为 **`faithful_memory_aiaaa_v2`**。
10 臂开发与 3 套完整 native 验证全部按正确模式重新运行，不拼接 v1 数据。
状态入口 `results/development/faithful_memory_aiaaa_v2/campaign_state.json`。
该 supervisor 自动验收 → 冻结 → 正式 100 cases → 评分；任一失败停止，不能按分数挑结果。
脚本只对明确 `upstream_stream_read_error` 做至多两次相同请求重试；保留未知费用，
不对 native 长度耗尽、解析问题或低分重试。旧 frozen relay 模块未改。


正式检索参数在打分前改为作者任务评测的推荐规模：Mem0 top 200、LightMem top 60、
A-Mem top 10，避免把 library 默认 20/10 的容量限制当作图的优势。
`retrieval_config_amendment.json` 记录依据及哈希。此时 Mem0/LightMem 的 Travel 开发尚未启动；
LoCoMo native 检查原本已显式使用 200/60，因此实际 native 检索配置不变。
其他八臂的 generation 分支未变，验收记录明确限定其源码兼容范围。


## v2 余额中断与未完成门槛

当前三个 online 机制小例、noGcompact/query_only 的完整开发 ID101 已通过，共 5/16。
其余八个 Travel 开发和三套 native 检查因 aiaaa 账户余额不足中断。Mem0/A-Mem 已写入 102/31
条发言；LightMem 写完 369 条后在原生 offline update 中断；三套 QA 均未完成。
`readiness.json` 是事件计数核对后的快照，旧 `campaign_state.json` 保留其当时的失败决定，不覆盖。

最小诊断确认 aiaaa 生成 403、TokenRhythm 生成 402，均为 `INSUFFICIENT_BALANCE`。
模型列表成功不能证明有生成额度。没有切换模型、缩短完整历史或降低验收门槛。
`faithful_suite.py` 增加失败即停止启动后续案例的调度，已经在途的任务允许结束；
未启动 scope 明确记录。五项调度/费用相关测试通过；没有改变任何 memory/actor 生成逻辑。

费用账本更新为新增 ¥44.03236976、累计 ¥320.51447876，未对账的调用另列。
恢复需可用额度、明确登记的新输出与来源，再完成全部门槛；正式冻结、100 cases、评分及新 demo 仍待执行。
