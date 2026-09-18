# 新工作区权威交接：重新实现真正的 causal memory（2026-09-19）

本页是迁移到新工作区时的首要入口。旧 `HANDOFF.md` 保存完整历史，但其中多轮状态已经被后续实验覆盖。**不要自动恢复 `autodl_travel_20260918`；该全表已主动暂停。**

## 1. 真正要实现和验证的命题

Agent memory 应被表示为可观察的 write--hold--read 时序过程。存储记录只有在被读取的 access regime 下才可能影响动作，因此方法需要：

1. 从 agent trajectory 估计随 access regime 改变的依赖；
2. 正向沿依赖选择当前决策真正需要的历史记录；
3. 反向沿 write--read--action provenance 定位驱动异常动作的记录；
4. 用匹配对照分别证明学得结构相对直接 lookup 的增量、相对全历史的读取效率，以及无标签审计能力；
5. 在结构无增量或识别失败时报告边界，不把结构化 parser、索引或序列化收益改名为 causal discovery 收益。

项目可以主张统一的 temporal-dependency/provenance framework。只有当两个方向确实消费同一张估计图时，才能写“the same learned structure is used in both directions”。

## 2. 可直接复用的可靠部分

| 内容 | 路径 | 用途与边界 |
|---|---|---|
| write--hold--read formulation | `causal_memory_formulation.tex` | 变量、regime 和论文表述的起点 |
| regime-conditioned estimator | `code/regime_grace.py` | 当前真正体现 access-regime conditioning 的实现 |
| E0 受控结果 | `results/regime_grace_e0.json` | 三档噪声下 conditioned 2/2，tested blind/additive 0/2；只证明这些受控设置 |
| Travel memory adapter | `code/arena_causal_memory.py` | 可复用存储、序列化和选择接口；当前 learned selector 的时间语义不能沿用 |
| implicit task transformation/audit | `code/travel_implicit.py`、`docs/travel-implicit-v1-2026-09-18.md` | 可复用不可变 gold、历史可见性和 transformation audit；不能作为 graph necessity 任务 |
| 完整无标签运行 | `code/minja_autodl_campaign.py`、`code/autodl_agentpoison.py` | 可复用冻结、运行、用量和完整性框架；本轮 MINJA 结构臂是负结果，AgentPoison 的 cluster expansion 不能全归因于图 |
| 停跑审计 | `docs/travel-campaign-pause-decision-2026-09-19.md` | 当前 Travel 为什么不能承担主要 causal claim |

## 3. 当前 Travel 为什么不能作为新实现

当前 Travel 图在 219 个 train episodes 上以旅行者轮次为时间轴学习 slot-activation lag。运行时却把折叠后的 slot ancestor 用于直接引用记录的同一个 `(person, day)`。训练边和 traversal 的时间语义不一致。

当前图为 12 条边，人工依赖边对照 TP=12、FP=0、FN=18，precision=1.0、recall=0.40。GRACE 输出与 PCMCI+ skeleton 完全相同。能实际扩展选择的跨 slot 关系只有 `breakfast -> lunch` 和 `breakfast -> dinner`；固定 demo 中 ours/query_only/noGcompact 只选择 5/42、4/42、42/42 cells。

implicit-v1 又把 future notice 与 source traveler 的 final plan 放在同一个历史 chunk。普通检索命中一个 chunk 时同时得到依赖说明和 source value；每个 episode 只有约 5--8 个 chunk，而多种 baseline 的 retrieval limit 已覆盖全部历史。因此它主要测写入保真和 context compression，不能有力区分 learned graph 与维护良好的 ledger/`memory.md`。

暂停、最后三条长时间未结束 case 的终止动作及覆盖率见[停跑决定](travel-campaign-pause-decision-2026-09-19.md)。旧 controller 和 watcher 已关闭；不要因为旧协议还有未完成 case 就恢复全表。

## 4. 新实现的硬性设计条件

### 4.1 学习对象和运行时必须一致

- 预先定义一个 sample、一个 variable、一个 time step 和一个 regime。
- 若图在 record/event 时间轴上学习，runtime 必须沿 record/event 节点和实际 lag 遍历。
- 若 runtime 使用 `(entity, day, slot)` cell graph，训练数据也必须在相同 cell 节点和时间语义上估计边。
- 不得把“跨旅行者轮次的 slot activation association”折叠后当成“同人同日 slot causal edge”。
- 每次 write、read、action 均记录稳定 ID 和 provenance；selector 与 auditor 只能使用运行时可见信息。

### 4.2 任务必须给图留下增量空间

