# 2026-09-22 session 总记录：四关执行、结果、验收与接续

## 0. 当前结论与阅读入口

**本轮冻结开发验证已经全部执行完毕，但Yujia的整体研究要求仍未达到。**
第三、四关实际使用了同一个discovery；尚未建立发现边的独立记忆收益，也
没有建立可靠安全处置闭环。不能把算法接入、短输入、局部正确案例或工程
修复写成研究要求已满足。

本文件汇总本session承接交接后的工作，包括执行过程、修订、负结果、代码、
成本与最终逐项回答。原始ledger/JSON是数值依据。下一session可先读本文件，
再按链接查证；起始交接中描述的“下一步”须结合这里的已完成状态理解。

- 起始交接：[CODEX-SESSION-HANDOFF-2026-09-22.md](CODEX-SESSION-HANDOFF-2026-09-22.md)。
- 本轮正式汇总：[完整结果报告](../results/development/progressive_search/report.md)、
  [机器可读报告](../results/development/progressive_search/report.json)。
- 最终逐项验收：[progressive-final-acceptance-2026-09-22.md](progressive-final-acceptance-2026-09-22.md)。
- 下一步门槛：[progressive-next-gates-2026-09-22.md](progressive-next-gates-2026-09-22.md)。

工作区：

```text
/mnt/dolphinfs/ssd_pool/docker/user/hadoop-nlp-hl02/hadoop-aipnlp/3A/multimodal/yangboxue/tts-sft/external/Memory-hm3-handoff-2026-09-18
```

下文结果路径若未写前缀，均相对于
`results/development/progressive_search/`。

## 1. 用户要求、授权与本轮边界

用户要求完整承接起始交接及指定材料，保留当前未提交工作，不重复已有实验，
不把正结果或算法接入等同于达到Yujia要求。用户随后明确：继续使用之前的
主模型，可开启thinking；按actor、原生对象、结构贡献、可信审计四关推进；
第三、四关都要加入discovery，并继续完成所有必要的固定检查。

本轮主生成模型保持`deepseek-v4-flash`，thinking enabled，temperature 0，
每请求`max_tokens=32768`，timeout 600秒。实际返回版本为
`DeepSeek-V4-Flash-0731`或大小写不同的同一版本，保留原始ID、仅casefold
归一检查。没有把更强模型结果混入方法效应表。

API沿用已授权endpoint `https://www.autodl.art/api/v1`。密钥仅从忽略文件
读取，没有写入报告、复制到其它供应商或输出。没有外部发信、联系Yujia、
commit、reset或删除旧结果。没有启用子agent。

起始702个既有未提交文件的hash保存在
`/tmp/hm3-discovery-continuation-start.json`。本轮新增代码、结果和文档使用
独立路径。历史原生Travel、MINJA、AgentPoison等关闭实验未重跑。既有
合成actor的29/30、9/10稳定记录不能替代新原生任务资格，本轮没有重跑它。

起始阅读范围包括9/21对齐结论、冻结协议、discovery替代方法结果、主报告
和UnCLe报告；其已完成实验作为背景，不重新包装为本轮新证据：

- [9/21对齐结论](yujia-alignment-results-2026-09-21.md)。
- [冻结协议与归因规则](structure-alignment-protocol-2026-09-21.md)。
- [discovery方法与历史结果](causal-discovery-alternatives-2026-09-21.md)。
- [历史总报告](../results/real/hm3/alignment/report.md)、
  [UnCLe报告](../results/real/hm3/alignment/uncle_report.md)。

## 2. 本轮实际执行过程

### 2.1 冻结新任务与数据接口

选择MemoryArena Progressive Search，固定开发ID 0–9，不按结果换题。
候选训练ID10–29、测试ID30–39只有通过门槛才启动，本轮最终没有启动。

