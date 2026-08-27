# Form B:MemoryArena / travel 环境的 Layer-1 实例化

> 承 `meeting-minutes-2026-08-15.md` 行动项 1,与 Form A(`form-a-representation.md`,LongMemEval)对照阅读。
> 所有代码事实已核对本仓库 `benchmarks/MemoryArena`(commit `6cd9de1`,README 自述 "preview version")
> 与 `benchmarks/MemoryAgentBench`(全 track 扫描结论见 §11)。引用格式 `file:line` 均相对各 benchmark 根目录。
> 本文档回答 Yujia 8/15 清单:t 是什么、变量是什么、X_t^i 存什么、样本是什么、
> 因果发现的输入输出、图如何作用于记忆、双评价目标——并预注册先行检验 T0(§8)。

---

## 0. 一句话

以 travel 环境的**轮次(traveler round)为时间步**、**(day, slot) 单元格为变量**、
**episode 为样本**,在 270 个共享同一 7-槽 schema 的 episode 上做池化时序因果发现;
我们自己注册为一个记忆系统,把图施加为 `wrap_user_prompt` 内的读取掩码;
下游用官方 PS/SPS/SR 评,结构用从 `questions` 文本解析出的实例 DAG 评。

**为什么是 travel(而非其余三个环境):**

| 判据 | travel | shopping | search | math/phys |
|---|---|---|---|---|
| 变量 schema 跨样本共享 | ✅ 固定 7 槽(`env/env_systems/travel_env.py:11`) | ✅ 6 步固定 | ⚠️ 子查询无共享 schema | ❌ 逐论文异构 |
| ground-truth 依赖图 | ✅ 模板化 NL,可解析可数值验证 | ✅ 兼容性链 + 预算超边 | ⚠️ 扇入星形(聚合,非链) | ⚠️ 仅 `\ref` 线索,无标注 |
| 记忆是否唯一跨步通道 | ✅(见 §1.3) | ⚠️ 默认 `include_history: false` 时是 | ✅ | ✅ |
| 工程成本 | 低(1 个手动 CSV) | 高(产品库+pyserini+JDK+WebShop 服务) | 最高 | 最低 |

math/phys 保留为**记忆服务器集成的冒烟测试**(HF-only 数据、可用免 key 的 `bm25`);
shopping 为备选实例化(§11)。search 的结构是"多约束共指一个潜实体"的聚合,
与 LongMemEval 的 multi-session 同型,对我们价值最低。

---

## 1. t 是什么:回合结构

三层嵌套循环(`run_travel.py`):

- **episode**(外层,`run_travel.py:183`):一行 HF 数据 = 一个旅行团,共 **270** 个;
  每个 episode 重置环境(`:191`)并**新建** `MemoryClient`(`:194-195`,
  `user_id = f"data_{idx}_{model}_{memory}"`)——记忆随 episode 清零,episode 间独立。
- **round = 我们的时间步 t**(中层,`run_travel.py:246`):一轮 = 一位 traveler。
  每轮恰好:1 次记忆读(`:261`)→ 1 次 agent 规划(`:279`)→ 1 次 `env.step`(`:299`)→
  1 次记忆写(`:343`)。**t = `round_item['round_idx']`;t=0 为 base person**(无 agent 动作,
  只把其固定行程作为种子块写入记忆,`:226-232`)。
- **ReAct 步**(内层,`agent/travel_planner.py:191`,`max_steps=30`):轮内工具调用,
  不作为时间步;其轨迹作为 `scratchpad` 进入该轮的记忆块。

**T(每 episode 轮数)**= traveler 数,实测全量分布 `{5:37, 6:47, 7:86, 8:100}`,均值 ≈ 6.9。
行程天数 D ∈ {3,5,7},各 90 个 episode。

### 1.3 关键性质:记忆是唯一跨轮通道

