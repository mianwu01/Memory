# Yujia memory 项目：2026-09-15 进展

**实现修复已落地，完整验收和正式比较尚未完成。当前阻塞是中转账户余额不足。**
新批次 `faithful_memory_aiaaa_v2` 的 16 个开发门槛有 5 个通过，正式案例为 **0/100**。
原 supervisor 在失败时停止；最新状态已逐项核对日志计数，见
[机器可读快照](../results/development/faithful_memory_aiaaa_v2/readiness.json)。
开发小例不能当作 benchmark 分数，旧 v5 不能补进新主表。

## 已修复的实现与仍需验证的范围

| 方法 / 组件 | 当前实现 | 验证状态 |
|---|---|---|
| Mem0 OSS | 作者代码；补齐 fastembed、spaCy 和模型，实际执行关键词、语义和实体检索；top 200 | 离线机制及当前 online 小例通过；完整历史验证未完成 |
| A-Mem | 作者指定的论文仓库 robust agent；原 metadata、evolution、查询生成、关联检索；top 10，原生 1000-token 输出上限 | 离线关联扩展及当前 online 演化小例通过；完整历史验证未完成 |
| LightMem | 作者预压缩、主题分段、metadata、检索及原生 offline update；top 60；移除跨 manager 方法拼接 | 离线机制及当前 online 小例通过；完整历史验证未完成 |
| MemoryArena actor | 原 actor、提示、全部工具、完整计划、30 steps、32768-token 上限；移除本地继承 decoder | noGcompact、query_only 的完整开发 ID101 通过；其他八臂待完成 |
| 消融与常规 baseline | ours / noGcompact / query_only 共用可见 base、格式与引用解析；BM25/full 用作者类，dense/rolling summary 明确为本地方法 | 等待完整配对比较，不把十臂说成十个外部官方 baseline |

五个上游 checkout 的 commit 和 clean 状态均重新核对，详见快照。
这些是调用作者核心机制的任务接口；跨任务的输入转换、统一 DeepSeek backbone 和配置差异均披露，
不能称为作者论文成绩或托管服务成绩的复现。

当前模型是 aiaaa `deepseek-v4-flash-0731`。困难请求的配对探针发现仅发送
`thinking=disabled` 无法可靠关闭该中转的推理；memory 现加 `reasoning_effort=none`，
并在仍出现 reasoning tokens 时拒绝验收。原 actor 保持默认模式。
此前将 A-Mem 上限加到 16000 的尝试已撤销，只留作失败的开发记录。

## 实际中断位置

| 门槛 | 已完成 | 尚未完成 |
|---|---:|---|
| online 机制小例 | 3/3 | 无；不是任务 accuracy 评测 |
| Travel 开发 ID101 | 2/10 | ours、BM25、full、dense、summary、Mem0、A-Mem、LightMem |
| LoCoMo 完整历史 + 原生 QA | 0/3 | Mem0 写入 102/369；A-Mem 31/369；LightMem 写入 369/369 后在离线更新阶段中断；三套原生 QA 均未完成 |
| 正式比较 | 0/100 | 十臂 × IDs111–120；尚未冻结或启动 |

LoCoMo 使用事前按长度选择的完整 `conv-30`，19 sessions、369 turns；全量写入后检查各作者支持题型。
LightMem 写完历史不等于完整验收通过；不能跳过离线更新或 QA 把它记成完成。

两次最小生成诊断分别确认：

- [aiaaa](../results/development/faithful_memory_aiaaa_v2/access_diagnostic.json)：HTTP 403，`INSUFFICIENT_BALANCE`。
- [TokenRhythm](../results/development/faithful_memory_aiaaa_v2/backup_generation_access_diagnostic.json)：HTTP 402，`INSUFFICIENT_BALANCE`。其模型列表仍能返回 200，不能据此判断生成可用。

所有失败原件保留。调度器现在遇到任何案例失败就停止启动后续案例，允许在途任务结束并保留费用，
未启动案例明确记为缺失。相关调度及费用测试 **5 项通过**；不放松原机制和评分验收条件。

恢复需账户有余额后先确认生成可用，再事前登记这 11 个失败门槛的技术恢复目录与来源。
已完成的五个门槛只在来源和最终配置兼容时复用。失败期间存储可能部分更新，
不得直接把其中间 store 当作完成状态；技术重跑须保留原尝试、从干净状态执行，不按得分选择。
全部门槛通过后才允许 acceptance → freeze → 正式比较 → 官方评分 → 新对比 demo。

## 费用

| 范围 | 已记录人民币 |
|---|---:|
| 旧账单与此前用量基数 | 276.482109 |
| 本次完整实现修复、开发、失败及探针新增 | 44.03236976 |
| 累计 | **320.51447876** |

当前 v2 本身已记录 ¥5.5065834；其余新增费用来自前序修复和探针。
[完整账本](../results/development/faithful_remediation_usage.json) 优先使用已结算的 API `cost_cny`，
仅 TokenRhythm 缺该字段时使用其公开单价，包含失败响应费用。
仍有 28 条未取得用量的错误/探针记录、74 个计费不明的传输 attempt、45 个无可用定价的响应；
这些口径有重叠，不能相加当成额外调用数。被终止的在途请求还可能没有可用日志。
**这不是平台账单对账总额，也不是完成剩余实验的预算。**

## 可立即审阅的材料

- [中文段落 / 句子目标 outline](yujia-paper-outline-2026-09-04.md)，[可分享 PDF](../results/development/yujia_offline_update_2026_09_15/outline_zh.pdf)。
- [原 LaTeX 中的英文 outline](../yujia_outline_2026_09_04.tex)，[重新编译的完整稿](../results/development/yujia_offline_update_2026_09_15/causal_memory_formulation.pdf)。
- [Setting 与变量口径](yujia-setting-2026-09-04.md)：Travel 七类变量固定，实例记录数量可变；真实数据没有 oracle graph。
- [已有具体读取 / 风险示例](../results/real/yujia_meeting_2026_09_04/slides.html)：历史同输入的读取比较与真实 MINJA 风险轨迹；不能作为修复后的端到端方法成绩。

新的实际运行对比 demo 仍待完整正式结果；固定取 episode111 第二位后续 traveler，不按结果挑例。
现有 demo 生成器要求完整配对结果，不能用缺失或伪造输出绕过该要求。

Simulation 冻结。旧 v5 仅有输入压缩观察，不能主张费用优势；四任务 necessity **0/4**、
latent identification 不支持、两个在线缓解协议 **FAIL** 均保留。
风险例支持审查可见 memory 及 write→read→action 轨迹，不能证明读取隐藏意图或识破撒谎。

给 Yujia 的简短文字草稿（未发送）：

> Hi Yujia, I'm still completing the full-history validation for Mem0, the paper implementation of A-Mem, and LightMem, and rerunning the comparison with MemoryArena's original actor. The new results aren't ready yet. Could we do an offline update instead of the meeting? I've updated the paragraph-level outline and the setting, so you can review the overall structure while I finish the experiments.
