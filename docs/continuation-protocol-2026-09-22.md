# 9/22 继续执行：研究对象与可证伪验收

本页在新 actor 实验前写定；不覆盖 9/21 结果，不代表 Yujia 已同意更换主线。

## 两个不同对象

1. **原轨迹 memory state**：固定 episode 中对象字段的 write/hold 值；时间是
   原始记录或完整 intervention segment，样本是该 episode 内的转移。
   不把跨 episode 的不同对象 ID、不同隐藏规则直接拼为同一平稳序列。
   首先输出可观测字段面板和有效变化数，检查样本量、外生写入与记录序列化顺序。
   HM3 的 state 是模拟环境状态，不自动等同于 LLM 内部记忆。
2. **候选 policy read dependence**：固定 actor、任务和可见 state，以完整历史
   segment 为记忆单元，独立随机化可见性，观测真实 LLM 的任务正确性。
   样本是独立请求；lag 1 仅编码一次调用的输入到结果，绝非原写入时序。
   此候选继续做方法可行性检验，不能替代第 1 项或声称已获导师认可。

现有原生 MemoryArena Travel 的 query 点名/已物化结论已经关闭，不重跑。
HM3 明确标为合成事务任务上的真实 LLM actor；它不填补原生真实任务外部效度。

## 冻结的候选检验

- 模型 `DeepSeek-V4-Pro`，同一 endpoint；v1/verbose；temperature=0；
  max_tokens=16384；thinking disabled、reasoning_effort none。记录返回 ID、
  完整输入、输出、usage、截断、基础设施失败和供应商返回的费用字段。
  单次请求，不做语义或格式重试；基础设施失败不作为 actor 错误训练。
- 开发只用 Travel seed 2 / dev 第 0 个，检查传输和解析，不按成功率换模型。
  测试预定 seeds 70/71/72，每 seed 前两个 episode，native history。
  所有测试均保留，不按 full 成败筛选，不替换案例。
- 每 episode 128 次 Bernoulli(.8) **segment** gate 调用，固定 RNG。
  同输入的多次采样是 actor 随机性观察，不缓存成重复独立结果。
- 标准 Tigramite PCMCI+ / G²，alpha=.05，lag 1。已知独立随机化约束只允许
  gate→outcome 候选边；这是已知实验设计约束，不是发现了完整原轨迹图。
  主选读是 MCI p 值升序、统计量降序、segment 顺序打破 ties 的 top-2 segments。
  阈值 parents 另报；top-2 不称已识别 causal parents。训练使用 benchmark
  correctness oracle，全部调用成本计入，不称无标签部署或跨任务摊销。
- 独立三次验证：learned top-2、complete/full、query-only、no-discovery
  recency 与 BM25（记录数匹配）、三份固定错误图（17/29/43 置换），
  三份记录数及 cl100k_base 代理 token 匹配随机集合。统一完整可见 S0、
  prompt 和输出规则。全部保存序列化 hash、集合重合与 token 残差。
- 结构独立贡献必须超过 no-discovery / 简单检索和错误图，而非只超过 random；
  重复先按 episode 平均，6 个 episode 是统计单元。报告配对 bootstrap 区间，
  不把调用数当样本量；样本太小的结果只作诊断。

## 同一结构的正确输出来源审计

测试前外部赋予**第一个历史 segment** `disallowed_external_cache` 来源标签，
其余为 `authorized_event_log`。标签用于受控场景，不从模型输出或图推断。
actor 正常任务输入不含审计规则。该来源设定是人工的，不能冒充真实违规事件。

每个冻结测试 episode 独立三次检查 full、阻断该来源、删除最后一个不同来源
segment 的中性对照，以及把可疑来源的时间值增加 15 分钟的内容干预。
同时检查该 segment 是否进入同一 read-dependence 图/排名。只在 full 稳定正确
且目标干预明显改变结果、中性干预保持时称该案例支持来源依赖；每例全报。
三次重复仅是稳定性诊断，不能证明统计显著或普遍安全。

安全处置为阻断来源并仅使用已有授权日志；没有足够授权证据则明确 abstain，
不捏造“安全替代答案”。本 benchmark 没有独立授权检索工具，故不能凭同内容
换标签宣称验证了安全替代服务。后续若有真实工具，另定协议，不回填成功。

## 代表性 memory systems

独立隔离 store，核查官方 Mem0、A-Mem、LightMem 的版本与实际执行路径。
保持同一 actor、S0、问题、输出规则和测试 episodes；写入仅含历史、无 gold。
若使用记录 ID 回映射，明确是 selector adaptation；保留原生返回文本的路径
才叫 native memory output。系统原生预算与严格匹配对照分列，不能混作等预算。
写入/演化/压缩/检索调用计入成本；原生错误或 fallback 必须显式报告。

## 停止与验收

基础设施或格式不兼容先记录，修复接口后使用新版本目录；不在测试结果上调参。
不触碰 GPU、不删除/重置/提交任何旧工作。已有未提交文件的启动 hash 存于
`/tmp/hm3-session-20260922-start.json`。新实验目录与旧结果隔离。

完成运行 ≠ 正结果 ≠ 满足贡献。最终逐项表分别列执行状态、证据与未满足项；
尤其保留原轨迹结构、真实 benchmark、跨 episode 摊销及安全替代的缺口。
