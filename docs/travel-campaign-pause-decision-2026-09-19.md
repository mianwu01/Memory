# Travel 正式实验暂停新增调度决定（2026-09-19）

状态：**已停止 campaign；保留全部既有结果。** 新增 dispatch 先被暂停，大部分已发出的 case 自然结束；最后 3 个持续 33--65 分钟仍未结束的 LightMem case 在工作区迁移前终止。该决定不是删除或否定整个 Travel 实验，而是停止继续补齐信息增量较低的 1,950-case 全表。

## 决定

2026-09-19 对 Travel implicit-v1 的学图和运行时链路复核后，停止主 controller 派发新的正式 case：

- `results/real/autodl_travel_20260918/dispatch_control.json` 已设为 `pause_dispatch: true`；controller 已确认 `dispatch_limit=0`。
- 暂停后先允许已经启动的 actor case 自然结束；迁移前仅终止最后 3 个长期未结束的 LightMem case，并保留其不完整状态、事件和已记录用量。
- 已停止“当前恢复批次结束后继续无限启动恢复轮次”的 supervisor；已经启动的有限恢复批次不强杀。
- 不删除、不改写、不按表现挑选已经产生的任何结果。
- 在完成覆盖率审计和重新定义科学问题前，不恢复十臂全表调度。

最终停止记录为 `results/real/autodl_travel_20260918/termination_record.json`：终止的 case 是 `implicit/lightmem/{133,135,142}/r2`，同时关闭已暂停的主 controller 和只读 watcher。任何新工作区都不得将这三例标记为 complete，也不得自动恢复旧 campaign。

暂停附近最近一次独立文件扫描记录为：全表 1,710/1,950 complete、77 failed、62 running、101 not started；预登记核心面板 819/900 complete、21 failed、60 尚未终态。该扫描只读取运行状态和用量，没有读取部分任务分数。主 controller 自身的 `campaign_state.json` 不包含其他 dispatcher 后来写入其内存状态表的完成更新，因此进度以 `monitoring/health_*.json` 对磁盘 case state 的扫描为准。

## 为什么暂停

### 1. Travel 中的图没有实现论文所述的 access-regime gated discovery

Travel 用 219 个排除 dev/test 的训练 episode，在七类 slot 的需求激活序列上运行 PCMCI+ skeleton 和 GRACE refinement。当前 `ind` 图有 12 条边，相对解析出的 30 条 lagged ground-truth edges 为 TP=12、FP=0、FN=18，即 precision=1.0、recall=0.40、F1=0.571。GRACE 保留的边集与 PCMCI+ skeleton 完全相同；当前实例没有显示 refinement 带来额外删边或加边。

Travel 没有调用 `regime_grace.py`，也没有估计 write/hold/read regime-gated edge。受控 E0 才是 regime-conditioned gated-edge recovery 的证据。Travel 只能描述为使用 discovered type-level temporal graph 的 dependency-guided selection。

### 2. 学习时和使用时的时间语义没有对齐

训练视图中的 `t` 是旅行者轮次。图边表达前一旅行者与后一旅行者之间 slot activation 的 lagged association。运行时 `_compact_learned_select` 却把折叠后的 slot ancestor 应用于直接引用记录的同一个 `(person, day)`：例如引用某人的 lunch 时，为同一个人、同一天补 breakfast。

因此当前 selection 把跨旅行者轮次学到的边当成同人同日 slot filter。论文不能把这一运行时操作表述为沿学到的 Travel 时序依赖传播。后续若保留 Travel 图实验，必须先统一训练变量、lag 与运行时 ancestor 的语义。

### 3. 当前图相对精确 lookup 的增量很小

12 条边主要是 breakfast、lunch、dinner、accommodation 的自依赖。自依赖不会在直接引用的 cell 外加入新内容。能改变选择的跨 slot 关系只有 `breakfast -> lunch` 和 `breakfast -> dinner`；运行时效果主要是引用 lunch/dinner 时额外加入同人同日 breakfast。事前固定 demo 中 ours/query_only/noGcompact 分别选择 5/42、4/42、42/42 cells，清楚显示学得边只增加一个 cell。

这使 `ours` 相对 `query_only` 不太可能产生稳定的任务分数增量。实验结果仍需以完整、预先定义的比较为准，不能把这一结构分析写成已经观察到的分数相等。

### 4. implicit-v1 仍允许强单跳 lookup

future notice 放入最新已见 source traveler 的历史 chunk；常规 memory baseline 收到的原始 chunk 同时包含该 notice 和 source 的 final plan。检索命中该 chunk 时通常同时得到依赖说明和被引用计划，不需要完成独立的“先找 notice、再沿边找 source record”的第二跳。

每个 episode 只有约 5--8 个历史 chunk，而 Dense、Mem0、LightMem 的 retrieval limits 分别可达到 10、200、60，常常等价于读取全部现有历史。因此全表更适合回答写入保真、系统兼容性和上下文效率，难以识别 learned graph 相对 lookup 的必要性。

## 已有实验仍然能回答什么

保留的数据仍可用于下列有边界的结论：

1. 十种 memory implementation 能否接入原 MemoryArena actor、工具和完整计划输出流程。
2. `ours` 相对 `noGcompact/full` 的任务分数与实际读取 context/cell/token 取舍。
3. `ours` 相对强 `query_only` ledger 的经验边界；若无增量，应作为 lookup 已足够的负结果报告。
4. 学得 type graph 的具体边、precision/recall，以及 GRACE 与 PCMCI+ 在该实例上输出相同边集。
5. 各 native memory baseline 的写入保真、完成率、延迟、token 和失败模式。

现有结果不能单独支持：

- Travel 证明 regime-gated causal discovery；
- GRACE refinement 在 Travel 中优于 PCMCI+；
- learned graph 优于维护良好的 `memory.md` 或结构化 history lookup；
- 同一张 Travel 图同时实现 selective reading 与 provenance auditing。

## 后续原则

1. 等已发出的 case 全部落盘后，只做状态、覆盖率和用量审计；不把非随机的 valid-only subset 当作冻结主表。
2. 不因已经投入大量调用而自动补齐十臂全表。
3. 若现有覆盖足够形成预先定义的完整配对，优先保留 implicit 下 `ours / query_only / noGcompact / full` 的最小比较；需要补 case 时先单独登记范围，不恢复全部低信息量组合。
4. 新 Travel 设计必须让图的训练时间单位与 runtime traversal 一致，并让 notice 与 source value 形成真正需要跨记录解析的依赖；多 episode 混池只能作为 retrieval-stress/scale 实验，不能自动证明 causal graph necessity。
5. Hidden Mechanism v3 当前只有预注册文档，仓库中没有可核验的 `0.88 vs 0.06` 完成结果；在产生冻结结果前不能用它替代 Travel 证据。
6. 摘要中的 Travel 结果句等待可审计的终态比较。当前只可预写方法和证据边界，不预写 `ours > query_only` 或 `ours = query_only` 的数值结论。

## 相关材料

- [Travel implicit-v1 协议](travel-implicit-v1-2026-09-18.md)
- [AutoDL campaign 总记录](autodl-campaign-2026-09-18.md)
- [当前 abstract 证据边界](yujia-abstract-draft-2026-09-18.md)
- [下一轮实验建议](next-experiment-plan-2026-09-18.md)
- [核心面板登记](../results/real/autodl_travel_20260918/registered_core/protocol.json)
- [当前图产物](../results/development/autodl_20260918/graph/typegraph.json)
