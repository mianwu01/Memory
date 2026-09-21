# 补充更直接的历史答案复用对照（新增响应前）

原answer_reuse按完整entry的BM25选择历史答案，可能受长tool trace影响，未
必选中最接近最终问题的子问题。保留该已冻结行；额外运行两个简单、无需
发现图的共享reader对照，全部10个固定case，不按结果换选择规则：

- last_answer_reuse：仅给最后一次原生子问题的query+实际predicted answer。
- question_answer_reuse：只对历史query字段做BM25，用最高者对应的实际答案；
  平分取较早session，与原rank_entries实现一致。

共用原reader、thinking、32768输出上限和原session时间戳，单条最多8192代理
tokens。没有gold参与选择；只在独立评分时使用官方答案。完整输入相同则复用
已有响应。这是增强基线的补充开发对照，不重写原表、不改变主结构停止结论。
