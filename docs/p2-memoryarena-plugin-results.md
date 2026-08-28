# P2 结果:把方法做成插件接进 MemoryArena(2026-08-27,真实系统)

> 对应 Yujia 任务乙:**找成熟平台,把我们的方法做成独立插件接进去,证明能提升现有记忆系统**。
> 脚本:`code/arena_causal_memory.py`(插件)、`code/arena_serve_causal.py`(运行时注册启动器)、
> `code/arena_p2_benchmark.py`(评测)、`code/p2_case_study.py`(单例可视化)。
> 数据:MemoryArena `group_travel_planner` 真实 HF 数据,60 episode / 401 轮。CPU-only。

---

## 0. "接进去"是字面意义上的接进去

- 插件实现 MemoryArena 的两方法鸭子接口(`add_chunk` / `wrap_user_prompt`),
  经其**真实 HTTP 服务**(`/memory/initialize`、`/memory/add`、`/memory/wrap_user_prompt`)调用;
- **不 fork、不 vendor、不改上游一行**:`arena_serve_causal.py` 导入其 FastAPI app,
  运行时把工厂塞进 `MEMORY_FACTORIES` 再 serve。
  验证:`git -C benchmarks/MemoryArena status --porcelain` **输出为空**。
  这不是洁癖——MemoryArena **没有 LICENSE 文件**(default copyright),分发改动版有法律风险。
- 注册后工厂数 12 → **14**(我们的 `causal` + 消融 `causal-noG`),
  顺带**实证确认**了"12 个内置记忆系统"这一修正(此前文档写 13,是文件数不是注册数)。
- 其余需要外部 SDK 的记忆系统(mirix/mem0/letta/zep/memorag…)在本机未装,
  启动器按**报错逐个 stub**,请求到被 stub 的后端会**显式抛错**而非静默假装工作。

## 1. 评的是什么(以及为什么不是端到端成功率)

**指标 = answerability at cost(可答性/代价)**:

- **cell recall**:该轮 query 依赖的**金标单元格值**,是否真的出现在记忆上下文里。
  金标来自 query 文本解析出的来源单元格(`join Eric` / `within $150 of Eric's`),
  再用该 episode 的 gold `daily_plans` 解析成**字面值**——所以命中意味着
  "agent 需要的那个字符串确实在上下文里",不是"人名对了"。
- **round solvable**:该轮**所有**依赖都在上下文里(能否独立完成该轮)。
- **context tokens / compression**:上下文 token 数,及其占全历史的比例。

**为什么不直接报 PS/SPS/SR**:travel 每轮跑最多 30 步 ReAct;4 个系统 × 可负担的
episode 数下,端到端指标的波动大于系统间差异。而可答性是那些指标的**上游机制**,
**不需要 LLM 在环**(完全可复现),且**逐例可读**。端到端小 N 版本另做,不作为主张。

## 2. 主结果(60 episode / 401 轮)

| 记忆系统 | cell recall | rounds answerable | context tokens | vs 全历史 |
|---|---|---|---|---|
| `causal-noG`(消融:关掉图) | 1.000 | 1.000 | 2487 | 0.82× |
| `long_context`(信息上界) | 0.999 | 0.994 | 3077 | 1.02× |
| **`causal`(我方)** | **0.989** | **0.952** | **1045** | **0.35×** |
| `bm25`(最强非因果检索基线) | 0.920 | 0.719 | 1951 | 0.65× |

**读数 1 —— 对检索基线是双轴支配,不是权衡。**
对 `bm25`:可答轮 **0.952 vs 0.719**(+23.3 点),同时 token **1045 vs 1951**(省 1.9×)。
**又更准又更省**,这正是任务乙要的"提升现有记忆系统"。
原因是机制性的:BM25 命中的是**整块**(含 30 步 scratchpad),
命不中就整轮缺信息;我们抽的是**槽位级祖先**,既不带垃圾也不漏点名对象。

**读数 2 —— 对信息上界是近无损压缩。**
对 `long_context`:cell recall 0.989 vs 0.999(**−1.0 点**),token 省 **2.9×**。

**读数 3 —— 消融把功劳分清楚了(这条最重要)。**
`causal-noG` = 同样的槽位解析 + hold 规则,**只关掉图选择**:
recall 满分 1.000,但 token **2487**(几乎没压缩)。
所以:**"结构化"负责不丢信息,"因果图"负责压缩**——
开图使 2487 → 1045(**2.4×**),代价仅 1.1 点 recall。**两者缺一不可**,
不能把收益笼统归给"我们用了结构化记忆"。

## 3. 逐例可读(`code/p2_case_study.py`)

episode 1 / round 4,query 点名 Jennifer、Bart、Eric,依赖 4 个金标单元格。
全历史 1640 token。四个系统给 agent 的上下文:

| 系统 | token | 金标命中 |
|---|---|---|
| long_context | 1700 | 4/4(整包 4 个 chunk 原文) |
| bm25 | 1189 | 4/4(整块检索,含无关 scratchpad) |
| causal-noG | 1388 | 4/4(所有槽位) |
| **causal** | **~600** | **4/4**(只有被点名者的相关日/槽) |

我方上下文长这样(可直接读):
```
=== Eric's Plan ===
Day 2:
Accommodation: Pure luxury one bdrm + sofa bed on Central Park, Rockford  (round 1)
Dinner: New Bhappe Di Hatti, Rockford  (round 1)
Lunch: Flying Mango, Rockford  (round 1)
```
`(round N)` 是 provenance——**同一张图既用于选择、也用于审计**(P3 用的就是它)。

## 4. 一个被抓住的测量假象(记录以免复现)

首轮结果里 `causal`(0.989)**高于** `long_context`(0.980)——**不可能**,
因为后者是信息上界。排查发现:`code/t0_travel.py:build_chunks` 用 `json.dumps` 
**默认 `ensure_ascii=True`**,把非 ASCII 店名(`和缘浪漫民宿, Billings(Montana)`)
写成 `\uXXXX`;逐字保存 chunk 的系统在字面子串检验下"丢失"该值,
而解析 JSON 后重渲染的系统则命中。**这是编码假象,不是记忆质量差异。**
`run_travel.py:226-232` 本身用的就是 `ensure_ascii=False`,故修正后既更忠实也更正确
(修正后 `long_context` 回到 0.999)。**教训:任何"我们超过了上界"的读数都先当 bug 查。**

## 5. 诚实边界

1. travel 的依赖**在 query 里被点名**(T0 已定论),故我方胜点是
   **槽位级祖先抽取带来的压缩/精度**,**不是"必须先做因果发现"**。
   发现必要性的主张只由仿真线(E0)承担,不能挂在这个环境上。
2. 未给端到端 PS/SPS/SR(理由见 §1),故不宣称"任务成功率提升"。
3. 对照只含 `long_context` / `bm25`(按 Yujia"只留 1–2 个 baseline");
   其余 10 个内置系统需外部 SDK/服务,本轮未跑。
4. `causal` 的规则图利用 query 中的点名,属该环境的 oracle 近似;
   接 GRACE 学得图(M4)后需重测。
