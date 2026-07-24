# 会议纪要 — Formulation Note 走读会（2026 年 7 月,与 Yujia）

> 记录人:Mian (Nothern) Wu。引号内为 Yujia 原话(转写清理版)。
> 本纪要按"verdict → 新输入 → 方向调整 → 行动项"组织,供 changelog 与 v0.2 使用。

---

## 一、总体 verdict

> "It's great… at least we are on the same page now, so you now see the formulation."
> "Great job. I think we are on the same page and I think it's a really good start… this project will be very impactful… we can already have two independent projects that are very different from the existing paradigm."

- **表述对齐达成**:R2(写下理解供核对)在实质上通过。
- 项目前景:他认为可拆出**两个相互独立的工作**(理解为 Layer-1 论文与 Layer-2 论文,待确认)。

## 二、逐条 verdict(对照笔记条目)

| 笔记条目 | 他的意见 | 结论 |
|---|---|---|
| A2 门控平稳性 / 区制过程 u_t | 把 u_t 读作 **auxiliary variable**,可以就是可观测动作(write/hold/read);"每个标签对应一张边集不同的图……that makes sense" | **接受**(用他的词汇:auxiliary variable) |
| regime-free 的含义 | "没有任何标签,要从数据推断标签" | 理解一致;Q1 实质上倾向保留门控/标签式表述 |
| Layer 1 / Layer 2 划分 | 完整复述:L1 = 全观测的时序因果发现;L2 = 潜变量模型,先反演生成过程恢复潜变量,再看结构;"I got that part" | **接受** |
| 记忆的本质 | **"Memory should be something latent, right? If everything is observed, then it's not a memory, it's just a direct observation."** | 强化了整体 framing:L2 才是"记忆"的本命场景 |
| O2a "agent's internal state" | **纠正**:KV cache、开源模型的激活层"not really hidden… from our perspective they are not internal. So they correspond to layer 1" | **v0.2 必改**:区分"可访问的内部(→观测,L1)"与"真正隐藏的内部(→潜变量,L2)" |
| Layer 2 的实例化 | "x = agent 在不同轮次的回复;z = 隐空间里的 latent thoughts——它对过去交互的记忆、对未来的规划" | 写进 v0.2 的 observation models |
| 老 Q5(L1 能否独立成文) | "That contribution can be a paper by itself." | **回答了:能** |
| F_t / leverage(他主动提出) | "不要依赖全部历史,只依赖与未来时刻相关的那些时间步……更进一步,不只依赖时间步,而是依赖那些时间步里的**具体变量**——变量可以是观测的、潜的、或混合的" | 与 D2/引理逐字对应;他的"variable-level"粒度 = F_t 本来就是**节点级**对象 |
| 文档本身 | "We need to **reorganize the documentation… start from scratch**. Only put those things that you understand thoroughly and that are also equivalent to our formulation… we start from something very slow. We don't need the whole formulation in one or two weeks. That part is much more important than others." | **v0.2 = 从零重写**,只放彻底理解且等价于共同表述的内容;节奏可以慢 |

## 三、新技术输入

1. **VARLiNGAM**(VAR + LiNGAM;Hyvärinen–Zhang–Shimizu–Hoyer, JMLR 2010):利用非高斯性同时估计瞬时与滞后效应的经典**时序因果发现**方法。他点名作为 Layer-1(全观测)设定的切入方法。检索关键词:**causal discovery for time series**。
2. **三级粒度层级**(他给的路线图语言):
   - 级 1:时间步之间的依赖——"agent-memory 文献从因果视角完全忽略的一层";
   - 级 2:依赖时间步内的**具体变量**(观测或潜);
   - 级 3(最一般):观测与潜变量的**混合**。
3. **Layer-1 论文定位**:"agent memory with observed state"——把现有以 KV cache / 激活层为"记忆"的工作**统一**进全观测时序因果框架,注入时序因果发现,看能否**提升它们的性能**;做出效果即可独立成文;进展顺利再进 Layer 2(发现潜过程)。

## 四、方向调整(相对此前计划)

- **Layer 1 先行且具体化**:载体是 KV cache / 开源模型激活(= 可观测变量),方法入口 VARLiNGAM 及时序 CD 家族;E0 类合成实验的意义上升。
- **阅读顺序调整**:时序因果发现(VARLiNGAM、causal discovery for time series 综述)前移;IDOL/CRL 线后移至 Layer-2 阶段。
- **评价口径微调**:对 Layer-1 论文,"在现有 KV-cache 记忆方法上注入因果结构并**改进性能**"成为核心论证之一(与此前"正确性为主、性能为副产物"的总框架并行不悖,但 L1 篇需要性能证据)。
- **文档策略**:不是在 2 页笔记上"加回" Layer-2 内容,而是**从零重组**——以双方已对齐的表述为骨架,只写彻底理解的部分。

## 五、行动项

1. **[文档] v0.2 从零重写**(他的原话要求)。建议骨架:
   - §1 共同表述(用他的词汇:auxiliary variable;memory-is-latent 一句放进动机)
   - §2 Layer 1 = observed temporal causal discovery:变量 = KV cache/激活维度;图;frontier F_t 及引理(含证明,时机成熟时);与 VARLiNGAM 的接口
   - §3 Layer 2 = temporal CRL:x = 回复,z = latent thoughts 实例;value correspondence 目标(简)
   - §4 Layer-1 实验设计草案(注入时序 CD、对照现有 KV-cache 记忆方法)
   - §5 问题清单(更新版)
2. **[阅读] VARLiNGAM 论文 + causal discovery for time series 综述**,输出一页笔记:假设、可扩展性、与门控/区制结构的兼容性。
3. **[调研] KV-cache / 激活层做记忆的代表工作清单**(待统一的对象),各一句话:它们把什么当变量、有无跨时间步结构。
4. **[修订] O2a 措辞**:internal → 区分 accessible(观测)与 hidden(潜);把他的 x/z 实例写入。
5. **[流程] 本纪要计入 changelog;下次会议 agenda 以 v0.2 骨架 + VARLiNGAM 笔记为主项。**

## 六、待确认(下次会议或邮件)

- "two independent projects" 的确切所指(L1 篇 + L2 篇?);
- Layer-1 论文的评价基准(哪些现有 agent-memory 方法作为对照);
- 合成 sanity 实验是否可以现在开跑(原 Q5/Q6——会上未明确答复,但"start from the simple case"的语气支持尽快做 observed-case 的小实验)。
