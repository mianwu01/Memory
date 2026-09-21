# Observed-memory 继续执行：资格检查、旧载体重审、来源验证

本协议先于本轮新 API 调用。用户接受先校准任务、重审已知 schema 的 layer 1
载体、读取干预作为验证工具，并追加 thinking on/off 并行比较。保留旧结果；
不代表 Yujia 已认可新的具体主实验。未向她发送信息。

## A. 新配对开发检查（不是新方法主结果）

- 现有 Flash thinking 的 seed80/dev 10题、30次结果已存在（29/30），不重跑。
- 新固定 HM3 Travel seed82/dev 前4题，每题3次，三种输入：full history、
  no history、no history + simulator policy dictionary。第三种只用于诊断能力
  上界，明确包含隐藏机制，绝不作为方法/部署成绩，不含正确动作或 post-state。
- 每种输入同时比较 thinking enabled/disabled；同一个 Flash 请求名、同
  v1/verbose、完整 S0、temperature0、32768输出上限。共72个新响应目标。
  固定洗牌请求顺序并交错并发，避免把模式完全混同于运行批次。
- 记录完整请求、模式、原始返回ID、reasoning内容/usage、截断、解析和所有评分。
  模型ID仅以casefold核对；不能从供应商ID证明内部权重不变。相同输出上限
  不等于实际计算量相同，报告全部实际token/latency，不称等算力比较。
- timeout600秒、并发最多6、最多3次基础设施attempt。只对网络/timeout/
  408/429/5xx恢复；成功但错误的回答不重试。途中中断的intent单列。
- 全部case与重复保留。重复先按case平均，4case只能做开发诊断，不外推。
- thinking full与policy-oracle分别至少10/12正确、无截断、无未解决请求，
  full至少3/4题3/3，且full比no-history至少多4/12正确，才通过本轮“actor
  可完成、历史有贡献”开发门槛。这是事前工程规则，不是统计显著性保证。
  不根据新开发结果换case或增加prompt版本；失败时分析信号/任务，不扩大
  per-episode discovery。固定模式的独立新测试必须另报，不能把dev当test。

## B. RoomEnv 重审

已知变量/schema不自动排除observed layer1；但环境状态不自动等同agent memory。
先检查原代码中discovery输出是否真正进入selector、给定拓扑/转移表占何角色、
训练可见性与测试可见性的区别、实际环境依赖是否存在。不要恢复旧headline。
需要运行时可取公开官方实现到独立目录，保留commit和依赖，不改邻近checkout。
若旧pipeline没有消费发现图，先用静态/控制证据记录，不能重复旧正数冒充新贡献。
原生环境不是强制门槛；受控agent实验可以被评估，但范围必须明确。

## C. 本轮后续的设计要求

主研究对象仍是原时间轴的observable memory；read-gate不替代它。
任何新受控实验在执行前补充具体变量、样本、write/hold/read与独立机制参考。
不把依赖检验p值直接作为正向utility排序；区分方向、交互与选读联合充分性。
可信审计需正常正确基线、真正影响决策的信息干预、中性/未使用来源负对照，
以及可执行的授权替代/拒答。权限外部给定，不推断意图。实际graph/discovery
贡献需与访问日志/简单provenance比较；局部audit成功不能填补主时序结构缺口。

所有新结果保存到独立目录，旧未提交文件不覆盖、不删除、不commit。

## D. RoomEnv 明确的受控重建（结果前追加）

官方RoomEnv commit `7e9d1f18e2a589d7d9ec46589ce8275deaee8b5a`，MIT，隔离安装。
旧C4的selector从连接构造incident与transition table，没有消费T0发现图。
新实验只检验“fully observed training dynamics 发现的时序先验用于局部记忆
选择”，不称LLM hidden-memory SCM，也不把世界全状态当局部agent已见历史。

- 原环境 small-01，先64条训练轨迹（seeds3000–3063）、每条120步；开发
  seeds4000–4007，120步。对象ID与规则固定，仅初始位置/墙相位改变；轨迹
  在Tigramite multiple模式中分开，不产生跨轨迹假lag。