有记忆系统时,runner 显式关闭其余全部跨轮信息流:
`include_previous_plans = (memory_system is None)`(`run_travel.py:274`),
`set_base_person` 也仅在无记忆分支调用(`:240-241`)。
所以**任何跨轮依赖若被满足,必然经过了记忆系统**——对记忆的干预就是对整条通道的干预。
这是四个环境里最干净的因果瓶颈,也是本实例化最重要的结构性事实。

---

## 2. 变量 i 是什么:两层定义

### 2.1 实例级(每个 episode 一张图,作 ground truth 用)

节点 = `(person t, day d, slot s)` 单元格。槽位 schema **全 corpus 固定 7 个**
(`travel_env.py:11`):`current_city, transportation, breakfast, attraction, lunch, dinner, accommodation`。
边 = `questions[t]` 文本中的显式约束,措辞模板化、被引用者**按名字点名**,类型可枚举:

| 边类型 | 例(HF row id=1) |
|---|---|
| equals / join | "For accommodation on the first day, I'd like to join **Eric**." |
| 数值比例 | "costs at least 20% more than **Emma's first-day stay**, is rated higher" |
| 数值区间 | "priced within $150 of **Eric's** but rated lower" |
| 属性同/异 | "same room type as **Emma's second-day accommodation**" / "different room type" |
| 规则同 | "shares the same no-parties rule" |

依赖会**成链**(row 1:Bart ← Emma ← Eric)且跨日、跨槽(dinner ← lunch 价格)。
每条边可用 `answers[t].daily_plans[d][s]` 与 CSV 数据库数值验证。
仓库自带的近似标注:`find_constraint_slots`(`env/env_systems/travel_planner_env/eval.py:66-83`)
给出每位 traveler"被约束改写的 (day, slot) 集合",即约束激活掩码 `A_t^i`,SPS 指标就用它。

### 2.2 类型级(跨 episode 共享,是因果发现的目标)

TCD 学的不是某个 episode 的实例图(那是解析出来的),而是**类型级图 G**:
哪些槽位类型在哪些轮距(lag)上系统性地依赖哪些槽位类型。三档粒度
(对应 Yujia 的"粒度是设计选择"):

| 档 | 变量集 | d | 备注 |
|---|---|---|---|
| v0 | 7 个槽位类型(跨天聚合) | 7 | 最粗,先探信号 |
| **v1(推荐)** | (day, slot) 单元格,按 D 分层 | 21 / 35 / 49 | 与 gold 粒度对齐;每层 90 个 episode |
| v2 | 单元格 × 值向量(embedding) | 同上,向量值 | Yujia 明确许可"整向量为一个变量" |

---

## 3. X_t^i 存什么

沿用 Form A §2 的取值阶梯,travel 的对应物:

| 选项 | 定义 | 来源 |
|---|---|---|
| (i) 指示变量 | `1[单元格 i 在第 t 轮被约束改写]`(= `A_t^i`),或 `1[答对]` | `find_constraint_slots` / `_similarity ≥ 0.7`(`travel_env.py:189`) |
| (ii) 数值编码 | 该单元格取值的价格 / 评分(CSV 可查) | `database/{restaurants,accommodations,…}` |
| (iii) 向量 | agent 输出字符串的 embedding | 解析器:`travel_env.py:39-57` 或 `combination.py:9-29` |

