# 基准审计第二轮:AMA-Bench T0 与 RoomEnv-v3 T0(2026-08-20)

> 承 `benchmark-audit-c1c4.md`(第一轮)。本轮按 GPT 提议的协议执行:
> 先审 AMA-Bench(TextWorld synthetic),no-go 则转 RoomEnv-v3。
> 脚本:`code/ama_t0.py`、`code/roomenv_t0.py`;仓库克隆在 `benchmarks/`。全程 CPU、零 LLM 调用。

## 0. GPT 候选表的核实结果(先修正前提)

| GPT 声称 | 核实 |
|---|---|
| AMA-Bench 提供 `relevant_turn_indices` | ❌ **不存在**。唯一相关脚本是 BabyAI 的事后正则抓取,且把 gold 答案里的 step 也并进去——用作 evidence gold 是循环论证 |
| AMA 的 causality graph 是 LLM 从相邻事件抽取 | ✅ 确认,且更糟:chunk 局部、默认关闭(配置键拼错 `casual: false` 使开关永远失效)、从不参与评分 |
| AMA-TextWorld 可无限生成轨迹 | ⚠️ 生成器在仓库里,但**发布数据集里没有任何 TextWorld 行**;再生成需装 TextWorld,且单轨迹脚本有 bug(QA 恒为空),B3 全"No",A3 有作用域 bug |
| RoomEnv-v3 隐状态完整、规则确定 | ✅ 确认,且优于预期(见 §2) |
| RMBench 机器人开销大 / MemGym 只是评测框架 | ✅ 均确认(RoboTwin+训练权重;可插拔记忆接口五赛道) |
| DynamicMem | ❌ 无法解析到任何匹配仓库,**待 GPT 提供链接,否则视为不可核实** |

## 1. AMA-Bench:发布数据 T0 → **主基准 no-go,保留为下游评测**

发布集 `test/open_end_qa_set.jsonl`:208 行 / 2,496 QA;六域
(TEXT2SQL 51、SOFTWARE 36、WEB 31、Game 30、EMBODIED_AI 30、OPENWORLD_QA 30)。
**逐行核实:0 行带 `state_snapshots` / `events` / `sub_type`**;模拟器 facts 在生成时
解析后即丢弃、未序列化。评分仅 LLM judge(judge 间一致率 0.33–0.49,README 自报)。

T0 度量(step 引用泄漏 + BM25@10 证据定位):

| 量 | 数值 |
|---|---|
| 零检索题(答案引用的 step 已全在题面) | 424 / 2,496(17%) |
| 答案不引用任何 step(无法按 step 定位) | 955(38%) |
| 可定位题的 BM25@10 证据召回 | **0.565**(SOFTWARE 0.19,Game 0.36,EMBODIED 0.42) |
| 因果 B 类:Game/B、EMBODIED/B 证据召回 | **0.235 / 0.263** |

**裁决**:C4 有真实空间(问句检索定位不了证据,与 LongMemEval 的 0.95 恰成对照),
但 **C3 在发布数据上不可能成立**(无模拟器状态、无 gold 边、无子类型标签,
评分器不可靠;仓库审计另证实多款题型把前提写进题面,含"答案是题面子串"的退化题型)。
→ 按预先议定的规则:**不作主基准;保留为"因果记忆方法的下游收益评测"**,
它的 B 类低证据召回正是将来展示下游增益的地方。
若坚持在 AMA 上做结构评测,唯一路线是打补丁重跑其 TextWorld 生成器并持久化 facts
——那是重构工作,与 travel-R 同级,暂缓。

## 2. RoomEnv-v3:T0 通过 → **升为 Layer-1 主实验基底(与 E0 并列)**

环境事实(源码核实):完全确定性、逐对象因子化转移(无对象间耦合)、
周期墙 = 外生时钟函数、观测局部(仅所在房间)、问题零泄漏(单个三元组挖空)、
隐状态全部为可读写的普通属性 → **干预 = 一行赋值**。工程注意:初始状态随配置固定,
轨迹多样性须靠初始位置/墙相位干预(已验证可行);缺 `rdflib`(已装);v2 提供
随机转移与对象-对象耦合(DependentObject),是 v3 之外的补充源。

T0 设计与结果(`code/roomenv_t0.py`,small-01,变量 = 对象位置 L_o + 墙位 W_w):

1. **gold 图按干预导出**(对每个观测语境反事实翻转墙位、重算强制移动——
   正是 formulation D1 的 do() 判据);自研转移复现与 env **0 失配**,gold 可信。
2. **结果**(K 条轨迹 × T 步;发现方法 vs gold):

| 设置 | 方法 | P | R | F1 | 假边 |
|---|---|---|---|---|---|
| K=40, T=100 | 池化多项逻辑回归 + LRT | 1.0 | 0.444 | 0.62 | 0 |
| K=40, T=100 | **语境条件化检验**(以 L_o(t)=r 为 regime) | 1.0 | 0.556 | 0.71 | 0 |
| K=200, T=200 | 池化 | 0.83 | 0.556 | 0.67 | **1**(时钟相位使墙间相关 → 代理边) |
| K=200, T=200 | **语境条件化** | **1.0** | **0.889** | **0.941** | 0 |

3. **与 E0 的汇合**:池化检验稀释语境特异边(墙只在对象邻接时起作用)
   ——与 E0 中 blind PCMCI+ 漏掉门控 read 边是**同一现象**;语境/regime 条件化
   在两个测试台上都是修复。剩余召回缺口是**正性(positivity)问题**
   (确定性轨道限制了语境×墙位的支撑),用更多初始/相位干预可继续收窄
   ——而干预在此环境恰好是免费的。负对照(跨对象边)在所有设置下干净。

**C1–C4 判定**:C1 ✅(观测局部、问题零泄漏、依赖只能从过程学)
C2 ✅(可无限生成带干预的重复轨迹)C3 ✅(干预式 gold,机械可得)
C4 ⏳(下一步:记忆任务对照——"X 现在在哪"上,recency/last-seen 基线 vs
学得动态 + 追踪;对象自上次目击后移动过的题目上 last-seen 必错,可量化)。

## 3. 更新后的格局

| 层 | 基底 | 状态 |
|---|---|---|
| 合成可控 | **E0**(自建 SCM) | v0 已跑,v1 修复清单在 `e0-v0-results.md` |
| 仿真真实 | **RoomEnv-v3**(+v2 补随机/耦合) | **T0 通过,主基准**;下一步 C4 记忆对照 + 放大配置(medium/large、RoomCreator 批量生成) |
| 语言真实(重构) | travel-R | C1 ✅ C4 需加硬(`travel-r-v0.md`) |
| 语言真实(as-is) | math/phys(隐式依赖) | 待符号溯源器(`benchmark-audit-c1c4.md` §3) |
| 下游收益评测 | AMA-Bench、MemoryArena、MemoryAgentBench(压缩轴) | 不测结构,测效果 |

## 4. 下一步(优先级序)

1. **RoomEnv-v3 C4 实验**:recency 基线 vs "学得图 + 追踪"在 QA reward 上的对照
   (这是第一个能同时给出结构指标与下游指标的真实环境);
2. E0 v1(共线修复、正式 CD-NOD、GRACE 首跑)与 RoomEnv 共用 regime 条件化结论;
3. medium/large 配置 + `RoomCreator` 批量生成 → 变量数 24–72,检验方法随维度的表现;
4. 会议汇报:两轮审计 + 双 T0 的完整证据链(GPT 协议执行完毕,结论:AMA no-go
   as primary / RoomEnv-v3 go)。
