# 2026-09-18 AutoDL 实验执行记录

状态：MINJA 与 AgentPoison 已完整完成并核验；Travel 正式 1,950 cases 已启动。以各目录的机器可读状态为准。本轮用户已授权大规模 API 运行。历史结果、失败尝试和旧 provider 输出独立保留。

> **2026-09-19 更新：** Travel 十臂全表已暂停新增调度，已发出的 case 自然结束，既有产物全部保留。暂停原因、图与 runtime 的语义问题、停跑时覆盖率及后续最小范围见[独立决策记录](travel-campaign-pause-decision-2026-09-19.md)。本页下文保留启动时的原始范围和执行历史，不应据此理解为全表仍在继续派发。

## 本轮范围

| 实验 | 已固定的范围 | 产物 |
|---|---|---|
| Travel 开发 | episode 101；implicit 十臂，explicit 三个结构臂，共 13 cases | [当前开发轮](../results/development/autodl_travel_dev_v2/campaign_state.json) |
| Travel 正式 | IDs 111–160，各 3 次 API realization；implicit 十臂 1,500 cases，explicit 三臂 450 cases，共 1,950 actor episodes；已冻结并启动 | [实时状态](../results/real/autodl_travel_20260918/campaign_state.json) |
| MINJA | 10 次独立写入；每次 12 trigger + 28 clean test queries，3 次生成，7 臂，共 8,400 test calls，另计 calibration | [协议说明](minja-autodl-campaign-2026-09-18.md)、[原始结果](../results/real/minja_autodl_2026_09_18/) |
| AgentPoison | 沿用 round2 的 64 calibration + 288 heldout trajectories、原 driver/轨迹/评分器 | [结果目录](../results/real/autodl_agentpoison_20260918/) |
| 原生 memory 接口检查 | Mem0、A-Mem、LightMem 各完成完整 conv-30 的 369 turns；保持顺序写入 | [进度](../results/development/autodl_native_validation_20260918/progress.json) |

Travel 十臂为 ours / noGcompact / query_only / bm25 / full / dense / summary / mem0 / amem / lightmem。explicit 面板仅运行 ours / noGcompact / query_only。

这是实际执行范围；[先前实验建议](next-experiment-plan-2026-09-18.md)中的 pooled/wrong-graph Travel 额外臂和新预算曲线不在这份十臂矩阵中，不能据现有矩阵声称已经检验全部拓扑消融。

## 任务与比较口径

- implicit 将历史依赖要求提前存入历史 notice，当前 query 保留目标指针；explicit 也收到相同提前 notice，但当前请求保留依赖句。独立生成后各臂历史可能不同，不能称完成后的历史逐字一致。
- 三个结构臂使用同一历史 notice 解析，因此 query_only 也是强 history lookup 对照。主要比较是 ours 对 noGcompact 的任务–读取取舍，以及 ours 对 query_only 的学得边增量；不预设图一定胜出。
- Travel 图只用排除 101、111–160 后的 219 episodes 拟合，产生 12 条边。旧基准和解析器的历史接触仍披露；这不等同于全新未见基准。
- 保留原 MemoryArena actor、工具、完整计划输出、30 steps 和官方评分。模型重复先在每个 episode 内平均，再以 50 个 episode 为单位做配对区间；不将 150 次调用当成 150 个独立任务。
- 十臂正式表全范围完成并通过完整性检查后才出排名；中途只报告进度、错误与开销。空答案或长度耗尽不能作为传输错误任意重采样。
- 在任何正式 dispatch 前，另登记完整核心面板：两种 query 条件 × 三个结构臂 × 50 episodes × 3 repeats = 900 cases，复用同一次生成。核心全部900例有效才单独出配对结果；不据结果删样本，也不把核心完成说成 native 比较完成。见 [核心协议](../results/real/autodl_travel_20260918/registered_core/protocol.json)。
- Native 检查验证完整实现的接口和机制，不等于复现三篇论文的基准分数。

## 无标签审计

MINJA 同时保留 frequency_regime、frequency_pooled 和真实 regime_structure 估计器，不能把频率打分改名为图恢复。另有 ungated、random_matched、oracle、noop。oracle 仅作评估上界。

完整8,400次测试及1,200组七臂配对核验通过。trigger攻击次数：ungated 158/360、frequency_regime 91/360、frequency_pooled 91/360、random_matched 93/360、oracle 0/360、noop和structure各158/360。regime频率法相对随机删除ASR差为−0.56个百分点，按写入run bootstrap的95%区间为[−6.11,+5.00]；本轮不支持额外定位收益。随机对照匹配删除record数，未匹配token长度。详见 [完整MINJA结果](../results/real/minja_autodl_2026_09_18/evidence_report.md)。

AgentPoison完成64 calibration + 288 heldout trajectories，协议和driver冻结核验通过。本轮沿原判据PASS：ungated 9/72、exact no-op 6/72、gated 0/72，3/3 blocks改善。直接定位1/2、冻结cluster扩展后2/2；不能把扩展贡献全部归给图。旧轮FAIL保留，正常查询0/24检索受干预，其accuracy变化不归因删除。详见 [AgentPoison结果](../results/real/autodl_agentpoison_20260918/results.md)。

第七个结构臂在任何 heldout test 结果产生前添加并冻结。当前 10 runs 均未检出显著正边，删除集合为空；保留这一结果，不据 test 修改阈值。校准中共检索相关性高、有效暴露有限，具体诊断和哈希随原始结果保存。

投毒 membership 只在后验评价和明确标注的 oracle 中使用。统计按独立写入 run 聚合；同一有限 query bank 的复用、重复解码和 record 实例的分母均需披露。来源定位与在线删除收益分别报告。