上游repository commit为`6cd9de14b71915e39ac742a20dc33785e14b6aab`；
任务数据revision为`da1a37c8b19280e18627ca01cf368195a5e1d92e`。
全量Tevatron/browsecomp-plus-corpus revision为
`b27b02bc3e45511b8b82a13e6f90ce761df726f6`，共100195文档、7个parquet分片，
全部对照HF LFS hash核验；未按gold docid缩小搜索空间。

为避开无关重型import，通过AST抽取并执行上游`SearchToolHandler`、
`build_request`、原生工具循环与`LongContextMemorySystem`；保存源码与hash。
这是原生核心函数的adapter，不是未经修改的整套作者部署。

检索后端使用SQLite FTS5 BM25，明确不同于作者的稠密检索器。工具k=5，
search snippet最多512 cl100k代理tokens，get_document最多6000。每子问题
最多12工具轮，原生累计输出预算131072，每次API请求最多32768。

首次网络盘索引构建因大量随机小写入受限而停止，保留中断文件；改在本机
`/tmp/hm3-progressive-search-20260922.sqlite`建立完整索引，再复制到
`.tmp/progressive_search/corpus-complete.sqlite`。**不要使用同目录的
`corpus.sqlite`，它是中断构建。** 数据provenance见
[corpus_and_initial_design.json](../results/development/progressive_search/corpus_and_initial_design.json)。

### 2.2 修复工具预算结束时没有最终答案的接口问题

v1在12轮结束后仍有pending tool_calls且没有最终答案，不能当正常writer。
停止接口调试进程，保留所有v1响应、session和请求意图。两次已发出而无终结
记录的请求可能已计费，最终单列，不为了补账重新调用。

v2在工具预算耗尽后补一次无工具收束，仅根据已有证据回答，不足则UNKNOWN；
不追加检索或gold。正常成功的v1请求按job和完整输入hash复用，不重复执行。
最终writer账本分布在`dev_v1/api/`及`dev_v2/api_more/`。保存原生预算命中
与finalization标记，不能用最后stop掩盖预算终止。

原生记忆按任务隔离，每轮实际写入预测答案和工具trace；下轮读取全部历史。
逻辑session时间戳固定以支持逐字恢复，真实wall time另存。容量500000代理
tokens，本轮未发现记忆容量截断。最终形成10条轨迹、67次写入。

### 2.3 执行actor资格、实际工具agent及错误诊断

固定10题每题3次full-memory只读reader，模型、prompt、接口、评分一致。
资格门槛预定为至少27/30正确、9题3/3、无截断及未恢复基础设施失败。
最终**15/30，5题稳定正确，1次截断，未通过**。

稳定正确为case0/1/2/6/9；其余3/4/5/7/8保留失败，不替换。case3实质混淆
作品；4/5/7包含UNKNOWN或证据判断不足；8包含正确诗名/书名却不符合冻结
严格格式。不能事后加别名规则通过门槛。

另对10题各跑一次可用原生工具的final agent，严格正确3/10。它不同于
只读reader的工具权限与prompt，单列，不合并得分。

还核对了独立官方答案映射：10题中8题与原生参考归一一致，2/8存在别名或
多字段表达差异；官方答案只用于评分/事后核查，未进入writer、reader、
表示或discovery输入。字面覆盖检查发现case3/5/7记忆中已有参考答案字面，
因此不能把错误都解释为资料完全缺失；字面存在也不等于所有关系约束已满足。

### 2.4 检查query依赖与稠密检索修复可行性

固定10题的query无URL，也无官方完整答案连续归一字面；这不构成语义无泄漏
证明。子问题分解与最终问题线索由数据集给定，不是discovery发现的。
原生跨轮读写确实发生，但不自动证明每条历史或发现边必要。

只读核查作者公开稠密索引`joanna690/websearch-embeddings`：构建脚本使用
`text-embedding-3-small`，搜索类默认却是`text-embedding-ada-002`，不能
假设编码空间兼容。已授权同一endpoint的模型目录列出39个模型，无embedding
模型；一次3-small通用文本探针返回404，未重试，也未改动冻结BM25实验。
因此不能把新任务资格失败全部归因于Flash本身。

