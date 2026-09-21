# Codex 新 session 交接（2026-09-22）

后续9/22更新：请先读[RoomEnv受控验证与当前对齐结论](observed-memory-results-2026-09-22.md)。
这一轮已完成thinking配对、真实接线的PCMCI选读、原生系统比较、错误图对照和
实际LLM授权替代/拒答；仍未完成原agent-memory-state研究对象的证据，不能
宣称整篇目标达成。原始结果、冻结协议、无API汇总入口和验收表均从该页链接。
以下旧交接保留，勿把旧“未执行”状态覆盖到新面板，也勿用新受控结果撤销旧负结果。

## 0. 从这里继续，不要从旧 narrative 重新开始

用户希望完成 9/21 的逐项对照，真正符合 Yujia 的期望；明确允许重做不成立
的工作、使用 API 和更强模型。随后用户要求先结束过长的 session，转到新
session 继续。因此本次收尾**没有启动任何新实验或 API 调用**，不代表研究
任务完成，也没有获得 Yujia 对候选研究对象变更的确认。

用户已认可的当前判断：**成熟 causal discovery 的接入已经完成，完整研究
贡献尚未完成。核心缺口是结构贡献、真实 agent 收益与可信审计的证据，
不是算法名字不够多，也不是只差润色论文。**

工作目录：

```text
/mnt/dolphinfs/ssd_pool/docker/user/hadoop-nlp-hl02/hadoop-aipnlp/3A/multimodal/yangboxue/tts-sft/external/Memory-hm3-handoff-2026-09-18
```

首先完整阅读：

1. [9/21 对齐结论](yujia-alignment-results-2026-09-21.md)。
2. [冻结协议与归因规则](structure-alignment-protocol-2026-09-21.md)。
3. [近期 discovery 方法与已完成结果](causal-discovery-alternatives-2026-09-21.md)。
4. [机器生成的总报告](../results/real/hm3/alignment/report.md)及
   [UnCLe 报告](../results/real/hm3/alignment/uncle_report.md)。

以上材料优先于旧 full-status、旧 outline 和历史 Claude review。
原始 ledger 和 JSON 是数值依据；本文是索引，不替代原始证据。

## 1. 必须保持的需求解释

Yujia 要的是发现有意义的记忆时序结构，让**同一方法自然带来**两类收益：
记忆效果/效率，以及可执行的可信审计。8/21 她说两类都重要，不要替她断言
只剩审计或只剩压缩一条主线。先做 observed layer 1 是允许的；无需为了
满足要求强行做 latent layer 2，也无需证明神经 discovery 超过 PCMCI。

8/15 的要求包括明确变量、样本、时间步，匹配具体 repository/benchmark，
并共同 double-check 实验方案。用户提供的 9/20 记录要求说清 dependence
test，并使用成熟 discovery 算法。“英国”已经澄清为 causal 的笔误，不是
英国团队或地理来源约束。

| 逐项要求 | 收尾时状态 | 下一阶段验收点 |
|---|---|---|
| 变量、样本、时间步、场景明确 | 代码实际含义已澄清；候选新对象不同于旧 formulation | 写清原轨迹 memory-state 与 read-gate 两个对象，不默认为 Yujia 已认可后者替换前者 |
| 使用成熟 discovery | PCMCI+、GRACE、UnCLe 已实际运行 | 保留假设、配置与方法归因，不再为凑年份堆算法 |
| 恢复结构可靠 | 已有仿真及合成 HM3 的局部验证；没有完整图恢复证据 | 对实际研究对象独立验证；局部 outcome-parent 结果不能当全图 |
| 结构确实改善记忆 | 旧 learned type-filter 贡献未成立；新方案是小规模 executor 信号 | 同一 agent 场景，同预算、同接口、同输出规则，发现依赖有独立作用 |
| 正常正确输出下发现问题来源 | 两次新审计均未通过 | 冻结场景与规则后，独立重复验证来源依赖及干预效果，不换 case 直到成功 |
| 系统接入及代表性公平比较 | 接口与简单 baseline 有了；memory-system 同协议表有缺口 | 实际运行代表性系统，明确变体和适配；不拼接旧混杂行 |

不能承诺科学结果必定为正。完成实验、得到负结果、达到研究贡献要求是三个
不同状态；不能以花完预算、跑通模型或得到一个正数宣称最后一项完成。

## 2. 已完成证据：不要重复跑

