# 面向 Yujia 9/04 要求的下一轮实验方案

日期：2026-09-18。状态：实验决策建议，不是已冻结协议或已取得结果；本次未启动新的 LLM 调用。新版 Travel 的具体数据/代码版本仍需与用户所指版本对齐。

## 1. 三个问题决定实验是否值得跑

1. **实际效用**：在同一个 LLM actor 下，结构化选择能否改善任务表现与读取开销的取舍？需要近期 memory 方法对照。
2. **结构的增量作用**：收益能否超出紧凑序列化、query/历史引用解析和简单统计？需要同表示、同信息、同预算的消融。
3. **来源审计**：不输入投毒标签时，结构能否更准确地定位可疑记忆；这些记录在后续动作中是否具有可检验的作用？需要无标签定位对照和真实分支干预。

Yujia 的要求是用真实对比支持结构的价值，不要求证明因果图对所有可能算法不可替代。与强手写程序持平可以限定贡献为自动估计或效率；不能把这种结果自动判成整个项目失败。

依据：[9/04 纪要](meeting-minutes-2026-09-04.md)、[8/21 纪要](meeting-minutes-2026-08-21.md)。simulation 不再扩展。

## 2. 当前实现与新实验必须区分

- `faithful_memory.py` 已有 10 个方法臂和原版 actor 接口。9/17 保存的 `acceptance.json` 为 accepted，native LoCoMo 检查单独 deferred；这是机制/接口验收，不是论文分数复现或主实验成功。9/15 的“正式 0/100、尚未启动”文档已经落后于这些产物。
- 当前 `faithful_suite.py` 将正式 IDs 固定为 111–120，图路径仍指向旧 compact-v3 图。扩大 test 集必须同步重新划分训练数据并重拟合图，不能只增加 actor 任务数。
- 用户确认已有新版 Travel。当前 checkout 能核实 Travel-R 和 Dynamic Travel 等版本；它们与旧正式十臂配置不自动等价。
- `minja_online_gate.py::learn_driver_scores` 是无标签异常检索频率打分。后续若要证明学得的结构有增量作用，应保留它作为强对照，而非将它直接改名为图方法。
- 现有代码支持 `--native-gates deferred`。完整 LoCoMo 检查可作为补充单独完成，不能把尚未取得的论文复现成绩写出来，也不必让它成为本轮 Travel 比较的统一前置条件。

以上实现路径为现有资源；下述 history lookup、pooled/wrong-graph 臂、新 test split 和 MINJA 图审计器仍须逐项实现或对齐，不能直接套用旧 runner 声称已可执行。

## 3. 第一优先级：新版 Travel 的机制对照

### 信息条件

主任务保留 actor 的正常任务请求，把所需历史依赖从当前 query 中移走；历史中必须保留解决任务所需的信息。明确这是“移除依赖线索”，还是“selector 不读取 query”，以及发现矩阵是否仍由 query 构造。三者分别记录。

在同一批基础 episodes 上建立两个配对条件：

- **explicit**：当前 query 显式提供历史依赖线索。
- **implicit**：当前 query 只给目标，不显式提供这些依赖。

为隔离 query 线索，两个条件使用同一历史，其中都包含必要的历史 note；explicit 额外给出当前线索。若已有新版同时改变了历史内容或任务目标，保留其正式任务，但另建配对诊断，不能把多项变化都归因于 query 去线索。

派生自同一基础 episode 的 explicit/implicit、表面改写及模型重复全部处于同一 split。图学习、抽取器和超参数只用 train/dev。若原基准全部内容曾被用于解析器开发，披露这个边界；换 ID 或改写措辞不能使其变为全新未见数据。

### 核心六臂

| 方法臂 | 具体操作 | 回答的问题 |
|---|---|---|
| learned structure | 使用实际部署的学得依赖和 provenance 选择记忆 | 主方法 |
| noGcompact | 同表示、同 base、同 actor，保留全部历史单元 | 是否有读取/计算效率收益 |
| no learned edges | 移除学得的边，保留其他抽取和引用解析 | 学得的边是否有增量作用；旧 query_only 可作为起点 |
| history structured lookup | 在同一历史上解析 note、引用、时间/覆盖关系并直接索引 | 去掉当前 query 线索后，是否只是把 lookup 捷径搬到历史 |
| pooled estimator | 同样变量、训练轨迹和候选边，去掉 regime 条件化 | regime 是否实际有用 |
| wrong graph | 扰乱边的对应关系并保持合理 lag/边数，控制选中量 | 是否只要任意裁剪/稀疏结构都有效 |