### 2.5 实际拟合discovery并触发结构停止条件

预先冻结TF-IDF+NMF四维有损文本投影，拟合只用开发轨迹真实写入，不看gold。
累计投影为S，实际写入增量为ΔS；对当前query投影做ridge残差化。时间步为
真实native memory write，不是API重复编号。不同任务保持独立轨迹。

官方Tigramite PCMCI+/ParCorr，lag1，BH .05，条件维度上限1；保存原始和
残差化结果、p/q/value、20次trajectory bootstrap、任务内去均值和时间置换。
67次写入形成57相邻对，PCMCI边界截取后的有效候选样本为47。

主图只有4条自环；去任务均值诊断0边；时间置换诊断1自环。四条主自环的
bootstrap频率分别为.60/.85/.75/.95。拟合约5.49秒，零新增LLM discovery
调用；这些关联不构成语义SCM或可靠完整图恢复。

消费者从final query的seed topic出发选祖先topic，在候选记忆中按BM25取
最多2条，每条最多8192内容代理tokens，保持原session时间戳。主图自环不
扩张祖先集合，**discovered与空图topic_only在10/10题上完整请求相同**，
与complete在8/10题相同。预定结构停止条件触发，不扩大训练/测试；仍完成
用户要求的有界开发对照和审计。

### 2.6 完成全部主对照，并透明补强退化错图与答案复用对照

主表160行、74个不同输入，其中10个full输入复用资格化repeat0；实际新增
64个成功返回。同输入共享响应，不是160次独立调用。

发现原wrong_17/29/43只置换节点标签，对全自环图完全无效。保留原行，事前
补充三份真正不同的derangement错图：4边、各节点入度/出度1、无自环。
同时增加last_answer_reuse与question_answer_reuse，防止完整trace检索分数
掩盖更简单的答案复用。补充共50行、28个不同输入，仅12个新增请求。

全方法结果、配对case bootstrap区间、内容token残差与截断均在总报告。
关键结果：discovered/topic_only各4/10，complete/BM25 matched各5/10，
recency matched 6/10，full repeat0为5/10，last_answer_reuse 5/10。
三份真实错图为5/10、5/10、4/10；不能用错图表现覆盖空图同输入的反证。

### 2.7 用同一个发现图完成来源审计

全部10题进入报告。仅full稳定正确且writer完整的0/1/2/6/9适用，其余5题
列为不适用，不换题。候选来源由discovered选择器及BM25定位，另用
complete/BM25定位作对照；5例中4例定位相同。

事前定义模拟撤销政策：历史副本可被撤销，真实corpus工具返回为当前授权
来源；不声称实际文档恶意。实际执行候选单条删除、反事实实体替换、中性
归档说明、complete候选删除、保守来源闭包阻断、授权重取、空记忆，每种
三次；baseline复用full三次。完整请求和repeat相同则共享响应。

case0/2/6分别发生12/6/17处替换，9次读取无一次跟随反事实实体；case1/9
替换0处，不算实质信息干预成功。其他记录仍有答案信息，不能从删除无效
推断候选没有被使用。来源闭包根据真实“后续writer读取全部历史”保守扩张，
五题均删除到空记忆；这不是最小因果来源集，也不是发现图特有收益。

授权重取真实调用原生搜索工具，排除候选记录原docid，核对无相同URL/hash。
最终105行干预全部完成：

| 条件 | 严格正确 | 严格UNKNOWN | 截断 |
|---|---:|---:|---:|
| discovered单条删除 | 15/15 | 0/15 | 0 |
| complete单条删除 | 15/15 | 0/15 | 0 |
| 反事实替换 | 13/15 | 0/15 | 0 |
| 中性修改 | 14/15 | 0/15 | 0 |
| 来源闭包阻断 | 1/15 | 0/15 | 7 |
| 空记忆 | 1/15 | 0/15 | 7 |
| 真实授权重取 | 9/15 | 2/15 | 1 |