- 变量为墙bit、对象location；时间是原环境step。按目标对象前一时刻位置
  条件化，用mask排除别的语境但保留原lag。PCMCI+/G²，lag1，pc_alpha .05，
  max_conds_dim=1，max_conds_py/px=1。所有墙和其他对象均为候选lagged父节点。
  输出候选p值后对本次fit集合BH .01。小条件表/确定性影响校准，独立机制
  检查是主要结构依据，不把名义FDR当严格保证。
- 机制reference仅离线用官方环境的wall翻转与_move_objects导出；不供selector。
  Shared answerer是原训练转移表/周期模型，所有方法相同，训练可见性一致。
- learned、complete、topology-only、三个固定置换图、query-ledger+recency、
  recency、random固定8/16条；不足budget用统一recency补齐。full单列。
  保存逐问题实际输入集合、分数和完全相同集合的比例；按episode汇总。
- 全部局部观测实际写入时间戳memory log，保存snapshots与truth分离。
  开发结果不作confirmatory证据；检查实现通过后相同算法可评估独立
  seeds5000–5023，不按开发分数修改图阈值或reader。
- 主用途成立至少需要：实际learned图进入reader、不同于topology/complete的
  输入，以及对同预算简单策略的效用证据；不足则报告哪一项没通过。

## E. 同一RoomEnv先验的来源审计与LLM桥（结果前追加）

固定沿用small-01已发现的三条context边、同一shared decoder与训练模型。
新seeds6000–6023，所有原定查询均保留；对每个墙来源分别做一个外部权限场景，
不是依据某次输出把记录追认为违规。独立sensor store由环境每步测量wallbit，
与agent局部memory分开保存。它是本受控扩展中明确提供的授权历史传感器，
不是声称原生RoomEnv就有这个工具，也不是复制memory改标签。

- baseline正确且唯一的查询才具有“正常正确输出”语义，但全部查询及这一
  子集的分母均报告。移除该来源的全部观测，另将来源流替换为同一周期的
  一步phase-shift观测；后者改变与位置推断相关的值，不改变world或真值。
- 所有来源都独立测两种干预，作为fixed decoder的有限行为依赖reference。
  learned graph只用于候选来源筛查；报告遗漏、与输入来源存在检测/topology
  的区别和成本。仅看边不声称违规或意图，权限由外部policy提供。
- 若被检测来源需要阻断，先只用授权memory；结果不唯一时，偶数seed允许
  调用独立sensor查询历史值，奇数seed模拟工具不可用并明确abstain。
  保存实际工具请求/返回；正确回答、错误回答、拒答与未检出分开报告。
- 真实LLM桥先用独立seeds6100–6103，每题固定t=50、对象mary，不选题。
  给所有臂同一个训练所得transition model（不是测试真值），完整原始观测
  文本；full、learned8、topology8、source_blocked、source_changed、neutral_blocked
  六臂；固定问题来源living|kitchen墙，中性来源office|den墙。中性是预设
  假设，不当作经证实无效应的来源，实际效应照报。
- 同一Flash，thinking开/关，32768输出、每臂3次，144请求目标，最多8并发。
  定义输出为JSON room或null，不需事务revision。原环境位置仅离线打分。
  开/关成本与样本均分开；同输入重复不缓存成独立新结果。全部case保留。
  这是受控世界模型+LLM回答器的桥接，不冒充无模型先验的一般语言memory。

## F. 第二原生配置的冻结复核

small-01开发及独立测试已完成后，保持同一算法、64条训练轨迹、120步、
8/16预算、decoder和alpha，增加medium-01（环境原有配置），训练仍为该配置
的seeds3000–3063，测试该配置的seeds5100–5123。与small配置不混合拟合，
不在medium测试后调参。单列结构误差、效用、同输入比例及失败；这个步骤是
范围检查，不是再增加合成噪声以让已选方法获胜。

审计报告解释补充：alert使用的两种行为干预与有限reference相同，因此
alert的零false-positive是规则构造的结果，不是独立检测精度；独立于新查询
的证据是训练所得graph是否能覆盖这些新查询的作用来源，以及减少多少
候选验证。不能用171/171之类数字声称学习器完美恢复审计真值。

## G. RoomEnv同场景memory-system比较（baseline结果前冻结）