`wrong graph` 至少用三份固定扰乱图，不能只挑一份特别差的图。与错误图和 lookup 的主比较匹配可供选择的历史、序列化和读取预算；full/noGcompact 自然使用更多内容，作为另一成本点而非等预算对照。若 rewiring 改变了选中量，补充匹配输出 token/cell 数的比较，避免把 mask 大小当拓扑收益。

开始正式 actor 调用前，对全部选定 episodes 做零 API 输入检查：implicit query 是否仍直接暴露来源；历史能否提供答案所需事实；最简单的历史解析能取回哪些依赖。这里检查的是任务信息条件，不要求预先证明 learned 必胜。

### 样本与执行

- 建议首轮 **50 个独立 test episodes × 2 个 query 条件 × 3 次模型调用重复**，六臂共 1,800 个 actor episodes。三次 API realization 不替代 50 个独立 episodes。
- 使用独立 dev episodes 完成接口和预算校准后，一次冻结完整矩阵；不能每看几例分数就改方法。
- 50 是建议的首轮规模，不是检测 1.5 个百分点差异的统计保证。正式冻结前用 dev 的 episode 方差和最小有意义效应规划 N；如需调整，应在查看新 test 结果前完成。
- 主报告先固定一个开发阶段选定的记忆预算。预算曲线只对核心方法另做两个预算点，不把所有维度与所有 native 方法全笛卡尔展开。
- 主结果是 actor 实际完整输出经 evaluator 评分；若新版改变了答案语义，需先验证对应 evaluator，不能机械沿用旧 gold。

### 指标

官方适用的 PS 为主要任务指标，SPS/SR 辅助。分别记录 memory context tokens、全部 actor input/output tokens、memory 写入/更新开销、图拟合/抽取成本与摊销次数。真实 monetary cost 与 token 减少分开。按独立 episode 聚合调用重复，再给配对差与区间。

另在固定共同历史上报告 selected records、必要信息 recall 与 serialization 开销，定位机制；正式 closed-loop 各臂则使用自己的 actor 写回。共同历史机制诊断与 closed-loop 总效果分别解释，不将两者混为同输入因果消融。

## 4. 并行补齐：近期 memory 方法主表

在上述 **implicit 主任务的同一 50 episodes × 3 repeats** 上运行：

- Full history；
- BM25；
- rolling summary；
- Mem0 OSS；
- A-Mem 论文实现；
- LightMem。

与 learned arm 合成主表。learned arm 已在核心矩阵中执行，复用同一原始结果，不重复抽一次取较好的结果。上述六个外部/通用方法增加 900 个 actor episodes；与核心矩阵合计 2,700 个 actor episodes。Dense 可保留现有小表或作为次要对照，不是必须再扩展的研究问题。

这张表回答系统效用。三套 native 方法使用验证过的完整机制和在 dev 上确定的合理配置，允许方法自身的额外写入调用并计入成本；不能靠刻意缩小它们的检索量取得优势。核心消融用于说明图的来源，native 对比不能代替图消融。

旧十臂配对复验有独立价值，可完成后单列；不让新旧 actor、任务、图版本和 query 条件拼成一个主表。

## 5. 第二优先级：MINJA 的无标签结构定位与干预

### 定位实验

使用相同 calibration 轨迹、record IDs、检索事件、可见 context/trigger 和机械异常信号；不读取 poison membership、poison source 或后续 test outcome。无投毒标签不意味着没有异常信号。

至少比较以下四种方法：

1. 现有 `learn_driver_scores` 异常检索频率法。
2. 与图方法相同变量和模型容量的 pooled 估计器。
3. regime-conditioned 结构估计 + write/retrieval provenance 的 record 排序。
4. 内容或检索相似度的 record 排序基线；允许获得同等 calibration 信息。

图审计器需从可观测 record/cluster 检索通道构造变量。若按 cluster 估计后再扩展 record，单列扩展前后结果。record 稀疏出现时，报告有效 exposure 数、无法估计的比例以及 co-retrieval 共线性；不借 poison 标签合并变量或筛选候选。

不重用 MINJA tagged 实验的 3/3 作为上述方法的成功率。主要指标为 PR 曲线/AUPRC、固定检查数量下的 precision/recall；同时给所有投毒记录与实际暴露候选记录两个明确的 recall 分母。定位、边恢复、在线删除是不同指标。

### 在线分支干预

先用 calibration 冻结排序器、阈值和 implicated IDs，然后在独立 test queries 上从同一 memory snapshot 分支调用。不能观察一次 test attack 后重新打分，再把对同一 query 的删除称作前瞻防御。

六臂：