**状态持续规则**(Form A §1.1 的对应):travel 里每轮每位 traveler 各有整份行程,
单元格不跨轮"持续"——持续的载体是**记忆库** `M_t` 本身(第 t' 轮的块永久可检索)。
即 hold 段从"变量不变"移到"记忆条目不灭",这一点要写进 v0.2 的正文,
因为它意味着 provenance 天然存在:块按轮写入,块 ↔ 轮的映射就是 `P`。

---

## 4. 样本是什么(回答"每个变量需要多个样本")

- **一个样本 = 一个 episode**:同一 d 维变量集上长度 T∈[5,8] 的一条多元序列。
- **样本量**:270 个 episode(按 D 分层各 90),≈1,864 轮观测。
  每条 (slot-type pair, lag ℓ) 边约有 `90 × (T−ℓ) ≈ 500+` 个跨 episode 转移样本(v1 粒度)。
- **T≈7 太短,逐 episode 拟合(Form A 时代的方案 A)在这里不可行**;
  但 schema 跨样本严格共享,**多试次池化(multi-trial pooling)是合法且必须的**——
  这正是 LongMemEval 里做不到的事(记忆单元因样本而异),也是选 travel 的核心理由。
- ⚠️ 池化 ≠ 拼接。`form-a-representation.md` §3.3 "不要把互不相关的序列首尾相接"仍然成立;
  正确做法是把 episode 作为 i.i.d. 试次,损失按试次求和。**GRACE 的 `run_cdnots_gated(df, …)`
  接口目前吃单条序列,需要小改:按 episode 分 batch、NLL 跨 episode 求和,不引入跨界 lag 项。**
  这是 v1 的第一个真实代码工作项,量级为改 dataloader/loss,不动 gating 与 L0。

---

## 5. 因果发现的输入 / 输出

```
输入:X ∈ R^{N × T × d}   N=90(每 D 层), T∈[5,8], d∈{21,35,49}(v1)
输出:lag-wise 邻接 A^(1..L), L ≤ T−1(轮距;瞬时边 v1 先不开)
方法:GRACE(causal-ts,多试次改造后) ;baseline CDNOTS+(同库同 API)
```

评图的 ground truth:把 270 个实例 DAG(§2.1 解析所得)投影到类型级——
边 `(s', d', ℓ) → (s, d)` 的真值 = 该型边在语料中出现且数值验证通过。
类型级图预期**稀疏且可解释**(accommodation←accommodation 同槽 join 为主,
餐饮槽间价格比较次之),这本身就是一个可写进论文的描述统计。

---

## 6. 图如何作用于记忆:接口与掩码链

### 6.1 接口(已核实,两个方法,鸭子类型)

```python
class CausalMemorySystem:                       # 注册进 MEMORY_FACTORIES(memory/server.py:49-62)
    def __init__(self): ...                     # 零参构造(server.py:101);要 episode id 需仿
                                                # reasoningbank 在 server.py:96 加分支
    def add_chunk(self, chunk: str):            # 返回值须 JSON 可序列化(server.py:109-111)
        ...                                     # travel 块:JSON{name, query, scratchpad, final_plan, judgement}
    def wrap_user_prompt(self, prompt: str) -> str:
        ...                                     # 必须返回 "<memory_context>…</memory_context>\nUser: {prompt}"
```

- **`</memory_context>` 哨兵是承重的**:`run_travel.py:262`、`agent/travel_planner.py:241`、
  `agent/search.py:60` 都按它切分;缺失则整个 wrapped prompt 被当作记忆上下文,静默出错。
- 实例按 `user_id` 常驻服务器进程(`MEMORY_SYSTEMS`,`server.py:74,102`),
  可自由持有可枚举的 `M`、时间戳、图等状态;重复 initialize 同 id 即清零(client 构造时就会,`client.py:21-24`)。
- 空记忆时上下文位置写字面量 `"None"`(与 `long_context.py:32-40` 等全部现有实现一致)。

### 6.2 掩码链(Form A §1 的对应)

```
add_chunk(块_t)        → 解析 name/round → M ← M ∪ {(t, 块_t)}          (provenance 即轮号)
wrap_user_prompt(q_t)  → 解析 q_t 的目标单元格 Y_t(点名的 person/day/slot)
                       → 用类型级 G(+实例解析)取祖先单元格 An*(Y_t)
                       → 经 provenance 映射到来源轮 S_t
                       → 槽位级抽取:只回填 S_t 中相关单元格的值,而非整块 scratchpad
                       → 组装 <memory_context>…</memory_context>
```

对照组(同一评测下正面比):`bm25`(top_k=3,`rag.py:103-114`)、`long_context`(全量)、
名字匹配检索(typed)、以及其余 12 个注册系统中跑得通的若干。

---

## 7. 评价:双目标 + 压缩

| 目标 | 指标 | 出处 | 备注 |
|---|---|---|---|
| 下游(主) | PS / SPS / SR | `eval.py:96-179` | ⚠️ 评 6 槽(无 current_city,`eval.py:56`);轮内 reward 评 7 槽(`travel_env.py:11`)——正文必须声明用哪套 |
| 结构可信性 | 类型级图边 P/R;实例级 An* 检索命中 | 对 §2.1 解析 DAG | LongMemEval 上不可测,这里可测 |
| 压缩(承 LongMemEval 结论) | wrapped prompt token 数 vs 下游成绩的 Pareto | 自行打点 | 槽位级抽取 vs 整块检索是压缩杠杆 |

---

## 8. 预注册先行检验 T0:G 挣不挣得到位置(无 LLM、零集成)

**动机:诚实面对 LongMemEval 的教训。** travel 的 query 会**按名字点名直接父辈**
("join Eric"),且父辈的最终行程已物化在记忆块里——所以直接父辈可能语义可检索,
An* 可能塌缩到"query 里点名的对象",重演 `E(q) ≈ An_G(Y_q)`。
预注册预期:**直接父辈基本都被点名;G 的空间(若有)在链式深度、槽位级精度与压缩,不在召回。**

**做法**:纯文本解析 270 个 episode 的 `questions` + `answers`,不调 LLM、不接环境:

1. **点名率**:实例 DAG 的每条边,其源 person(及 day/slot)是否出现在 query 字面。
2. **链深分布**:深度 ≥2 的祖先链(Bart←Emma←Eric 型)占多少 episode / 多少边;
   深链祖先(Eric 之于 Bart)是否已被中间块物化到无需再取。
3. **前沿塌缩检验**:给定"块含最终行程"的物化假设,是否存在任何 query,
   其正确规划需要**未点名**轮的信息(= An* 严格大于点名集的证据)。
4. **精度/歧义面**:名字在 scratchpad 里的复现频率(检索噪声源);
   BM25-on-names 在 T=8、块含 30 步 scratchpad 时的模拟命中与误检率。
5. **压缩帐**:所需单元格 token 数 / 整块检索 token 数——槽位级抽取的理论收益。

**判据(先写死再跑)**:
- 若 (3) 非空或 (4) 显示名字检索有系统性精度缺口且槽位级掩码能补 → G 有位置,进 v1 集成;
- 若 (3) 空且 (4) 干净 → 召回轴重演 LongMemEval;叙事转向 (5) 的**槽位级压缩**
  与结构可信性(类型级图作为可辨识的记忆组织),或走 Form A §7 的 gated-selection 退路。

T0 通过与否,都在下次会前出一页结果——这正是 Yujia 要的"持续挑战表述"。

> **已执行(2026-08-20)**:结果见 `t0-results.md`,脚本 `code/t0_travel.py`。
> **裁决(同日修订):no-go——判据第二分支触发。** 依赖 100% 在当前 query 点名、
> 来源单元格显式(槽位 100%、日期 95.6%),query-aware 解析器即 oracle;
> 实例 DAG 是当前输入的确定函数,时序因果发现"在此按构造无必要"。
> 初版"部分通过"误把 BM25 的弱当成了判据缺口,已在 t0-results.md §3.0 作废。
> travel 原样降级为集成 harness / structured-memory 压缩测试台 / 重构原料;
> 主基准路径改为:E0 合成 → travel-R 重构 → 按新适格标准 C1–C4 重审(t0-results.md §5)。
> **本节其余文字保留为预注册记录,不再更新。**

---

## 9. 我们设定的开关位(与出厂默认的偏离,必须在论文/文档声明)

| 开关 | 出厂默认 | 我们的设定 | 依据 |
|---|---|---|---|
| `judgement_mode` | **全部 14 份 travel 配置为 `"none"`** | v1 仍用 `none`;`hint` 作为独立消融(反馈闭环) | `run_travel.py:111,126`;hint 模板 `travel_env.py:76-92` |
| hint 阈值 | 0.9(比 reward 的 0.7 严) | 沿用,但正文声明两阈值不等 | `travel_env.py:13,15` |
| `use_step_memory` | 关 | v1 关(每轮一读一写,序列干净) | `run_travel.py:261`, `travel_planner.py:239-246` |
| 记忆后端 | — | 我们的 `CausalMemorySystem` + §6.2 对照组 | `memory/server.py:49` |
| 底座 LLM | 配置各异 | 固定一个,全对照组同款 | — |

⚠️ 你的 8/12 笔记(`form-a-representation.md` §6.9)称 travel "hint 模式逐步纠错闭环"——
**代码属实、默认关闭**;同型情况:math 的判决默认不进记忆(`judge_result_in_memory: false`,
全部配置),search 的 `store_eval_in_memory` 是死参数(`browsecomp_plus_env.py:52,245,270`)。
"反馈闭环"是我们可打开的开关,不是基准默认——改 DGP 的开关位必须逐一声明。

---

## 10. 环境怪癖清单(已核实,建仓 issue 或本地补丁)

1. 槽位 schema 双轨:reward/hint 7 槽 vs PS/SPS/SR 6 槽(见 §7)。
2. 端口:`env_server.py:232` 绑 **8001**,travel/shopping 配置与 setup 文档写 **8005**——跑前对齐。
3. `math_task.json:37` 的 `env_name: formal_reasoning_math` 不在注册表,会 400;用 `math`/`phys` 配置。
4. math 判卷 prompt 恒为 `Question: None`(`math_env.py:159` 少传一参);auto-eval 被注释
   (`run_math.py:285`),按 `setup_formal_reasoning.md:104-109` 事后跑。
5. `mem0` 破坏 wrap 约定(`User Prompt:` 而非 `User:`,`mem0.py:48`)——对照组慎用或修。
6. `memory/test_memory.py:8` import 路径过期(`MemActBench.client` → 实为 `memory/client.py`)。
7. travel 依赖 `datasets` 的 import 失败会被静默吞掉,环境从 `/env/available` 消失
   (`env_systems/__init__.py:14-16`)。
8. 数据:travel 需手动下载 `clean_Flights_2022.csv`(`setup_travel.md:20-28`);其余 CSV 已随仓库。

---

## 11. 备选与旁证

- **shopping(备选实例化)**:150 任务 × 恒定 6 步;依赖 = 逐步兼容性约束
  ("pairs well with / avoids",固定文法)+ 全局预算超边;属性级 gold(`requirements.attributes`)。
  结构好,工程重(产品库 + pyserini/JDK + WebShop 服务)。travel 若 T0 失败,这里是第二战场。
- **MemoryAgentBench(全 track 扫描定论)**:四个 track 共用同一"先灌注后只读问答"管线,
  无任何 track 级控制流差异;Conflict_Resolution 的"新旧"是文本内序号整数(注入顺序无关),
  Test_Time_Learning 是冻结语料 ICL,均非 write–hold–read。README 自述 "inject once, query
  multiple times"。→ 8/12 的降级结论从"LongMemEval 如此"升级为"**全基准如此,且是设计选择**";
  它保留为压缩诊断与集成 harness,不再考察其余 track。

---

## 12. 开放问题(供走读时挑战)

1. 类型级图的节点要不要带 day 维(v1 的 (day,slot) vs 只按 slot)?day 维使 d 随 D 变,
   分层后每层仅 90 样本——够不够?
2. 轮距 lag 的语义:travelers 的顺序是数据给定的,但"第 3 轮依赖第 1 轮"是否真是时间结构,
   还是仅仅"被点名的对象恰好在前"?(T0 的 (1)(2) 会给出经验答案;若点名完全决定依赖,
   lag 结构退化为拓扑序的副产品——这要在表述里正面讨论。)
3. X_t^i 取 (i) 指示变量时,信号是否被约束激活稀疏性(每 traveler 仅少数单元格被约束)压死?
4. `hint` 消融开启后 DGP 改变(反馈进块的 `judgement` 字段)——作为第二 regime(u_t)
   纳入 A2 门控框架,还是单独一组实验?
5. 发表 venue(转写不可靠,口头确认)。