- notice、依赖描述和 source value 应是不同记录；检索到 notice 不应同时获得答案来源。
- query 和 target-index metadata 不能直接给出完整 source dependency。
- 至少包含需要两跳或多跳 traversal 的样本，以及同名、同类型、不同 episode 的干扰记录。
- 历史池要大于各 baseline 的 `top_k`，但扩大历史只能证明 retrieval scalability；graph necessity 还需要 `ours > zero-edge/query-only`。
- 必须有 lookup 可解的 matched negative controls，用来界定何时图不必要。

### 4.3 公平对照

至少保留：

1. `query_only`：相同 parser/index/serialization，清空 learned edges；
2. `noGcompact/full`：相同表示，读取全部可用历史；
3. BM25 与 dense retrieval：匹配可见历史和读取预算；
4. PCMCI+ skeleton：区分 GRACE refinement 的增量；
5. 三份预先固定的 wrong/permuted graph，并匹配选择 cell/token 数；
6. 强 relational/program baseline：允许从相同 train trajectories 学规则，不能故意削弱；
7. oracle graph：只作上界，不进入方法输入。

主比较是 `ours vs query_only`。`ours ≈ noGcompact` 且读得少只能支持效率；`ours ≈ query_only` 表示 ledger 已足够；`ours < query_only` 表示图扩展有害。不能用 `ours vs BM25/full` 代替图的单因素消融。

### 4.4 冻结和验收

- train/dev/test entity、episode 和 mechanism composition 分离；test graph/evaluator artifact 与 runtime 物理分离。
- 在 test API 调用前冻结 generator、图估计器、selector、baseline、预算、失败策略和 primary endpoint。
- primary endpoint 同时报告任务正确性与读取成本；统计以独立 world/episode 为单位，重复生成先在 episode 内聚合。
- API/transport failure 可按预登记规则恢复；语义、JSON 和工具调用失败不得按结果重采样。
- 完整报告 learned graph、PCMCI+、wrong graph、zero-edge 和 lookup 的 paired intervals，不只报告 aggregate mean。

## 5. 建议的最小推进顺序

1. **语义单元测试：** 构造一条两跳 write--hold--read trajectory，确认训练图的 node/lag 与 runtime 选择出的 record ID 完全一致。
2. **离线 identifiability gate：** 在不调用 LLM 的 held-out worlds 上要求 `ours > query_only`，并验证 wrong graph 下降；过不了就不扩大 API 实验。
3. **小规模真实 actor pilot：** 10--20 episodes，只跑 ours/query_only/noGcompact/full/strong program，检查任务差异和实际 read set。
4. **冻结确认实验：** pilot 通过后才扩大，并保留所有失败与 token accounting。
5. **审计实验：** 先验证同一 graph artifact 是否真的被正向 selector 和反向 provenance traversal 同时消费；否则分别命名两种估计器和证据。

## 6. 已完成证据的真实状态

- E0：支持受控条件下的 regime-conditioned gated-edge recovery。
- Travel implicit-v1：暂停；可作系统兼容性、保真和效率档案，不支持 graph necessity。
- MINJA AutoDL：8,400/8,400 tests 完成；真实结构臂 10/10 未选边，frequency-regime 与 matched random 没有明确增量。这是识别边界。
- AgentPoison AutoDL：352/352 trajectories 完成；直接无标签定位 1/2，冻结 cluster expansion 后 2/2；在线结果与 no-op、旧 FAIL 必须分别报告。
- Hidden Mechanism v3：仓库中只有预注册，没有可核验的 `0.88 vs 0.06` 完成结果，不能作为已有证据引用。

完整的 MINJA、AgentPoison 和 Travel 最小复核包存放在私有 Hugging Face dataset：[zrp1211/causal-memory-handoff-20260919](https://huggingface.co/datasets/zrp1211/causal-memory-handoff-20260919)。Git clone 后不需要下载旧 Travel raw trajectories 就可以开始新实现。

## 7. 新工作区启动检查

```bash
git clone https://github.com/mianwu01/Memory.git
cd Memory
git checkout claude/artifact-ordering-inzyf3
python3 -m compileall -q code
PYTHONPATH=code python3 -m unittest discover -s code -p 'test_*.py'
python3 code/regime_grace.py
```

需要复核完整结果时，在已登录 Hugging Face 的环境中下载：

```bash
hf download zrp1211/causal-memory-handoff-20260919 \
  --repo-type dataset --local-dir external-results/causal-memory-handoff-20260919
```

API token 只应通过环境变量或工作区私密文件配置。`.secrets/`、`.env`、`deepseek_apikey.md` 和 `.tmp/` 均不得提交。
