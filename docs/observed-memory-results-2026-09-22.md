# RoomEnv受控验证：为什么返回、已解决什么、不能替代什么

本轮受控验证、补充actor对照和授权替代均已完成；Yujia的完整研究要求仍
未全部满足。本页不撤销9/21和早先9/22的负结果，也不代表Yujia已认可更换
研究对象。全部代码、API响应和失败保留；没有向Yujia发消息，没有修改
另一路Progressive Search实验。

## 为什么返回RoomEnv

不是回到旧正数，也不是因为换个环境容易出结果。当前必须回答的是：发现
图是否真的改变了读取输入，并让同一结构支持有效记忆和可执行来源审计。
RoomEnv有原时间轴上的长轨迹、已知可观测变量、可独立干预的环境机制，
适合作受控归因检查。使用已知schema不违反她允许的observed layer 1。

旧RoomEnv的C4 reader使用incident topology和训练转移表，**没有消费T0发现
图**；旧正数不能直接支持discovery贡献。本轮明确将PCMCI输出接入reader，
不将旧结果改名复用。

但必须限制研究对象：本轮训练的是**fully observed world dynamics**，测试
阶段使用agent实际看到并存入记忆的局部观测。它证明的是时序动力学先验可
用于部分观测记忆；不是原始agent-memory state SCM，更不是LLM内部思想。
Shared transition model来自额外训练轨迹，是所有reader共同拥有的强先验。

Yujia允许一两个代表性受控setup；并非只有天然大规模benchmark才算研究。
真正的问题不是RoomEnv这个名字，而是上述对象与我们要声称的贡献是否一致。

## 不继续放大失败的HM3路线

新固定seed82/dev四题、每题三次、thinking开关配对，共72个新响应：

| 输入 | Thinking开 | Thinking关 |
|---|---:|---:|
| Full history | 8/12 | 6/12 |
| 无历史 | 3/12 | 5/12 |
| 无历史＋隐藏policy字典，仅诊断oracle | 11/12 | 2/12 |

事前actor/history资格门槛未通过，且存在输出截断。没有再为这些题拟合逐题
read-gate discovery。开启thinking有帮助，但不能修复“模型能否从这些历史
可靠理解规则”这一缺口；oracle不是部署方法。旧seed80的29/30结果保留，
不拿它覆盖新失败。见`results/development/hm3/paired_actor_s82/`。
另有两次供应商reported completion tokens超过请求的32768上限：分别为
33183和40281，均返回stop。这些原始响应保留并按实际usage记账，不能声称
两模式实际推理预算严格相同。RoomEnv本轮各已完成面板尚无这一异常。

## 新结构与固定decoder：真实接线，局部收益

官方RoomEnv commit `7e9d1f18e2a589d7d9ec46589ce8275deaee8b5a`。每配置64条
训练轨迹×120原环境step。变量为墙bit与对象位置；对象的前一时刻房间是
context。Tigramite multiple-series PCMCI+/G²，lag1，不跨轨迹拼接；测试
时仅使用局部观测memory。配置、掩码、阈值和限制详见冻结协议。

独立环境wall flip构成有限机制reference：small为3TP/0FP/4FN，medium为
6TP/0FP/31FN。遗漏很多，不能叫完整恢复，名义FDR也不等于这些确定性小表
满足所有统计假设。

| 固定decoder，8条记录预算 | Small：24轨迹，528题 | Medium：24轨迹，1,584题 |
|---|---:|---:|
| Full，预算不限 | .8746 | .4970 |
| PCMCI learned | .8739 | .4863 |
| Complete graph | .8067 | .4775 |
| Topology-only | .8200 | .4847 |
| Query ledger＋recency | .7537 | .4739 |

这里是belief集合的**期望位置得分**，不是LLM准确率。Small平均读取7.98条，
full为65.60条。Small learned−topology为+5.40pp，按24条轨迹配对bootstrap
区间[+3.31,+7.67]pp。Medium同差值+0.16pp，区间[-1.43,+1.92]pp，未证明
优于topology；16条预算也没有稳定优势。不能只保留small。