## Provider、并发与费用

- Endpoint：`https://www.autodl.art/api/v1`。
- 请求模型：`DeepSeek-V4.1-Flash`；API 返回模型名：`DeepSeek-Flash`。这只是接口的 requested/returned 元数据，不独立认证底层权重。
- Actor 保留默认 thinking；memory JSON 操作关闭 thinking，并验证无 reasoning 输出。CPU-only。
- 32/64/128 个短请求并发测试均通过。首次 128 探针因 prompt 未含 JSON 关键词全部返回 400，修正后 128/128 成功；失败探针保留，不能据其判断负载能力。
- 短请求成功不保证完整长轨迹吞吐，实际并发依长请求、CPU、内存和错误情况调整，不改变方法。
- 正式controller使用128进程上限、初始64并发；`dispatch_control.json`只调度并发/暂停，所有研究配置冻结。SIGINT/SIGTERM只停止新dispatch并允许在途请求结束。
- 提升至96并发后出现明确的`Model tpm limit exceeded`，长请求延迟增加。正式dispatch先降至44，为native、开发和传输恢复预留约4槽；稳定约14分钟、p95延迟下降后小幅试调52，若再限流则回调。实际值以`dispatch_control.json`为准；硬件内存充足，当前瓶颈是服务商吞吐。
- 未获得 AutoDL 单价。记录全部成功/失败尝试的用量及 provider billing 字段；无法确认费用时写未知，不套用旧渠道报价或把缺失价格写成零。
- 已确认一例 actor 工具参数解析在 LLM 日志写入之前失败，返回响应的 payload、finish_reason 和 usage 均未保存。已记录 token 总数因此是下界；独立[用量完整性附表](../results/real/autodl_travel_20260918/usage_coverage.md)核对所有尝试并单列这一缺口，既有冻结报告和生成代码不变。

## 技术恢复与当前交付

第一轮 Travel 开发在 LLM 调用前因真实环境 observation 使用 `group_id` 而解析器期待 `id` 失败；13 例和源码快照保存在 `autodl_travel_dev`。修复仅在解析器内部映射字段，6 个测试及真实 HTTP reset 核对通过后，新建 `autodl_travel_dev_v2`。

具体 demo 事前固定为 episode 101 round 2，未按结果挑选：[对比页面](../results/development/autodl_travel_dev_v2/demo/comparison.html)。其生成记录、选取和舍弃单元可直接核对；完整 episode 评分完成前不写成功结论。

三核心implicit开发episode现已完整执行，demo证据齐备。正式启动时，全部十个方法已走通实际read/write/actor接口。旧预算13-case开发轮现已结束：11完整完成；A-Mem发生旧预算截断，dense在round7发生断流，失败均保留。新预算A-Mem开发attempt1现已完整完成（49次LLM、8write/7read），初次断流也保留；完整长对话检查仍独立推进。

A-Mem在独立旧native检查中发生1000-token正文截断；相同请求16k诊断得到1289tokens、原parser完整恢复5/5邻居。正式前已统一把AutoDL A-Mem memory调用上限改为16k，保留作者prompt/parser/流程及原actor预算。原生默认预算与实际请求预算均逐调用记录。旧进程加载旧代码的证据保留，新预算开发和native检查使用独立目录，不回填旧失败。

LightMem原JSON模式下有重复键循环；相同请求诊断和top_p=1诊断各1/2复现，停止参数搜索，正式保留原配置。完整native检查失败不能称通过；若正式出现语义失败，独立报告完成率和故障，严格十臂主表仍不输出缺失情况下的排名。

旧版 Travel 的39.55% / −1.43点、带标签MINJA的3/3不回填本轮摘要。Travel结果句等待这次协议的完整评分。

给Yujia审论证结构的[18段P/S稿](yujia-paper-outline-2026-09-18.md)已按当前结果更新：formulation先于估计器，Travel留完整结果槽，AgentPoison正结果与MINJA识别边界分别进入主文，每句均指向证据或待填面板。

## 2026-09-19 双凭据续跑

第二凭据先通过29/29短流请求、16/16长输入请求（977,666 input tokens，11.8秒）和一个完整Travel开发episode。完整episode包含7位旅行者、18次LLM调用、200,269 input tokens与159,802 output tokens，19.03分钟结束，无传输失败。凭据只以SHA256前缀`631e69909c18624a`登记。

首个正式远端分片预先登记16个repeat-2 cases，覆盖全部13个方法/条件组合；14/16完整结束，A-Mem与LightMem各一例发生可恢复的流式传输失败。该分片31.05分钟额外完成14个episode，证明第二路由增加实际完成吞吐，但不支持线性加速主张。证据为`monitoring/secondary_key2_shard_001.json`及对应`_report.json`。

在首批结果后，第二批扩至32 workers，选择repeat 2、episodes 151–156的32个未启动cases；精确分配在调用前写入`monitoring/secondary_key2_shard_002.json`。后续控制器只在前一批成功率至少75%、无401/402/403时继续32-case均衡批次，并且只领取尚无state文件的repeat-2远端cases。主controller继续60 workers；传输恢复另限2 workers。新增调度器不修改冻结的actor、prompt、memory实现、图、模型或预算。

2026-09-19 00:02的磁盘快照为539/1,950 complete、60 running、38 failed；核心面板269/900 complete。38个failed中34个被现有恢复判据识别为API/流传输失败，4个为模型工具参数/JSON语义失败。后者保留且禁止个例重采样；技术失败按最多三次总attempt的既有规则恢复。所有中途数字仅用于执行健康检查，不读取或报告部分任务分数。
