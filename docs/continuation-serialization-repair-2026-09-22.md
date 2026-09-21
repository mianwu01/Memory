# 完整序列化一致性修复

恢复失败请求前，完整 messages hash 断言发现：冻结的 `episodes.json` 使用
sort_keys，直接 `Episode.from_dict` 会改变 H、S0.fields 等字典插入顺序。
语义内容未变，但 verbose prompt 并非逐字一致。断言在 API 调用之前失败，
没有把不同输入当成相同请求复用。

修复通过原 seed/split/index 确定性恢复 episode，先断言 `to_dict()` 与冻结
数据逐字段相等，再断言完整 messages hash 与原请求一致；不重新拟合或采样案例。

同一检查发现 native memory-system actor 的 S0 字段排列也与主实验不同。
旧 actor 结果留在每 cell 的 `actor/`，不进入最终主表。已经构建的 native
memory output 全部保留和复用，不重做写入、演化、压缩或检索。只对改变后的
actor messages 做三次新验证，存入 `actor_v2/`，并保存排除 HISTORY 后的完整
system/state/query framing hash 及其与主实验输入逐字相同的断言。

记忆系统写入仍是冻结的公开 JSON segment，键顺序作为该适配器的表示保留。
native output 本就允许重新组织信息；修复针对所有方法应共享的 actor 背景。
原生输出为空或生成失败的案例不更换，不按旧 actor 正确率筛选。旧版 actor
费用、修复后的调用、全部基础设施失败都计入总成本。
