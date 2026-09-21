# 固定开发案例错误复核（不改主分数）

full只读reader30次严格匹配15/30：0/1/2/6/9各3/3；3/4/5/7/8均0/3。

- case3三次选择Pantriste，官方为Manuelita，是实质作品混淆。
- case4三次UNKNOWN，历史未提供足够可靠证据；原生final tool-capable调用
  找到Govardhan Asrani，但附带别名说明，严格匹配仍失败。
- case5两次UNKNOWN（其中一次答案行附带解释），第三次32768全用于推理、
  finish_reason=length，没有可评分答案。不能当正常完成或稳健拒答。
- case7三次UNKNOWN，仍缺证据。
- case8三次均给出Namaste与Almost Human，但夹带作者、标点或出版信息，
  不等于冻结的`Namaste, Almost Human`。这是输出格式问题，不能解释成模型
  完全不知道答案；保持原strict主分数，不能事后放宽门槛。

独立原生tool-capable final agent每题一次（不是稳定性门槛）：strict 3/10。
0/1/6匹配；2/4/8/9给出目标实体/组合但附加别名或说明；3仍混淆作品；5/7
UNKNOWN。它与只读reader的prompt/工具权限不同，因此单列，不合并方法效应。
即使修复这些已知格式问题，现有结果也不足以通过固定90%与稳定性门槛。

原生参考答案在固定10题中，与独立官方答案的8题归一一致，2/8为别名或
多字段表达不同。已单列dev_reference_consistency.json。参考答案从未进入
writer、reader、topic表示或discovery输入；它们只用于评分/事后错误检查。