闭包阻断与空记忆两行共享响应，不是独立试验。反事实与中性条件中严格失败
含多写别名/解释，不能直接等同实质事实改变或不安全行动。授权case1/2/9
稳定正确，case0不稳定，case6稳定错答NYU。

### 2.8 追加统一证据隔离修复，并保留失败

发现case6授权writer承认未检索证实仍猜NYU，reader也给出NYU；不能凭一致
直接认定因果复制。事先写明追加修复：对全部五例各三次，仅保留实际工具
返回，去除assistant答案、说明及搜索query文本；不追加检索、不挑证据。

15次全部完成，仍9/15正确、1次严格UNKNOWN、1次截断。case6仍NYU 3/3，
case0另出现错误人名Meghann Fahy。**修复未建立安全拒答，也没有证明错误
唯一依赖writer猜测。** case1/2/9真实工具文档含官方答案字面，这仅是支持性
检查，不自动证明全部问题约束。

### 2.9 接续在途进程，生成最终报告并检查

续作时主对照、审计缓存和补充对照waiter仍在运行；用户中断的是sleep，
后台实验并未消失。先检查现有状态，再接续等待，没有重复启动成功任务。
审计提前读取与主队列通过`audit_dev/run.lock`串行写共享账本；主对照同输入
和预定重复按协议复用。只对传输错误重试，未因答错或截断重跑。

最终主队列和补充队列正常结束。执行report.py、figure.py，检查PNG可读性；
补充报告中的置信区间、截断、总成本与服务端输出预算异常。完成最终验收、
query依赖复核、后续门槛文档。离线验证确认必要结果行齐全、哈希/模型/预算
配置一致、原生读写链一致、授权来源无禁止docid交集、原有文件未改动、
新增文件无密钥匹配。`git diff --check`通过，21个Python模块语法解析通过。
本轮原有9项离线测试已通过，覆盖工具thinking恢复、任务隔离、记忆重放与
时间戳、预算、真实错图、来源闭包和工具证据过滤。

## 3. 最终逐项对照

| Yujia/用户要求 | 当前状态 |
|---|---|
| 合格actor | 未通过：15/30，5题稳定正确，1截断 |
| 具体场景、变量、样本、时间步明确 | 原生读写和样本已落实；有意义的语义记忆变量仍未验证 |
| 实际运行成熟discovery及明确dependence test | 执行完成：PCMCI+/ParCorr与全部诊断均已保存 |
| 结构恢复可靠、有机制意义 | 未成立：自环关联与任务因素尚未区分，不能称完整因果图 |
| 结构独立改善记忆效果或效率 | 未成立：空图10/10同输入，未证明总效率收益 |
| 正常正确输出下定位问题源并安全处置 | 未通过：来源归因、阻断后拒答和授权替代均有缺口 |
| 同协议代表性memory systems、独立测试 | 未完成：未启动新训练/测试及本场景Mem0/A-Mem/LightMem表 |
| 全部案例、失败、成本和可复现性披露 | 本轮完成，科学要求未因此自动通过 |
| 同一方法连接记忆收益与可信审计收益 | 未形成证据链，整体研究目标未达成 |

## 4. 调用、费用与异常账本

本轮共817个成功返回、822次请求意图、3次基础设施失败、2个早期中断意图
无终结记录。成功返回指传输完成，不表示任务答对。按实际账本分阶段如下：

| API账本 | 请求意图 | 返回 | 基础设施失败 | 无终结记录 |
|---|---:|---:|---:|---:|
| dev_v1/api | 130 | 127 | 1 | 2 |
| dev_v2/api_more | 411 | 411 | 0 | 0 |
| dev_v2/api_reader | 30 | 30 | 0 | 0 |
| evaluation_dev/api | 66 | 64 | 2 | 0 |
| evaluation_rewired_dev/api | 12 | 12 | 0 | 0 |
| audit_dev/api | 114 | 114 | 0 | 0 |
| audit_evidence_only_dev/api | 15 | 15 | 0 | 0 |
| full_agent_dev/api | 44 | 44 | 0 | 0 |