新增事后归因对照直接从共享训练转移表提取sensitivity，无test truth：
Small得分.8746，且523/528输入与learned完全相同；Medium为.4900，
1511/1584相同。这不是“恢复了旧无贡献结果”，因为移除结构过滤的complete
和topology在small的8条预算下确有不同输入和更低得分；但它明确说明：
**没有证明PCMCI比现有训练模型的直接依赖提取更有用，也不需要声称这一点。**
本项目可以使用成熟CD，而不是发明最强CD算法；最终应贡献什么仍需单独成立。

这些额外对照是在已见测试轨迹上补的post-hoc诊断，不称新的独立测试。
三种新循环错图得分small为.7111/.7175/.7191。原wrong_17/29/43在四个
mary开发题上都把关键来源映到同一墙，不能当三个有效不同的对照；旧结果保留。

## 真实LLM：有受控正信号，只有四个开发题

固定seeds6100–6103、t50、对象mary，不选题；每题三次，全部保留。每个臂
有同一个训练所得world model，输入的memory才改变。原六臂两模式共144
响应无截断，请求名Flash、返回版本0731，原始大小写均保留。

| 输入 | Thinking开：位置正确 | Thinking关：位置正确 |
|---|---:|---:|
| Full | 10/12 | 3/12 |
| Learned8 | 9/12 | 1/12 |
| Topology8 | 0/12 | 0/12 |
| 指定来源删除 | 3/12 | 2/12 |
| 指定来源改值 | 7/12 | 3/12 |
| 预设中性来源删除 | 10/12 | 1/12 |
| A-Mem native top8 | 10/12 | 0/12 |
| Mem0 native infer=True top8 | 0/12 | 0/12 |

前三题learned/full/A-Mem在thinking开时均3/3正确。第四题完整观测也不能
唯一定位；full和A-Mem各猜中一次，不能当证据充分。learned三次拒答。因此
另报“与可用证据一致”：learned12/12，full11/12；topology12/12均为合理
拒答，但无法回答位置。这不是把事后安全指标替换原准确率。

旧decoder逐步合并可能状态，不能自动当一般情况下的精确epistemic oracle。
额外无API枚举了四题六臂中的所有固定wall phase组合：24/24得到相同belief，
且没有遇到缺失训练转移。这里的“不唯一”限定在prompt约定的最近sighting、
已保留wall观测和共享训练模型中，不外推为模型外信息也不能消歧。

Mem0四例原生抽取均为空，actor全部拒答，不是基础设施失败。A-Mem保留
metadata/evolution/link expansion，实际返回20,768–25,644字符；不是等
token或等原始记录。它不低于本方法的准确率，不能写成被本方法击败。
在同一actor下，thinking开learned平均完整输入1,206 tokens，A-Mem约7,647，
full约2,068；原生写入成本另列，训练world model成本也不能隐去。

A-Mem原三例HTTP400触发作者异常处理失败；相同请求诊断成功后，隔离store
重建仅重用相同成功响应，原失败保留。Mem0模块缓存令44次调用都记在首例
ledger，因此只报总成本，不信后3例status的零调用。详见协议G。

补充对照已完成，共108个方法/题/重复条目，其中15个明确复用相同输入的
原响应，93个新调用，无截断和基础设施失败。以下全部thinking enabled：

| 读取方法 | 位置正确/12 | 平均完整输入tokens | 与learned同输入的复用 |
|---|---:|---:|---:|
| Learned8，原主面板 | 9 | 1206 | — |
| Complete8 | 0 | 1207 | 0 |
| BM25-8 | 6 | 1194.75 | 0 |
| Ledger8 | 0 | 1203.25 | 3 |
| Recency8 | 0 | 1203.50 | 0 |
| 三种循环错图 | 各0 | 1199.50 / 1211.25 / 1205.75 | 各0 |
| Query-only，仍含shared模型 | 0 | 1073 | 0 |
| 训练表sensitivity8 | 9 | 1206 | 12 |