| 干预 | 用途 |
|---|---|
| 不删除 | 同期基线 |
| 结构方法删除 | 主干预 |
| 现有频率法删除 | 检验结构的额外收益 |
| 内容/相似度方法删除 | 对照常见筛选信号 |
| 随机匹配删除 | 按删除数量并尽量按 token 量匹配，检验一般上下文扰动 |
| oracle poison 删除 | 仅 evaluator 上界，检验可移除记忆是否仍控制当前攻击 |

matched random 优先从当前候选检索集合抽取，防止“删除根本不会被读到的记录”造成无效对照。保留无删除但重复生成的样本，量化 LLM 随机变化。

建议首轮 **10 个独立攻击/写入 runs × 40 个 test queries（20 trigger、20 benign）× 3 次调用重复 × 6 干预臂 = 7,200 次 actor 调用**，另计 calibration 调用。run 应包含独立写入 realization 和预先安排的模板/问题差异，不能只是同一快照的十次重采样。请求顺序按固定规则交错；统计以攻击 run 为 cluster。

一起报告 triggered ASR、benign task accuracy、误删、删除量与预算。只有 relative-to-controls 的攻击下降且正常任务效用满足事前标准，才把结论扩大为 mitigation。若 oracle 删除也不能阻止攻击，应检查当前 prompt、scratchpad 或其他状态中的残留，而非盲目扩大 graph 参数搜索。

### 正常行为下的潜伏风险

预先选定一段时间截面，只用截至该时刻已观察到的信息给记录排序。若当前答案正常，保存当时的风险记录与分数，再观察后续独立 probe 的触发。记录命中与误报，而非只展示事后挑出的成功例子。后续才发现的证据只能用于 retrospective auditing，不能写成提前检测。

## 6. 结果如何决定论文主张

| 新结果 | 可保留的中心主张 | 后续动作 |
|---|---|---|
| learned 在 implicit 条件胜 history lookup / no-edges，且 task–cost 取舍优于 full | 估计依赖对选择有增量价值 | 放入摘要，给机制例子 |
| learned 与 lookup 正确率持平，但读得更少或所需人工规则更少 | 效率或自动化价值；需实际测量对应收益 | 收窄主张，不将持平写成因果图不可替代 |
| learned 与 no-edges / wrong-graph 都接近，增益主要来自格式 | 当前图增益未证实 | 在 dev 诊断图/selector 是否真的被使用；不靠增加 seeds 寻找显著性 |
| implicit 下所有方法相近且都接近满分 | 当前任务对该比较区分力有限 | 报告结果；长历史/覆盖冲突仅作为事前有动机的新条件，不能修改同一个 test 直到获胜 |
| 无标签图审计优于频率法，但删除无稳定净收益 | 来源定位贡献 | 保留 provenance 主张，完整报告干预限制 |
| 图方法与频率法持平 | 无标签关联定位成立，图的额外贡献未证实 | 统一框架可保留，不能说同一学得图解释了全部收益 |
| matched removal 对照下攻击下降且正常任务表现保持 | 可操作的记忆干预 | 才将摘要扩展到 mitigation |

实用效应门槛、非劣 margin 和主要 comparisons 在冻结前确定，不沿用旧实验中偶然出现的 1.5 点或 40% 作为新验收阈值。不为了一个 noisy PASS 反复复用 test。

## 7. 运行顺序与完成标准

1. 固定新版 Travel 的语义、数据版本、变量/样本定义与 split；让一个具体 episode 走通提取、图、选择、actor、评分，确认方法真正消费了所声称的结构。
2. 在 dev 完成所需对照和接口校准，保存具体 read/write/provenance trace。API 并发按生成探针的稳定吞吐设置，隔离每个 memory store；调度顺序按 episode/arm 交错。
3. 冻结 Travel 核心矩阵与主表、MINJA calibration/test 和干预矩阵后，可并行提交独立案例。日志同一份生成同时服务任务评分、成本和 demo，不再为每个报告另跑一次。
4. 技术失败按事前规则恢复且保留原件；空答案、长度耗尽等按任务合同报告，不能当作“传输失败”反复抽取。少数 baseline 的失败不静默缩小共同样本。
5. 输出两张主表、一张机制消融图、两个具体 demo（Travel 的保留/舍弃与结果；MINJA 的写入/检索/动作与分支干预），同时更新 P/S outline 和 abstract 的结果槽。

到这里即可让 Yujia 评审论文主线。更多 simulation、多个同构 synthetic 任务、第三个攻击载体、十几种新 retriever 或跨 backbone 全矩阵都不在当前关键路径上。若尚未跑完，outline 仍可先交，结果槽明确标为待填。
