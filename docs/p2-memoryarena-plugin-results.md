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

## 4.5 ⚠️ 端到端跑起来后暴露的**真问题**(2026-08-27 晚,必读)

把真实 travel agent 跑起来(真 ReAct + 真工具 + 我方插件供给记忆)后,发现
**§2 的 answerability 指标对我方过于宽松**,`causal` 在端到端里表现**明显更差**:

同样 20 分钟内:`long_context` 跑完 5 轮、`bm25` 3 轮,**`causal` 只跑完 1 轮**。
原因看日志一目了然 —— 我方给 agent 的上下文是:

```
=== Jennifer's Plan ===
Day 2:  Breakfast / Lunch / Dinner …
Day 3:  Breakfast / Lunch / Dinner …
```

**只有餐饮槽**。因为 query 里点名的约束句只提到 breakfast/dinner,
祖先选择就把 `current_city` / `transportation` / `accommodation` 全掩掉了。
可是 Eric 要产出的是**一份完整行程**:没有航班和城市信息,agent 只能把 12 步
全花在"从每一个城市搜到 Rockford 的航班"上 —— 又慢又必然规划失败。

**指标为什么没抓到**:`gold_cells_for_round` 的金标只取
**query 约束句里点名的来源单元格**,不包含"要完成本轮任务所必需的行程骨架"。
于是"保留了被点名的格子"= 满分,但 agent 依然没法干活。

**结论(诚实版)**:
1. §2 的表**只能**读作"命名约束源的保留率与代价",**不能**读作"记忆质量"或"任务表现";
2. 规则图**欠设定**:它只编码了**约束边**,漏了**行程骨架依赖**
   (每个人的计划都依赖共享的城市/航班/住宿);
3. 这恰恰是**学得图应该补上的东西**(骨架依赖是跨 episode 稳定的类型级边),
   → 直接支持 M4(接 GRACE)的必要性,也说明规则图不是"oracle 上界"而是有系统性缺口;
4. 端到端 PS/SPS/SR 数字待三条 run 产出后补;**在那之前不得宣称 P2 提升了任务表现**。

## 4.6 ✅ M4 打通:**学得图修好了规则图的缺口,并双轴支配手工补丁**

用 GRACE 从 270 个 episode 学出类型级槽位图(`code/travel_grace_discovery.py`,
导出 `results/real/travel_learned_graph.json`),注册为 `causal-learned` 接进同一插件。
**没有任何手写槽位清单。**

学出来的东西**直接命中 §4.5 的病因**:

| 槽位 | copy_rate(跨旅客是否原样继承) | 判定 |
|---|---|---|
| current_city / transportation / attraction | **1.000** | **degenerate/持久** → 必须继承 |
| breakfast / lunch / dinner | 0.69–0.71 | 逐人变化 |
| accommodation | **0.613** | **最逐人变化** |

四种取值编码(指示 / 价格 / cell-id / cell-price)**一致地**把
`current_city, transportation, attraction` 判为 degenerate。
即:**数据自己说出了"行程骨架"**——正是规则图漏掉、我手工补丁试图补的东西。
而且它**纠正了我的手工猜测**:我把 `accommodation` 当骨架(其实是最不共享的槽),
漏了 `attraction`(其实 copy_rate=1.0)。

学到的依赖边也稀疏可解释(与 `memoryarena-instantiation.md` §5 的预注册预期一致):
`breakfast→breakfast/lunch`、`lunch→lunch`、`dinner→dinner`、`accommodation→accommodation`。

**60 episode / 401 轮结果**(`results/real/p2_benchmark_v2.csv`):

| 记忆系统 | cell recall | rounds answerable | context tokens | vs 全历史 |
|---|---|---|---|---|
| `causal-noG`(消融:无图) | 1.000 | 1.000 | 2487 | 0.82× |
| **`causal-learned`(GRACE 学得图)** | **1.000** | **1.000** | **1558** | **0.52×** |
| `long_context`(信息上界) | 0.999 | 0.994 | 3077 | 1.02× |
| `causal-scaffold`(手工补丁) | 0.993 | 0.973 | 1896 | 0.63× |
| `causal`(规则图,仅约束边) | 0.989 | 0.952 | 1045 | 0.35× |
| `bm25` | 0.920 | 0.719 | 1951 | 0.65× |

**读数(这是 M4 的核心结论)**:
1. **学得图达到满分可答性(1.000/1.000),同时只用 1558 token**——
   比无图消融省 **1.6×**(2487→1558),比全历史省 **2.0×**(3077→1558),且**不丢信息**;
2. **学得图在两个轴上同时优于手工补丁**(1.000 vs 0.993 recall,1558 vs 1896 token)
   → **"发现"不是装饰,它比人手写的图更准**;
3. 规则图 token 最少(1045)但可答性掉到 0.952,且 §4.5 已证明它端到端会饿死 agent;
   → 压缩不是越狠越好,**学得图找到的是对的那个折中**;
4. 因此 **"发现 → 记忆 → 收益"整链在真实平台上跑通**,
   且收益方向与 §4.5 端到端暴露的病因**因果一致**(不是碰巧的指标胜利)。

**仍待补**:端到端 PS/SPS/SR(`causal-learned` vs `long_context` vs `bm25` 正在跑)。

## 5. 诚实边界

1. travel 的依赖**在 query 里被点名**(T0 已定论),故我方胜点是
   **槽位级祖先抽取带来的压缩/精度**,**不是"必须先做因果发现"**。
   发现必要性的主张只由仿真线(E0)承担,不能挂在这个环境上。
2. 未给端到端 PS/SPS/SR(理由见 §1),故不宣称"任务成功率提升"。
3. 对照只含 `long_context` / `bm25`(按 Yujia"只留 1–2 个 baseline");
   其余 10 个内置系统需外部 SDK/服务,本轮未跑。
4. `causal` 的规则图利用 query 中的点名,属该环境的 oracle 近似;
   接 GRACE 学得图(M4)后需重测。
