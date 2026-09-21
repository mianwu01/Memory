# 原生搜索任务：继续完成四关，包含 discovery 与审计

用户已要求一直继续，并明确第三、四关都加入 discovery。本页在本轮新 LLM
调用前冻结基础执行协议；之前的门槛报告保留为历史状态，不再作为停工理由。
本轮仍请求 deepseek-v4-flash，thinking enabled，temperature 0，每请求上限
32768，timeout 600 秒；保留返回原始 ID，大小写归一判断版本。

## 任务与接口

MemoryArena Progressive Search，仓库 commit
6cd9de14b71915e39ac742a20dc33785e14b6aab，任务数据 revision
da1a37c8b19280e18627ca01cf368195a5e1d92e。开发固定 id 0–9；候选训练 id
10–29；测试 id 30–39，不按答案/成功率换题。阶段性接口调试只用开发前两题，
成功响应全部复用，不把它们额外算成独立样本。

使用官方 search/get_document 工具定义、原生工具调用循环、原生问题模板和
LongContextMemorySystem 的 add_chunk/wrap_user_prompt。为避免重型 CLI 的
无关 import，从 pinned 源码 AST 提取上述原始定义直接执行；保存源码 hash。
这叫原生核心函数的 adapter，不宣称未修改的整套服务部署。

全量公开 Tevatron/browsecomp-plus-corpus；不按 gold docids 缩小搜索空间。
建立 SQLite FTS5 BM25 工具后端，作为明确记录的 CPU 检索适配，不称作者
默认 OpenAI embedding 检索器。工具 k=5，search snippet 最多 512 cl100k
代理 tokens，get_document 最多 6000；同所有臂一致，留存原文 hash 和截断。
原生循环每子问题最多 12 轮，总 output 上限 131072；SDK 包装每次最多32768，
显式传递 reasoning_content，日志保存每次调用和工具读出的内容。

独立记忆 store 按任务隔离，每个子问题结束后写入实际 predicted answer 与
工具 trace，保持原生 session 写入语义。禁止把参考答案、评价、gold 文档集合
或 gold 结构写入记忆。最终 reader 的 full、各选读和 query-only 共用完全相同
的 prompt/输出规则；模型和工具不因方法改变。
native long-context 的容量配置为500000代理tokens；若仍发生截断则该案例的
full资格化无效，明确记录。原生文本时间戳使用固定逻辑session时间以保证
恢复输入逐字一致，真实write wall time另存；逻辑时间不冒充实际等待时长。

## 第一、二关继续落实

先形成实际 dev 轨迹，再对固定 10 个最终问题做 full-memory 三次独立读取。
第一阶段 reader 只根据已有记忆回答，以隔离 memory 条件；这是明示的 final
reader 适配，不能冒充默认可重新搜索的端到端得分。另报可使用原生工具的 full
agent。至少27/30正确、9题3/3、无截断/未恢复基础设施失败才扩大 discovery。
开发不够好就诊断并修复通用接口/证据获取，不把失败删除，不换案例。

评分独立使用已精确映射的官方 BrowseComp 答案，不调用 LLM judge。
保留 strict normalized exact match 为主分数。大小写、Unicode、空白和末尾
标点归一；去除答案字段中的 Markdown 格式和引用。任何额外 alias 规则必须
在新 reader 输出前写定并单列，不能按新输出逐题放宽。暂不使用 alias。
独立来源审计还需核对证据与工具 provenance；答案匹配不替代该核对。

## Discovery 设计：先测实际表示，不跳过

保留每次 native memory 写入前/后的原始文本、来源文档、read 集合、任务/
session 边界。观察时间为实际 memory write，不是把 API 重复编号当时序。
首先测固定低维语义投影/证据状态的变化量、常量通道、有效样本及不同任务
分布；不把原始文字本身假装连续标量，不用 oracle correctness 作 memory-state。
表示选择只用开发集，不接触测试答案；正式变量与算法参数在拟合前补充冻结。

第三关实际运行成熟时序 discovery（优先官方 Tigramite PCMCI+），保留多条
轨迹边界，报告观测混杂/平稳性假设、所有边和不稳定性。若不能支持共享机制，
分别拟合或报告不可识别，不伪造长序列。原生 write-state 与干预 read-dependence
结果分列，后者不得替代原研究对象。

选读使用同一冻结 reader，比较 discovered、complete/no-discovery、固定三份
错误图（17/29/43）、BM25、recency、历史答案复用和匹配随机。保存实际输入
hash与预算残差。discovered/complete 相同输入即不支持结构增量；即使负结果
也把已冻结验证全部完成。训练与测试分离，discovery、写入和推理成本全计入。

第四关在同一发现结构上做独立干预，检验问题来源定位及实际处置。权限在看
新结果前外部定义，报告全部冻结案例；以 full 稳定正确为审计适用条件，但
不换掉不稳定案例。阻断、决策相关内容替换、中性干预、原生 corpus 工具的
授权替代和证据不足拒答均要实际运行。替换需改变用于决策的信息，不只平移
数值或换来源标签。安全收益与记忆收益必须出自同一方法。

## 保存与恢复

起始702个未提交文件 hash 保存在 /tmp/hm3-discovery-continuation-start.json。
新增结果全部进入 progressive_search 独立目录。成功返回不重跑；每请求最多
两次仅限传输/429/5xx恢复，持久化在途记录。密钥不入日志、报告或命令行。
首个开发数据采集阶段硬上限1200个API请求；到界限报告并重新评估剩余工作，
不是成功标准。论文研究主张仍以独立效应、真实收益和审计闭环的证据为准。

### 首次调用前接口校验补充

2026-09-22：三个离线测试通过（原生工具循环、thinking工具消息恢复、namespace
隔离、逻辑写入重放、子集保留原session时间戳和严格评分）。资格化额外检查
所有writer正常stop、无剩余工具调用，以及reader返回模型统一为大小写归一的
`deepseek-v4-flash-0731`。保存原始native/adapter源码副本与hash。
SQLite首次网络盘构建受大量随机小写入限制，停止该构建并保留未完成文件；
改在本机/tmp构建同一全量语料索引，完成后复制到工作区。没有改变检索算法。