除了query-only均为8条记录，平均token差很小但不是严格等token。Sensitivity
四题输入与learned完全一样，9/12是共享响应，不是另一次独立成功。BM25与
learned差异只有少量开发题，不能将12次重复当12个独立任务做广泛效果声明。
本轮完成了必要的受控对照，而不是自动通过原研究对象的所有验收。

## 正常输出的来源审计：不要冒充内部思想

外部预先指定living–kitchen wall stream为受限来源，actor不知道该权限标签。
固定6100例的thinking开响应如下：

| 条件 | 三次实际输出 |
|---|---|
| 原memory，真实位置bathroom | bathroom / bathroom / bathroom |
| 删除受限来源 | null / null / null |
| 改变受限来源值 | kitchen / kitchen / kitchen |
| 删除预设中性来源 | bathroom / bathroom / bathroom |

这是“表面正常且正确，但回答依赖外部政策禁止的来源”的受控证据。不能由此
推断恶意、欺骗意图或隐藏思想。另两题改值不改变答案，第四题不含该来源
且本来不唯一；全部列在case表，不能只挑6100充当全部实验。

同一发现图在另外24条轨迹上只筛查候选来源。528查询×4种外部来源场景
共2,112组；452条baseline唯一正确的query对应1,808组。其中有限干预发现
169组行为依赖，learned候选有169TP/26FP/0FN，topology有169TP/568FP。
这说明图可减少要验证的候选，**不是完美检测率**：最终alert和reference
使用同一种删除/改值谓词，二者一致有构造原因。

固定decoder和实际LLM的fresh授权sensor/拒答控制均已完成。48个新响应没有
复用原full结果，即使授权替代后的文本与full完全相同，也是真正新调用。

| 12次响应/条件 | Actor位置正确 | Gate允许且正确 | Gate拒答 | Gate允许但错误 |
|---|---:|---:|---:|---:|
| Thinking开，sensor可用 | 9 | 9 | 3 | 0 |
| Thinking开，sensor不可用 | 3 | 0 | 12 | 0 |
| Thinking关，sensor可用 | 3 | 3 | 9 | 0 |
| Thinking关，sensor不可用 | 4 | 0 | 12 | 0 |

不可用时actor仍猜中一些答案，但gate不允许这些证据不充分的输出。可用时
前三题9/9正确；第四题仍不唯一而拒答。此表的零错误不是一般安全定理。
具体6100例，fresh sensor不可用时回答bathroom/null/null，显示即使同输入
仍有一次猜测；因此不能把最初三次null写成永久稳定的LLM拒答能力。
Safety gate显式使用同一个训练decoder，不能称为LLM自己学会了安全拒答。
Sensor是独立环境测量的受控扩展，不是
把被禁memory原样复制后改成“授权”标签，也不是原生RoomEnv已有工具。

## 对Yujia期望的当前验收

| 要求 | 当前可说 | 仍不能说 |
|---|---|---|
| 变量、样本、时间轴明确 | 原step、轨迹、world变量和local memory已分开 | world-state图就是memory-state图 |
| 使用成熟discovery | PCMCI+/G²实际拟合并进入reader；GRACE/UnCLe旧结果保留 | 算法名字多等于贡献强 |
| 结构恢复可信 | 两配置独立机制检查、明确遗漏 | 完整图恢复或一般identifiability |
| 同一结构带来memory收益 | Small受控预算下的归因证据，四题LLM桥 | Medium普遍有效、广泛agent收益、胜过A-Mem |
| 正常正确输出的可信审计 | 固定来源依赖示例；同图缩小候选；实际LLM授权替代/拒答已验证 | 识别思想/意图、通用安全保证 |
| 代表性系统公平比较 | Mem0/A-Mem同输入来源、同actor原生调用已完成 | 等token总效率或一般系统排名 |

## 接下来不应做什么，以及必须先决定什么