### A. 旧结构归因审计

`results/real/hm3/alignment/controls_complete.json`：Travel、Shopping32，
seeds 30/31/32，24 格，1,536 请求、1,531 有效 episode-condition 评估。

- GRACE-open/parser 与 complete/parser 的**完整序列化输入 1,531/1,531 相同**。
  Complete 仍保留给定实例链接和 parser，仅移除 learned type-edge filter。
- GRACE-open×3 相同输入为 1,278/1,531，不能泛化 open 的结果到所有 GRACE。
- 错图、query-only、随机选读失败，不能抵消 complete 对照揭示的归因问题。
- 实际旧变量是对象类型的二值写入指示，不是逐字段 SCM；one-hot 互斥约束
  且缺失字段值。GRACE wrapper 也未沿用原回归的外生写入行掩码。
- `LearnedGraph` reference 是类型路径投影，不是直接机制真值。Travel 的
  bundle 更新实际依赖 `dinner_changed`，旧 `stay→bundle` 不能直接当真边。

### B. 非 discovery 的读取规则修正

`reader_fresh.json`：冻结 `component_key2` 后，用新 seeds 40/41/42，
18 格、1,152 个 executor 评估。它使用可见链接、同 key 响应先例及时间顺序，
不访问 gold action、隐藏参数或 required-read 标签；但**不是 causal discovery**。

- Travel c100：88.0% → 92.2%，配对 +4.2 pp [1.0, 7.3]。
- Travel 500：81.3% → 90.1%，+8.9 pp [4.7, 13.0]。
- Shopping 500：95.8% → 100.0%。
- 可能受益于合成 augmentation 的断开连通分量；不能当普适真实任务优势。

### C. 已完成真实 LLM 诊断

`actor_v1_closed/`：Travel seeds 30/31/32，每条件 23 个有效 episode，
c100/500，12 臂共 552 行、430 个不同输入调用。相同输入共享调用，不能当
独立重复。v1/verbose，输出上限 16,384，无 infrastructure failure。

| 读取方法 | c100 | 500 |
|---|---:|---:|
| component_key2 | .5652 | .3043 |
| complete/key2 | .3478 | .2174 |
| complete/parser | .3913 | .4783 |
| GRACE-open×3/parser | .3043 | .3478 |
| full | .2174 | .3043 |
| BM25-16 | .2609 | .1304 |
| recency-16 | .3043 | .2609 |

Full 每条件 4/23 截断，component_key2 无截断；不能把 c100 差异全部解释成
结构增益。500 持平，尚无稳定跨条件 LLM 提升。

`actor_v1_pilot/` 是此前**无效接口**诊断：44/46 输入缺选中记录所引用的
对象上下文，已停止并保留，不可并入有效表。后续代码修复了可见 referent。

### D. 两次正确输出来源审计失败

- `source_reliance_demo/summary.json`：full、删除可疑、删除中性、改变可疑值
  四种条件全部 3/3 正确，没有证明 LLM 依赖 executor 提议的可疑记录。
- `actor_source_audit/summary.json`：固定 `travel-s31-test-004`，39 calls；
  独立 full 0/3、候选 subset 2/3、阻断来源 1/3，无法支撑稳定正常输出审计。
  独立验证失败后没有替换 case。
- 来源权限必须由外部场景定义；子集成员身份不等于必要性，更不等于撒谎、
  私有思想或恶意意图。需要识别冗余来源与替代路径。

### E. 随机 read-gate：较窄的候选研究对象

`read_gate_tcd_s50/s51/s52.json` 与 `read_gate_attribution.json`：
12 个新 native Travel episode，每个 512 随机 gate 试验、64 个独立上下文/
gate 翻转检查，固定 deterministic executor，每个 episode 分别拟合。

- GRACE+G²：11/12 选读正确，平均 3.83 records；匹配随机 9/36。
- PCMCI-G² 单独得到 **12/12 完全相同的 outcome-parent 集合**，同样 11/12。
- PCMCI-ParCorr：7/12；其检验和 alpha 均不同，不能用来归因神经 refinement。
- Full 12/12、empty 0/12；实际历史平均 18.25 条。属于压缩/保持任务结果，
  不是比 full 更准。有限 flip reference 不是总体真图。
- 独立随机化 gates 之间仍被推断出虚假 lagged 边：GRACE 91、ParCorr 24；
  没有恢复可靠完整图。固定失败例漏了两个效应 1/64 的低频 gate。