复用已核验的Mem0 infer=True与A-Mem paper实现，不扩展方法列表。与LLM桥
相同四个固定seed6100–6103、t50、同一shared learned model与查询。原始局部
观测按五个环境step分批写入（0–4,...,50），保留每条原时间戳，不提供truth、
测试phase或发现图。检索原生top8，A-Mem link expansion保留；不回映射原记录。
固定memory模型Flash thinking disabled，原算法prompt与temperature保留。
两个系统独立store，写入、检索、metadata/evolution成本全部记录。每个成功
memory output交给相同actor的thinking开/关各3次；检索文本原样进入相同
MEMORY区，其余prompt逐字一致。原生条目不是等记录/token预算，表里明确区分。
复用原适配器的96-call技术上限足够覆盖11次写入；不把它当用户费用预算。
作者fallback、输出截断、服务失败单列为无效执行，不算算法得零分。

G执行修正：A-Mem三例在HTTP400后触发作者异常处理错误。对三份失败请求
逐字相同的独立诊断重试均成功，未改schema/prompt。允许新隔离store重建
这三例，复用所有精确匹配的成功metadata/evolution响应（包括诊断返回），
只对新输入或未成功的网络请求调用；临时400/网络/5xx最多3次，总体失败保留。
不重跑已成功的case6101。原版本和新版本分别留档，重复使用不重复计费。

Mem0四例均完成但抽取为空。首次多case同进程复用了作者模块缓存的OpenAI
类，使44个memory响应都记到首例的meter ledger；所以后3例status中的
memory_calls=0不代表没有调用。总44个响应均保存、没有丢失；按批次总体
计费，不误报逐case成本。后续runner支持单case进程隔离；不为修正计费归属
重发已有成功请求。

## H. 有限收尾：结构对照与授权替代（新调用前追加）

四例RoomEnv actor结果已知；以下是同一开发集上的补充诊断，不升级为新的
独立任务测试。不得据此宣布全部要求满足或继续无限扩展RoomEnv。

- 固定thinking enabled补complete8、ledger8、recency8、BM25-8、query-only、
  三个循环置换图和shared transition-table sensitivity图，每例每臂3次。
  shared model、system、question、序列化、输出上限不变；前三者沿用原selector。
  BM25对记录JSON分词，query为“Where is mary at environment time 50?”，
  k1=1.5、b=.75，同分以新记录优先。8条匹配不是严格等token，另报完整输入
  token差；不padding伪造等预算。query-only只清空memory，不移除shared模型。
- 原wrong_17/29/43虽然置换不同，均将本case所用living-kitchen映到bedroom-den，
  因而不是三个有效不同的对照。保留原结果；新增按已保存walls顺序分别循环
  1/2/3位的三张图，事前不根据actor分数选图。仍报告有效输入重合。
- transition-table sensitivity仅使用共享训练表：同对象/房间中两行wall bits
  恰好差一位且下一房间不同，就保留该wall依赖。不调用test环境、不使用
  独立机制reference。该对照用于检验CD是否只是重现已有decoder可提取的依赖。
- 相同case/mode/prompt/repeat复用原actor响应或同批唯一调用，并显式记录alias；
  不将多个方法标签当独立样本。完整保留已有正/负结果。
- 授权替代只补四例×两种工具可用状态×两种thinking模式×3次，48请求。
  工具可用时真正查询独立sensor store，保留完整请求和返回；不可用时删除
  指定来源。其余prompt不变，actor看不到外部违规标签或decoder答案。
  全部为fresh responses，即使恢复后的prompt和full一致，也不复用独立验证。
- 外部controller用原训练decoder检查授权memory是否唯一：不唯一或actor
  答案不属于唯一belief时拒答，否则允许输出。这是显式model-assisted安全
  gate，不冒充LLM自行学会拒答，更不能以gate零错误证明学到了审计真图。
  无论discovery是否报警，都不允许受限来源进入安全reader；报警用于诊断
  为什么原来的正常输出值得检查，权限执行不依赖报警成功。
- 本轮结果后的收尾必须明确：受控world-dynamics先验不是完整memory-state
  SCM；同场景原生baseline不是原生任务总体榜单；四例不是广泛有效性证据。

H补充：同一批small/medium已保存轨迹上，额外离线比较训练表sensitivity、
三循环错图。明确标为已见测试集上的post-hoc归因诊断；不重新训练，
不发API，不将其包装为新的confirmatory test。由相同seed重建环境时必须
逐查询断言完整memory与原落盘记录完全相同。