审计114个返回含47个来源重取调用与67个新增reader返回。方法行、干预行、
不同序列化输入、独立repeat和API调用数不是同一个量，不能混用。

实际usage为输入130722582、缓存输入98610432、输出2853541、reasoning
2740379 tokens。输入中缓存部分是子集，reasoning是输出的组成部分。
旧费率情景为133.4684美元（未缓存输入2.5/M、缓存.25/M、输出10/M），
**不是确认的Flash价格或账单**。中断和传输失败的额外费用未知。另有模型
目录查询与一次404 embedding探针，不计为成功chat任务返回。

总成本以API ledger为准；session.usage只含原生循环，不包含额外收束，
不能仅相加session usage。discovery虽零新增LLM调用，轨迹生成、开发失败、
模型推理与授权重取都已计入，短reader输入本身不能证明总效率收益。

4次服务端报告的completion_tokens超过请求32768，全部保留并按报告usage
计入，不删除后重新计算优胜结果：

| 输入 | 报告completion_tokens |
|---|---:|
| 主对照case0 query_only | 54515 |
| 主对照case5 query_only | 62566 |
| 主对照case8 query_only | 60800 |
| 审计case2空记忆repeat1，同时为来源闭包阻断 | 45028 |

只能确认请求预算配置相同，不能确认服务端实际执行了相同上限。两个中断
意图为`collect/case1/session1/turn3`及`collect/case0/session2/turn2`，均在
dev_v1；不是待补必要实验，不要为了“清零pending”重新调用。

## 5. 新增实现与证据索引

代码统一在[code/progressive_memory/](../code/progressive_memory/)：

| 模块 | 用途 |
|---|---|
| runtime.py | 原生函数抽取、记忆包装、thinking传输、输入/响应账本和精确缓存 |
| corpus.py | 全量语料校验、FTS5索引与文档来源记录 |
| collect.py、qualify_incremental.py | 真实记忆轨迹与增量actor资格检查 |
| discovery.py | 文本测量、PCMCI+、bootstrap及诊断；用load_projection加载投影 |
| selection.py、evaluate.py | 冻结选读规则、主对照、按完整输入共享响应 |
| rewired_controls.py | 真实错图及两种更直接答案复用对照 |
| audit.py、audit_early_reads.py | 来源定位、干预、授权重取与不重复的提前读取 |
| evidence_only.py | 全五例统一工具证据隔离复测 |
| full_agent.py、coverage_diagnostic.py | 独立工具agent、参考答案字面覆盖诊断 |
| continuation_queue.py、status.py | 接续队列、进度/账本/保留检查 |
| report.py、figure.py、verify.py | 总报告、独立SVG/PNG、输入与来源完整性检查 |
| test_runtime.py、test_controls.py | 有针对性的原生接口与对照测试 |

投影pickle保存的是projection.__dict__，通过load_projection恢复，避免
`__main__`类路径不可反序列化问题。不要改回直接pickle运行模块中的实例。

核心结果目录与文件：

- `dev_v1/`：保留的早期接口失败与共享writer账本。
- `dev_v2/case_*/`：67个session及10条完整trajectory；`reader/`为30行资格。
- `dev_v2/reader_gate.json`：未通过的actor门槛，不应覆盖。
- `discovery_dev/`：投影、fit、诊断与冻结参数。
- `development_structure_gate.json`：actor失败、结构停止、不扩大训练/测试。
- `evaluation_dev/`与`evaluation_rewired_dev/`：冻结输入、响应与210行结果。
- `audit_dev/`：冻结干预、授权真实来源、105行结果及共享API账本。
- `audit_evidence_only_dev/`：追加修复的冻结输入及15行结果。
- `full_agent_dev/`：10个独立原生工具agent结果及账本。
- `dev_reference_consistency.json`、`reference_literal_coverage.json`、
  `authorized_evidence_review.json`、`query_dependency_review.json`：辅助核查。
