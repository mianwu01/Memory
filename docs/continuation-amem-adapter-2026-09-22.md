# A-Mem 接口修复记录

冻结的论文仓库 commit `0c8039f...` 在 `MemoryNote.analyze_content` 中使用
`re.sub`，但文件未导入 `re`。7 条开发 note 的 7 次 metadata 请求都成功返回
JSON，却全部因这个 NameError 走默认 metadata。原运行保留为 invalid_execution。

`hm3.continuation_amem` 只在导入后给作者模块补充 Python 标准库 `re`。
不编辑上游 checkout、不修改作者 prompt、排序、演化或返回记忆内容。
修复开发检查按 model/messages/response_format/temperature/max_tokens 的
完整一致性复用 7 个已有 metadata 响应；metadata 改变后，7 个演化输入也改变，
因此只为这些新输入发出新请求。复用不计作新调用或新费用。

开发接口通过，actor 三次均错误，保留结果；没有因此再调方法。正式 6 个冻结
任务使用同一修复。每个 cell 有 `adapter_patch.json` 记录 wrapper hash。

补充预算解释：作者 `find_related_memories_raw(k=8)` 会展开 links 并可能重复
输出邻居，所以 8 是 initial retrieval k，**不是输出条目数或 token 上限**。
原生返回完整保留，额外开销在 actor token 中报告，不伪称等预算比较。