- 这里的 lag 是“试验输入→下一行试验输出”，**不是原 agent 记忆演化时间**。
  使用 benchmark 正确性标签，不是无标签部署；没有 LLM/跨 episode 摊销证明。

`read_gate_structure.svg` 是实际依赖和固定失败例示意，已检查；它不是已完成
的“正常输出却依赖问题来源”审计 demo。

### F. UnCLe 2025 扩展全部结束

`uncle_s60/s61/s62.json`、`uncle_report.md/.json`、`uncle_budget_check.json`：
全新 12 个 episode，固定 NC8 配置，官方 `run_unicsl`，未用真值调 threshold。

| 方法 / k | 2 | 4 | 8 |
|---|---:|---:|---:|
| UnCLe permutation | 2/12 | 4/12 | 11/12 |
| UnCLe parameter | 3/12 | 3/12 | 10/12 |
| PCMCI-G² ranking（事后同记录预算） | 2/12 | 5/12 | 11/12 |

UnCLe k8 随机 16/36；full 12/12、empty 0/12；原历史平均 20.58 条。
与同预算 PCMCI 没有 utility 优势。排名 top-k 不称为已识别 causal parents。
三随机对照先按 episode 平均；token matching 是 cl100k_base 代理，有残差。
本轮无额外 LLM API 调用。

LCM 2026、TGES 2025、SPACETIME AAAI 2025 只做了来源、假设、实现筛选，
**没有运行**。LCM 公开模型最多 12 variables，不适配当前 14–28 维面板；
其他两者也有分布/实现适配问题，详见专门文档，不写成负实验结果。

## 3. 下一 session 应做什么

用户希望解决所有真正必要的缺口，并允许更强模型。先形成一个简短的可证伪
执行方案，再实施；不继续沿用“目前已足够、冻结 narrative”的旧建议。

1. **研究对象先对齐。** 并列写清两个对象：原轨迹内 observable memory
   states/write dynamics；随机 read-gate 对固定策略的依赖。前者更直接延续
   原 formulation，后者是已试验的候选收窄。若必须用后者替换论文主线，
   向用户明确该科学选择；不能把用户授权继续工作说成 Yujia 已认可 pivot。
   未有外部发送授权，不联系 Yujia；可准备本地确认页。
2. **在真实 agent 使用中建立发现依赖的独立贡献。** 先审计可用 benchmark
   与表示；冻结 discovery/reader/protocol 后，用 fresh held-out episodes，
   与 complete/no-discovery、query-only、三份固定错误结构、matched budget、
   简单检索比较。记录对象上下文、实际序列化、token 残差、全部排除项。
   不为使 preferred method 获胜而改任务；合成 HM3 明确标注为合成。
3. **补稳定的正确输出来源审计。** 更强模型可用于减少 actor 能力不足，
   但必须在测试前固定模型、场景与规则；独立检验 full 正确、阻断/替换
   问题来源的效果、中性干预和安全替代。报告全部冻结案例，保留失败率；
   不通过无限挑 case、根据输出改 prompt 或泄漏答案制造 demo。
4. **补同协议代表性 memory systems。** 当前新一轮没有 Mem0/A-Mem/LightMem。
   旧 v2/seed/截断混杂结果不能拼表。实际审查 adapter，Mem0 raw 必须标 raw，
   不把简化 embedding baseline 写成完整 Mem0。不要沿用“Python 3.13 所以
   LightMem 装不了”的旧理由：本机实际 Python 3.10.16。
5. **最终逐项验收。** 同一结构/方法的 memory 和 audit 两条证据要接起来。
   完成可复现报告、结构可视化、统计不确定性、失败和成本披露，再判断是否
   达标。若证据仍不支持贡献，就如实保留未完成，不靠改名或 narrative 补足。

独立重放验证在 audit 或 LLM read-dependence 成为主要证据时是必要的；此前
“这周不做 held-out validation”的旧建议不能自动延续。无需为了叙事重跑
已经被撤回的 generic ddmin scaling 主张。

## 4. 理论、写作与 baseline 红线

- 已撤回通用 ddmin `O(k log n)`、唯一 frontier 与任意正确子集等价的主张。
  精确 oracle 一般给 1-minimal；monotonicity 才支持 inclusion-minimal。
  Generic worst case 可为 quadratic；deterministic policy 本身不保证 monotone。