- `embedding_capability.json`、`embedding_probe.json`：脱敏模型目录与404探针。
- `report.md/.json`、`structure_and_results.svg/.png`：最终报告和已检查图。
- `verification.json`、`file_manifest.json`：最终实验验证及新增文件hash清单。

## 6. 本轮文档全索引

| 文档 | 内容 |
|---|---|
| [discovery协议](progressive-discovery-protocol-2026-09-22.md) | 任务、四关、API和冻结基础规则 |
| [接口修订](progressive-interface-amendment-2026-09-22.md) | v1→v2工具预算收束与缓存复用 |
| [结构测量协议](progressive-structure-measurement-2026-09-22.md) | 变量、PCMCI、消费者与停止条件 |
| [审计协议](progressive-audit-protocol-2026-09-22.md) | 来源政策、定位、各干预与闭包 |
| [错图修订](progressive-wrong-graph-amendment-2026-09-22.md) | 标签置换退化及真实错图补充 |
| [答案复用补充](progressive-reuse-control-amendment-2026-09-22.md) | 最后答案与query字段排序的复用对照 |
| [证据隔离修订](progressive-authorized-evidence-amendment-2026-09-22.md) | 全五例工具返回隔离条件 |
| [证据隔离结果](progressive-evidence-repair-results-2026-09-22.md) | 修复未通过，保留失败 |
| [检索诊断](progressive-retrieval-diagnostic-2026-09-22.md) | 原生稠密后端差异与404探针 |
| [开发错误复核](progressive-dev-error-review-2026-09-22.md) | 格式、实质错误、参考答案差异 |
| [query依赖复核](progressive-query-dependency-review-2026-09-22.md) | 外部给定线索与真正记忆依赖的边界 |
| [复现入口](progressive-reproduction-2026-09-22.md) | 索引路径、账本归属与离线命令 |
| [最终验收](progressive-final-acceptance-2026-09-22.md) | 四关、审计、成本和未完成项 |
| [下一轮门槛](progressive-next-gates-2026-09-22.md) | 修actor、明确变量后才恢复扩展 |

## 7. 收尾检查、复现与下一session注意事项

最终实验验证确认817个响应、822个意图、744个不同已记录API输入；必要结果
行数为160/50/105/15；错误列表为空。702个原有文件全部未改动，新增1053个
文件扫描无凭据匹配。该冻结verification/manifest生成于本session总记录之前，
**本文件不在当时1053个文件的清单中**；不要为补入本文件覆盖冻结清单。

实验收尾时主队列、补充对照和审计均已退出，没有待续必要API任务。无需
重启continuation_queue，也无需重跑fit或已有响应。所需结果已经落盘。

离线测试入口（不会发API请求）：

```bash
PYTHONPATH=code python3 -B -m unittest progressive_memory.test_runtime progressive_memory.test_controls
```

`report.py`、`figure.py`只读已有结果；`verify.py`会写冻结产物。新增本文件后
不要直接重跑verify并覆盖原manifest；若需新一轮验证，应先采用独立输出
文件名。报告JSON同样不可覆盖，修订应使用新版本产物。

科学上仍需：先修同一主模型的证据获取与严格输出接口；在开发集另立透明
版本，保留原失败；落实原生语义记忆变量及query混杂问题；通过actor和输入
级结构作用门槛后，才启动独立训练/测试及同协议代表性系统比较。来源审计
还需解决冗余路径、真实决策信息干预、证据不足拒答和授权证据支持。

不要重启已关闭Travel/MINJA/AgentPoison，不要把原来随机read-gate结果当
原生记忆机制，不要把旧memory-system面板拼到本表，不要从四条主题自环
外推语义因果结构，也不要把用户允许继续推进说成Yujia已经认可研究对象。
