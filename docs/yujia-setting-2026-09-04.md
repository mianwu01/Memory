# 9/04 后采用的 setting 与变量口径

当前主线是 **MemoryArena travel 的结构选择与 memory 审计**。已有 simulation 保留为方法背景；不再把重做因果发现仿真或 synthetic v3 当成这轮实验的前置条件。

## “各 region 的变量集合是否相同？”

转录中的 region 是否指 regime 尚未确认。下面同时回答环境、episode 和 regime 三种解释，避免依赖转写猜测。

| 层级 | 变量 / 记录 | 是否共享同一集合 |
|---|---|---|
| Travel 类型图 | `current_city, transportation, breakfast, attraction, lunch, dinner, accommodation` | 是，所有 episode 固定 7 列、相同含义 |
| Travel 实例记忆 | `(traveler, day, slot)` 单元格及来源 round | 否，旅行者数与天数变化；实例节点数不等于发现模型的变量维数 |
| Travel 不同 trip length / 城市 | 同一 7 类变量，不同取值与记录数 | 是；天数 3/5/7 不自动意味着 3 张已识别的 regime 图 |
| 审计中不同 regime | 同一组可观测 write/read/action/context 通道 | 是；允许边权或激活变化。不能把新增 record ID 当作新增变量维度 |
| 不同环境，例如 Travel 与 MINJA | 各自定义 schema | 否；没有把语义不同的列拼起来估计一张图 |

实例记忆解析还会省略值为 `-` 的未设置单元格。因此 demo 中的 84 个非空历史单元格是
运行时记录数，不应反推为发现模型只有 6 个变量；发现矩阵一直保持 7 列。

## 实际运行版本，而非早期拟议版本

目前 P2 使用的冻结图是 `results/real/p2_compact_v3/travel_learned_graph_holdout_111_120.json`。
它的 `source` 是 **`spec=ind`、lag ≤ 3、260 episodes / 260 trials / 1283 windows**。
`X[t,s] = 1[第 t 位 traveler 的 query 约束修改了 slot s]`，跨天取该 slot 是否被激活；
数据来自训练 query 的约束解析，**这张实际使用的图不是从 held-out gold plan 数值学得的**。
`current_city` 等列即使没有激活也保留 schema，不以观察到的边数替代变量数。

一个 trial 是一个 episode；t=0 是公开 base person，t>0 是后续 traveler round。
发现窗口只在 trial 内展开，再汇总拟合，绝不把 episode 尾部和下一个 episode 开头拼成 lag。
`cell_price/cell_id` 的备选实验才把 `(episode, day)` 当 trial，并可能读取训练 gold plan；
它们不是这轮使用的 `ind` 图。早期 `memoryarena-instantiation.md` 推荐的 21/35/49 维 day×slot
版本是设计备选，不能写成当前实现。

图训练排除了 IDs 111–120。新 baseline 的开发用 ID 101，完整实现重评拟覆盖全部 111–120，
待实现验收后冻结；旧 v5 仅用前三个 ID，现降为历史探索性结果。
这些 ID 在历史实验中已经看过，因此称为**配对复验 / 描述性扩展**，不称全新确认性测试。

## 记忆、actor 与评价各能看到什么

每个 episode 新建记忆。t=0 只写入环境公开提供的 base plan；以后每轮先检索，再规划，
再把 **actor 自己生成的计划、query 和 scratchpad** 写回。失败的生成也会传入后续记忆。
不得把当前或未来 traveler 的 gold answer 写进任何 baseline。

修复后的所有方法使用 MemoryArena 原 actor 提示、完整工具集、30 steps 与完整计划输出。
Ours/noGcompact/query_only 把完整公共 base 显式保留为可见 memory，由 actor 自行写完整计划。
其他方法收到相同的官方 base 写回，经各自原生 memory 管线保存和检索。
旧 `query-target/base-inheritance-v3` decoder、隐藏 base tag、答案回填与 query 工具过滤已移除。

Ours 还使用 query 的 person/day/slot 解析、公开行程 scaffold 和紧凑序列化。
因此 **ours 对 noG 的现有对比包含图选择与表示压缩差异**，不是只换一个邻接矩阵的纯图消融。
`noGcompact` 与 ours 同配置只关闭选择，隔离选择规则的整体作用。
另加 `query_only`：保留同一引用解析器、可见 base 与格式，但移除学得的类型边，进一步分离图与解析器。
对 BM25 / dense /摘要 / native memory 的结果衡量整个 memory pipeline；不能证明图对所有算法不可替代。

主指标使用 MemoryArena 官方 PS / SPS / SR；与环境即时 reward 不同，官方 plan evaluator
不计 `current_city`。同时给出 episode 等权均值、每个 episode 原始值、actor 输入/输出 tokens、
memory 写入/更新 tokens、各阶段耗时。少量复用 episode 不足以支持稳定排名或总体非劣结论；
bootstrap 只作描述，不能用大量单元格伪造独立样本量。

## identifiability 与 oracle

真实轨迹不能默认满足 causal sufficiency、噪声独立、faithfulness、足够 regime 变化或 latent
可识别性。Travel 的 `ind` 图首先描述 query 约束激活的时序规律，不能直接当成世界中价格/偏好
的真实 SCM；MINJA 的同轮 read→action 方向有运行时顺序先验。统一称 **估计的时序依赖图 / 候选驱动结构**，
结构价值由下游配对比较与干预检验，而不是由预测拟合好来保证。

| oracle / 标签 | 允许用途 | 当前证据边界 |
|---|---|---|
| 合成 SCM 的真 DAG | 单列 oracle 上界、结构恢复评价 | 不与 learned 方法混名 |
| Travel gold plan | 官方评分；若用于训练编码则单独声明 | 当前 `ind` 图用 query 激活；测试 actor 不读 gold |
| MINJA `is_poison` / `poison_retr` | 受控攻击的事后审计演示 | 属于 oracle-tagged channel；不能冒充标签未知的部署检测器 |
| AgentPoison record IDs / 检索 / 异常 action / 时间先后 / embedding cluster | 标签未知的校准溯源 | poison 标签只供事后评价；不保证因果唯一识别 |
| 模型输出的 thought 文字 | 可审计的存储内容、行为证据 | 不是访问隐藏心理状态，不能据此断言“撒谎”或“危险意图” |

目前支持 P3-A 的来源追踪；两个 P3-B 在线缓解协议均 FAIL，继续保留。正常回答与风险记忆
共存只能说明行为检测可能漏掉潜伏污染；识别并移除一个记录也不等于任务正确率恢复。