- 不能从 CI failure 推出所有 observational estimators 信息论上都不可能。
- Shopping v2 accuracy headline 受截断混杂，不能恢复；未截断子样本分析也是
  outcome-conditioned 诊断，正式协议需要一致且充分的输出预算/格式。
- Parser/给定链接的正结果不归于 discovery；executor 的正结果不归于 LLM。
- “MemoryArena substrate” 仍是合成生成器换名称及接口，不是原生真实
  MemoryArena task。原生 Travel 旧 campaign 已被审计关闭。
- 使用更强模型要重新记录请求和返回模型 ID、prompt、token 限制、重试、
  截断率和费用；旧 DeepSeek 行不能直接与新模型行组成方法效应表。

## 5. 工作区、API、依赖与复现

- 初始分支基点为 `bc370d5`；当前有较多先前 Codex 留下的未提交修改和新增
  文件。保留它们与所有历史结果；本次收尾不 commit、不删除、不重置。
- API 配置在用户提供、被忽略的 `api/api.txt`。不要打印、写入报告或提交
  密钥。先前 endpoint 为 `https://www.autodl.art/api/v1`，请求模型
  `deepseek-v4-flash`，返回 `deepseek-v4-flash-0731`。更强模型尚未选择或调用。
- 记录的历史调用按旧费率合计约 **$27.3471795**，不是供应商实际账单；
  connectivity 检查/被停止时未记账的在途请求可能另外计费。
- Python **3.10.16**。UnCLe pinned checkout：
  `/tmp/hm3-cd-alternatives-PuWnuZ/uncle`，commit
  `820da2a7690e8528ecf8d346cd44545624dfe85b`；隔离包目录同级 `pylib`。
  官方仓库无 license，未 vendor。临时目录不保证新环境存在。
- 隔离依赖：tsai 0.3.9、fastai 2.7.18、fastcore 1.7.29、fastdownload 0.0.7、
  fastprogress 1.0.3、sparsemax 0.1.9；现有 torch 2.9.0+cu126 未替换。
- GPU 上可能有其他用户/任务进程，不触碰。收尾通过进程名检查未发现本轮
  alignment、read-gate、UnCLe、reader 或审计实验 runner 仍在运行。
- 前阶段验证：7 项 unittest 通过，17 个相关 Python 文件语法检查通过。
  本次收尾检查 `git diff --check` 通过；不要将旧实验验证误写为新实验结果。
- 未调用 subagents。遵循新 session 的实际指令；没有明确请求时不要自动
  派生 agent。先检查适用 AGENTS.md/skills；此前没有发现适用 AGENTS.md。

主要代码均在 `code/hm3/`：`structure_alignment.py`、`reader_repair.py`、
`alignment_actor.py`、`alignment_report.py`、`merge_alignment_controls.py`、
`memory_reliance_demo.py`、`actor_source_audit.py`、`read_gate_tcd.py`、
`read_gate_attribution.py`、`alignment_figure.py`、`uncle_read_gate.py`、
`uncle_report.py`、`uncle_budget_check.py`、`test_structure_alignment.py`。
原 `llm.py`/`scaling.py` 已接入 component_key2，`replay.py` 修改了保证说明。
多份旧文档已有更正 banner；不要覆盖或移除来恢复旧主张。

只读检查/测试入口（无需额外 API）：

```bash
git status --short
git diff --check
PYTHONPATH=code python3 -B -m unittest hm3.test_structure_alignment
```

需要重建报告时可以运行 `hm3.alignment_report`、`hm3.uncle_report`；它们会写
报告文件，不是纯只读检查。没有必要为了接手重复昂贵实验。

## 6. 给新 session 的启动语

> 请完整阅读 docs/CODEX-SESSION-HANDOFF-2026-09-22.md 和其中指定的三份
> 对齐文档，核对现有代码及原始结果后继续。我要逐项解决 9/21 对照中真正
> 必须解决的问题，以符合 Yujia 的期望；API 和更强模型可以用。不要重复
> 已完成实验，不要把接入算法等同研究完成，不要为了正结果更换案例或隐去
> 失败。先明确研究对象及冻结的验收方案，再做结构独立贡献、真实 agent
> 收益、正常正确输出来源审计和同协议代表性 baseline。需要改变主线时
> 明确说明科学选择，不能假定 Yujia 已同意。保留当前全部未提交工作。
