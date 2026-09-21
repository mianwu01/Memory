# 第二关：原生任务源码与数据审查

这是只读准备，不是新任务实验结果。未重跑原生 Travel、MINJA-QA 或
AgentPoison-StrategyQA 的旧 campaign。HM3 的 actor 资格化不自动转移到这里。

审查仓库：[MemoryArena](https://github.com/ZexueHe/MemoryArena)，本地 commit
`6cd9de14b71915e39ac742a20dc33785e14b6aab`。实际读取文件 SHA-256 另存，
不假定邻近 checkout 与上游 commit 字节完全一致。数据 revision
`da1a37c8b19280e18627ca01cf368195a5e1d92e`，只下载公开任务定义用于审查，
没有把答案写入 actor memory。证据在
`results/development/hm3/native_task_screen/`。

## 候选 A：Bundled Shopping

已核验全部 150 个任务、900 个 query：每任务恰好 6 个 session；750 个 query
直接提供 `Compatibility notes:`，750 个要求兼容 `previous (ground truth)`
products，900 个均列出可选商品。当前目标 ASIN 未直接出现在对应 query
（0/900）；不能把“给了规则”误写成“直接泄漏当前答案”。

实际 memory 是 `run_shopping.build_memory_entries` 写入的用户输入、动作和
工具观测文本，以及 memory backend 的 store；商品数据库本身不是 agent memory。
一次 write 是 `memory.add(entry)`，读取发生在下一 session 首次
`wrap_user_prompt`；session 内还保留原生 conversation。`use_step_memory=false`
时先累计全部回合，结束后批量写入。6 个 session 只给 5 个跨 session 转移，
回合数尚未运行测得，不能用 900 条数据定义当作 900 次真实 memory 转移。

需要逐项防止的捷径：

- `build_instruction_for_step` 函数默认 `include_history=true`，但当前 runner
  和 long-context config 实际默认 **false**。开启时把购买摘要和 ground truth
  放入当前 query；正式实验必须保持 false。不能说默认 runner 已经泄漏。
- `backfill_memory_from_artifacts` 某些 fallback 使用含目标商品的反馈摘要；
  新实验需独立空 store、关闭旧结果续跑，不混入这些数据。
- `webshop_env._build_observation` 的字典含 `target_products`，当前 runner 正常
  只取非空 `observation['state']`。若为空后整字典序列化会暴露该字段；适配器
  必须 fail closed，不能把整字典交给 actor。
- 原生 `_build_judgement` 可独立核对购买 ASIN；另一个离线 reward 脚本使用
  LLM 属性评分，不混成确定性检查。精确 ASIN 判断的范围也比“任何合理商品”窄。
- query 已给兼容规则，后续即使记忆检索有效，也必须与直接执行这些规则的
  no-discovery 对照比较。不能把给定规则解释为发现的结构。

结论：可作为真实多轮购物的记忆使用基准候选，但当前不通过原 memory-state
时序结构主实验的准入。不能为了得到一个正结果就下载 5.48 GB 商品表并开始
大规模调用；先解决表示与规则归因。数据库和索引未在此工作区安装。

## 候选 B：Progressive Search（优先继续审查）

已核验全部 221 个任务、1,641 个 query；每任务 4–16 个 session（包含最终
综合问题）。query 中 URL 为 0/1,641。这只排除直接提供 URL，不能证明没有
给定语义依赖或模型先验捷径。首个固定案例的最终 query 汇总先前人物属性，
先前答案会重复同一人物；这些冗余必须保留并作为替代读取路径处理。
对 `Exact Answer` 最后一个标记后的首行做大小写/标点归一化，221/221 个任务
均可抽取，203/221 个最终参考答案与至少一个前置参考答案相同。这是参考文本
冗余诊断，不是新的正确性评分器，也不能假设真实 actor 的前置答案都会正确。
新实验必须包含简单历史答案复用对照，不能将该捷径算作结构发现收益。

具体执行链：`BrowseCompPlusEnvironment.run_full` 调用原生
`agent.search.run_query_with_agent_and_memory`，每子问题结束把 predicted answer
和工具 trace 通过 `memory_client.add` 写入 backend；下一子问题和最终问题
通过 `wrap_user_prompt` 读取。外部 corpus 是工具来源，memory 是 agent 已存的
答案/证据文本；二者必须分开留档。`store_eval_in_memory=false`，不用 gold
answers 填充历史。

这一路径比 Shopping 更适合检查“证据来源→记忆→后续回答”和独立授权检索
替代。候选工具是该仓库已有 corpus search / document fetch，不是给记忆改
权限标签。授权仍需按固定 source policy 外部定义，并检查替代来源能否提供
同一决策所需信息；目前仅源码审查，**没有运行或通过该闭环**。

尚未通过第二关，原因具体如下：

1. 下载的是问题/答案，尚没有实际 actor 的 memory snapshots。真实转移数未知。
   即使每 session 都写入，单任务也只有 3–15 次后续跨 session 转移，不能直接
   拟合几十个变量的 SCM；不能拼接不同人物/规则任务来伪造平稳长序列。
2. 原生默认 checker 是 LLM judge；数据中的 1,641 个答案都含 `Exact Answer`
   标记，但主体是解释文本。这不能替代独立确定性评分和证据正确性校验。
   本轮进一步获取了官方 simple-evals 指定的 BrowseComp 原始测试文件，
   221/221 个最终问题按空白归一化后精确映射。已有独立原始答案来源；
   不是只能依赖 MemoryArena 的解释文本。两份最终答案经简单文本归一化
   后相同为 170/221，其余可能是别名、措辞或错误，不能直接称 51 个错标。
   具体 checker 和别名规则仍须在看新 actor 结果前冻结，不能逐题放宽。
3. 需先检查子问题之间哪些只是同一答案的重复表述、哪些真正依赖新增证据，
   以及 query-only / 原生工具重查是否已足够。来源 URL 缺失不是结构未知证明。
4. corpus/index 尚未安装；现有 searcher 的检索预算、截断和 reasoning 接口
   还需在小开发集统一冻结。不得先花逐题 128 次请求拟合 read-gate。

下一步优先围绕这一具体仓库做低维 observed memory 表示的可辨识性设计，
同时保留原生文本。只有实际写入轨迹、checker 和同任务 actor 均合格，才进入
第三关。候选选择不等于通过准入，也不默认把论文改为 read-dependence。

## 其他已检查选项

只读复现上述搜索数据审查（不发 API）：

```bash
PYTHONPATH=code python3 -B -m hm3.native_search_screen
```

官方参考来源为 `openai/simple-evals/browsecomp_eval.py` 中指定的
`https://openaipublic.blob.core.windows.net/simple-evals/browse_comp_test_set.csv`，
下载字节 SHA-256 为
`7b24471cd5b3eb2a46830a14802b5c029ea62f488ff75a0f88af7923d1454abf`。
原始参考答案仅用于离线评分设计，不注入 actor 或记忆写入。对应原始行号、
映射规则和完整结果见 `search_screen_report.json`。

Formal Reasoning 的原生评分路径依赖 LLM judge，暂不优先；MINJA-QA 和
AgentPoison-StrategyQA 有大量已有实验，不重开以寻找正数。EHR-agent 虽有
真实 exemplar memory 和代码执行，但当前 checkout 未提供可执行的 EHR 数据；
没有把“找到另一个仓库”写成已完成新场景。
