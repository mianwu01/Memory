# 本轮复现入口与结果归属

主模型始终deepseek-v4-flash，thinking enabled，temperature0，32768每请求输出
上限。返回原始model ID保留，版本仅casefold归一。所有成功响应按job+完整
请求hash保存，method同输入共享响应；只有预定full/audit repeat是独立调用。

- 原始语料与索引provenance：results/development/progressive_search/corpus_and_initial_design.json。
  全量100195文档，7个parquet分片hash已对照HF LFS验证。
- 原生轨迹：results/development/progressive_search/dev_v2/case_*/。
  v1是未做工具预算收束的接口诊断；v2复用它的完全相同成功请求。
- writer实际API账本分为dev_v1/api与dev_v2/api_more；reader在dev_v2/api_reader。
  session中的usage是原生工具循环usage，不含额外收束；**总成本以完整API
  ledger为准**，不能只加session usage。
- 开发门槛：dev_v2/reader_gate.json；正式actor要求27/30且9题3/3，不因结果放宽。
- PCMCI+：discovery_dev/；4维文本投影不是语义字段SCM。保存所有p/q/value、
  bootstrap、去task均值与时间置换诊断；native写入67次、相邻57对，实际
  PCMCI tau_max=1默认截取有效47个候选样本。
- 共享reader主对照：evaluation_dev/。补充实际错图和更直接答案复用对照在
  evaluation_rewired_dev/，有单独修复协议，不覆盖原置换退化行。
- 来源审计：audit_dev/。来源重取与不共享的冻结读取曾与主对照并行，但共享
  输入只复用原响应。run.lock保证多进程不会同时写同一API账本。
- 授权文档与writer猜测隔离的追加检查：audit_evidence_only_dev/；在发现污染
  后对全部原适用五例实施，明确为开发修复，不冒充原预注册主结果。
- 原生可用工具final agent：full_agent_dev/，每题一次，与只读reader分列。
- 格式、实质错误、资料缺失与检索backend差异见本轮error/retrieval诊断文档。

索引实际执行路径为/tmp/hm3-progressive-search-20260922.sqlite；其完整工作区
副本为.tmp/progressive_search/corpus-complete.sqlite（同目录metadata）。
不要使用同目录corpus.sqlite：它是保留的网络盘中断构建，不是完整索引。
新环境可用corpus.py从相同revision的全量7个分片重建到一个不存在的新路径。

运行离线检查：

```bash
PYTHONPATH=code python3 -B -m unittest progressive_memory.test_runtime progressive_memory.test_controls
```

运行过的fit/评估结果是冻结文件，不要为了复现报告重新调用API。所有调用
已持久化，凭原始响应可重评分。report.py和figure.py读取全部完成结果产生
报告与图；报告JSON也是不可覆盖的冻结产物，新修订应使用新文件名或目录。
没有commit、reset、删除历史结果或重跑已关闭Travel/MINJA/AgentPoison实验。