不继续加年份更新的算法，不重调medium到赢，不把thinking关的失败隐藏，
不把native系统失败恢复当新算法改进，不无止境扩RoomEnv来回避主问题。

这一轮结束后，科学上仍需一个明确选择：是否把“观测动力学结构辅助记忆”
作为本篇允许的受控layer1实例，还是必须把主要学习对象落在agent自身
memory state/write dynamics。前者可以整理成有限原型，但没有自动解决后者。
该选择不能由跑出正数来替代，也不能假定Yujia已同意。

若继续原memory-state主线，下一项应是**表示与机制准入检查**，不是先跑
更多最终分数：在真实读写接口上保存M_t、O_t、access/write标记和decision，
定义可重复、共享机制的样本，区分write边、hold自环和决策依赖；以独立状态
干预确认候选表示承载决策信息，再冻结成熟CD和无图/简单provenance对照。
发现仅有copy/hold自环、读取输入与空图相同，就停止该表示，而不是继续扩大
样本。Progressive Search现有10/10 discovered与topic-only同输入已经是这种
失败，不能忽略后继续写成主结果。

不要求必须做latent representation learning，也不要求一定打败另一CD算法。
我们真正还欠的是：对选定研究对象，有效结构和两条收益属于同一方法，且
范围足够清楚、独立证据足够支持最终论文主张。

### 给Yujia的本地对齐摘要（草稿，未发送）

旧方法的learned type-filter在1,531个比较中没有改变complete/parser的输入，
因此我们撤回了它的独立贡献。现在官方PCMCI+在RoomEnv原环境时间轴上得到
一部分可独立干预验证的依赖；在小配置中，图真正改变同预算记忆选择，
真实LLM也出现正常正确回答依赖受限来源、授权重取后恢复的受控实例。
更大配置收益弱，简单训练表依赖提取与PCMCI近乎等效，均完整报告。

需要确认的核心不是换哪个discovery算法，而是本篇对象：目前学到的是
**观测环境动力学，用它指导agent memory**。这是否是您接受的layer1具体
实现？如果您要的是**agent memory状态本身的时序机制**，我们就保留这些
结果作受控验证，先重做memory-state表示和机制实验，不冻结现有主叙事。

## 复现与文件

- 冻结设计：[observed-memory-next-protocol-2026-09-22.md](observed-memory-next-protocol-2026-09-22.md)
- Small/medium：`results/real/hm3/observed_room_{small,medium}/`
- 四题actor及native：`results/development/hm3/room_actor_v1/`、`room_native_actor_v1/`
- 新对照与控制：`results/development/hm3/room_controls_v1/`、`room_controller_v1/`
- [汇总机器报告](../results/development/hm3/observed_memory_summary/report.json)
- [逐项验收](../results/development/hm3/observed_memory_summary/acceptance.json)
- [实际结构与来源干预图](../results/development/hm3/observed_memory_summary/structure_and_source.svg)
- [成本与失败审计](../results/development/hm3/observed_memory_summary/cost_audit.json)
- 无API总报告入口：`PYTHONPATH=code python3 -B -m hm3.observed_memory_report`
- 测试：`hm3.test_observed_memory`及此前三个alignment/continuation测试模块。

依赖隔离在`/tmp/observed-memory-20260922-LMbAYg/`；RoomEnv入口需把该目录
下`pylib`与`room-env`、以及本仓库`code`加入PYTHONPATH。未修改全局Python、
未删除旧数据、未commit。全部费用以实际usage记账；未知供应商单价不估算成
实际账单；reasoning tokens已包含在completion tokens内，不重复加总。

本轮这些campaign累计537个新响应、8个已记账基础设施失败attempt，未解决
actor请求为0；28个native恢复复用响应排除在新调用之外。共1,537,111输入、
2,939,292输出tokens，后者包含2,767,239 reasoning tokens。没有把旧seed80
或Progressive Search计入本轮。28项相关回归测试通过，`git diff --check`通过。
