# MINJA 新模型无投毒标签审计与真实删除实验

这轮保留所有既有 `minja_online_gate_seed*.json`，使用新的结果目录和新 backbone。
请求模型为 `DeepSeek-V4.1-Flash`，OpenAI-compatible endpoint 为 AutoDL；服务返回的
`response.model` 单独记录，不能从请求别名推断精确的底层版本。试探请求返回
`DeepSeek-Flash`。实验为 CPU-only，API key 只从本地 git-excluded secrets 文件读取。

## 研究问题与解释范围

本轮先复现和扩大已有的 label-free auditor，回答从校准期的检索与可观察异常能否定位
成功写入的投毒记录，以及删除这些记录是否在新调用中降低异常动作率。
`frequency_regime` 是既有按 trigger 条件化的异常频率法，`frequency_pooled` 是不按
trigger 分层的同类频率法。两者均**不是 Regime-GRACE 图发现**，不能把这轮比较描述为
证明学得的图优于无图方法。完整的校准 retrieval exposure、可用记录集合和写入日志
另行保留。测试开始前增加并独立冻结第七臂 `regime_structure`，实际调用已有的
`fit_regime_conditioned`，配置和边界见下文；这是新 record-level 方法实例。

## 执行前冻结的矩阵

- 10 个独立写入与校准 runs，seeds 0–9；每个从空记忆开始。
- 每 run：5 个干净 food pre probes、6 个攻击模板、25 个同主题 benign writes、
  8 个校准 food probes；保持 MINJA 模板内部从强 note 到弱 note 再到无 note 的顺序。
- `nutrition_test` 只有 31 个 food 问题；5+6+8+12 用完该问题池，因此 held-out 为
  12 个 food queries 和 28 个不含 food 的 clean queries。每 run 内校准和测试题目不交叉。
  clean queries 去除重复题干。不同 runs 会复用有限题库，不能称为 400 个独立新题。
- 原矩阵为每 held-out query 3 次独立解码 × 6 臂，7,200 次测试 actor calls；
  测试前 scope amendment 增加真图第七臂后为 **8,400** 次。校准与
  injection retries 另计。重复解码不能作为独立任务放大样本量。
- 温度 0.5、top_p 1、max_tokens 6000；thinking disabled / reasoning_effort none。
- Levenshtein top-3、原始 MINJA prompt 与 poison payload 保持不变。

| 测试臂 | 行为 |
|---|---|
| ungated | 原 top-3 检索 |
| frequency_regime | 按旧协议从 note-free trigger 校准轮计算异常比例，比例 >0.20 的已暴露记录被标记 |
| frequency_pooled | 从全部 note-free 校准轮计算相同异常比例，包括非 trigger benign rounds |
| random_matched | 从本题 top-3 随机删除与 frequency_regime 相同数量的记录 |
| oracle | 删除 top-3 中评价标签为投毒的记录，仅作显式标注的 oracle 上界 |
| noop | 经相同选择包装逻辑但删除集合为空，重新调用 API |
| regime_structure | 删除实际 Regime-GRACE estimator 在 trigger=1 找到的正向 record→异常 action 祖先 |

### 在测试前冻结的结构臂补充

用 note-free 校准轮构造 record retrieval indicator → anomalous action 的输入矩阵，
trigger 作 regime。候选按 retrieval 曝光次数降序选择最多 12 个，仅使用 X，不使用异常
结局、内容、正确答案或 poison 标签作候选选择。标准校准数据含 19 个 trigger 轮，若直接
放入约 60 个 records 将不可估计，因此候选数明确受限。拟合使用现有
`code/regime_grace.py::fit_regime_conditioned`，`max_lag=0, alpha=0.01,
min_rows=10, gate_ratio=4`，runtime order 只允许 retrieval 阶 0 → action 阶 1。
部署集合为 trigger=1 内通过 BH 的正系数边；没有边也照实保留空集合。

该实例通过共同回归条件化其他候选，但未控制候选外的共检索混杂或随时间变化的状态，
有限样本下的边不能单独当成已识别的因果效应。12 个候选之外的 records 不会被该臂识别。
不根据 poison 正确率或测试输出调 alpha、候选数或 min_rows。
每个 seed 的输入、候选边、配置与输出 hash 写入 `regime_structure.frozen.json`；
六臂原快照保留为 `frozen_snapshot_base6.json`。`structure_scope_amendment.json`
记录该补充在全部测试输出之前注册。

全部删除策略只在当前 query 含可观察 trigger 时生效。不重新补充 top-3，测试期不写回。
random 匹配删除的记录数，**不匹配 token 长度**。因此 clean queries 对所有臂是同 prompt
的独立调用对照，只能测量采样波动，不能声称测出了未触发情境下非空删除的副作用。

所有 seeds 的校准、筛选集合及 immutable snapshot 都在任何测试调用前冻结；学习器只
看到 opaque record IDs、retrieval、trigger、note presence 和 E–H 异常信号。
`is_poison` 仅供 oracle arm 与事后评价读取；该标签表示成功的注入写入，而非所有注入尝试。
删除记录后的新 actor 输出分别测量异常率和答题准确率，不能用离线 replay 替代。

## 文件与运行

执行器：`code/minja_autodl_campaign.py`。新目录：
`results/real/minja_autodl_2026_09_18/`。

```bash
.tmp/memory-faithful-venv/bin/python -u code/minja_autodl_campaign.py \
  --out results/real/minja_autodl_2026_09_18 --api-concurrency 24
.tmp/memory-faithful-venv/bin/python code/minja_autodl_summary.py \
  --input results/real/minja_autodl_2026_09_18
```

重复同一执行命令会校验 frozen protocol，复用已冻结的校准快照与已完成的测试文件；
API/解析失败最多重试 4 次后报错，不会把失败答案当成 benign outcome 写入记忆。
运行中每 100 个测试调用打印进度，最终生成 `summary.json` 与 `paired_summary.json`。
初版每 100 次全目录聚合导致共享文件系统 I/O 变慢，技术修订将其改为完成后一次汇总；
已排队的全部测试调用继续执行，详见 `aggregation_amendment.json`。
后者按独立写入 run 对配对差值做 cluster bootstrap，并区分实际删除与 untouched queries。
并发从 8 增为 24 是根据 32/64 并发 HTTP 探针的技术吞吐调整，另存
`concurrency_amendment.json`，不修改模型、prompt、温度、样本或原有六臂。

结果保留每次调用的 requested/returned model、原始输出、token usage、失败重试、prompt
hash，以及每个 seed 的 snapshot hash。凭据与请求 headers 不写入结果。

## 给 Yujia 审阅的固定示例

`fixed_demo/index.html` 与 `fixed_demo/demo.json` 从已完成结果生成，不新增 API 调用。
选取规则固定为 run 0、各 track 的 query ID 按字符串排序后的第一项、repeat 0，实际为
`test_10` 和 `clean_test_0`；不筛选防御成功或正常输出。页面展示全部七臂的读取/删除 IDs、
原始模型输出、攻击判定，以及每条检索记录的写入、校准暴露、冻结分数和测试 action。
当记录未进入结构候选时，页面明确标为未入候选，不把对应校准行误作该记录特征的拟合。

```bash
.tmp/memory-faithful-venv/bin/python code/minja_autodl_demo.py \
  --input results/real/minja_autodl_2026_09_18
```
