# GRACE 以外的近期 causal discovery：筛选与执行协议

用户追加要求：除 GRACE 外接入其他成熟因果发现方法，优先 2025–2026；
“英国”已澄清为 causal，不是地域条件。选择依据是研究对象与假设匹配，
不以找到一个赢的算法为停止标准。

## 来源核验与筛选

| 方法 | 来源 / 状态 | 本次判断 |
|---|---|---|
| UnCLe | [NeurIPS 2025 论文](https://arxiv.org/abs/2511.03168)，[官方代码](https://github.com/etigerstudio/uncle-causal-discovery) | 接入官方实现；神经 Granger/扰动依赖，不自带完整可辨识保证 |
| Large Causal Models | [2026 预印本](https://arxiv.org/abs/2602.18662)，[官方代码与权重说明](https://github.com/kougioulis/LCM-paper) | 已核验；公开权重最多 12 变量、500 时间步、lag 3，不能直接吞下本次 14–28 维读取面板；不截去变量来制造可比结果 |
| TGES | [2025 论文](https://arxiv.org/abs/2502.06232) | 正式因果等价类搜索，但论文假设 Gaussian / faithful / i.i.d.，不是本次二值、可能非 faithful 的数据；不移植理论保证 |
| SPACETIME | [AAAI 2025](https://doi.org/10.1609/aaai.v39i18.34136)，[公开代码](https://github.com/srhmm/spacetime) | 已检查主入口和评分实现：GP 回归/MDL、联合搜索 regime 与图；当前二值 replay 不满足其典型连续残差设定，暂不接入 |
| PCMCI+ G² | 已安装的 tigramite 官方实现 | 与二值输入匹配的标准参照；先前已证实可独立复现 GRACE 的新读取集合 |

LCM 是近期预印本，不仅因为是 2026 就称为成熟方法。UnCLe 的 prediction-error
perturbation 是模型上的依赖诊断，不等于对真实 agent/世界的干预；其与实际
executor gate 干预之间的对应要由独立验证决定。任何理论保证都保留原条件。

LCM 的 12 变量限制并不排除它运行旧的 6 维类型写入编码；但那条编码的图在
下游已被给定实例链接架空，直接换模型不会自动修复该问题。因此本轮不为
凑一个 2026 名字，把低维旧编码上的可运行性当作新读取问题上的可比结果。

SPACETIME 的公开实现默认 `TimeseriesScoringFunction.GP`；`fit_gaussian_process`
使用 GP 回归而不是 Bernoulli likelihood。入口还要求 `truths.true_links` 等
字段用于搜索/日志调用，正式接入前需进一步审查其信息流；本轮没有向它提供
benchmark 真值或声称跑过该方法。这是适配筛选，不是它在任务上的负结果。

## UnCLe 接入与冻结规则（结果产生前）

- 官方代码独立检出在临时目录，commit
  `820da2a7690e8528ecf8d346cd44545624dfe85b`；不修改或复制其模型进本仓库。
  官方仓库当前没有 license 文件，代码不随本项目重新分发。
- 用官方 `run_unicsl`，不运行其依赖真值挑最优 accuracy threshold 的
  `run_grid_search`。仅消费官方返回的 parameter 与 permutation 图。
- 数据仍用已有 `read_gate_tcd.panel`：固定 HM3 executor，512 次 gate 试验，
  64 个独立 flip contexts。主比较用固定输入，不为了适应网络增加仿真世界。
- 小规模开发：Travel seed 0，dev episodes 0–2。首先做 1-epoch smoke，
  只检查调用、形状、方向和有限数值，不解释其性能。
- 正式拟合使用论文 NC8 配置：kernel 8、6 层、20 channels、学习率 .0003、
  重建 1,000 epochs、联合训练 2,000 epochs、模型 seed 0。不做 grid search。
  实际耗时若超出可行范围，记录为未完成，不把短跑当作论文配置结果。
- 结构本身先报 ranking/AP（对有限 flip reference），而非在测试标签上
  找 threshold。选读使用预先固定的 top-k 曲线 k=2/4/8，与相同 k 的随机
  读取及旧 PCMCI-G² 输出分开报告。top-k 不称为已识别 causal parents。
- 固定设置后，若开发调用与输出检查通过，用新 Travel seeds 60/61/62、
  每 seed 前 4 个 episode 验证；先前 50/51/52 不用来调本方法。
- 所有比较以 episode 为单位；三随机对照先在 episode 内平均；同时保留
  非 outcome 边，不能把只挑 outcome 子图的精度说成完整图精度。
- 不对这一轮新增 LLM 调用；先判断结构/选读证据是否值得花 actor 预算。

新结果单独保存，不覆盖第一轮 alignment 文件或将不同协议混成一张主表。

## 执行记录

接口 smoke 已通过；三个开发 episode 已完成原配置训练。两个读 4/8 条成功，
第三个在所有固定预算下失败；没有据此修改配置。新 seeds 60/61/62 各四个
episode 已全部完成，结果保存在 `results/real/hm3/alignment/uncle_s*.json`。

使用独立依赖目录，不替换当前环境的 torch：tsai 0.3.9、fastai 2.7.18、
fastcore 1.7.29、fastdownload 0.0.7、fastprogress 1.0.3、sparsemax 0.1.9；
实际 Python 为 3.10.16。公开代码 import 成功。

```bash
CUDA_VISIBLE_DEVICES=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
PYTHONPATH=/tmp/hm3-cd-alternatives-PuWnuZ/pylib:code \
python3 -B -m hm3.uncle_read_gate \
  --checkout /tmp/hm3-cd-alternatives-PuWnuZ/uncle \
  --seed 60 --split test --episodes 4 \
  --out results/real/hm3/alignment/uncle_s60.json

PYTHONPATH=code python3 -B -m hm3.uncle_report
```

临时路径只适用于本次环境；复现时重新检出上述 commit 并安装这些隔离依赖，
然后替换 `PYTHONPATH` 和 `--checkout`。其他两个测试 seed 为 61、62。

追加一个事后归因检查：UnCLe top-k 与 PCMCI-G² 阈值图的读取量不同，不能
直接比较正确数来宣称 neural 更好。因此对相同输入重算同一 PCMCI-G² 的
MCI p 值，固定按 p 递增、statistic 递减、record 原顺序打破 ties，取同样
k=2/4/8。只补同记录预算的 score-ranking 对照，不重训或改变 UnCLe。
这是事后诊断，不称为预注册主结果；token 数不保证相同。

## 新测试结果（已完成）

| 方法 / 固定读取数 | 2 | 4 | 8 |
|---|---:|---:|---:|
| UnCLe permutation score | 2/12 | 4/12 | 11/12 |
| UnCLe parameter score | 3/12 | 3/12 | 10/12 |
| PCMCI-G² MCI ranking（事后同预算检查） | 2/12 | 5/12 | 11/12 |

UnCLe permutation 的 8 条读取，相应随机对照为 16/36（每个 episode 三个），
配对增益 +47.2 pp，seed 内 bootstrap CI [27.8, 63.9]。此处只有 12 个
episode，不是 36 个独立随机样本；代理 token 匹配为 34/36，最大差 9 tokens。
完整历史平均 20.58 条，全读 12/12、空读 0/12。UnCLe 的两个分数对独立
flip reference 的 macro AP 为 0.901 / 0.860，这不是完整 causal graph AP。

**结论：成功接入并评估了一个 2025 年的独立官方方法，重复得到了有用的
依赖排序，但未证明它优于同预算 PCMCI-G²。** 不能把 11/12 对阈值图 7/12
归因于神经网络；同为 8 条时二者成功/失败指标完全一致。读取依赖的可用性
与算法独特优势是两条不同的主张。

三份测试共 12 次独立拟合，累计 episode 计时约 1,586 秒（含诊断/对照，
并行运行，非总 wall time）；没有新增 LLM 调用。

完整结果：[新方法报告](../results/real/hm3/alignment/uncle_report.md)；
同预算检查：`../results/real/hm3/alignment/uncle_budget_check.json`。
