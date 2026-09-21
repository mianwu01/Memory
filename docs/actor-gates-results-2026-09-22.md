# 四个门槛的执行结果：Flash thinking

**Actor 的本轮开发数值门槛已通过；新原生研究对象尚未通过准入，因此没有
启动结构 discovery 或来源审计调用。Yujia 的完整研究要求仍未达到。**

本轮沿用长期主模型 `deepseek-v4-flash`，开启 thinking，未改用 Pro。
起始 647 个未提交文件全部保持原字节内容；不重跑既有 campaign，不覆盖旧结果。

## 第一关：固定开发集

测试前冻结合成 HM3 Travel seed 80 / dev 前 10 题，每题三次独立请求。
全部 full-read，v1/verbose，完整 S0，temperature 0，max_tokens 32768，
`thinking: {type: enabled}`。没有 format/semantic retry、没有筛换题目、
没有进行第二版 prompt 调参。10 题都需非空修复，历史长度 7–21 条。

| 指标 | 预定门槛 | 结果 |
|---|---:|---:|
| 正确请求 | 至少 27/30 | **29/30** |
| 每题三次全正确 | 至少 9/10 | **9/10** |
| 完成请求 | 30/30 | 30/30 |
| 有 thinking 证据 | 30/30 | 30/30 |
| 截断 | 0 | 0 |
| 基础设施失败/在途 | 0 | 0/0 |

**模型 ID 修正必须与通过结论一并阅读。** 供应商返回大写形式
`DeepSeek-V4-Flash-0731` 20 次、小写形式 `deepseek-v4-flash-0731` 10 次。
原程序按原始字符串判断两个版本，原始 report.json 因而保留 `passed=false`。
离线验收只做大小写归一后通过，保留原始 ID 与严格失败状态。
这是结果产生后的元数据定义修正，不是预注册部分；没有改版本后缀、prompt、
评分或重发请求。见[完整修正说明](actor-gate-model-id-amendment-2026-09-22.md)。

唯一失败为 `travel-s80-dev-005` 的第 2 次请求（repeat=1）：选对对象，
但错误地把接送时间视为整点后固定时刻，输出 checkin=840；正确值为 855。
它混用了初始状态、直接修改 transfer 的干预，以及 flight 变化后的响应证据。
同题另两次正确。失败完整保留，未通过追加重试改成正确。

此结果仅资格化**短历史合成开发集**上的 actor。不能据此宣布长历史、
新原生任务或所有输入子集都稳定，也不能与此前不同模型/任务的非 thinking
结果相减来声称 thinking 的净因果提升。新任务仍需要任务自己的开发资格化。

## 第二关：具体任务审查

完整的源码、版本、时间步和数据核对见
[原生任务审查](native-task-screen-2026-09-22.md)。

- **Bundled Shopping**：150 个原生任务，每个 6 个 session；900 个 query
  中 750 个直接给出兼容规则。已区分原生 memory store 与商品环境数据库，
  核对实际写入/读取接口和确定性 ASIN checker；发现 query history、续跑
  回填及空 state fallback 三条潜在答案信息路径。它可研究记忆使用，但当前
  不足以支持“发现未知原记忆时序结构”的主张。
- **Progressive Search，优先继续审查的具体候选**：221 个原生任务，
  每个 4–16 个 session。已定位原生答案/工具证据写入和下轮读取路径。
  203/221 个任务的最终参考答案在前置参考答案中重复；必须包含简单答案复用
  对照。已将 221/221 个最终问题精确映射到官方 BrowseComp 原始答案来源，
  补上独立参考来源。别名/checker 规则尚须冻结；文本匹配不是来源正确性审计。

两者均未通过第二关：没有足够且已观测、定义稳定的 memory-state 转移面板，
不能把任务定义数量当轨迹样本数，也不能将不同任务直接拼接成平稳时序。
Search 的原生 corpus 工具可作为后续授权替代来源的实现基础，但本轮未安装
或执行该替代工具，没有安全闭环结果。

不默认把主线改为 read-gate。主目标仍是原轨迹内 observable memory state
和 write dynamics；read-gate 可作为独立依赖验证/审计工具。若没有适合的
原生表示，先停在研究对象与方法设计阶段，不以逐题 128 次调用绕过问题。

## 第三、四关：停止于前置门槛

本轮 **0 次 discovery、0 次来源审计、0 次 native agent 任务调用**。
研究对象未通过准入，因而不产生新的 discovered/complete 效果表，也不挑选
已经正确的少数回答补成审计演示。下一阶段需要落实的是：

1. 在优先候选上定义低维、含义稳定、确属 agent memory 的可观测变量，
   采集实际 write/hold/read 快照，核对有效转移与 regime；样本不够则换对象，
   不能用模拟加长或跨身份拼接补足。
2. 冻结独立答案 checker、原生工具和同任务 actor 开发门槛，保留简单历史
   答案复用、完整结构、错结构和同预算检索对照，再决定是否值得 discovery。
3. 只有前述条件通过，才在同一方法上验证结构增量、训练成本摊销与来源阻断/
   决策相关替换/中性干预/真实授权替代；全部案例报告。

这些是未完成工作，不是已取得的研究贡献，也不代表 Yujia 已认可对象变更。

## 成本与验证

仅 30 个新模型响应：188,178 input tokens、604,164 output tokens，其中
595,476 为供应商记录的 reasoning tokens。缓存输入 86,272 tokens。
按旧费率情景折算 $6.317973，**不是当前 Flash 确认价格或实际账单**。
无失败/在途调用，无语义重试，无第二版开发实验。公共数据下载未调用 LLM。

30/30 响应已离线重评分，结果一致；门槛、稳定性、缺失、截断与模型 ID
修正的测试通过。此前 15 项相关测试通过；修正后 6 项 actor gate 测试通过
（含 2 项新增回归）。所有请求、完整序列化输入、原始响应、模型 ID、usage、
失败诊断、源文件 hash 和冻结源码均保留。

- [机器验收表](../results/development/hm3/actor_gate_summary/report.md)
- [完整数值与修正状态](../results/development/hm3/actor_gate_summary/report.json)
- [冻结协议](actor-gates-protocol-2026-09-22.md)
- [文件保留核验](../results/development/hm3/actor_gate_summary/preservation_check.json)

只读重评分/报告重建（不调用模型）：

```bash
PYTHONPATH=code python3 -B -m hm3.actor_gate_report \
  results/development/hm3/actor_gate_flash_thinking_v1
PYTHONPATH=code python3 -B -m hm3.native_search_screen
```
